"""DuckDB catalog: SQL views over every Parquet table (no copies of the data).

Views (all created by ``setup``; the same definitions back ``hebloc.data.connect()`` in memory and
the persistent ``data/hebloc.duckdb`` written by ``hebloc catalog``):

    documents, units                    M1/M2 tables
    runs                                small TABLE: one row per parse run (manifest + status + canonical)
    inputs_all, pieces_all,             every run, committed shards only, with a ``run`` column
    dicta_raw_all, tokens_all             (pilot runs included: ALWAYS filter on ``run``)
    inputs, pieces, dicta_raw, tokens   CANONICAL runs only (config/annotations.yaml), each run
                                          restricted to the corpus it is canonical for → at most one
                                          analysis per unit. Empty (typed) until M5 registers runs
    piece_status                        canonical pieces + parse status + word-level tree validity
    parse_coverage                      per corpus × stratum: units, parsed, multi-piece, errors,
                                          invalid trees (what any statistic must report, D-021/D-025)

Every parse-derived view carries ``corpus_id`` and ``doc_id`` (taken from ``sent_id``) for joins
with ``documents`` (views, strata) without touching the large ``units`` table.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pyarrow as pa

from hebloc.catalog import DOCUMENTS_PATH
from hebloc.paths import ANNOTATIONS_DIR, CORPORA, DATA_DIR, UNITS_DIR
from hebloc.store.io import sql_list, sql_str
from hebloc.store.runs import ALL_PARTS, ANNOTATIONS_CONFIG, Run, list_runs, load_registry

DUCKDB_PATH = DATA_DIR / "hebloc.duckdb"

_DUCK_TYPES = {pa.string(): "VARCHAR", pa.int16(): "SMALLINT", pa.int32(): "INTEGER", pa.int64(): "BIGINT",
               pa.bool_(): "BOOLEAN", pa.float32(): "FLOAT", pa.float64(): "DOUBLE",
               pa.list_(pa.string()): "VARCHAR[]"}


def _empty_select(schema: pa.Schema, extra: list[str] = ()) -> str:
    cols = [f'CAST(NULL AS VARCHAR) AS "{c}"' for c in extra]
    cols += [f'CAST(NULL AS {_DUCK_TYPES[f.type]}) AS "{f.name}"' for f in schema]
    return f"SELECT {', '.join(cols)} WHERE false"


def _part_schema(part: str) -> pa.Schema:
    from hebloc.store.schemas import registry

    return registry()[part].schema


def _run_files(run: Run, part: str) -> list[Path]:
    """Committed shards that actually have a file for ``part``."""
    return [f for s in run.shards() if (f := run.part_file(part, s)).exists()]


_ID_COLS = "split_part(sent_id, ':', 1) AS corpus_id, split_part(sent_id, ':', 2) AS doc_id"


def _part_union(part: str, runs: list[tuple[Run, str | None]]) -> str:
    """UNION of ``part`` over runs; the optional corpus restricts a run to that corpus's units."""
    selects = []
    for run, corpus in runs:
        files = _run_files(run, part)
        if not files:
            continue
        where = f" WHERE sent_id LIKE {sql_str(corpus + ':%')}" if corpus else ""
        selects.append(f"SELECT {sql_str(run.ref)} AS run, {_ID_COLS}, * "
                       f"FROM read_parquet({sql_list(files)}){where}")
    if not selects:
        return _empty_select(_part_schema(part), ["run", "corpus_id", "doc_id"])
    return "\nUNION ALL BY NAME\n".join(selects)


def runs_table(root: Path = ANNOTATIONS_DIR, config: Path = ANNOTATIONS_CONFIG) -> pa.Table:
    reg = load_registry(config)
    canon = {ref: c for c, refs in reg.items() for ref in refs}
    rows = []
    for r in list_runs(root):
        m, st = r.manifest, r.status()
        rows.append({
            "run": r.ref, "collection": r.collection, "run_id": r.run_id, "path": r.path.as_posix(),
            "canonical_for": canon.get(r.ref), "complete": st["complete"], "shards": st["shards"],
            "tokens_shards_up_to_date": st["tokens"]["up_to_date"],
            "model": m.get("model"), "repo": m.get("repo"), "revision": m.get("revision"), "variant": m.get("variant"),
            "fixes": ",".join(m.get("fixes") or []), "norm_version": m.get("norm_version"),
            "segment_version": m.get("segment_version"), "piece_version": m.get("piece_version"),
            "runner_version": m.get("runner_version"), "budget": m.get("budget"), "units": m.get("units"),
            "pieces": m.get("pieces"), "multi_piece_units": m.get("multi_piece_units"),
            "errors": (m.get("status") or {}).get("error"), "code_commit": m.get("code_commit"),
            "created_utc": m.get("created_utc"),
        })
    schema = pa.schema([("run", pa.string()), ("collection", pa.string()), ("run_id", pa.string()),
                        ("path", pa.string()), ("canonical_for", pa.string()), ("complete", pa.bool_()),
                        ("shards", pa.int64()), ("tokens_shards_up_to_date", pa.int64()), ("model", pa.string()),
                        ("repo", pa.string()), ("revision", pa.string()), ("variant", pa.string()),
                        ("fixes", pa.string()), ("norm_version", pa.string()), ("segment_version", pa.string()),
                        ("piece_version", pa.string()), ("runner_version", pa.string()), ("budget", pa.int64()),
                        ("units", pa.int64()), ("pieces", pa.int64()), ("multi_piece_units", pa.int64()),
                        ("errors", pa.int64()), ("code_commit", pa.string()), ("created_utc", pa.string())])
    return pa.Table.from_pylist(rows, schema=schema)


def view_definitions(*, documents_path: Path = DOCUMENTS_PATH, units_root: Path = UNITS_DIR,
                     annotations_root: Path = ANNOTATIONS_DIR, config: Path = ANNOTATIONS_CONFIG) -> dict[str, str]:
    from hebloc.catalog import DOCUMENTS_SCHEMA
    from hebloc.units import UNITS_SCHEMA

    defs: dict[str, str] = {}
    defs["documents"] = (f"SELECT * FROM read_parquet({sql_str(documents_path)})" if documents_path.exists()
                         else _empty_select(DOCUMENTS_SCHEMA))
    unit_files = sorted(f for c in CORPORA for f in (units_root / c).glob("*.parquet"))
    defs["units"] = (f"SELECT * FROM read_parquet({sql_list(unit_files)})" if unit_files
                     else _empty_select(UNITS_SCHEMA))
    every = [(r, None) for r in list_runs(annotations_root)]
    canonical = [(Run(*_split(ref, annotations_root)), corpus)
                 for corpus, refs in load_registry(config).items() for ref in refs]
    for part in ALL_PARTS:
        defs[f"{part}_all"] = _part_union(part, every)
        defs[part] = _part_union(part, canonical)
    defs["piece_status"] = """
        SELECT p.run, p.corpus_id, p.doc_id, p.sent_id, p.piece_idx, p.n_pieces, p.cost,
               r.status, t.n_words, coalesce(t.tree_valid, false) AS tree_valid
        FROM pieces p
        LEFT JOIN dicta_raw r USING (run, sent_id, piece_idx)
        LEFT JOIN (SELECT run, sent_id, piece_idx, count(*) AS n_words, bool_and(piece_tree_valid) AS tree_valid
                   FROM tokens GROUP BY ALL) t USING (run, sent_id, piece_idx)"""
    defs["parse_coverage"] = """
        WITH u AS (SELECT corpus_id, stratum, sent_id, is_empty_norm FROM units),
             s AS (SELECT sent_id, max(n_pieces) AS n_pieces,
                          bool_or(status = 'error') AS any_error,
                          bool_or(status <> 'error' AND NOT tree_valid) AS any_invalid_tree
                   FROM piece_status GROUP BY sent_id)
        SELECT u.corpus_id, u.stratum,
               count(*) AS units,
               count(*) FILTER (WHERE NOT u.is_empty_norm) AS units_nonempty,
               count(i.sent_id) AS units_parsed,
               count(*) FILTER (WHERE s.n_pieces > 1) AS units_multi_piece,
               count(*) FILTER (WHERE s.any_error) AS units_with_error_piece,
               count(*) FILTER (WHERE s.any_invalid_tree) AS units_with_invalid_tree
        FROM u LEFT JOIN (SELECT DISTINCT sent_id FROM inputs) i USING (sent_id)
               LEFT JOIN s USING (sent_id)
        GROUP BY ALL ORDER BY ALL"""
    return defs


def _split(ref: str, root: Path) -> tuple[str, str, Path]:
    collection, run_id = ref.split("/", 1)
    path = root / collection / "runs" / run_id
    if not path.is_dir():
        raise FileNotFoundError(f"canonical run {ref!r} in {ANNOTATIONS_CONFIG.name} does not exist at {path}")
    return collection, run_id, path


def setup(con: duckdb.DuckDBPyConnection, **paths) -> duckdb.DuckDBPyConnection:
    annotations_root = paths.get("annotations_root", ANNOTATIONS_DIR)
    config = paths.get("config", ANNOTATIONS_CONFIG)
    for name, sql in view_definitions(**paths).items():
        con.execute(f"CREATE OR REPLACE VIEW {name} AS {sql}")
    con.register("_hebloc_runs", runs_table(annotations_root, config))
    con.execute("CREATE OR REPLACE TABLE runs AS SELECT * FROM _hebloc_runs")
    con.unregister("_hebloc_runs")
    return con


def connect(**paths) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with all catalog views (cheap: views only bind Parquet metadata)."""
    return setup(duckdb.connect(), **paths)


def build(path: Path = DUCKDB_PATH, **paths) -> Path:
    """(Re)write the persistent catalog file atomically (temp file, then rename)."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    try:
        setup(con, **paths)
        con.execute("CHECKPOINT")
    finally:
        con.close()
    os.replace(tmp, path)
    tmp.with_name(tmp.name + ".wal").unlink(missing_ok=True)
    return path
