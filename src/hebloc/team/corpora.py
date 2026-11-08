"""Install the corpora on a new machine and prove they are the exact files the project uses.

``hebloc corpora install --from <folder or .zip>`` copies (or extracts) the course corpora into
``corpora/``. It looks for the folder that contains all five corpus folders (Mikra, Hazal, Medieval,
Haskala, Modern), so it works whether the download has them at the top or one level down.
It then hashes every file and compares the result with the git-tracked anchor
(``config/corpora_anchor.json``: 404,294 files, sizes, sha256 manifest). Only if they match is the
baseline written, which unlocks ``hebloc inventory``.

This is the only code that creates ``corpora/``, and it refuses if ``corpora/`` already exists. It
never modifies an existing corpora folder. Extra files in the download (e.g. a readme next to the
five folders) are not copied.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from hebloc.paths import ANCHOR_PATH, BASELINE_PATH, CORPORA, CORPORA_DIR

FOLDERS = tuple(CORPORA.values())


def find_root(base: Path, max_depth: int = 3) -> Path | None:
    """The directory under ``base`` that contains all five corpus folders."""
    base = Path(base)
    frontier = [base]
    for _ in range(max_depth + 1):
        nxt = []
        for d in frontier:
            if all((d / f).is_dir() for f in FOLDERS):
                return d
            nxt += [c for c in sorted(d.iterdir()) if c.is_dir()] if d.is_dir() else []
        frontier = nxt
    return None


def verify(root: Path = CORPORA_DIR, *, workers: int = 8, write: bool = True,
           baseline_path: Path = BASELINE_PATH, anchor_path: Path = ANCHOR_PATH) -> dict:
    """Hash every file under ``root`` and compare with the anchor (writes the baseline if equal)."""
    from hebloc.baseline import anchor_mismatches, compute_baseline, read_anchor, write_baseline

    table = compute_baseline(root, workers=workers)
    problems = anchor_mismatches(table, read_anchor(anchor_path))
    if not problems and write:
        write_baseline(table, baseline_path, force=True)
    return {"ok": not problems, "files": table.num_rows,
            "bytes": int(sum(table.column("size").to_pylist())), "problems": problems[:20]}


def install(source: Path, dest: Path = CORPORA_DIR, *, workers: int = 8, verify_after: bool = True,
            baseline_path: Path = BASELINE_PATH, anchor_path: Path = ANCHOR_PATH) -> dict:
    source, dest = Path(source), Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError(f"{dest} already exists and is not empty: corpora are never overwritten. "
                              "Run `uv run hebloc corpora verify` to check it instead.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".corpora-staging-", dir=dest.parent))
    try:
        if source.is_file() and zipfile.is_zipfile(source):
            with zipfile.ZipFile(source) as zf:
                for name in zf.namelist():
                    p = Path(name)
                    if p.is_absolute() or ".." in p.parts:
                        raise ValueError(f"unsafe path in archive: {name}")
                zf.extractall(staging / "x")
            root = find_root(staging / "x")
        elif source.is_dir():
            root = find_root(source)
        else:
            raise FileNotFoundError(f"{source} is neither a folder nor a .zip file")
        if root is None:
            raise FileNotFoundError(f"could not find a folder containing {', '.join(FOLDERS)} in {source}")
        target = staging / "corpora"
        target.mkdir()
        for f in FOLDERS:
            if root.is_relative_to(staging):
                os.replace(root / f, target / f)          # extracted copy: just move it
            else:
                shutil.copytree(root / f, target / f)     # never move the user's original files
        if dest.exists():
            dest.rmdir()                                  # empty placeholder only
        os.replace(target, dest)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    report = {"installed": str(dest), "from": str(source)}
    if verify_after:
        report["verify"] = verify(dest, workers=workers, baseline_path=baseline_path, anchor_path=anchor_path)
    return report
