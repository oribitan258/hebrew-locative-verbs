"""Content fingerprints of the rebuilt data, compared across machines.

Every partner rebuilds ``documents`` and ``units`` from their own corpora. To prove that the result
is identical to Ori's (not just "the commands ran"), each table gets an order-independent digest:
the row count plus the sum of the first 60 bits of md5(row rendered as text) over all rows. Any
changed, missing or extra row changes it. File bytes are NOT compared: Parquet layout may differ
while content is equal.

Reference values: ``config/reference/fingerprints.json`` (git-tracked, written on Ori's machine
with ``hebloc fingerprint --write-reference``).
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from hebloc.catalog import DOCUMENTS_PATH
from hebloc.paths import CONFIG_DIR, CORPORA, UNITS_DIR
from hebloc.store.io import atomic_write_json, sql_list, sql_str

REFERENCE_PATH = CONFIG_DIR / "reference" / "fingerprints.json"
METHOD = "rows + sum(first 60 bits of md5(CAST(row AS VARCHAR))), DuckDB"


def _digest(con, source_sql: str) -> dict:
    n, s = con.execute(
        f"SELECT count(*), sum(CAST(('0x' || substr(md5(CAST(t AS VARCHAR)), 1, 15)) AS HUGEINT)) "
        f"FROM ({source_sql}) t").fetchone()
    return {"rows": int(n), "digest": format(int(s or 0), "x")}


def compute(*, documents_path: Path = DOCUMENTS_PATH, units_root: Path = UNITS_DIR) -> dict:
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    out = {"method": METHOD, "duckdb": duckdb.__version__, "tables": {}}
    if documents_path.exists():
        out["tables"]["documents"] = _digest(con, f"SELECT * FROM read_parquet({sql_str(documents_path)})")
    for c in CORPORA:
        files = sorted((units_root / c).glob("*.parquet"))
        if files:
            out["tables"][f"units/{c}"] = _digest(con, f"SELECT * FROM read_parquet({sql_list(files)})")
    return out


def compare(current: dict, reference: dict) -> list[str]:
    probs = []
    for name, ref in reference["tables"].items():
        cur = current["tables"].get(name)
        if cur is None:
            probs.append(f"{name}: missing")
        elif cur != ref:
            probs.append(f"{name}: rows {cur['rows']:,} vs reference {ref['rows']:,}; digest "
                         f"{'same' if cur['digest'] == ref['digest'] else 'DIFFERENT'}")
    if current.get("duckdb") != reference.get("duckdb"):
        probs.append(f"note: DuckDB {current.get('duckdb')} vs reference {reference.get('duckdb')} "
                     "(row rendering could differ; run `uv sync`)")
    return probs


def read_reference(path: Path = REFERENCE_PATH) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def write_reference(fp: dict, path: Path = REFERENCE_PATH) -> Path:
    return atomic_write_json(fp, path)
