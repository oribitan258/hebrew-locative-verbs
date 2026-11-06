"""Checksum baseline of the immutable ``corpora/`` tree.

The baseline records, for every file under ``corpora/``: its relative path (POSIX style),
size in bytes, modification time (ns) and SHA-256. It is the reference against which the
immutability tests verify that no original corpus file was ever changed.

Reading only — this module never opens corpus files for writing.
"""

from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pyarrow as pa
import pyarrow.parquet as pq

from hebloc.paths import BASELINE_PATH, CORPORA_DIR, assert_not_in_corpora

_CHUNK = 1 << 20  # 1 MiB

SCHEMA = pa.schema(
    [
        pa.field("rel_path", pa.string(), nullable=False),
        pa.field("size", pa.int64(), nullable=False),
        pa.field("mtime_ns", pa.int64(), nullable=False),
        pa.field("sha256", pa.string(), nullable=False),
    ]
)


@dataclass(frozen=True)
class FileStat:
    rel_path: str
    size: int
    mtime_ns: int


def iter_files(root: Path = CORPORA_DIR) -> Iterator[FileStat]:
    """Yield every regular file under ``root`` (recursive), using cached directory stats.

    Paths are relative to ``root`` with '/' separators, so they are stable across OSes.
    """
    stack = [root]
    while stack:
        current = stack.pop()
        with os.scandir(current) as it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    st = entry.stat(follow_symlinks=False)
                    rel = Path(entry.path).relative_to(root).as_posix()
                    yield FileStat(rel, st.st_size, st.st_mtime_ns)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:  # read-only
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def compute_baseline(root: Path = CORPORA_DIR, workers: int = 8, progress: bool = True) -> pa.Table:
    """Stat and hash every file under ``root``. Returns a table sorted by rel_path."""
    stats = sorted(iter_files(root), key=lambda s: s.rel_path)

    def _hash(s: FileStat) -> str:
        return sha256_file(root / s.rel_path)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = pool.map(_hash, stats, chunksize=256)
        if progress:
            from tqdm import tqdm

            results = tqdm(results, total=len(stats), desc="sha256", unit="file")
        hashes = list(results)

    return pa.table(
        {
            "rel_path": [s.rel_path for s in stats],
            "size": [s.size for s in stats],
            "mtime_ns": [s.mtime_ns for s in stats],
            "sha256": hashes,
        },
        schema=SCHEMA,
    )


def write_baseline(table: pa.Table, path: Path = BASELINE_PATH, force: bool = False) -> Path:
    """Atomically write the baseline. Refuses to overwrite an existing baseline unless ``force``."""
    assert_not_in_corpora(path)
    if path.exists() and not force:
        raise FileExistsError(
            f"Baseline already exists at {path}. It is the immutability reference; "
            "overwrite only deliberately with --force."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, tmp, compression="zstd")
    os.replace(tmp, path)
    return path


@dataclass
class Drift:
    missing: list[str]
    added: list[str]
    changed: list[str]  # size or mtime differs (fast) / content differs (deep)

    @property
    def clean(self) -> bool:
        return not (self.missing or self.added or self.changed)


def compare_to_baseline(baseline: pa.Table, root: Path = CORPORA_DIR, deep: bool = False) -> Drift:
    """Compare the current state of ``root`` with ``baseline``.

    Fast mode compares the file set, sizes and mtimes. Deep mode additionally re-hashes every
    file present in both and reports content differences.
    """
    ref = {
        r: (s, m, h)
        for r, s, m, h in zip(*(baseline.column(c).to_pylist() for c in SCHEMA.names))
    }
    cur = {f.rel_path: (f.size, f.mtime_ns) for f in iter_files(root)}
    common = set(ref) & set(cur)
    changed = {p for p in common if ref[p][:2] != cur[p]}
    if deep:
        changed |= {p for p in common - changed if sha256_file(root / p) != ref[p][2]}
    return Drift(sorted(set(ref) - set(cur)), sorted(set(cur) - set(ref)), sorted(changed))


def read_baseline(path: Path = BASELINE_PATH) -> pa.Table:
    if not path.exists():
        raise FileNotFoundError(f"No corpora baseline at {path}. Run: uv run hebloc baseline")
    return pq.read_table(path)
