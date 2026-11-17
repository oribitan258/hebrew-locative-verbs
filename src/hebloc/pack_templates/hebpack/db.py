"""DuckDB views over every table of the package (read-only; nothing is ever written into data/ or official/).

    from hebpack.db import connect, q
    con = connect()
    q("SELECT corpus_id, upos, count(*) n FROM words GROUP BY ALL ORDER BY corpus_id, n DESC", con)

Views (columns: docs/DATA_DICTIONARY.md):

=================  ========================================================================================
tokens             every Dicta token of all 5 corpora (186.9M rows), incl. punctuation
words              tokens that are not punctuation (upos <> 'PUNCT'): the official "word"
sentences          every unit (verse in Mikra, sentence elsewhere): text, provenance, stratum, views
unit_metrics       official per-unit measures: n_words, n_distinct_words, depth, tree_status
documents          one row per corpus file: sub-corpus, source, work, author, year, genre, stratum, ...
pieces             parser pieces (only long units have more than one) with Dicta's status
run_units          which parse run holds each unit, with the sha1 of the parsed text
sentence_info      sentences + unit_metrics + the most useful document columns, joined
official_<table>   the 11 official §4 tables (coverage, lexicon, word_freq, lemma_freq, sentence_stats,
                   distributions, depth_by_length, tree_status, pos, features, deprel)
=================  ========================================================================================

Modern is large (168.7M tokens): aggregate in SQL (GROUP BY) and only bring small results into pandas.
"""

from __future__ import annotations

import json

import duckdb

from hebpack import DATA, OFFICIAL

OFFICIAL_TABLES = ("coverage", "lexicon", "word_freq", "lemma_freq", "sentence_stats", "distributions",
                   "depth_by_length", "tree_status", "pos", "features", "deprel")


def _glob(*parts: str) -> str:
    return "'" + DATA.joinpath(*parts).as_posix().replace("'", "''") + "'"


def stats_dir():
    """The official statistics folder (official/stats_tables/final-...)."""
    dirs = sorted((OFFICIAL / "stats_tables").glob("final-*"))
    if len(dirs) != 1:
        raise FileNotFoundError(f"expected one official/stats_tables/final-* folder, found {len(dirs)}")
    return dirs[0]


def _ram_gb() -> float:
    """Physical memory in GB (Windows API or POSIX sysconf); 8 if unknown."""
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullTotalPhys / 2**30
    except (AttributeError, OSError):
        import os

        try:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
        except (ValueError, OSError, AttributeError):
            return 8.0


def duck(threads: int | None = None, memory_limit: str | None = None) -> duckdb.DuckDBPyConnection:
    """A DuckDB connection that never makes Windows page: memory capped at half the RAM (DuckDB then spills to a
    temp folder outside the package, which is much faster than the operating system's paging)."""
    import tempfile
    from pathlib import Path

    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{memory_limit or f'{max(2, int(_ram_gb() * 0.5))}GB'}'")
    tmp = Path(tempfile.gettempdir()) / "hebpack-duckdb"
    tmp.mkdir(exist_ok=True)
    con.execute(f"SET temp_directory = '{tmp.as_posix()}'")
    con.execute("SET preserve_insertion_order = false")
    if threads:
        con.execute(f"SET threads = {int(threads)}")
    return con


def connect(threads: int | None = None, memory_limit: str | None = None) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB connection with all views (memory capped at half the RAM unless ``memory_limit``)."""
    con = duck(threads, memory_limit)
    sd = stats_dir()
    um = "'" + (sd / "unit_metrics").as_posix().replace("'", "''") + "/*/*.parquet'"
    con.execute(f"CREATE VIEW tokens AS SELECT * FROM read_parquet({_glob('tokens', '*', '*.parquet')})")
    con.execute("CREATE VIEW words AS SELECT * FROM tokens WHERE upos IS DISTINCT FROM 'PUNCT'")
    con.execute(f"CREATE VIEW sentences AS SELECT * FROM read_parquet({_glob('sentences', '*', '*.parquet')})")
    con.execute(f"CREATE VIEW pieces AS SELECT * FROM read_parquet({_glob('pieces', '*', '*.parquet')})")
    con.execute(f"CREATE VIEW run_units AS SELECT * FROM read_parquet({_glob('run_units', '*', '*.parquet')})")
    con.execute(f"CREATE VIEW documents AS SELECT * FROM read_parquet({_glob('documents.parquet')})")
    con.execute(f"CREATE VIEW unit_metrics AS SELECT * FROM read_parquet({um})")
    con.execute("""CREATE VIEW sentence_info AS
        SELECT s.sent_id, s.corpus_id, s.doc_id, s.ref, s.unit_type, s.stratum, s.aramaic, s.in_full_view,
               s.in_curated_view, s.text_norm, m.n_words, m.n_punct, m.n_distinct_words, m.n_pieces,
               m.tree_status, m.depth, d.subcorpus, d.source, d.work, d.author, d.year, d.genre, d.subperiod,
               d.period_status, d.rel_path
        FROM sentences s LEFT JOIN unit_metrics m ON m.sent_id = s.sent_id
             LEFT JOIN documents d ON d.doc_id = s.doc_id""")
    for t in OFFICIAL_TABLES:
        p = "'" + (sd / f"{t}.parquet").as_posix().replace("'", "''") + "'"
        con.execute(f"CREATE VIEW official_{t} AS SELECT * FROM read_parquet({p})")
    return con


_DEFAULT = None


def q(sql: str, con: duckdb.DuckDBPyConnection | None = None, params=None):
    """Run SQL and return a pandas DataFrame (reuses one default connection)."""
    global _DEFAULT
    if con is None:
        if _DEFAULT is None:
            _DEFAULT = connect()
        con = _DEFAULT
    return con.execute(sql, params or []).df()


def manifest() -> dict:
    from hebpack import ROOT

    return json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
