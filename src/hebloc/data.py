"""Public read API for the project's data layer (catalog + units; tokens added in M3/M4).

Typical use::

    from hebloc import data
    df = data.units("mikra", columns=["sent_id", "ref", "text_norm"])        # pandas
    df = data.units("hazal", view="curated")                                 # curated view
    for batch in data.iter_units("modern", columns=["sent_id", "text_norm"]):  # streaming
        ...
    data.trace("mikra:<doc_id>:2:0")      # unit → exact source file/line/offsets, verified
    con = data.connect(); con.sql("SELECT corpus_id, count(*) FROM units GROUP BY 1")

Views (decision D-015): ``view=None`` → all units; ``"full"`` → units of the full view (primary
reference; identical to all units, since units exist only for documents with text); ``"curated"`` →
units of the curated historical/deduplicated view.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import duckdb
import pyarrow as pa
import pyarrow.dataset as ds

from hebloc.catalog import DOCUMENTS_PATH
from hebloc.paths import CORPORA, CORPORA_DIR, UNITS_DIR
from hebloc.textstats import decode_bytes, split_lines

VIEWS = (None, "full", "curated")


def _units_dataset(corpus: str | list[str] | None, root: Path = UNITS_DIR) -> ds.Dataset:
    corpora = list(CORPORA) if corpus is None else ([corpus] if isinstance(corpus, str) else list(corpus))
    paths = []
    for c in corpora:
        if c not in CORPORA:
            raise ValueError(f"unknown corpus {c!r}")
        files = sorted((root / c).glob("*.parquet"))
        if not files:
            raise FileNotFoundError(f"No units for {c!r} under {root}. Run: uv run hebloc prepare --corpus {c}")
        paths += [str(p) for p in files]
    return ds.dataset(paths, format="parquet")


def _filter(view: str | None):
    if view not in VIEWS:
        raise ValueError(f"view must be one of {VIEWS}")
    return None if view is None else (ds.field(f"in_{view}_view") == True)  # noqa: E712


def units(corpus: str | list[str] | None = None, *, view: str | None = None,
          columns: list[str] | None = None, root: Path = UNITS_DIR):
    """Load units as a pandas DataFrame (use ``iter_units`` for the large Modern corpus)."""
    return _units_dataset(corpus, root).to_table(columns=columns, filter=_filter(view)).to_pandas()


def iter_units(corpus: str | list[str] | None = None, *, view: str | None = None,
               columns: list[str] | None = None, batch_size: int = 50_000,
               root: Path = UNITS_DIR) -> Iterator[pa.RecordBatch]:
    """Stream units as Arrow record batches (bounded memory)."""
    scanner = _units_dataset(corpus, root).scanner(columns=columns, filter=_filter(view), batch_size=batch_size)
    yield from scanner.to_batches()


def connect(root: Path = UNITS_DIR) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with views ``documents`` and ``units`` over the Parquet files (no copies)."""
    con = duckdb.connect()
    con.execute(f"CREATE VIEW documents AS SELECT * FROM read_parquet('{DOCUMENTS_PATH.as_posix()}')")
    con.execute(f"CREATE VIEW units AS SELECT * FROM read_parquet('{(root / '*' / '*.parquet').as_posix()}')")
    return con


def trace(sent_id: str, root: Path = UNITS_DIR) -> dict:
    """Map a unit back to its exact source and VERIFY it: re-read the original file (read-only),
    take the line and the character span, and check it equals the stored ``text_raw``."""
    corpus = sent_id.split(":", 1)[0]
    t = _units_dataset(corpus, root).to_table(filter=ds.field("sent_id") == sent_id)
    if t.num_rows != 1:
        raise KeyError(f"sent_id not found: {sent_id}")
    u = t.to_pylist()[0]
    doc = duckdb.connect().execute(f"SELECT rel_path, encoding, sha256 FROM read_parquet('{DOCUMENTS_PATH.as_posix()}') "
                     f"WHERE doc_id = '{u['doc_id']}'").fetchone()
    rel_path, encoding, sha = doc
    text, detected, _ = decode_bytes((CORPORA_DIR / rel_path).read_bytes())
    line = split_lines(text)[u["line_no"] - 1]
    source_slice = line[u["char_start"]:u["char_end"]]
    return {
        "sent_id": sent_id, "ref": u["ref"], "rel_path": rel_path, "encoding": detected,
        "file_sha256": sha, "line_no": u["line_no"], "char_start": u["char_start"], "char_end": u["char_end"],
        "source_line": line, "text_raw": u["text_raw"], "text_norm": u["text_norm"],
        "norm_flags": u["norm_flags"], "verified": source_slice == u["text_raw"],
    }
