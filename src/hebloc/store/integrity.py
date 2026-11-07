"""Integrity checks of the whole data layer (``hebloc check``). No model, no network, read-only.

Levels:
- **documents**: schema; unique ``doc_id``; row count equals the git-tracked anchor's file count.
- **units** (per corpus): schema of every part; rows = ``_manifest.json``; unique ``sent_id``;
  ``sent_id`` = ``<corpus_id>:<doc_id>:<line_no>:<k>``; every ``doc_id`` is a full-view document
  of the same corpus; versions are the current ``norm``/``segment`` versions.
- **runs** (each): no orphan/missing shard files; schema of every part file; tokens up to date
  (source hashes); every parsed ``sent_id`` is a unit; default-variant runs parsed exactly
  ``units.text_norm``; run versions = units versions; the run's own validation (``checks.json``,
  re-run with ``deep=True``) is ``ok`` and still describes the run (fingerprint).
- **canonical registry**: every registered run exists, is complete, default-variant, valid, and no
  unit has two canonical analyses.

``ok`` is True only if every hard check passes. Model-quality facts (invalid trees, error pieces)
are reported, never treated as integrity failures.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import duckdb

from hebloc.catalog import DOCUMENTS_PATH
from hebloc.paths import ANCHOR_PATH, ANNOTATIONS_DIR, CORPORA, DATA_DIR, UNITS_DIR
from hebloc.store.io import atomic_write_json, read_json, sql_list, sql_str
from hebloc.store.runs import ANNOTATIONS_CONFIG, RUN_PARTS, Run, canonical_runs, list_runs
from hebloc.store.schemas import check_schema

REPORT_PATH = DATA_DIR / "catalog" / "integrity.json"
SENT_ID_RE = r"^([a-z]+):([0-9a-f]{12}):([0-9]+):([0-9]+)$"


def _one(con, sql: str):
    return con.execute(sql).fetchone()


def check_documents(con, documents_path: Path = DOCUMENTS_PATH, anchor_path: Path = ANCHOR_PATH) -> dict:
    if not documents_path.exists():
        return {"ok": False, "problems": [f"missing {documents_path}"]}
    probs = [f"schema: {p}" for p in check_schema(documents_path, "documents")]
    rows, distinct = _one(con, f"SELECT count(*), count(DISTINCT doc_id) FROM read_parquet({sql_str(documents_path)})")
    if rows != distinct:
        probs.append(f"duplicate doc_id: {rows - distinct}")
    anchor = read_json(anchor_path) if anchor_path.exists() else {}
    if anchor and anchor.get("file_count") != rows:
        probs.append(f"rows {rows} != anchor file_count {anchor.get('file_count')}")
    return {"ok": not probs, "rows": rows, "problems": probs}


def check_units(con, units_root: Path = UNITS_DIR, documents_path: Path = DOCUMENTS_PATH) -> dict:
    from hebloc.normalize import NORM_VERSION
    from hebloc.segment import SEGMENT_VERSION

    out = {}
    for c in CORPORA:
        files = sorted((units_root / c).glob("*.parquet"))
        probs = []
        if not files:
            out[c] = {"ok": False, "problems": ["no unit files"]}
            continue
        for f in files:
            probs += [f"{f.name}: {p}" for p in check_schema(f, "units")]
        man_path = units_root / c / "_manifest.json"
        man = read_json(man_path) if man_path.exists() else {}
        r = _one(con, f"""
            SELECT count(*), count(DISTINCT u.sent_id),
                   count(*) FILTER (WHERE NOT regexp_full_match(u.sent_id, '{SENT_ID_RE}')),
                   count(*) FILTER (WHERE split_part(u.sent_id, ':', 1) <> u.corpus_id OR u.corpus_id <> '{c}'
                                     OR split_part(u.sent_id, ':', 2) <> u.doc_id
                                     OR split_part(u.sent_id, ':', 3) <> CAST(u.line_no AS VARCHAR)
                                     OR split_part(u.sent_id, ':', 4) <> CAST(u.k AS VARCHAR)),
                   count(*) FILTER (WHERE d.doc_id IS NULL),
                   count(*) FILTER (WHERE d.doc_id IS NOT NULL AND (NOT d.in_full_view OR d.corpus_id <> u.corpus_id)),
                   count(*) FILTER (WHERE u.norm_version <> '{NORM_VERSION}' OR u.segment_version <> '{SEGMENT_VERSION}')
            FROM read_parquet({sql_list(files)}) u
            LEFT JOIN (SELECT doc_id, corpus_id, in_full_view FROM read_parquet({sql_str(documents_path)})) d
                   USING (doc_id)""")
        rows, distinct, bad_id, id_mismatch, no_doc, bad_doc, bad_version = r
        checks = {"duplicate_sent_id": rows - distinct, "malformed_sent_id": bad_id,
                  "sent_id_fields_mismatch": id_mismatch, "doc_not_in_catalog": no_doc,
                  "doc_not_full_view_or_other_corpus": bad_doc, "version_mismatch": bad_version}
        if man and man.get("units") != rows:
            probs.append(f"rows {rows} != _manifest.json units {man.get('units')}")
        if not man:
            probs.append("missing _manifest.json")
        probs += [f"{k}: {v}" for k, v in checks.items() if v]
        out[c] = {"ok": not probs, "rows": rows, "files": len(files), "problems": probs}
    return out


def check_run(run: Run, con, *, deep: bool = False, units_root: Path = UNITS_DIR) -> dict:
    from hebloc.normalize import NORM_VERSION
    from hebloc.parse.checks import run_fingerprint, validate_run
    from hebloc.parse.tokens import shard_up_to_date
    from hebloc.segment import SEGMENT_VERSION

    st = run.status()
    probs, notes = [], []
    if not st["complete"]:
        probs.append("run incomplete (run.json missing/stale or shard files missing)")
    if st["missing_part_files"]:
        probs.append(f"missing part files: {st['missing_part_files'][:5]}")
    if st["uncommitted_shards"]:
        probs.append(f"uncommitted shard files: {st['uncommitted_shards'][:5]}")
    shards = run.shards()
    for part in RUN_PARTS + ("tokens",):
        for s in shards:
            f = run.part_file(part, s)
            if f.exists():
                probs += [f"{part}/{s}: {p}" for p in check_schema(f, part)]
    stale = [s for s in shards if not shard_up_to_date(run.path, s, verify_hashes=True)]
    if stale:
        probs.append(f"tokens stale or missing for {len(stale)} shard(s) (run: hebloc tokens {run.ref})")
    m = run.manifest
    if m and (m.get("norm_version") != NORM_VERSION or m.get("segment_version") != SEGMENT_VERSION):
        probs.append(f"run versions norm={m.get('norm_version')} segment={m.get('segment_version')} "
                     f"!= units norm={NORM_VERSION} segment={SEGMENT_VERSION}")
    files = [f for s in shards if (f := run.part_file("inputs", s)).exists()]
    vs_units = {}
    if files:
        unit_files = sorted(f for c in CORPORA for f in (units_root / c).glob("*.parquet"))
        not_unit, differs = _one(con, f"""
            SELECT count(*) FILTER (WHERE u.sent_id IS NULL),
                   count(*) FILTER (WHERE u.sent_id IS NOT NULL AND i.text IS DISTINCT FROM u.text_norm)
            FROM read_parquet({sql_list(files)}) i
            LEFT JOIN (SELECT sent_id, text_norm FROM read_parquet({sql_list(unit_files)})) u USING (sent_id)""")
        vs_units = {"inputs_not_in_units": not_unit, "text_differs_from_text_norm": differs}
        if not_unit:
            probs.append(f"{not_unit} parsed sent_id(s) are not units")
        if m.get("variant") == "default" and differs:
            probs.append(f"default-variant run: {differs} input text(s) differ from units.text_norm")
        elif differs:
            notes.append(f"variant {m.get('variant')!r}: {differs} input texts differ from text_norm (expected)")
    fp = run_fingerprint(run.path)
    if deep:
        rep = validate_run(run.path, write=False, derive_tokens=False)
        validation = {"source": "re-run", "ok": rep["ok"], "fingerprint_current": True}
    else:
        cj = run.path / "checks.json"
        rep = read_json(cj) if cj.exists() else {}
        validation = {"source": "checks.json", "ok": rep.get("ok", False),
                      "fingerprint_current": rep.get("fingerprint") == fp}
        if not rep:
            probs.append("no checks.json (run: hebloc check --deep)")
        elif not validation["fingerprint_current"]:
            probs.append("checks.json does not describe the current run content (run: hebloc check --deep)")
    if rep and not rep.get("ok"):
        probs.append(f"run validation failed: { {k: v for k, v in rep.get('checks', {}).items() if v} }")
    model = {"model_invalid_tree_share": rep.get("model_invalid_tree_share"), "errors_logged": rep.get("errors_logged"),
             "tokens": rep.get("tokens")}
    return {"ok": not probs, "shards": len(shards), "variant": m.get("variant"), "model": m.get("model"),
            "vs_units": vs_units, "validation": validation, "model_output": model, "problems": probs, "notes": notes}


def check_canonical(con, run_reports: dict, *, root: Path = ANNOTATIONS_DIR, config: Path = ANNOTATIONS_CONFIG) -> dict:
    probs = []
    try:
        canon = canonical_runs(root=root, config=config)
    except (FileNotFoundError, ValueError) as e:
        return {"ok": False, "registered": {}, "problems": [str(e)]}
    for corpus, runs in canon.items():
        for r in runs:
            rep = run_reports.get(r.ref, {})
            if not rep.get("ok"):
                probs.append(f"{corpus}: canonical run {r.ref} fails its checks")
            if r.manifest.get("variant") != "default":
                probs.append(f"{corpus}: canonical run {r.ref} is variant {r.manifest.get('variant')!r}, not 'default'")
        files = [f for r in runs for s in r.shards() if (f := r.part_file("inputs", s)).exists()]
        if files:
            dup = _one(con, f"""SELECT count(*) - count(DISTINCT sent_id) FROM read_parquet({sql_list(files)})
                               WHERE sent_id LIKE {sql_str(corpus + ':%')}""")[0]
            if dup:
                probs.append(f"{corpus}: {dup} unit(s) have more than one canonical analysis")
    return {"ok": not probs, "registered": {c: [r.ref for r in rs] for c, rs in canon.items()}, "problems": probs}


def check_all(*, deep: bool = False, runs: list[str] | None = None, skip_units: bool = False,
              write: bool = True, documents_path: Path = DOCUMENTS_PATH, units_root: Path = UNITS_DIR,
              annotations_root: Path = ANNOTATIONS_DIR, config: Path = ANNOTATIONS_CONFIG,
              anchor_path: Path = ANCHOR_PATH, report_path: Path = REPORT_PATH) -> dict:
    con = duckdb.connect()
    rep: dict = {"deep": deep}
    rep["documents"] = check_documents(con, documents_path, anchor_path)
    rep["units"] = {} if skip_units else check_units(con, units_root, documents_path)
    selected = [r for r in list_runs(annotations_root) if runs is None or r.ref in runs]
    rep["runs"] = {r.ref: check_run(r, con, deep=deep, units_root=units_root) for r in selected}
    rep["canonical"] = check_canonical(con, rep["runs"], root=annotations_root, config=config)
    failed = []
    if not rep["documents"]["ok"]:
        failed.append("documents")
    failed += [f"units:{c}" for c, v in rep["units"].items() if not v["ok"]]
    failed += [f"run:{k}" for k, v in rep["runs"].items() if not v["ok"]]
    if not rep["canonical"]["ok"]:
        failed.append("canonical")
    rep["failed"] = failed
    rep["ok"] = not failed
    rep["summary"] = dict(Counter("ok" if v["ok"] else "failed" for v in rep["runs"].values()))
    if write:
        atomic_write_json(rep, report_path)
    return rep

