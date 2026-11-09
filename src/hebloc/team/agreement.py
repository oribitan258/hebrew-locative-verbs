"""Cross-machine parse agreement: does this computer produce the same parser output as Ori's?

Each machine parses the 1,000-unit pilot sample (``annotation/pilot_sample.csv``: ids only) with
the plan's settings and compares every piece's verbatim raw output (md5 of ``raw_json``) with the
reference written on Ori's laptop (``config/reference/agreement_reference.json``; md5s only, no
corpus text). Identical everywhere → slices parsed on different machines are interchangeable.
Any difference is reported per piece; the run itself can be bundled and diffed token by token with
``compare_runs`` on Ori's machine.

The run also measures this machine's real throughput (sub-words/s) for the work plan.
"""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

from hebloc.paths import ANNOTATIONS_DIR, CONFIG_DIR, DATA_DIR
from hebloc.store.io import atomic_write_json, read_json

REFERENCE_PATH = CONFIG_DIR / "reference" / "agreement_reference.json"
RESULT_PATH = DATA_DIR / "team" / "agreement.json"
COLLECTION = "agreement"


def _units(limit: int | None) -> list[tuple[str, str]]:
    from hebloc.pilot import runs as R

    ids = R.sample_ids()
    if limit:
        ids = ids[:limit]
    return [(s, t) for s, t in R.unit_rows(ids)]


def raw_md5s(run_dir: Path) -> dict[str, str]:
    from hebloc.parse.run import read_run

    return {f"{r['sent_id']}#{r['piece_idx']}": (hashlib.md5(r["raw_json"].encode("utf-8")).hexdigest()
                                                if r["raw_json"] is not None else f"status:{r['status']}")
            for r in read_run(run_dir, "dicta_raw").to_pylist()}


def _settings_key(settings: dict, model_revision: str) -> dict:
    return {k: settings[k] for k in ("settings_id", "model", "mst_fix", "lex_topk", "budget")} | {"revision": model_revision}


def run(person: str, *, threads: int | None = None, limit: int | None = None) -> dict:
    """Parse the pilot sample with the plan settings, compare with the reference, store the result."""
    from hebloc.parse import models as M
    from hebloc.parse.checks import validate_run
    from hebloc.parse.run import RunConfig, run as parse_run
    from hebloc.team.plan import load

    plan = load()
    st = plan.settings
    threads = threads or st["threads"]          # the plan's pinned value unless a diagnostic override
    units = _units(limit)
    run_id = f"{st['settings_id']}__{person}" + (f"__n{limit}" if limit else "")
    rdir = ANNOTATIONS_DIR / COLLECTION / "runs" / run_id
    lm = M.load(st["model"], threads=threads)
    manifest = parse_run(units, lm, rdir, RunConfig(
        run_id=run_id, variant="default", budget=st["budget"], batch_size=st["batch_size"],
        max_batch_subwords=st["max_batch_subwords"], mst_fix=st["mst_fix"], lex_topk=st["lex_topk"],
        shard_size=st["shard_size"], threads=threads, extra={"purpose": "agreement", "person": person}))
    checks = validate_run(rdir, expected=dict(units))
    mine = raw_md5s(rdir)
    ref = read_json(REFERENCE_PATH) if REFERENCE_PATH.exists() else None
    key = _settings_key(st, lm.revision)
    result = {"person": person, "when_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "machine": {"platform": platform.platform(), "processor": platform.processor(),
                          "python": platform.python_version(), "threads": threads},
              "settings": key, "run": f"{COLLECTION}/{run_id}", "units": len(units), "pieces": len(mine),
              "integrity_ok": checks["ok"], "subwords_per_second": round(manifest["subwords"] / manifest["parse_seconds"], 1)
              if manifest.get("parse_seconds") else None}
    if ref is None:
        result.update({"compared": False, "ok": False, "reason": "no reference file"})
    elif ref["settings"] != key:
        result.update({"compared": False, "ok": False,
                       "reason": f"reference was made with {ref['settings']}, this run uses {key}"})
    else:
        shared = [k for k in mine if k in ref["pieces"]]
        diff = [k for k in shared if mine[k] != ref["pieces"][k]]
        missing = [k for k in mine if k not in ref["pieces"]]
        result.update({"compared": True, "pieces_compared": len(shared), "pieces_identical": len(shared) - len(diff),
                       "pieces_different": len(diff), "pieces_not_in_reference": len(missing),
                       "different_examples": diff[:20],
                       "ok": checks["ok"] and not diff and not missing and len(shared) > 0})
        if not result["ok"] and not limit:
            result["package"] = _package_for_ori(f"{COLLECTION}/{run_id}", person)
    atomic_write_json(result, RESULT_PATH)
    return result


def _package_for_ori(ref: str, person: str) -> str | None:
    """On a mismatch, bundle this run so Ori can compare it token by token (`hebloc agreement --compare`)."""
    from hebloc.store import bundle as B
    from hebloc.team.work import OUTBOX_DIR

    try:
        return B.create(ref, out_dir=OUTBOX_DIR / f"{person}-agreement")["path"]
    except Exception as e:  # noqa: BLE001 — the report must still be written
        return f"could not package: {type(e).__name__}: {e}"


def compare_bundle(zip_path: Path) -> dict:
    """(Ori) Restore a partner's agreement bundle and compare it token by token with Ori's reference run."""
    from hebloc.store import bundle as B
    from hebloc.store.runs import resolve
    from hebloc.team.plan import load

    st = load().settings
    ref_dir = ANNOTATIONS_DIR / COLLECTION / "runs" / f"{st['settings_id']}__ori"
    if not ref_dir.exists():
        raise FileNotFoundError(f"reference run {ref_dir} not found on this machine (Ori's computer only)")
    res = B.restore(Path(zip_path))
    other = resolve(res["path"])
    if other.path.resolve() == ref_dir.resolve():
        raise ValueError("that bundle IS the reference run")
    return {"reference": str(ref_dir), "other": other.ref, **compare_runs(ref_dir, other.path)}


def write_reference(run_dir: Path, settings: dict, revision: str, path: Path = REFERENCE_PATH) -> dict:
    """(Ori) Pin this machine's agreement run as the reference: md5 per piece, no text."""
    ref = {"written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "machine": {"platform": platform.platform(), "processor": platform.processor()},
           "settings": _settings_key(settings, revision), "pieces": dict(sorted(raw_md5s(run_dir).items()))}
    atomic_write_json(ref, path, indent=0)
    return {"path": str(path), "pieces": len(ref["pieces"])}


def compare_runs(ref_dir: Path, other_dir: Path) -> dict:
    """Token-level agreement between two runs of the same units (for diagnosing differences)."""
    from hebloc.parse.tokens import read_tokens

    cols = ("form", "prefix", "lemma", "upos", "feats", "suffix", "head", "deprel")

    def by_key(d):
        return {(r["sent_id"], r["piece_idx"], r["word_idx"]): tuple(r[c] for c in cols)
                for r in read_tokens(d).to_pylist()}

    a, b = by_key(ref_dir), by_key(other_dir)
    shared = a.keys() & b.keys()
    per_col = {c: round(sum(a[k][i] == b[k][i] for k in shared) / max(len(shared), 1), 5) for i, c in enumerate(cols)}
    ma, mb = raw_md5s(ref_dir), raw_md5s(other_dir)
    return {"tokens_ref": len(a), "tokens_other": len(b), "tokens_compared": len(shared),
            "tokens_identical": sum(a[k] == b[k] for k in shared), "agreement_by_column": per_col,
            "pieces_identical_md5": sum(1 for k, v in mb.items() if ma.get(k) == v), "pieces": len(mb)}
