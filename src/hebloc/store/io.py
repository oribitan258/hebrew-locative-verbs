"""Low-level, crash-safe file I/O shared by every writer of the data layer.

Rule: a reader must never see a half-written file. Every file is written under a temporary name
in the same directory and then moved into place with ``os.replace`` (atomic on one volume, on
Windows and POSIX). Every writer refuses to write inside ``corpora/``.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hebloc.paths import assert_not_in_corpora

PARQUET_COMPRESSION = "zstd"


def _tmp_for(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.tmp")


def atomic_write_parquet(table: pa.Table, path: Path) -> Path:
    """Write ``table`` to ``path`` (zstd) via temp file + rename."""
    path = Path(path)
    assert_not_in_corpora(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_for(path)
    try:
        pq.write_table(table, tmp, compression=PARQUET_COMPRESSION)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def atomic_write_text(text: str, path: Path) -> Path:
    path = Path(path)
    assert_not_in_corpora(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_for(path)
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:   # LF on every platform
            fh.write(text)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def atomic_write_json(obj, path: Path, indent: int | None = 2) -> Path:
    return atomic_write_text(json.dumps(obj, indent=indent, ensure_ascii=False, default=str) + "\n", path)


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def file_sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def parquet_rows(path: Path) -> int:
    return pq.ParquetFile(path).metadata.num_rows


def sql_str(value: str | Path) -> str:
    """A single-quoted SQL string literal (for DuckDB file paths)."""
    s = value.as_posix() if isinstance(value, Path) else str(value)
    return "'" + s.replace("'", "''") + "'"


def sql_list(values) -> str:
    return "[" + ", ".join(sql_str(v) for v in values) + "]"
