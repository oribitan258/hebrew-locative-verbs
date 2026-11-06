"""Canonical project paths.

All code resolves locations through this module so that nothing hard-codes absolute paths.
The project root is the directory containing ``pyproject.toml``; it can be overridden with the
``HEBLOC_ROOT`` environment variable (useful for tests).
"""

from __future__ import annotations

import os
from pathlib import Path


def _find_root() -> Path:
    env = os.environ.get("HEBLOC_ROOT")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError("Could not locate project root (no pyproject.toml above hebloc package).")


ROOT: Path = _find_root()

# Original, immutable source data. NEVER write here.
CORPORA_DIR: Path = ROOT / "corpora"

# Derived, reproducible data (gitignored).
DATA_DIR: Path = ROOT / "data"
CATALOG_DIR: Path = DATA_DIR / "catalog"
UNITS_DIR: Path = DATA_DIR / "units"
ANNOTATIONS_DIR: Path = DATA_DIR / "annotations"
STATS_DIR: Path = DATA_DIR / "stats"
EXTERNAL_DIR: Path = DATA_DIR / "external"

# Versioned, small artefacts.
CONFIG_DIR: Path = ROOT / "config"
DOCS_DIR: Path = ROOT / "docs"
RESULTS_DIR: Path = ROOT / "results"
ANNOTATION_DIR: Path = ROOT / "annotation"

BASELINE_PATH: Path = CATALOG_DIR / "corpora_baseline.parquet"  # gitignored, regenerable
ANCHOR_PATH: Path = CONFIG_DIR / "corpora_anchor.json"  # git-tracked pin of the baseline

# The five corpora, in chronological order. Keys are the stable corpus_id values.
CORPORA: dict[str, str] = {
    "mikra": "Mikra",
    "hazal": "Hazal",
    "medieval": "Medieval",
    "haskala": "Haskala",
    "modern": "Modern",
}


def assert_not_in_corpora(path: Path) -> None:
    """Guard for every writer: refuse to write anywhere inside corpora/."""
    resolved = Path(path).resolve()
    corpora = CORPORA_DIR.resolve()
    if resolved == corpora or corpora in resolved.parents:
        raise PermissionError(f"Refusing to write inside immutable corpora/: {resolved}")
