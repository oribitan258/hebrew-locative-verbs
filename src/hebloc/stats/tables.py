"""Corpus-level tables of project.pdf §4 (docs/m6_design.md §2), computed with DuckDB.

Inputs per corpus: the ``tokens`` shard files of its runs (restricted to the corpus's units) and the
unit-metrics table (``hebloc.stats.metrics``). Every table is long-format with ``corpus_id``.

=================  ======  ===========================================================
table              §4      content
=================  ======  ===========================================================
coverage           rules   units by status, words, punctuation, blank lemmas, exclusions
word_freq          R1      every word type with its frequency and rank
lemma_freq         R1      every lemma with its frequency and rank ([BLANK] excluded)
lexicon            R1      tokens, types, types occurring once (words; lemmas)
sentence_stats     R2–R4   summary of length / distinct_words / depth per unit
distributions      R2–R4   full distribution (value → number of units)
depth_by_length    R4      mean and median depth per sentence-length band
tree_status        R4      units and words per tree status (what depth excludes)
pos                R5      count of each POS
features           R5      every Dicta inflection feature value, per POS and for all words
deprel             R6      count of each dependency relation
=================  ======  ===========================================================

``reconcile`` cross-checks the totals; any problem stops the run before anything is published.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pyarrow as pa

from hebloc.store.io import sql_list, sql_str

# Dicta's complete morphological label set (dicta_code/BertForMorphTagging.py: ALL_FEATURES,
# ALL_SUFFIX_POS; checked by tests/test_stats.py against the vendored code).
WORD_FEATURES = {
    "Gender": ("Masc", "Fem", "Fem,Masc"),
    "Number": ("Sing", "Plur", "Plur,Sing", "Dual", "Dual,Plur"),
    "Person": ("1", "2", "3", "1,2,3"),
    "Tense": ("Past", "Fut", "Pres", "Imp"),
}
SUFFIX_TYPES = ("ADP_PRON", "PRON")
NONE = "(none)"
ALL_WORDS = "(all words)"
LENGTH_BANDS = ((1, 5), (6, 10), (11, 15), (16, 20), (21, 30), (31, 40), (41, 60), (61, 100), (101, None))
QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95, 0.99)
MEASURES = {"length": "n_words", "distinct_words": "n_distinct_words", "depth": "depth"}


def _band_sql(col: str) -> tuple[str, str]:
    label = "CASE " + " ".join(
        f"WHEN {col} BETWEEN {lo} AND {hi} THEN '{lo}-{hi}'" if hi else f"WHEN {col} >= {lo} THEN '{lo}+'"
        for lo, hi in LENGTH_BANDS) + " END"
    order = "CASE " + " ".join(
        f"WHEN {col} BETWEEN {lo} AND {hi} THEN {i}" if hi else f"WHEN {col} >= {lo} THEN {i}"
        for i, (lo, hi) in enumerate(LENGTH_BANDS)) + " END"
    return label, order


def _mean(col: str) -> str:
    """Exact mean of an integer column (HUGEINT sum): identical across runs and thread counts."""
    return f"CAST(sum(CAST({col} AS HUGEINT)) AS DOUBLE) / count({col})"


def setup(con: duckdb.DuckDBPyConnection, corpus: str, token_files: list[Path], metrics_files: list[Path]) -> None:
    """Views ``tok`` (all Dicta tokens of the corpus), ``w`` (words = non-punctuation) and ``m`` (units)."""
    con.execute(f"CREATE OR REPLACE VIEW tok AS SELECT * FROM read_parquet({sql_list(token_files)}) "
                f"WHERE sent_id LIKE {sql_str(corpus + ':%')}")
    con.execute("CREATE OR REPLACE VIEW w AS SELECT * FROM tok WHERE upos IS DISTINCT FROM 'PUNCT'")
    con.execute(f"CREATE OR REPLACE VIEW m AS SELECT * FROM read_parquet({sql_list(metrics_files)})")


def _t(con, sql: str) -> pa.Table:
    return con.sql(sql).to_arrow_table()


def corpus_tables(con: duckdb.DuckDBPyConnection, corpus: str) -> dict[str, pa.Table]:
    """All §4 tables for the corpus whose views ``setup`` created."""
    c = sql_str(corpus)
    label = sql_str("verse" if corpus == "mikra" else "sentence")
    out: dict[str, pa.Table] = {}
    measured = "tree_status IN ('multi_piece', 'invalid_tree', 'complete')"

    # ---------------------------------------------------------------- coverage (project rules)
    out["coverage"] = _t(con, f"""
        WITH s AS (SELECT
            count(*) AS units,
            count(*) FILTER (WHERE tree_status = 'empty') AS units_empty,
            count(*) FILTER (WHERE tree_status = 'parse_error') AS units_parse_error,
            count(*) FILTER (WHERE tree_status = 'no_words') AS units_punctuation_only,
            count(*) FILTER (WHERE {measured}) AS units_measured,
            count(*) FILTER (WHERE tree_status = 'complete') AS units_with_depth,
            count(*) FILTER (WHERE tree_status = 'multi_piece') AS units_multi_piece,
            count(*) FILTER (WHERE tree_status = 'invalid_tree') AS units_invalid_tree,
            CAST(coalesce(sum(n_words), 0) AS BIGINT) AS words, CAST(coalesce(sum(n_punct), 0) AS BIGINT) AS punctuation_tokens,
            CAST(coalesce(sum(n_words) FILTER (WHERE tree_status = 'multi_piece'), 0) AS BIGINT) AS words_in_multi_piece,
            CAST(coalesce(sum(n_words) FILTER (WHERE tree_status = 'invalid_tree'), 0) AS BIGINT) AS words_in_invalid_tree,
            CAST(coalesce(sum(n_words) FILTER (WHERE tree_status = 'complete'), 0) AS BIGINT) AS words_in_depth_units,
            CAST(coalesce(sum(n_pieces), 0) AS BIGINT) AS pieces, CAST(coalesce(sum(n_error_pieces), 0) AS BIGINT) AS error_pieces FROM m),
        t AS (SELECT count(*) AS tokens,
                     count(*) FILTER (WHERE lemma_blank AND upos IS DISTINCT FROM 'PUNCT') AS words_lemma_blank,
                     count(DISTINCT (sent_id, piece_idx)) FILTER (WHERE status = 'mst_fallback') AS mst_fallback_pieces
              FROM tok)
        SELECT {c} AS corpus_id, {label} AS unit_label, s.*, t.* FROM s, t""")

    # ---------------------------------------------------------------- R1 words and lemmas
    for name, col, where in (("word_freq", "surface", "TRUE"), ("lemma_freq", "lemma", "NOT lemma_blank")):
        key = "word" if name == "word_freq" else "lemma"
        out[name] = _t(con, f"""
            WITH f AS (SELECT {col} AS {key}, count(*) AS n FROM w WHERE {where} GROUP BY 1)
            SELECT {c} AS corpus_id, CAST(row_number() OVER (ORDER BY n DESC, {key}) AS INTEGER) AS rank,
                   {key}, n, n / sum(n) OVER () AS share FROM f ORDER BY rank""")
    out["lexicon"] = _t(con, f"""
        SELECT {c} AS corpus_id, 'word' AS kind, CAST(sum(n) AS BIGINT) AS tokens, count(*) AS types,
               count(*) FILTER (WHERE n = 1) AS types_once FROM (SELECT surface, count(*) n FROM w GROUP BY 1)
        UNION ALL
        SELECT {c}, 'lemma', CAST(sum(n) AS BIGINT), count(*), count(*) FILTER (WHERE n = 1)
        FROM (SELECT lemma, count(*) n FROM w WHERE NOT lemma_blank GROUP BY 1)
        ORDER BY kind DESC""")

    # ---------------------------------------------------------------- R2–R4 sentence measures
    stats, dists = [], []
    for i, (measure, col) in enumerate(MEASURES.items()):
        where = "tree_status = 'complete'" if measure == "depth" else measured
        q = ", ".join(f"quantile_cont({col}, {p}) AS p{int(p * 100)}" for p in QUANTILES)
        # mean and sd from exact integer sums (HUGEINT): bit-identical across runs and thread counts
        stats.append(f"""SELECT {c} AS corpus_id, {label} AS unit_label, '{measure}' AS measure, {i} AS measure_order,
            count(*) AS n_units,
            CAST(sum(CAST({col} AS HUGEINT)) AS DOUBLE) / count(*) AS mean,
            CASE WHEN count(*) > 1 THEN sqrt(CAST(count(*) * sum(CAST({col} AS HUGEINT) * {col})
                 - sum(CAST({col} AS HUGEINT)) * sum(CAST({col} AS HUGEINT)) AS DOUBLE)
                 / (CAST(count(*) AS DOUBLE) * (count(*) - 1))) END AS sd,
            min({col}) AS min, {q}, max({col}) AS max FROM m WHERE {where}""")
        dists.append(f"""SELECT {c} AS corpus_id, '{measure}' AS measure, {i} AS measure_order,
            CAST({col} AS INTEGER) AS value, count(*) AS n_units FROM m WHERE {where} GROUP BY 4""")
    out["sentence_stats"] = _t(con, " UNION ALL ".join(stats) + " ORDER BY measure_order")
    out["distributions"] = _t(con, f"""SELECT *, n_units / sum(n_units) OVER (PARTITION BY measure) AS share
        FROM ({' UNION ALL '.join(dists)}) ORDER BY measure_order, value""")
    band, order = _band_sql("n_words")
    out["depth_by_length"] = _t(con, f"""
        SELECT {c} AS corpus_id, {band} AS length_band, {order} AS band_order, count(*) AS n_units,
               {_mean('n_words')} AS mean_length, {_mean('depth')} AS mean_depth, quantile_cont(depth, 0.5) AS median_depth,
               min(depth) AS min_depth, max(depth) AS max_depth
        FROM m WHERE tree_status = 'complete' GROUP BY 2, 3 ORDER BY band_order""")
    out["tree_status"] = _t(con, f"""
        SELECT {c} AS corpus_id, tree_status, count(*) AS units, count(*) / sum(count(*)) OVER () AS share_units,
               CAST(sum(n_words) AS BIGINT) AS words, sum(n_words) / sum(sum(n_words)) OVER () AS share_words,
               {_mean('n_words')} AS mean_length, quantile_cont(n_words, 0.5) AS median_length, max(n_words) AS max_length
        FROM m GROUP BY 2 ORDER BY 2""")

    # ---------------------------------------------------------------- R5 POS and inflection
    out["pos"] = _t(con, f"""
        SELECT {c} AS corpus_id, upos, count(*) AS n, count(*) / sum(count(*)) OVER () AS share_tokens,
               CASE WHEN upos = 'PUNCT' THEN NULL
                    ELSE count(*) / sum(count(*)) FILTER (WHERE upos IS DISTINCT FROM 'PUNCT') OVER () END AS share_words
        FROM tok GROUP BY 2 ORDER BY n DESC, upos""")
    feats = [f"SELECT upos, '{f}' AS feature, coalesce({f.lower()}, '{NONE}') AS value FROM w" for f in WORD_FEATURES]
    feats.append(f"SELECT upos, 'Suffix' AS feature, coalesce(suffix, '{NONE}') AS value FROM w")
    for f in ("Gender", "Number", "Person"):
        feats.append(f"SELECT upos, 'Suffix.{f}' AS feature, "
                     f"coalesce(nullif(regexp_extract(suffix_feats, '{f}=([^|]+)', 1), ''), '{NONE}') AS value "
                     f"FROM w WHERE suffix IS NOT NULL")
    feats.append(f"SELECT upos, 'Definite (DET prefix)' AS feature, "
                 f"CASE WHEN list_contains(prefix_upos, 'DET') THEN 'Def' ELSE '{NONE}' END AS value FROM w")
    con.execute(f"CREATE OR REPLACE TEMP TABLE fv AS {' UNION ALL '.join(feats)}")
    out["features"] = _t(con, f"""
        WITH g AS (SELECT upos, feature, value, count(*) AS n FROM fv GROUP BY ALL
                   UNION ALL SELECT '{ALL_WORDS}', feature, value, count(*) FROM fv GROUP BY ALL)
        SELECT {c} AS corpus_id, upos, feature, value, n,
               n / sum(n) OVER (PARTITION BY upos, feature) AS share
        FROM g ORDER BY upos, feature, n DESC, value""")

    # ---------------------------------------------------------------- R6 relation types
    out["deprel"] = _t(con, f"""
        SELECT {c} AS corpus_id, deprel, count(*) AS n, count(*) / sum(count(*)) OVER () AS share_tokens,
               count(*) FILTER (WHERE upos IS DISTINCT FROM 'PUNCT') AS n_words,
               count(*) FILTER (WHERE upos IS DISTINCT FROM 'PUNCT')
                 / sum(count(*) FILTER (WHERE upos IS DISTINCT FROM 'PUNCT')) OVER () AS share_words
        FROM tok GROUP BY 2 ORDER BY n DESC, deprel""")
    return out


def reconcile(con: duckdb.DuckDBPyConnection, corpus: str, tables: dict[str, pa.Table], units_expected: int) -> list[str]:
    """Cross-checks of the totals (docs/m6_design.md §4). Returns problems; empty = consistent."""
    p: list[str] = []
    one = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    tokens = one("SELECT count(*) FROM tok")
    words = one("SELECT count(*) FROM w")
    m_rows, m_ids, m_tok, m_words = con.execute(
        "SELECT count(*), count(DISTINCT sent_id), sum(n_words + n_punct), sum(n_words) FROM m").fetchone()
    blank = one("SELECT count(*) FROM w WHERE lemma_blank")

    def eq(name, a, b):
        if a != b:
            p.append(f"{corpus}: {name}: {a} != {b}")

    eq("units in metrics vs units in corpus", m_rows, units_expected)
    eq("unit ids unique", m_ids, m_rows)
    eq("words+punct per unit vs token rows", m_tok, tokens)
    eq("words per unit vs non-punct tokens", m_words, words)
    col = lambda t, name: tables[t].column(name).to_pylist()  # noqa: E731
    eq("word_freq total vs words", sum(col("word_freq", "n")), words)
    eq("lemma_freq total + blank vs words", sum(col("lemma_freq", "n")) + blank, words)
    eq("pos total vs tokens", sum(col("pos", "n")), tokens)
    eq("deprel total vs tokens", sum(col("deprel", "n")), tokens)
    eq("deprel word total vs words", sum(col("deprel", "n_words")), words)
    eq("tree_status units vs units", sum(col("tree_status", "units")), units_expected)
    cov = tables["coverage"].to_pylist()[0]
    eq("coverage words", cov["words"], words)
    eq("status counts sum", sum(cov[k] for k in ("units_empty", "units_parse_error", "units_punctuation_only",
                                                 "units_measured")), units_expected)

    pos_n = {r["upos"]: r["n"] for r in tables["pos"].to_pylist()}
    pos_n[ALL_WORDS] = words
    suffix_n = {}
    totals: dict[tuple[str, str], int] = {}
    for r in tables["features"].to_pylist():
        totals[(r["upos"], r["feature"])] = totals.get((r["upos"], r["feature"]), 0) + r["n"]
        if r["feature"] == "Suffix" and r["value"] != NONE:
            suffix_n[r["upos"]] = suffix_n.get(r["upos"], 0) + r["n"]
        allowed = (WORD_FEATURES.get(r["feature"]) or (SUFFIX_TYPES if r["feature"] == "Suffix" else None)
                   or (WORD_FEATURES.get(r["feature"].split(".")[-1]) if r["feature"].startswith("Suffix.") else None)
                   or ("Def",))
        if r["value"] != NONE and r["value"] not in allowed:
            p.append(f"{corpus}: feature {r['feature']} has a value outside Dicta's label set: {r['value']!r}")
    for (upos, feat), n in totals.items():
        expected = suffix_n.get(upos, 0) if feat.startswith("Suffix.") else pos_n.get(upos)
        eq(f"features {feat} total for {upos}", n, expected)
    return p
