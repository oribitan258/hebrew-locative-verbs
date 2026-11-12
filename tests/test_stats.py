"""M6 statistics (docs/m6_design.md): depth, unit statuses, label set, completeness gate, tables and
reconciliation on handmade data; cross-checks against the pilot when its data is on this computer."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hebloc.paths import ANNOTATIONS_DIR, ROOT, STATS_DIR
from hebloc.stats import compute as C
from hebloc.stats import metrics as M
from hebloc.stats import runset as R
from hebloc.stats import tables as T
from hebloc.stats.accuracy import wilson

# ------------------------------------------------------------------------------------------ depth

def test_node_depths_chain_star_forest():
    assert M.node_depths(np.array([-1, 0, 1, 2])).tolist() == [1, 2, 3, 4]          # chain
    assert M.node_depths(np.array([1, -1, 1, 1])).tolist() == [2, 1, 2, 2]          # star, root in the middle
    assert M.node_depths(np.array([-1, 0, -1, 2, 3])).tolist() == [1, 2, 1, 2, 3]   # two trees
    with pytest.raises(ValueError):
        M.node_depths(np.array([1, 0]))                                              # cycle


def _tok(sid, piece, idx, surface, upos, head, valid=True):
    return {"sent_id": sid, "piece_idx": piece, "word_idx": idx, "surface": surface, "upos": upos,
            "head": head, "piece_tree_valid": valid}


def _units():
    """sid → (pieces, raw statuses, tokens) of handmade units covering every tree status."""
    U = {}
    # depth: V(root) ← N ← PUNCT : words reach level 2; the punctuation leaf (level 3) is ignored
    U["c:d:1:0"] = ([1], ["ok"], [_tok("c:d:1:0", 0, 0, "הלך", "VERB", -1), _tok("c:d:1:0", 0, 1, "איש", "NOUN", 0),
                                   _tok("c:d:1:0", 0, 2, ".", "PUNCT", 1)])
    # chain of 4 words, with a repeated surface (distinct = 3)
    U["c:d:2:0"] = ([1], ["ok"], [_tok("c:d:2:0", 0, 0, "א", "VERB", -1), _tok("c:d:2:0", 0, 1, "ב", "NOUN", 0),
                                   _tok("c:d:2:0", 0, 2, "ב", "NOUN", 1), _tok("c:d:2:0", 0, 3, "ג", "ADJ", 2)])
    # two pieces → no single tree
    U["c:d:3:0"] = ([2], ["ok", "ok"], [_tok("c:d:3:0", 0, 0, "א", "VERB", -1), _tok("c:d:3:0", 1, 0, "ב", "VERB", -1)])
    # invalid word-level tree
    U["c:d:4:0"] = ([1], ["ok"], [_tok("c:d:4:0", 0, 0, "א", "VERB", 1, False), _tok("c:d:4:0", 0, 1, "ב", "NOUN", 0, False)])
    # missing head → treated like an invalid tree
    U["c:d:5:0"] = ([1], ["ok"], [_tok("c:d:5:0", 0, 0, "א", "VERB", -1), _tok("c:d:5:0", 0, 1, "ב", "NOUN", None)])
    # punctuation only
    U["c:d:6:0"] = ([1], ["ok"], [_tok("c:d:6:0", 0, 0, "...", "PUNCT", -1)])
    # a piece with Dicta status error (no tokens)
    U["c:d:7:0"] = ([1], ["error"], [])
    # empty: no pieces at all
    U["c:d:8:0"] = ([], [], [])
    return U


def _frames(U):
    pieces = [{"sent_id": s, "piece_idx": i, "n_pieces": n[0]} for s, (n, _, _) in U.items() for i in range(n[0] if n else 0)]
    raw = [{"sent_id": s, "piece_idx": i, "status": st} for s, (_, sts, _) in U.items() for i, st in enumerate(sts)]
    toks = [t for _, _, ts in U.values() for t in ts]
    return (pd.DataFrame(pieces, columns=["sent_id", "piece_idx", "n_pieces"]),
            pd.DataFrame(raw, columns=["sent_id", "piece_idx", "status"]),
            pd.DataFrame(toks, columns=M.TOKEN_COLUMNS).astype({"head": "Int64"}))


def test_unit_metrics_statuses_lengths_depth():
    U = _units()
    pieces, raw, toks = _frames(U)
    m = M.unit_metrics(list(U), pieces, raw, toks).set_index("sent_id")
    assert m["tree_status"].to_dict() == {
        "c:d:1:0": "complete", "c:d:2:0": "complete", "c:d:3:0": "multi_piece", "c:d:4:0": "invalid_tree",
        "c:d:5:0": "invalid_tree", "c:d:6:0": "no_words", "c:d:7:0": "parse_error", "c:d:8:0": "empty"}
    assert m.loc["c:d:1:0", ["n_words", "n_punct", "depth"]].tolist() == [2, 1, 2]     # punctuation leaf ignored
    assert m.loc["c:d:2:0", ["n_words", "n_distinct_words", "depth"]].tolist() == [4, 3, 4]
    assert m.loc["c:d:3:0", "n_words"] == 2 and pd.isna(m.loc["c:d:3:0", "depth"])
    assert m["depth"].notna().sum() == 2                                                # complete units only
    assert m.loc["c:d:7:0", "n_error_pieces"] == 1 and m.loc["c:d:8:0", "n_pieces"] == 0
    assert set(m["corpus_id"]) == {"c"} and set(m["doc_id"]) == {"d"}
    pa.Table.from_pandas(m.reset_index(), schema=M.UNIT_METRICS_SCHEMA, preserve_index=False)   # schema fits


# ------------------------------------------------------------------------------------------ label set

def _vendored_constants() -> dict:
    src = (ROOT / "src/hebloc/parse/dicta_code/BertForMorphTagging.py").read_text(encoding="utf-8")
    out = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in (
                "ALL_FEATURES", "ALL_SUFFIX_POS", "ALL_POS"):
            out[node.targets[0].id] = ast.literal_eval(node.value)
    return out


def test_feature_label_set_is_dictas_complete_set():
    """R5 must cover every inflection feature Dicta can output (D-046)."""
    v = _vendored_constants()
    assert {name: tuple(x for x in vals if x != "none") for name, vals in v["ALL_FEATURES"]} == T.WORD_FEATURES
    assert tuple(sorted(x for x in v["ALL_SUFFIX_POS"] if x != "none")) == T.SUFFIX_TYPES


# ------------------------------------------------------------------------------------------ tables

def _token_rows():
    base = dict(lemma_blank=False, gender=None, number=None, person=None, tense=None, suffix=None, suffix_feats=None,
                prefix_upos=[], status="ok", piece_idx=0)
    rows = [
        dict(base, sent_id="c:d:1:0", surface="הלך", upos="VERB", lemma="הלך", gender="Masc", number="Sing", person="3",
             tense="Past", deprel="root"),
        dict(base, sent_id="c:d:1:0", surface="הבית", upos="NOUN", lemma="בית", gender="Masc", number="Sing",
             prefix_upos=["DET"], suffix="PRON", suffix_feats="Gender=Masc|Number=Sing|Person=3", deprel="obj"),
        dict(base, sent_id="c:d:1:0", surface=".", upos="PUNCT", lemma=".", deprel="punct"),
        dict(base, sent_id="c:d:2:0", surface="הלך", upos="VERB", lemma="[BLANK]", lemma_blank=True, tense="Past",
             person="1,2,3", deprel="root"),
    ]
    return rows


def _tables(tmp_path: Path, units_expected=2):
    import duckdb

    tok = tmp_path / "tok.parquet"
    pq.write_table(pa.Table.from_pylist(_token_rows()), tok)
    met = tmp_path / "m.parquet"
    pq.write_table(pa.Table.from_pylist([
        dict(sent_id="c:d:1:0", corpus_id="c", doc_id="d", n_words=2, n_punct=1, n_distinct_words=2, n_pieces=1,
             n_error_pieces=0, tree_status="complete", depth=2),
        dict(sent_id="c:d:2:0", corpus_id="c", doc_id="d", n_words=1, n_punct=0, n_distinct_words=1, n_pieces=1,
             n_error_pieces=0, tree_status="complete", depth=1)], schema=M.UNIT_METRICS_SCHEMA), met)
    con = duckdb.connect()
    T.setup(con, "c", [tok], [met])
    tabs = T.corpus_tables(con, "c")
    return con, tabs


def test_corpus_tables_content_and_reconciliation(tmp_path):
    con, tabs = _tables(tmp_path)
    assert T.reconcile(con, "c", tabs, 2) == []
    wf = tabs["word_freq"].to_pylist()
    assert [(r["rank"], r["word"], r["n"]) for r in wf] == [(1, "הלך", 2), (2, "הבית", 1)]   # punctuation excluded
    assert [(r["lemma"], r["n"]) for r in tabs["lemma_freq"].to_pylist()] == [("בית", 1), ("הלך", 1)]  # [BLANK] untyped
    cov = tabs["coverage"].to_pylist()[0]
    assert (cov["words"], cov["punctuation_tokens"], cov["words_lemma_blank"], cov["tokens"]) == (3, 1, 1, 4)
    f = {(r["upos"], r["feature"], r["value"]): r["n"] for r in tabs["features"].to_pylist()}
    assert f[("NOUN", "Definite (DET prefix)", "Def")] == 1
    assert f[("NOUN", "Suffix", "PRON")] == 1 and f[("NOUN", "Suffix.Person", "3")] == 1
    assert f[("VERB", "Person", "1,2,3")] == 1 and f[("VERB", "Tense", "Past")] == 2
    assert f[(T.ALL_WORDS, "Gender", T.NONE)] == 1                                     # the [BLANK] verb
    st = {r["measure"]: r for r in tabs["sentence_stats"].to_pylist()}
    assert st["length"]["mean"] == 1.5 and st["depth"]["max"] == 2 and st["length"]["n_units"] == 2


def test_reconciliation_detects_a_mismatch(tmp_path):
    con, tabs = _tables(tmp_path)
    assert any("units in metrics" in p for p in T.reconcile(con, "c", tabs, 3))


# ------------------------------------------------------------------------------------------ run set gate

def _fake_corpus(tmp_path: Path, n_units=3, parsed=3, checks_ok=True):
    from hebloc.parse.checks import run_fingerprint

    units = tmp_path / "units" / "mikra"
    units.mkdir(parents=True)
    ids = [f"mikra:0123456789ab:{i}:0" for i in range(1, n_units + 1)]
    pq.write_table(pa.table({"sent_id": ids, "in_full_view": [True] * n_units}), units / "part-0.parquet")
    run = tmp_path / "ann" / "mikra" / "runs" / "r1"
    (run / "inputs").mkdir(parents=True)
    (run / "_shards").mkdir()
    pq.write_table(pa.table({"sent_id": ids[:parsed]}), run / "inputs" / "shard-00000.parquet")
    (run / "_shards" / "shard-00000.json").write_text(json.dumps({"key": "k"}), encoding="utf-8")
    (run / "checks.json").write_text(json.dumps({"ok": checks_ok, "fingerprint": run_fingerprint(run)}), encoding="utf-8")
    return tmp_path / "units", tmp_path / "ann"


def test_runset_complete_corpus_is_accepted_and_provisional(tmp_path):
    units, ann = _fake_corpus(tmp_path)
    rs = R.check(R.from_refs(["mikra/r1"], root=ann), units_root=units)
    assert rs.checks["mikra"]["complete"] and rs.status() == "provisional"     # explicit list is never final


def test_runset_refuses_partial_corpus_unless_scale_test(tmp_path):
    units, ann = _fake_corpus(tmp_path, parsed=2)
    with pytest.raises(R.RunSetRefusal, match="2/3 units"):
        R.check(R.from_refs(["mikra/r1"], root=ann), units_root=units)
    rs = R.check(R.from_refs(["mikra/r1"], root=ann), scale_test=True, units_root=units)
    assert not rs.checks["mikra"]["complete"]


def test_runset_refuses_unvalidated_run_and_pilot_runs(tmp_path):
    units, ann = _fake_corpus(tmp_path, checks_ok=False)
    with pytest.raises(R.RunSetRefusal, match="runs not validated"):
        R.check(R.from_refs(["mikra/r1"], root=ann), units_root=units)
    (ann / "pilot" / "runs" / "p").mkdir(parents=True)
    with pytest.raises(R.RunSetRefusal, match="not a corpus run"):
        R.from_refs(["pilot/p"], root=ann)


def test_scale_test_never_writes_into_stats_or_results(tmp_path):
    rs = R.RunSet({"mikra": []}, "explicit", checks={"mikra": {"complete": False, "validations": {}}})
    with pytest.raises(ValueError, match="never writes"):
        C.compute(rs, STATS_DIR / "x", scale_test=True)
    with pytest.raises(ValueError, match="explicit output folder"):
        C.compute(rs, None, scale_test=True)


def test_wilson_interval():
    lo, hi = wilson(0.5, 100)
    assert (lo, hi) == (0.4038, 0.5962)


# ------------------------------------------------------------------------------------------ real data (if present)

PILOT = ANNOTATIONS_DIR / "pilot" / "runs" / "base__default"


@pytest.mark.skipif(not (PILOT / "tokens").exists(), reason="pilot run not on this computer")
def test_depth_matches_pilot_tree_depths():
    """Independent cross-check: node_depths reproduces the M3 recursive tree_depths on every valid
    single-piece pilot piece (counting punctuation, as the pilot did); ignoring punctuation can only
    lower the depth."""
    from hebloc.parse.tokens import read_tokens
    from hebloc.pilot.experiments import tree_depths

    rows = read_tokens(PILOT).to_pylist()
    ref = tree_depths(rows)
    df = pd.DataFrame(rows)
    df = df[(df["n_pieces"] == 1) & df["piece_tree_valid"]].sort_values(["sent_id", "word_idx"])
    checked = 0
    for sid, g in df.groupby("sent_id"):
        d = M.node_depths(g["head"].to_numpy())
        assert int(d.max()) == ref[(sid, 0)]
        words = d[(g["upos"] != "PUNCT").to_numpy()]
        if len(words):
            assert words.max() <= d.max()
        checked += 1
    assert checked > 900
