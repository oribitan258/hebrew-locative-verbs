"""One row per unit: the sentence-level measures of project.pdf §4 (R2–R4), docs/m6_design.md §2.2.

* ``n_words``: Dicta words that are not punctuation (``upos != 'PUNCT'``), the R2 sentence length.
* ``n_punct``: punctuation tokens.
* ``n_distinct_words``: distinct word types (``surface``) among the words, the R3 measure.
* ``depth``: levels on the longest root→word path of the unit's dependency tree (root = 1),
  maximised over words (punctuation leaves ignored). Computed only for units with ONE valid tree.
* ``tree_status``, first match wins:

  ===============  ===========================================================  =================
  ``empty``        no pieces (no text after normalization)                     not measured
  ``parse_error``  a piece has Dicta status ``error`` (its words are missing)  not measured
  ``no_words``     only punctuation                                            not measured
  ``multi_piece``  parsed in several pieces: no single tree (D-021)            R2, R3; no depth
  ``invalid_tree`` the word-level graph is not a tree (D-025) or lacks a head  R2, R3; no depth
  ``complete``     one valid tree                                              R2, R3, R4
  ===============  ===========================================================  =================

Computed per run shard (all pieces of a unit are in one shard), so memory is bounded by one shard.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from hebloc.store.runs import Run

TOKEN_COLUMNS = ["sent_id", "piece_idx", "word_idx", "surface", "upos", "head", "piece_tree_valid"]
STATUSES = ("empty", "parse_error", "no_words", "multi_piece", "invalid_tree", "complete")
MEASURED = ("multi_piece", "invalid_tree", "complete")     # R2/R3 use these; R4 uses "complete" only

UNIT_METRICS_SCHEMA = pa.schema([
    ("sent_id", pa.string()),
    ("corpus_id", pa.string()),
    ("doc_id", pa.string()),
    ("n_words", pa.int32()),
    ("n_punct", pa.int32()),
    ("n_distinct_words", pa.int32()),
    ("n_pieces", pa.int16()),
    ("n_error_pieces", pa.int16()),
    ("tree_status", pa.string()),
    ("depth", pa.int32()),             # null unless tree_status == "complete"
])


def node_depths(parent: np.ndarray) -> np.ndarray:
    """Depth of every node of a forest given as parent indices (-1 = root): root = 1.

    Vectorised ancestor walk: one pass per tree level. Raises ``ValueError`` on a cycle, which a
    caller must have excluded (``piece_tree_valid``)."""
    parent = np.asarray(parent, dtype=np.int64)
    depth = np.ones(len(parent), dtype=np.int32)
    anc = parent.copy()
    for _ in range(len(parent) + 1):
        live = anc >= 0
        if not live.any():
            return depth
        depth[live] += 1
        anc[live] = parent[anc[live]]
    raise ValueError("cycle in parent array")


def unit_metrics(unit_ids: list[str], pieces: pd.DataFrame, raw_status: pd.DataFrame,
                 tokens: pd.DataFrame) -> pd.DataFrame:
    """Metrics for ``unit_ids`` from one shard's pieces (sent_id, piece_idx, n_pieces), Dicta statuses
    (sent_id, piece_idx, status) and tokens (``TOKEN_COLUMNS``)."""
    out = pd.DataFrame({"sent_id": pd.Series(unit_ids, dtype=object)})
    parts = out["sent_id"].str.split(":", n=2, expand=True) if len(out) else pd.DataFrame({0: [], 1: []})
    out["corpus_id"], out["doc_id"] = parts[0], parts[1]

    n_pieces = pieces.groupby("sent_id")["piece_idx"].nunique() if len(pieces) else pd.Series(dtype="int64")
    n_err = (raw_status[raw_status["status"] == "error"].groupby("sent_id").size()
             if len(raw_status) else pd.Series(dtype="int64"))

    t = tokens.sort_values(["sent_id", "piece_idx", "word_idx"], kind="stable").reset_index(drop=True)
    is_word = (t["upos"] != "PUNCT").to_numpy()
    g = t.groupby("sent_id", sort=False)
    n_words = pd.Series(is_word, index=t.index).groupby(t["sent_id"], sort=False).sum()
    n_tok = g.size()
    n_distinct = t[is_word].groupby("sent_id", sort=False)["surface"].nunique()
    head_missing = t["head"].isna().groupby(t["sent_id"], sort=False).any()
    tree_ok = g["piece_tree_valid"].all() & ~head_missing

    out["n_words"] = out["sent_id"].map(n_words).fillna(0).astype("int32")
    out["n_punct"] = (out["sent_id"].map(n_tok).fillna(0) - out["n_words"]).astype("int32")
    out["n_distinct_words"] = out["sent_id"].map(n_distinct).fillna(0).astype("int32")
    out["n_pieces"] = out["sent_id"].map(n_pieces).fillna(0).astype("int16")
    out["n_error_pieces"] = out["sent_id"].map(n_err).fillna(0).astype("int16")
    ok = out["sent_id"].map(tree_ok).fillna(False).astype(bool)

    status = np.select(
        [out["n_pieces"] == 0, out["n_error_pieces"] > 0, out["n_words"] == 0, out["n_pieces"] > 1, ~ok],
        ["empty", "parse_error", "no_words", "multi_piece", "invalid_tree"], default="complete")
    out["tree_status"] = status

    # depth for complete units: global parent index = piece start row + piece-local head
    complete = set(out.loc[out["tree_status"] == "complete", "sent_id"])
    tc = t[t["sent_id"].isin(complete)].reset_index(drop=True)
    depth = pd.Series(dtype="float64")
    if len(tc):
        start = tc.groupby(["sent_id", "piece_idx"], sort=False).cumcount().to_numpy()
        base = np.arange(len(tc)) - start                     # row of word 0 of the row's piece
        head = tc["head"].to_numpy(dtype=np.int64)
        local = tc["word_idx"].to_numpy(dtype=np.int64)
        if not (local == start).all():
            raise ValueError("word_idx is not 0..n-1 within a piece")
        parent = np.where(head >= 0, base + head, -1)
        d = node_depths(parent)
        wd = pd.Series(np.where(tc["upos"].to_numpy() != "PUNCT", d, 0), index=tc.index)
        depth = wd.groupby(tc["sent_id"], sort=False).max()
    out["depth"] = out["sent_id"].map(depth).astype("Int32")
    return out


def shard_metrics(run: Run, shard: str, corpus: str) -> pa.Table:
    """Unit metrics for one committed shard of ``run``, restricted to ``corpus``."""
    def read(part: str, columns: list[str]) -> pd.DataFrame:
        f = run.part_file(part, shard)
        df = pq.read_table(f, columns=columns).to_pandas() if f.exists() else pd.DataFrame(columns=columns)
        return df[df["sent_id"].str.startswith(corpus + ":")]

    inputs = read("inputs", ["sent_id"])
    pieces = read("pieces", ["sent_id", "piece_idx", "n_pieces"])
    raw = read("dicta_raw", ["sent_id", "piece_idx", "status"])
    tok_file = run.path / "tokens" / f"{shard}.parquet"
    if not tok_file.exists():
        raise FileNotFoundError(f"{run.ref}: tokens missing for {shard} (run: hebloc tokens {run.ref})")
    tokens = pq.read_table(tok_file, columns=TOKEN_COLUMNS).to_pandas()
    tokens = tokens[tokens["sent_id"].str.startswith(corpus + ":")]
    m = unit_metrics(inputs["sent_id"].tolist(), pieces, raw, tokens)
    return pa.Table.from_pandas(m, schema=UNIT_METRICS_SCHEMA, preserve_index=False)


def run_metrics(run: Run, corpus: str, progress: bool = False) -> pa.Table:
    shards = run.shards()
    it = shards
    if progress:
        from tqdm import tqdm

        it = tqdm(shards, desc=f"{run.ref} unit metrics", unit="shard")
    tables = [shard_metrics(run, s, corpus) for s in it]
    return pa.concat_tables(tables) if tables else UNIT_METRICS_SCHEMA.empty_table()
