"""Run the OFFICIAL statistics code (verbatim copies in ``hebpack/_official``) on the package data.

The official code imports two helpers from the main project (``hebloc.store.io.sql_list/sql_str`` and the type
``hebloc.store.runs.Run``). When the main project is not installed, a minimal shim provides exactly those, so the
vendored files stay byte-identical to the code that produced the official numbers.

Per run file, every Parquet row group holds one original parse shard (all pieces of a unit are in one shard), so
``unit_metrics_run`` calls the official ``unit_metrics`` on exactly the batches the official run used.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hebpack import DATA


def _install_shim() -> None:
    try:
        import hebloc.store.io  # noqa: F401  (main project installed: use the real helpers)
        import hebloc.store.runs  # noqa: F401
        return
    except ImportError:
        pass
    hebloc = types.ModuleType("hebloc")
    store = types.ModuleType("hebloc.store")
    io = types.ModuleType("hebloc.store.io")
    runs = types.ModuleType("hebloc.store.runs")

    def sql_str(value) -> str:                       # identical to hebloc.store.io.sql_str
        s = value.as_posix() if isinstance(value, Path) else str(value)
        return "'" + s.replace("'", "''") + "'"

    def sql_list(values) -> str:                     # identical to hebloc.store.io.sql_list
        return "[" + ", ".join(sql_str(v) for v in values) + "]"

    class Run:                                       # only used as a type annotation by the official code
        pass

    io.sql_str, io.sql_list, runs.Run = sql_str, sql_list, Run
    hebloc.store, store.io, store.runs = store, io, runs
    sys.modules.update({"hebloc": hebloc, "hebloc.store": store, "hebloc.store.io": io, "hebloc.store.runs": runs})


_install_shim()
from hebpack._official import metrics as M  # noqa: E402
from hebpack._official import tables as T  # noqa: E402


def run_ids(corpus: str) -> list[str]:
    return sorted(p.stem for p in (DATA / "run_units" / corpus).glob("*.parquet"))


def _rg_by_shard(path: Path) -> dict[str, int]:
    """shard name -> row-group index (one row group per shard; shards without rows have none)."""
    if not path.exists():
        return {}
    pf = pq.ParquetFile(path)
    return {pf.read_row_group(i, columns=["shard"]).column(0)[0].as_py(): i for i in range(pf.num_row_groups)}


def unit_metrics_run(corpus: str, run_id: str, progress: bool = False) -> pa.Table:
    """The official per-unit measures (``M.unit_metrics``) for one run, shard by shard."""
    paths = {p: DATA / p / corpus / f"{run_id}.parquet" for p in ("run_units", "pieces", "tokens")}
    idx = {p: _rg_by_shard(f) for p, f in paths.items()}
    files = {p: pq.ParquetFile(f) for p, f in paths.items() if f.exists()}
    empty_tok = files["tokens"].schema_arrow.empty_table().select(M.TOKEN_COLUMNS).to_pandas()
    empty_pc = files["pieces"].schema_arrow.empty_table().select(["sent_id", "piece_idx", "n_pieces", "status"]).to_pandas()
    shards = sorted(idx["run_units"])
    it = shards
    if progress:
        from tqdm import tqdm

        it = tqdm(shards, desc=f"{corpus}/{run_id}", unit="shard")
    out = []
    for s in it:
        units = files["run_units"].read_row_group(idx["run_units"][s], columns=["sent_id"]).to_pandas()
        units = units[units["sent_id"].str.startswith(corpus + ":")]
        pc = (files["pieces"].read_row_group(idx["pieces"][s], columns=["sent_id", "piece_idx", "n_pieces", "status"])
              .to_pandas() if s in idx["pieces"] else empty_pc)
        tok = (files["tokens"].read_row_group(idx["tokens"][s], columns=M.TOKEN_COLUMNS).to_pandas()
               if s in idx["tokens"] else empty_tok)
        tok = tok[tok["sent_id"].str.startswith(corpus + ":")]
        m = M.unit_metrics(units["sent_id"].tolist(), pc[["sent_id", "piece_idx", "n_pieces"]],
                           pc[["sent_id", "piece_idx", "status"]], tok)
        out.append(pa.Table.from_pandas(m, schema=M.UNIT_METRICS_SCHEMA, preserve_index=False))
    return pa.concat_tables(out) if out else M.UNIT_METRICS_SCHEMA.empty_table()


def corpus_tables(corpus: str, metrics_files: list[Path]) -> tuple[dict[str, pa.Table], list[str]]:
    """The 11 official §4 tables for ``corpus`` + the official reconciliation problems (must be [])."""
    from hebpack.db import duck

    token_files = sorted((DATA / "tokens" / corpus).glob("*.parquet"))
    con = duck()
    T.setup(con, corpus, token_files, metrics_files)
    tabs = T.corpus_tables(con, corpus)
    units = con.execute(f"SELECT count(*) FROM read_parquet('{(DATA / 'sentences' / corpus).as_posix()}/*.parquet')"
                        ).fetchone()[0]
    probs = T.reconcile(con, corpus, tabs, units)
    con.close()
    return tabs, probs
