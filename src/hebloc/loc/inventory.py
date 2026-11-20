"""Dicta's verb inventory per corpus: counts of VERB tokens by ``(lemma, host)``.

Used to (1) check the lexicon's ``dicta_lemmas`` against what Dicta actually outputs, and (2) derive
the fallback form lists deterministically (``hebloc.loc.lexicon.build_forms``). ``host`` is the token
without its proclitic prefix letters (``tokens.host``); ``[BLANK]`` lemmas are kept as such.

Output: ``data/loc/inventory/<corpus>.parquet`` (+ ``manifest.json``), columns ``lemma, host, n``,
sorted. One full scan of the corpus (Modern: minutes).
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa

from hebloc.loc.source import Source, connect
from hebloc.paths import DATA_DIR
from hebloc.store.io import atomic_write_parquet

INVENTORY_DIR = DATA_DIR / "loc" / "inventory"
INVENTORY_SCHEMA = pa.schema([("lemma", pa.string()), ("host", pa.string()), ("n", pa.int64())])


def build(corpus: str, source: Source, out_dir: Path = INVENTORY_DIR, *, progress: bool = True) -> Path:
    con = connect()
    parts = []
    for run in source.runs(corpus):
        if progress:
            print(f"  inventory {corpus}: {run.run_id}", flush=True)
        t = con.sql(f"SELECT lemma, host, count(*)::BIGINT AS n FROM {source.tokens_sql(run, ('lemma', 'host', 'upos'))} "
                    f"WHERE upos = 'VERB' GROUP BY ALL").to_arrow_table()
        parts.append(t)
    con.register("parts", pa.concat_tables(parts))
    t = con.sql("SELECT lemma, host, sum(n)::BIGINT AS n FROM parts GROUP BY ALL").to_arrow_table()
    t = t.cast(INVENTORY_SCHEMA).sort_by([("lemma", "ascending"), ("host", "ascending")])
    path = Path(out_dir) / f"{corpus}.parquet"
    atomic_write_parquet(t, path)
    return path


def load(corpora: list[str] | None = None, root: Path = INVENTORY_DIR) -> pa.Table:
    """Inventories of the given corpora (default: all present), with a ``corpus`` column."""
    import pyarrow.parquet as pq

    files = sorted(Path(root).glob("*.parquet"))
    tabs = []
    for f in files:
        if corpora and f.stem not in corpora:
            continue
        t = pq.read_table(f)
        tabs.append(t.append_column("corpus", pa.array([f.stem] * len(t), pa.string())))
    if not tabs:
        return pa.table({"lemma": pa.array([], pa.string()), "host": pa.array([], pa.string()),
                         "n": pa.array([], pa.int64()), "corpus": pa.array([], pa.string())})
    return pa.concat_tables(tabs)
