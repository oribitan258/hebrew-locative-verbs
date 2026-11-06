"""M1 — build the document catalog from the read-only ``corpora/`` tree.

Steps:
 1. enumerate every file (same walker as the checksum baseline);
 2. in parallel, read each file's bytes ONCE (read-only) → sha256 + text profile;
 3. attach parsed path metadata and curation tags (stratum, period status);
 4. detect exact duplicates (identical sha256, non-empty files), scoped to stratum|source;
 5. derive the full view (primary) and the curated view (with explicit exclusion reasons);
 6. VERIFY against the baseline and the git-tracked anchor — refuse to write on any mismatch;
 7. write ``documents.parquet`` + a JSON manifest atomically.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hebloc.baseline import anchor_mismatches, canonical_digest, iter_files, read_anchor, read_baseline
from hebloc.catalog import DOCUMENTS_PATH, DOCUMENTS_SCHEMA, INVENTORY_VERSION, MANIFEST_PATH
from hebloc.curation import load_curation
from hebloc.metadata import GENERIC_FIELDS, parse_metadata
from hebloc.paths import ANCHOR_PATH, BASELINE_PATH, CORPORA, CORPORA_DIR, ROOT, assert_not_in_corpora
from hebloc.textstats import looks_like_7zip_log, profile_text

FOLDER_TO_CORPUS = {folder: cid for cid, folder in CORPORA.items()}
AUXILIARY_EXTENSIONS = {".log"}


def doc_id_for(rel_path: str) -> str:
    """Stable 12-hex-char id derived from the path relative to corpora/ (POSIX)."""
    return hashlib.blake2b(rel_path.encode("utf-8"), digest_size=6).hexdigest()


def _profile_one(rel_path: str, root: str) -> dict:
    """Worker: read one file (read-only) and profile it. Top-level for multiprocessing."""
    with open(os.path.join(root, rel_path), "rb") as fh:
        data = fh.read()
    prof = profile_text(data).as_dict()
    prof["is_7zip_log"] = looks_like_7zip_log(data)
    prof["sha256"] = hashlib.sha256(data).hexdigest()
    prof["size_bytes"] = len(data)
    prof["rel_path"] = rel_path
    return prof


def _git_commit() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.strip()
        return sha + ("+dirty" if dirty else "")
    except Exception:  # noqa: BLE001 — provenance is best-effort
        return "unknown"


def build_rows(root: Path = CORPORA_DIR, workers: int | None = None, progress: bool = True) -> list[dict]:
    rel_paths = sorted(f.rel_path for f in iter_files(root))
    workers = workers or max(1, min(12, (os.cpu_count() or 4) - 2))
    fn = partial(_profile_one, root=str(root))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        it = pool.map(fn, rel_paths, chunksize=512)
        if progress:
            from tqdm import tqdm

            it = tqdm(it, total=len(rel_paths), desc="inventory", unit="file")
        return list(it)


def assemble(profiles: list[dict]) -> pa.Table:
    """Add identity, metadata, duplicates, curation and view columns."""
    curation = load_curation()
    rows = []
    for p in profiles:
        rel = p["rel_path"]
        folder, _, rel_in_corpus = rel.partition("/")
        if folder not in FOLDER_TO_CORPUS or not rel_in_corpus:
            raise ValueError(f"File outside the five corpus folders: {rel}")
        corpus_id = FOLDER_TO_CORPUS[folder]
        name = rel.rsplit("/", 1)[-1]
        ext = os.path.splitext(name)[1].lower()
        aux_reason = None
        if p["size_bytes"] == 0:
            kind = "empty"
        elif ext in AUXILIARY_EXTENSIONS:
            kind, aux_reason = "auxiliary", f"extension {ext}"
        elif p["is_7zip_log"]:
            kind, aux_reason = "auxiliary", "content: 7-Zip archiving log"
        else:
            kind = "text"

        meta = parse_metadata(corpus_id, rel_in_corpus)
        extras = {k: v for k, v in meta.items() if k not in GENERIC_FIELDS and v is not None}
        rule = curation.classify(corpus_id, rel_in_corpus)
        subperiod = None
        if corpus_id == "haskala" and meta.get("year") is not None:
            subperiod = "haskala" if meta["year"] <= curation.haskala_cutoff_year else "post_haskala"

        n_heb = p["n_hebrew_letters"]
        n_letters = n_heb + p["n_latin_letters"]
        row = {
            "doc_id": doc_id_for(rel),
            "corpus_id": corpus_id,
            "rel_path": rel,
            "file_name": name,
            "ext": ext,
            "file_kind": kind,
            "aux_reason": aux_reason,
            "hebrew_ratio": (n_heb / n_letters) if n_letters else None,
            "niqqud_per_letter": (p["n_niqqud"] / n_heb) if n_heb else None,
            **{k: v for k, v in p.items() if k not in ("rel_path", "is_7zip_log")},
            **{k: meta.get(k) for k in GENERIC_FIELDS},
            "meta_json": json.dumps(extras, ensure_ascii=False, sort_keys=True) if extras else None,
            "stratum": rule.stratum,
            "period_status": rule.period_status,
            "curation_rule": rule.id,
            "subperiod": subperiod,
            "inventory_version": INVENTORY_VERSION,
            "curation_hash": curation.version_hash,
        }
        rows.append(row)

    # Exact duplicates (identical bytes, non-empty files) — decision D-015.
    # A copy is excluded from the curated view ONLY if an identical file exists in the same
    # DUPLICATE SCOPE (same stratum and same source category). Identical files in different
    # scopes/corpora are all kept and merely flagged (dup_cross_scope / dup_cross_corpus).
    for r in rows:
        r["dup_scope"] = f"{r['stratum']}|{r['source'] or ''}"
        r.update(dup_count=1, dup_rank=0, is_dup_copy=False, dup_of=None,
                 dup_count_global=1, dup_cross_scope=False, dup_cross_corpus=False)
    global_groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["size_bytes"] > 0:
            global_groups[r["sha256"]].append(r)
    for members in global_groups.values():
        if len(members) < 2:
            continue
        cross_scope = len({m["dup_scope"] for m in members}) > 1
        cross_corpus = len({m["corpus_id"] for m in members}) > 1
        scoped: dict[str, list[dict]] = defaultdict(list)
        for m in members:
            m.update(dup_count_global=len(members), dup_cross_scope=cross_scope, dup_cross_corpus=cross_corpus)
            scoped[m["dup_scope"]].append(m)
        for group in scoped.values():
            group.sort(key=lambda r: r["rel_path"])  # rank 0 = canonical (first path)
            for rank, r in enumerate(group):
                r.update(dup_count=len(group), dup_rank=rank, is_dup_copy=rank > 0,
                         dup_of=group[0]["doc_id"] if rank > 0 else None)

    # Views (D-015). FULL = every corpus text file as supplied (primary reference).
    # CURATED = additional analytical view; every exclusion is explained.
    for r in rows:
        r["in_full_view"] = r["file_kind"] == "text"
        reasons = []
        if r["file_kind"] != "text":
            reasons.append(f"file_kind:{r['file_kind']}")
        elif r["is_blank"]:
            reasons.append("blank")
        if r["period_status"] != "in_period":
            reasons.append(f"period:{r['period_status']}")
        if r["is_dup_copy"]:
            reasons.append("duplicate_copy_within_scope")
        r["curated_exclusion_reasons"] = reasons
        r["in_curated_view"] = not reasons

    rows.sort(key=lambda r: r["rel_path"])
    return pa.Table.from_pylist(rows, schema=DOCUMENTS_SCHEMA)


def verify(table: pa.Table, baseline_path: Path = BASELINE_PATH, anchor_path: Path = ANCHOR_PATH,
           root: Path = CORPORA_DIR) -> dict:
    """Cross-check the catalog against the filesystem, the baseline and the anchor."""
    checks: dict[str, object] = {}
    cat = dict(zip(table.column("rel_path").to_pylist(),
                   zip(table.column("size_bytes").to_pylist(), table.column("sha256").to_pylist())))
    fs = {f.rel_path: f.size for f in iter_files(root)}
    checks["filesystem_paths_equal"] = set(cat) == set(fs)
    checks["filesystem_sizes_equal"] = all(cat[p][0] == fs.get(p) for p in cat)
    base = read_baseline(baseline_path)
    bmap = dict(zip(base.column("rel_path").to_pylist(),
                    zip(base.column("size").to_pylist(), base.column("sha256").to_pylist())))
    checks["baseline_rows_equal"] = cat == bmap
    as_baseline = pa.table({"rel_path": table.column("rel_path"), "size": table.column("size_bytes"),
                            "sha256": table.column("sha256")})
    anchor = read_anchor(anchor_path)
    checks["catalog_digest"] = canonical_digest(as_baseline)
    checks["anchor_digest"] = anchor["manifest_sha256"]
    checks["anchor_digest_equal"] = checks["catalog_digest"] == anchor["manifest_sha256"]
    checks["baseline_matches_anchor"] = not anchor_mismatches(base, anchor)
    checks["doc_ids_unique"] = len(set(table.column("doc_id").to_pylist())) == table.num_rows
    checks["no_unclassified"] = not any(s.endswith(".unclassified") for s in table.column("stratum").to_pylist())
    required = ("filesystem_paths_equal", "filesystem_sizes_equal", "baseline_rows_equal",
                "anchor_digest_equal", "baseline_matches_anchor", "doc_ids_unique", "no_unclassified")
    checks["ok"] = all(checks[k] is True for k in required)
    return checks


def write_catalog(table: pa.Table, manifest: dict, path: Path = DOCUMENTS_PATH,
                  manifest_path: Path = MANIFEST_PATH) -> None:
    for p in (path, manifest_path):
        assert_not_in_corpora(p)
        p.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp, compression="zstd")
    os.replace(tmp, path)
    tmpm = manifest_path.with_suffix(".json.tmp")
    tmpm.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmpm, manifest_path)


def run_inventory(workers: int | None = None, progress: bool = True) -> tuple[pa.Table, dict]:
    t0 = time.perf_counter()
    profiles = build_rows(CORPORA_DIR, workers=workers, progress=progress)
    table = assemble(profiles)
    checks = verify(table)
    if not checks["ok"]:
        raise RuntimeError(f"Catalog verification FAILED — nothing written: {checks}")
    per_corpus = {}
    for cid in CORPORA:
        mask = [c == cid for c in table.column("corpus_id").to_pylist()]
        sub = table.filter(pa.array(mask))
        per_corpus[cid] = {"files": sub.num_rows, "bytes": sum(sub.column("size_bytes").to_pylist())}
    manifest = {
        "table": "documents",
        "inventory_version": INVENTORY_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code_commit": _git_commit(),
        "curation_hash": table.column("curation_hash")[0].as_py(),
        "rows": table.num_rows,
        "per_corpus": per_corpus,
        "verification": checks,
        "runtime_seconds": round(time.perf_counter() - t0, 1),
    }
    write_catalog(table, manifest)
    return table, manifest
