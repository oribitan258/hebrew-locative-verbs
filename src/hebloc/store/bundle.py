"""Verified backup/sharing bundles of parse runs (decision D-012, ``docs/data_management.md``).

A bundle is one zip (``ZIP_STORED``: Parquet is already zstd-compressed) holding every file of
one run directory, at its path relative to ``data/`` (``annotations/<collection>/runs/<run_id>/…``),
plus ``BUNDLE_MANIFEST.json``:

- sha256 and size of every file;
- the corpora anchor (``manifest_sha256``, file count, bytes) the run was based on;
- code commit, model repo + pinned revision, runtime fixes, norm/segment/piece/tokens versions;
- row counts per table; the run's validation result and fingerprint.

``create`` refuses an incomplete, stale or failing run. ``verify`` re-hashes every member and
checks the anchor against the git-tracked ``config/corpora_anchor.json``. ``restore`` verifies
first, refuses to overwrite different existing files, writes atomically, then re-validates the
restored run (read-only).
"""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from hebloc.paths import ANCHOR_PATH, ANNOTATIONS_DIR, DATA_DIR, assert_not_in_corpora
from hebloc.store.io import atomic_write_text, file_sha256, parquet_rows, read_json
from hebloc.store.runs import ALL_PARTS, Run, resolve

BUNDLE_DIR = DATA_DIR / "bundles"
MANIFEST_NAME = "BUNDLE_MANIFEST.json"
BUNDLE_VERSION = "1"


def bundle_name(run: Run) -> str:
    return f"hebloc-annotations-{run.collection}-{run.run_id}.zip"


def _run_files(run: Run) -> list[Path]:
    return sorted(p for p in run.path.rglob("*") if p.is_file() and not p.name.startswith("."))


def _preflight(run: Run) -> list[str]:
    from hebloc.parse.checks import run_fingerprint
    from hebloc.parse.tokens import shard_up_to_date

    probs = []
    st = run.status()
    if not st["complete"]:
        probs.append("run is incomplete")
    if st["uncommitted_shards"]:
        probs.append(f"uncommitted shard files: {st['uncommitted_shards'][:5]}")
    if any(not shard_up_to_date(run.path, s) for s in run.shards()):
        probs.append(f"tokens are stale (run: hebloc tokens {run.ref})")
    cj = run.path / "checks.json"
    checks = read_json(cj) if cj.exists() else {}
    if not checks.get("ok"):
        probs.append("checks.json missing or not ok (validate the run first)")
    elif checks.get("fingerprint") != run_fingerprint(run.path):
        probs.append("checks.json is out of date for this run (re-validate)")
    return probs


def create(ref: str | Path | Run, out_dir: Path = BUNDLE_DIR, *, data_dir: Path = DATA_DIR,
           anchor_path: Path = ANCHOR_PATH) -> dict:
    from hebloc.inventory import _git_commit
    from hebloc.parse.tokens import TOKENS_VERSION

    run = resolve(ref, data_dir / "annotations") if not isinstance(ref, Run) else ref
    probs = _preflight(run)
    if probs:
        raise RuntimeError(f"refusing to bundle {run.ref}: " + "; ".join(probs))
    files = _run_files(run)
    rel = {f: PurePosixPath(f.relative_to(data_dir).as_posix()) for f in files}
    anchor = read_json(anchor_path)
    m, checks = run.manifest, read_json(run.path / "checks.json")
    manifest = {
        "bundle_version": BUNDLE_VERSION, "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run": run.ref, "root": PurePosixPath(run.path.relative_to(data_dir).as_posix()).as_posix(),
        "corpora_anchor": {k: anchor[k] for k in ("manifest_sha256", "file_count", "total_bytes")},
        "code_commit_bundle": _git_commit(), "code_commit_run": m.get("code_commit"),
        "model": {k: m.get(k) for k in ("model", "repo", "revision")}, "fixes": m.get("fixes"),
        "versions": {"norm": m.get("norm_version"), "segment": m.get("segment_version"),
                     "piece": m.get("piece_version"), "runner": m.get("runner_version"), "tokens": TOKENS_VERSION},
        "rows": {part: sum(parquet_rows(f) for f in run.part_files(part)) for part in ALL_PARTS},
        "validation": {"ok": checks.get("ok"), "fingerprint": checks.get("fingerprint"),
                       "model_invalid_tree_share": checks.get("model_invalid_tree_share"),
                       "errors_logged": checks.get("errors_logged")},
        "files": {str(rel[f]): {"sha256": file_sha256(f), "bytes": f.stat().st_size} for f in files},
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    assert_not_in_corpora(out_dir)
    out = out_dir / bundle_name(run)
    tmp = out.with_name(f".{out.name}.{os.getpid()}.tmp")
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
            zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=1, ensure_ascii=False))
            for f in files:
                zf.write(f, str(rel[f]))
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
    digest = file_sha256(out)
    atomic_write_text(f"{digest}  {out.name}\n", out.with_name(out.name + ".sha256"))
    return {"path": str(out), "sha256": digest, "files": len(files), "bytes": out.stat().st_size,
            "rows": manifest["rows"]}


def _member_sha256(zf: zipfile.ZipFile, name: str) -> str:
    h = hashlib.sha256()
    with zf.open(name) as fh:
        while b := fh.read(1 << 20):
            h.update(b)
    return h.hexdigest()


def verify(zip_path: Path, anchor_path: Path = ANCHOR_PATH) -> dict:
    """Every member's sha256 matches the manifest, nothing missing or extra, and the anchor in the
    manifest equals the git-tracked anchor."""
    probs = []
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        if MANIFEST_NAME not in names:
            return {"ok": False, "problems": ["no BUNDLE_MANIFEST.json"]}
        man = json.loads(zf.read(MANIFEST_NAME))
        expected = man["files"]
        missing = sorted(set(expected) - names)
        extra = sorted(names - set(expected) - {MANIFEST_NAME})
        if missing:
            probs.append(f"missing members: {missing[:5]}")
        if extra:
            probs.append(f"unexpected members: {extra[:5]}")
        bad = [n for n in sorted(set(expected) & names) if _member_sha256(zf, n) != expected[n]["sha256"]]
        if bad:
            probs.append(f"sha256 mismatch: {bad[:5]}")
        for n in names:
            p = PurePosixPath(n)
            if p.is_absolute() or ".." in p.parts:
                probs.append(f"unsafe member path: {n}")
    anchor = read_json(anchor_path)
    if man["corpora_anchor"]["manifest_sha256"] != anchor["manifest_sha256"]:
        probs.append("bundle was made from a different corpora/ (anchor manifest_sha256 differs)")
    return {"ok": not probs, "run": man["run"], "files": len(expected), "rows": man["rows"],
            "model": man["model"], "problems": probs}


def restore(zip_path: Path, data_dir: Path = DATA_DIR, *, overwrite: bool = False,
            anchor_path: Path = ANCHOR_PATH) -> dict:
    """Verify, then unpack into ``data_dir`` (only under ``annotations/``) and re-validate the run."""
    from hebloc.parse.checks import validate_run

    v = verify(zip_path, anchor_path)
    if not v["ok"]:
        raise RuntimeError(f"bundle failed verification: {v['problems']}")
    data_dir = Path(data_dir).resolve()
    ann = (data_dir / "annotations").resolve()
    with zipfile.ZipFile(zip_path) as zf:
        man = json.loads(zf.read(MANIFEST_NAME))
        plan, conflicts = [], []
        for name, meta in man["files"].items():
            target = (data_dir / name).resolve()
            if ann not in target.parents:
                raise RuntimeError(f"member outside data/annotations: {name}")
            assert_not_in_corpora(target)
            if target.exists():
                if file_sha256(target) == meta["sha256"]:
                    continue
                if not overwrite:
                    conflicts.append(name)
                    continue
            plan.append((name, target))
        if conflicts:
            raise RuntimeError(f"refusing to overwrite {len(conflicts)} different existing file(s), e.g. "
                               f"{conflicts[:3]} (use overwrite=True / --overwrite deliberately)")
        for name, target in plan:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
            try:
                with zf.open(name) as src, open(tmp, "wb") as dst:
                    while b := src.read(1 << 20):
                        dst.write(b)
                os.replace(tmp, target)
            finally:
                tmp.unlink(missing_ok=True)
    run_dir = data_dir / man["root"]
    rep = validate_run(run_dir, write=False, derive_tokens=False)
    return {"run": man["run"], "path": str(run_dir), "written": len(plan),
            "already_present": len(man["files"]) - len(plan), "validation_ok": rep["ok"],
            "fingerprint_matches": rep["fingerprint"] == man["validation"]["fingerprint"]}
