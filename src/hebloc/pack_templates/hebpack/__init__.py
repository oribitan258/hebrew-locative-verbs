"""hebpack: tools for the Hebrew corpora analysis package.

Start with README.md and CLAUDE.md in the package root. Main entry points:

* ``hebpack.db.connect()``: a DuckDB connection with views over all the data (tokens, words, sentences, ...);
* ``hebpack.db.q(sql)``: run SQL and get a pandas DataFrame;
* ``python -m hebpack.verify``: check that every file arrived intact;
* ``python -m hebpack.selftest --quick``: recompute the official statistics and compare.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OFFICIAL = ROOT / "official"
ANALYSES = ROOT / "analyses"

# The five corpora in chronological order (keys = corpus_id values in every table).
CORPORA = {"mikra": "Mikra", "hazal": "Hazal", "medieval": "Medieval", "haskala": "Haskala", "modern": "Modern"}
