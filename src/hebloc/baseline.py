"""Checksum baseline of the immutable ``corpora/`` tree.

The baseline records, for every file under ``corpora/``: its relative path (POSIX style),
size in bytes, modification time (ns) and SHA-256. It is the reference against which the
immutability tests verify that no original corpus file was ever changed.

Reading only — this module never opens corpus files for writing.

Trust chain
-----------
The baseline itself lives in ``data/`` (gitignored, regenerable). To stop an accidentally
regenerated baseline from silently becoming the new source of truth, it is pinned by a small,
**git-tracked anchor** (``config/corpora_anchor.json``) holding the expected file count, total
bytes and a *canonical manifest digest*: SHA-256 over the sorted lines
``rel_path<TAB>size<TAB>sha256<LF>`` (UTF-8). The digest deliberately excludes mtimes, so it
identifies corpus *content* and stays valid on a partner's machine after copying.
A baseline is trusted only if it matches the anchor; ``hebloc baseline --force`` refuses to write
a recomputed baseline that disagrees with the anchor.
"""

from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pyarrow as pa
import pyarrow.parquet as pq

from hebloc.paths import ANCHOR_PATH, BASELINE_PATH, CORPORA_DIR, assert_not_in_corpora

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


# --------------------------------------------------------------------------- anchor

ANCHOR_FORMAT = 1
DIGEST_RECIPE = "sha256 over sorted lines 'rel_path\\tsize\\tsha256\\n' (UTF-8); mtimes excluded"


def canonical_digest(table: pa.Table) -> str:
    """Content digest of a baseline: independent of row order, mtimes and Parquet encoding."""
    rows = sorted(
        zip(
            table.column("rel_path").to_pylist(),
            table.column("size").to_pylist(),
            table.column("sha256").to_pylist(),
        )
    )
    h = hashlib.sha256()
    for rel, size, sha in rows:
        h.update(f"{rel}\t{size}\t{sha}\n".encode("utf-8"))
    return h.hexdigest()


def make_anchor(table: pa.Table) -> dict:
    """Build the git-tracked anchor record for a baseline table."""
    per_corpus: dict[str, dict[str, int]] = {}
    for rel, size in zip(table.column("rel_path").to_pylist(), table.column("size").to_pylist()):
        top = rel.split("/", 1)[0]
        entry = per_corpus.setdefault(top, {"files": 0, "bytes": 0})
        entry["files"] += 1
        entry["bytes"] += size
    return {
        "format": ANCHOR_FORMAT,
        "description": "Pinned identity of the immutable corpora/ tree. Do not edit by hand.",
        "digest_recipe": DIGEST_RECIPE,
        "file_count": table.num_rows,
        "total_bytes": sum(table.column("size").to_pylist()),
        "manifest_sha256": canonical_digest(table),
        "per_corpus": dict(sorted(per_corpus.items())),
    }


def read_anchor(path: Path = ANCHOR_PATH) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"No corpora anchor at {path}. Run: uv run hebloc anchor")
    return json.loads(path.read_text(encoding="utf-8"))


def write_anchor(anchor: dict, path: Path = ANCHOR_PATH, force: bool = False) -> Path:
    assert_not_in_corpora(path)
    if path.exists() and not force:
        raise FileExistsError(f"Anchor already exists at {path}; it is the pinned reference.")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(anchor, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)
    return path


def anchor_mismatches(table: pa.Table, anchor: dict) -> list[str]:
    """Return human-readable differences between a baseline table and the anchor (empty = OK)."""
    actual = make_anchor(table)
    problems = []
    for key in ("file_count", "total_bytes", "manifest_sha256"):
        if actual[key] != anchor.get(key):
            problems.append(f"{key}: anchor={anchor.get(key)!r} baseline={actual[key]!r}")
    if actual["per_corpus"] != anchor.get("per_corpus"):
        problems.append(f"per_corpus differs: anchor={anchor.get('per_corpus')} baseline={actual['per_corpus']}")
    return problems
