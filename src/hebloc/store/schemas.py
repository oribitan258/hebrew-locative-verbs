"""Registry of every persisted table: schema, version, primary key and location.

The schemas themselves stay next to the code that writes them (``catalog``, ``units``, ``pieces``,
``parse.run``, ``parse.tokens``); this module only gathers them so that the integrity checker,
the DuckDB catalog and the docs agree on one list. ``check_schema`` compares a Parquet file's
schema with the registered one (names, order and types; nullability and metadata are ignored).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


@dataclass(frozen=True)
class TableSpec:
    name: str
    schema: pa.Schema
    key: tuple[str, ...]
    version: str
    location: str
    doc: str


def registry() -> dict[str, TableSpec]:
    from hebloc.catalog import DOCUMENTS_SCHEMA, INVENTORY_VERSION
    from hebloc.normalize import NORM_VERSION
    from hebloc.parse.run import INPUTS_SCHEMA, RAW_SCHEMA, RUNNER_VERSION
    from hebloc.parse.tokens import TOKENS_SCHEMA, TOKENS_VERSION
    from hebloc.pieces import PIECE_VERSION, PIECES_SCHEMA
    from hebloc.segment import SEGMENT_VERSION
    from hebloc.units import UNITS_SCHEMA

    specs = [
        TableSpec("documents", DOCUMENTS_SCHEMA, ("doc_id",), f"inventory {INVENTORY_VERSION}",
                  "data/catalog/documents.parquet", "one row per file under corpora/ (M1)"),
        TableSpec("units", UNITS_SCHEMA, ("sent_id",), f"norm {NORM_VERSION}, segment {SEGMENT_VERSION}",
                  "data/units/<corpus>/part-*.parquet", "complete sentences/verses (M2/M2.1)"),
        TableSpec("inputs", INPUTS_SCHEMA, ("sent_id",), f"runner {RUNNER_VERSION}",
                  "data/annotations/<collection>/runs/<run_id>/inputs/shard-*.parquet", "exact text parsed per unit"),
        TableSpec("pieces", PIECES_SCHEMA, ("sent_id", "piece_idx"), f"piece {PIECE_VERSION}",
                  "…/runs/<run_id>/pieces/shard-*.parquet", "parse-time pieces of a unit"),
        TableSpec("dicta_raw", RAW_SCHEMA, ("sent_id", "piece_idx"), f"runner {RUNNER_VERSION}",
                  "…/runs/<run_id>/dicta_raw/shard-*.parquet", "verbatim Dicta JSON per piece"),
        TableSpec("tokens", TOKENS_SCHEMA, ("sent_id", "piece_idx", "word_idx"), f"tokens {TOKENS_VERSION}",
                  "…/runs/<run_id>/tokens/shard-*.parquet", "one row per Dicta word (derived, PROPOSED schema)"),
    ]
    return {s.name: s for s in specs}


def schema_problems(actual: pa.Schema, expected: pa.Schema) -> list[str]:
    a = [(f.name, f.type) for f in actual]
    e = [(f.name, f.type) for f in expected]
    if a == e:
        return []
    probs = []
    an, en = [n for n, _ in a], [n for n, _ in e]
    if missing := [n for n in en if n not in an]:
        probs.append(f"missing columns {missing}")
    if extra := [n for n in an if n not in en]:
        probs.append(f"unexpected columns {extra}")
    at = dict(a)
    if wrong := [f"{n}: {at[n]} != {t}" for n, t in e if n in at and at[n] != t]:
        probs.append(f"wrong types {wrong}")
    if not probs:
        probs.append("column order differs")
    return probs


def check_schema(path: Path, table: str) -> list[str]:
    return schema_problems(pq.read_schema(path), registry()[table].schema)
