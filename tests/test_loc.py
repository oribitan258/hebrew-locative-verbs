"""Tests of hebloc.loc (S56-v1 release R1): lexicon, paradigm forms, identification with the ambiguity rule,
DO/PP reading, the deterministic gold sampler (repo == package), the text-free gold check, noun lists/merge."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hebloc.loc import gold as G
from hebloc.loc import identify as ID
from hebloc.loc import lexicon as L
from hebloc.loc import morph
from hebloc.loc import nouns as N
from hebloc.loc import tree as TR
from hebloc.loc.manifest import verify
from hebloc.loc.source import TOKEN_COLUMNS, Source, connect
from hebloc.paths import ROOT

GIT = {"git_commit": "test", "git_tag": None, "git_describe": "test", "dirty": False, "dev_override": False}


# ------------------------------------------------------------------------------------------- real lexicon
def test_real_lexicon_is_valid_and_matches_the_paper():
    lex = L.load()
    assert L.problems(lex) == []
    assert L.count_problems(lex) == []
    c = L.counts(lex)
    assert c["totals"] == {"A": 96, "A/B": 45, "B": 37}            # 96 = the paper's lists (text says 95)
    assert c["stated_totals"] == {"A": 95, "A/B": 45, "B": 37}
    ids = {d["id"] for d in lex.meta["discrepancies"]}
    assert {"simple_A_46_vs_45", "asar_list_A_vs_example_AB"} <= ids
    asar = lex.by_id()["אסר.S"]
    assert asar.klass == "A" and "paper_conflict" in asar.flags
    assert not L.forms_stale(lex), "regenerate: hebloc loc lexicon forms"


def test_real_lexicon_shared_lemmas_are_flagged():
    lex = L.load()
    # שלח: Dicta has no שילח lemma in Mikra -> both templates own שלח, both flagged
    assert "שלח" in lex.by_id()["שלח.I"].own_lemmas and "שלח" in lex.by_id()["שלח.S"].own_lemmas
    assert "template_ambiguous" in lex.by_id()["שלח.I"].flags


# ------------------------------------------------------------------------------------------- paradigm forms
@pytest.mark.parametrize("root,template,expected", [
    ("מלא", "Intensive", {"מילא", "ימלא", "התמלא", "מולא", "ממלא"}),
    ("גלה", "Causative", {"הגלה", "הגלתה", "יגלה", "הוגלה"}),
    ("נתן", "Simple", {"נתן", "יתן", "תת", "לתת", "נתתי", "ניתן"}),
    ("נזה", "Causative", {"הזה", "יזה"}),
    ("שים", "Simple", {"שם", "ישים", "שמתי", "ישם"}),
    ("סתר", "Intensive", {"הסתתר", "יסתתר"}),
])
def test_paradigm_forms(root, template, expected):
    assert expected <= morph.forms(root, template)


def test_no_degenerate_doubly_weak_forms():
    f = morph.forms("נזה", "Causative")
    assert "הזינו" not in f and "אזיין" not in f        # one-consonant stems are not generated


# ------------------------------------------------------------------------------------------- tiny lexicon
LEX_YAML = """
meta: {methodology: S56-v1, stated_counts: {A: 1, A/B: 1, B: 1}, discrepancies: []}
entries:
- {id: שלח.S, root: שלח, template: Simple, citation: שלח, gloss: send, class: A, status: core, putting_removal: UNKNOWN,
   dicta_lemmas: [{lemma: שלח, voice: active}, {lemma: נשלח, voice: passive}], flags: [template_ambiguous]}
- {id: שלח.I, root: שלח, template: Intensive, citation: שילח, gloss: send, class: A/B, status: core, putting_removal: BOTH,
   dicta_lemmas: [{lemma: שלח, voice: active}], flags: [template_ambiguous]}
- {id: צפה.I, root: צפה, template: Intensive, citation: ציפה, gloss: overlay, class: B, status: core, putting_removal: PUTTING,
   dicta_lemmas: [], shared_lemmas: [{lemma: ציפה, other: expect}], flags: [homograph_nonlexicon]}
- {id: מלא.I, root: מלא, template: Intensive, citation: מילא, gloss: fill, class: A/B, status: core, putting_removal: PUTTING,
   dicta_lemmas: [{lemma: מילא, voice: active}, {lemma: מולא, voice: passive}]}
- {id: גלה.C, root: גלה, template: Causative, citation: הגלה, gloss: deport, class: A, status: core, putting_removal: BOTH,
   dicta_lemmas: [], flags: [no_own_lemma]}
"""
FORMS_YAML = "meta: {lexicon_file_sha256: null}\nforms:\n  גלה.C: [הגלה]\n  מלא.I: [ימלא]\n"


#: the samples frozen by the R1 release, captured before the fixture below hides them from the synthetic draws
RELEASED_FROZEN = dict(G.FROZEN_SAMPLES)


@pytest.fixture(autouse=True)
def _no_frozen_samples(monkeypatch):
    """Synthetic lexicons draw other ids: the release freeze is tested explicitly, not on every draw."""
    monkeypatch.setattr(G, "FROZEN_SAMPLES", {})


@pytest.fixture()
def lex(tmp_path):
    (tmp_path / "lex.yaml").write_text(LEX_YAML, encoding="utf-8")
    (tmp_path / "forms.yaml").write_text(FORMS_YAML, encoding="utf-8")
    return L.load(tmp_path / "lex.yaml", tmp_path / "forms.yaml")


def test_unflagged_shared_lemma_is_a_problem(tmp_path):
    (tmp_path / "lex.yaml").write_text(LEX_YAML.replace("flags: [template_ambiguous]}", "flags: []}"), encoding="utf-8")
    lx = L.load(tmp_path / "lex.yaml", tmp_path / "absent.yaml", validate=False)
    assert any("שלח" in p and "flag" in p for p in L.problems(lx))


def test_ambiguity_rule_one_token_one_instance(lex):
    idx = ID.build_index(lex)
    m = ID.identify(idx, "שלח", "וישלח", "VERB")
    assert m["verb_key"] == "שלח.I|שלח.S" and m["members"] == ["שלח.I", "שלח.S"] and m["match_method"] == "lemma"
    m = ID.identify(idx, "ציפה", "ציפה", "VERB")
    assert m["verb_key"] == "צפה.I|~ציפה" and m["tilde"] == ["~ציפה"]          # may be 'expect'
    m = ID.identify(idx, "[BLANK]", "הגלה", "VERB")
    assert m["verb_key"] == "גלה.C" and m["match_method"] == "form"
    m = ID.identify(idx, "מילא", "ימלא", "VERB")
    assert m["match_method"] == "both" and m["voice"] == "active"
    assert ID.identify(idx, "שלח", "שלח", "NOUN") is None                       # VERB only


def test_identify_sql_equals_python(lex):
    rows = [("s:a:1:0", 0, i, lem, host, upos) for i, (lem, host, upos) in enumerate([
        ("שלח", "וישלח", "VERB"), ("ציפה", "ציפה", "VERB"), ("[BLANK]", "הגלה", "VERB"), ("מילא", "ימלא", "VERB"),
        ("שלח", "שלח", "NOUN"), ("אמר", "אמר", "VERB"), ("נשלח", "נשלח", "VERB")])]
    t = pa.table({"sent_id": [r[0] for r in rows], "piece_idx": pa.array([r[1] for r in rows], pa.int16()),
                  "word_idx": pa.array([r[2] for r in rows], pa.int32()), "lemma": [r[3] for r in rows],
                  "host": [r[4] for r in rows], "upos": [r[5] for r in rows]})
    con = connect()
    ID.register(con, lex)
    con.register("t", t)
    got = {r["word_idx"]: r for r in con.sql(ID.identify_sql("t")).to_arrow_table().to_pylist()}
    idx = ID.build_index(lex)
    for r in rows:
        py = ID.identify(idx, r[3], r[4], r[5])
        if py is None:
            assert r[2] not in got
        else:
            g = got[r[2]]
            assert (g["verb_key"], g["match_method"], g["voice"]) == (py["verb_key"], py["match_method"], py["voice"])


# ------------------------------------------------------------------------------------------- trees
def _tok(sid, w, form, lemma, upos, head, deprel, prefix=None, prefix_upos=(), suffix=None, piece=0):
    return {"sent_id": sid, "piece_idx": piece, "n_pieces": 1, "word_idx": w, "sent_word_idx": w, "char_start": 0,
            "char_end": 0, "ws_idx": w, "form": form, "surface": form, "prefix": prefix,
            "host": form[len(prefix or ""):], "lemma": lemma, "lemma_blank": lemma == "[BLANK]", "upos": upos,
            "feats": None, "gender": None, "number": None, "person": None, "tense": None,
            "prefix_upos": list(prefix_upos), "suffix": suffix, "suffix_feats": None, "head": head, "head_sent": head,
            "deprel": deprel, "piece_tree_valid": True}


TREE = [  # מילא את המיכל במים ; הסיר ממנו את העול מעל צווארו ; נשלח מכתב ; ויזרעה מלח
    _tok("x:d:1:0", 0, "מילא", "מילא", "VERB", -1, "root"),
    _tok("x:d:1:0", 1, "את", "את", "ADP", 2, "case:acc"),
    _tok("x:d:1:0", 2, "המיכל", "מיכל", "NOUN", 0, "obj", prefix="ה", prefix_upos=["DET"]),
    _tok("x:d:1:0", 3, "במים", "מים", "NOUN", 0, "obl", prefix="ב", prefix_upos=["ADP"]),
    _tok("x:d:2:0", 0, "הסיר", "הסיר", "VERB", -1, "root"),
    _tok("x:d:2:0", 1, "ממנו", "[BLANK]", "ADP", 0, "obl", suffix="PRON"),
    _tok("x:d:2:0", 2, "את", "את", "ADP", 3, "case:acc"),
    _tok("x:d:2:0", 3, "העול", "עול", "NOUN", 0, "obj", prefix="ה", prefix_upos=["DET"]),
    _tok("x:d:2:0", 4, "מעל", "מעל", "ADP", 5, "case"),
    _tok("x:d:2:0", 5, "צווארו", "צוואר", "NOUN", 0, "obl"),
    _tok("x:d:3:0", 0, "נשלח", "נשלח", "VERB", -1, "root"),
    _tok("x:d:3:0", 1, "מכתב", "מכתב", "NOUN", 0, "nsubj"),
    _tok("x:d:4:0", 0, "ויזרעה", "זרע", "VERB", -1, "root", prefix="ו", prefix_upos=["CCONJ"], suffix="PRON"),
    _tok("x:d:4:0", 1, "מלח", "מלח", "NOUN", 0, "xcomp"),
]


def test_arguments_sql_reads_do_pp_and_bare_np():
    t = pa.Table.from_pylist(TREE)
    con = connect()
    con.register("tok", t)
    v = pa.table({"sent_id": ["x:d:1:0", "x:d:2:0", "x:d:3:0", "x:d:4:0"], "piece_idx": pa.array([0, 0, 0, 0], pa.int16()),
                  "word_idx": pa.array([0, 0, 0, 0], pa.int32()), "suffix": [None, None, None, "PRON"],
                  "voice": ["active", "active", "passive", "active"]})
    con.register("v", v)
    rows = con.sql(TR.arguments_sql("v", "tok")).to_arrow_table().to_pylist()
    got = {(r["sent_id"][4], r["slot"], r["head_lemma"], r["p_exact"], r["p_family"], r["do_kind"]) for r in rows}
    assert ("1", "DO", "מיכל", None, None, "noun") in got
    assert ("1", "PP", "מים", "ב", "B", None) in got
    assert ("2", "PP", "[BLANK]", "מן", "MIN", None) in got          # ממנו
    assert ("2", "PP", "צוואר", "מעל", "MIN", None) in got           # מ+על compound -> MIN (fn 22)
    assert ("2", "DO", "עול", None, None, "noun") in got
    assert ("3", "PASSIVE_SUBJ", "מכתב", None, None, "passive_subject") in got
    assert ("4", "DO", None, None, None, "suffix") in got
    assert ("4", "BARE_NP", "מלח", None, None, None) in got


@pytest.mark.parametrize("p", ["ב", "בתוך", "מ", "מן", "מעל", "מתוך", "מאת", "מעם", "מיד", "מקרב", "על", "אל", "ל", "עם", "תחת", "כ"])
def test_p_family_sql_equals_python(p):
    con = connect()
    assert con.execute(f"SELECT {TR.p_family_sql(repr(p))}").fetchone()[0] == TR.p_family(p)


# ------------------------------------------------------------------------------------------- repo & package
def _corpus_tokens(n_units: int = 60) -> list[dict]:
    """Synthetic 'mikra': each unit has one verb (cycling through lexicon verbs and a non-lexicon one)."""
    verbs = [("שלח", "וישלח"), ("מילא", "ימלא"), ("[BLANK]", "הגלה"), ("ציפה", "ציפה"), ("אמר", "אמר")]
    rows = []
    for i in range(n_units):
        sid = f"mikra:d{(i % 3):011d}:{i + 1}:0"
        lem, host = verbs[i % len(verbs)]
        rows.append(_tok(sid, 0, host, lem, "VERB", -1, "root"))
        rows.append(_tok(sid, 1, "את", "את", "ADP", 2, "case:acc"))
        rows.append(_tok(sid, 2, "הבית", "בית", "NOUN", 0, "obj", prefix="ה", prefix_upos=["DET"]))
        rows.append(_tok(sid, 3, "במים", "מים", "NOUN", 0, "obl", prefix="ב", prefix_upos=["ADP"]))
    return rows


def _units(rows: list[dict]) -> pa.Table:
    sids = sorted({r["sent_id"] for r in rows})
    text = {sid: " ".join(r["surface"] for r in rows if r["sent_id"] == sid) for sid in sids}
    return pa.table({"sent_id": sids, "corpus_id": ["mikra"] * len(sids), "doc_id": [s.split(":")[1] for s in sids],
                     "ref": [f"Genesis 1:{i + 1}" for i in range(len(sids))], "text_norm": [text[s] for s in sids],
                     "stratum": ["mikra.torah"] * len(sids), "in_full_view": [True] * len(sids),
                     "in_curated_view": [True] * len(sids), "is_empty_norm": [False] * len(sids)})


def _with_offsets(rows):
    by = {}
    for r in rows:
        by.setdefault(r["sent_id"], []).append(r)
    for rs in by.values():
        pos = 0
        for r in sorted(rs, key=lambda r: r["word_idx"]):
            r["char_start"], r["char_end"] = pos, pos + len(r["surface"])
            pos = r["char_end"] + 1
    return rows


@pytest.fixture()
def world(tmp_path):
    rows = _with_offsets(_corpus_tokens())
    docs = pa.table({"doc_id": sorted({r["sent_id"].split(":")[1] for r in rows}), "corpus_id": ["mikra"] * 3,
                     "subcorpus": [None] * 3, "source": [None] * 3, "stratum": ["mikra.torah"] * 3,
                     "in_full_view": [True] * 3, "in_curated_view": [True] * 3})
    units = _units(rows)
    # repo layout: two runs? one run with two shards
    ann = tmp_path / "ann"
    run = ann / "mikra" / "runs" / "r1"
    half = len(rows) // 2
    for k, part in enumerate((rows[:half], rows[half:])):
        (run / "_shards").mkdir(parents=True, exist_ok=True)
        (run / "_shards" / f"shard-0000{k}.json").write_text(json.dumps({"key": k}), encoding="utf-8")
        (run / "tokens").mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(part, schema=None).select(list(TOKEN_COLUMNS)), run / "tokens" / f"shard-0000{k}.parquet")
    reg = tmp_path / "annotations.yaml"
    reg.write_text("canonical:\n  mikra: [mikra/r1]\n", encoding="utf-8")
    (tmp_path / "units" / "mikra").mkdir(parents=True)
    pq.write_table(units, tmp_path / "units" / "mikra" / "part-00000.parquet")
    pq.write_table(docs, tmp_path / "documents.parquet")
    repo = Source.repo(annotations_root=ann, registry=reg, units_root=tmp_path / "units", documents=tmp_path / "documents.parquet")
    # package layout: one file per run with shard/corpus_id/doc_id columns, rows in a different order
    pkg = tmp_path / "pkg"
    (pkg / "data" / "tokens" / "mikra").mkdir(parents=True)
    ptab = []
    for k, part in enumerate((rows[:half], rows[half:])):
        for r in part:
            ptab.append({**{c: r[c] for c in TOKEN_COLUMNS}, "corpus_id": "mikra", "doc_id": r["sent_id"].split(":")[1],
                         "shard": f"shard-0000{k}"})
    pq.write_table(pa.Table.from_pylist(list(reversed(ptab))), pkg / "data" / "tokens" / "mikra" / "r1.parquet")
    (pkg / "data" / "sentences" / "mikra").mkdir(parents=True)
    pq.write_table(units, pkg / "data" / "sentences" / "mikra" / "part-00000.parquet")
    pq.write_table(docs, pkg / "data" / "documents.parquet")
    (pkg / "VERIFICATION.json").write_text('{"ok": true}', encoding="utf-8")
    return {"repo": repo, "package": Source.from_package(pkg), "tmp": tmp_path}


@pytest.fixture()
def small_design(monkeypatch):
    monkeypatch.setitem(G.DESIGN, "mikra", {"core": 40, "mh": 0, "nonpaper": 0, "test_only": False})
    monkeypatch.setattr(G, "CAP_PER_KEY", 5)
    monkeypatch.setattr(G, "AGREEMENT", {"dev": 1, "validation": 1, "test": 2})


def test_gold_sampler_is_deterministic_and_source_independent(world, lex, small_design):
    from hebloc.store.io import file_sha256

    a = G.draw("mikra", world["repo"], lex, out_root=world["tmp"] / "g1", git=GIT, progress=False)
    b = G.draw("mikra", world["package"], lex, out_root=world["tmp"] / "g2", git=GIT, progress=False)
    c = G.draw("mikra", world["repo"], lex, out_root=world["tmp"] / "g3", git=GIT, progress=False)
    assert a["sample_id"] == b["sample_id"] == c["sample_id"]
    for f in ("sample.parquet", "sample.csv", "population.parquet", "sheets/dev.csv", "sheets/test.csv"):
        h = {file_sha256(world["tmp"] / g / "mikra" / a["sample_id"] / f) for g in ("g1", "g2", "g3")}
        assert len(h) == 1, f
    s = pq.read_table(world["tmp"] / "g1" / "mikra" / a["sample_id"] / "sample.parquet").to_pylist()
    # each token at most once; combined key for שלח; cap per key respected
    assert len({x["instance_key"] for x in s}) == len(s)
    assert all(x["verb_key"] != "שלח.S" and x["verb_key"] != "שלח.I" for x in s)
    from collections import Counter

    assert max(Counter(x["cap_key"] for x in s).values()) <= 5
    assert {x["split"] for x in s} <= {"dev", "validation", "test"}
    assert a["shortfall"]                                   # the tiny corpus cannot fill the design: recorded
    assert verify(world["tmp"] / "g1" / "mikra" / a["sample_id"]) == []


def test_gold_check_writes_text_free_files(world, lex, small_design):
    m = G.draw("mikra", world["repo"], lex, out_root=world["tmp"] / "g", git=GIT, progress=False)
    sdir = world["tmp"] / "g" / "mikra" / m["sample_id"]
    sheet = sdir / "sheets" / "dev.csv"
    with open(sheet, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r.update({"is_target_verb": "Y", "locative": "Y", "frame": "B", "do": "2", "pps": "3:ב", "locatum": "3", "location": "2"})
    rows[0]["do"] = "99"                                     # out of range -> problem
    with open(sheet, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    bad = G.check_sheet(sheet, sdir, "tester", world["tmp"] / "out")
    assert not bad["ok"] and any("do must be" in p for p in bad["problems"])
    rows[0]["do"] = "2"
    with open(sheet, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    ok = G.check_sheet(sheet, sdir, "tester", world["tmp"] / "out")
    assert ok["ok"] and ok["written"]
    header = Path(ok["written"][0]).read_text(encoding="utf-8-sig").splitlines()[0]
    for text_col in ("sentence", "words", "target", "notes"):
        assert f'"{text_col}"' not in header and f",{text_col}," not in header


def test_noun_list_and_merge(world, lex, tmp_path, monkeypatch):
    monkeypatch.setattr(N, "NOUN_TYPES_PATH", tmp_path / "noun_types.yaml")
    m = N.list_nouns("mikra", world["repo"], lex, out_root=tmp_path / "n", git=GIT, progress=False)
    assert m["n_to_label"] >= 2                                  # בית (DO), מים (PP)
    out = tmp_path / "reviewed.csv"
    out.write_text("lemma,type,proposed_by,reviewed_by,note,corpus_source\nבית,LOCATION,claude_code,claude_code,,mikra\n", encoding="utf-8")
    assert not N.merge(out, tmp_path / "noun_types.yaml")["ok"]  # a machine is not a reviewer
    out.write_text("lemma,type,proposed_by,reviewed_by,note,corpus_source\nבית,LOCATION,claude_code,ori,,mikra\nמים,LOCATUM,human,ori,,mikra\n", encoding="utf-8")
    r = N.merge(out, tmp_path / "noun_types.yaml")
    assert r["ok"] and r["total"] == 2
    assert N.load_types(tmp_path / "noun_types.yaml")["בית"]["type"] == "LOCATION"


# ------------------------------------------------------------------------------------------- hygiene
def test_annotation_gold_files_have_no_corpus_text():
    for f in (ROOT / "annotation" / "gold").glob("*.csv"):
        header = f.read_text(encoding="utf-8-sig").splitlines()[0]
        cols = {c.strip('"') for c in header.split(",")}
        assert not cols & {"sentence", "words", "target", "notes", "text", "text_norm"}, f


# ------------------------------------------------------------------------------------------- R1 correction (2026-11-20)
@pytest.mark.parametrize("root,template,form,present", [
    ("ספן", "Simple", "יספו", False), ("ספן", "Simple", "תסף", False),       # final nun only assimilates in the perfect
    ("שכן", "Simple", "ישכם", False), ("שים", "Simple", "ישמן", False),       # no rare ן object suffix
    ("נתן", "Simple", "נתתי", True), ("נתן", "Simple", "יתן", True), ("נתן", "Simple", "תת", True),
    ("נפל", "Simple", "יפל", True), ("נפל", "Simple", "נפלתי", True),
    ("נפל", "Causative", "הפיל", True), ("יצא", "Causative", "הוציא", True),
    ("קום", "Causative", "הקים", True), ("קום", "Simple", "יקים", False),      # hollow ו/י swap only in the causative
    ("שכם", "Causative", "ישכימו", True), ("שוך", "Simple", "ישכימו", False),  # no י- prefix with the 2fs -י ending
])
def test_morph_v2_regressions(root, template, form, present):
    assert (form in morph.forms(root, template)) is present
    assert morph.MORPH_VERSION == "morph-v2"


def test_neutral_and_inflected_lemmas():
    est = {"שתה", "שמתי", "וישם", "מת"}
    assert L.neutral_lemma("[BLANK]", "שמת", est) and L.neutral_lemma("##בס", "יכבס", est)
    assert L.neutral_lemma("רר", "שמת", est)                                  # not established: neutral
    assert L.neutral_lemma("שמתי", "שמתי", est, self_share=0.9)               # Dicta copied the word
    assert not L.neutral_lemma("שתה", "שתה", est, self_share=0.2)            # a real lemma spread over many words
    assert not L.neutral_lemma("מת", "שמת", est)                              # another verb
    assert L.looks_inflected("שמתי") and L.looks_inflected("וישם", {"ישם"})
    assert not L.looks_inflected("שתה", {"שתה"})                              # ש + a non-form is not a proclitic


def _inv(rows):
    return pa.table({"lemma": [r[0] for r in rows], "host": [r[1] for r in rows], "n": pa.array([r[2] for r in rows], pa.int64()),
                     "corpus": ["mikra"] * len(rows)})


ZONES_INV = [
    ("זרק", "זרק", 30), ("זרק", "יזרק", 20), ("זרק", "זורק", 10),          # an established competing verb
    ("מילא", "מילאו", 10),                                                  # clean
    ("[BLANK]", "מלאתי", 7), ("זרק", "מלאתי", 3),                           # 30% foreign -> ambiguous ~זרק
    ("[BLANK]", "ממלא", 2), ("זרק", "ממלא", 8),                             # 80% foreign -> dropped
    ("[BLANK]", "יגלה", 5),                                                 # causative = Simple shape -> ~גלה.S
    ("מילא", "קקקק", 6), ("[BLANK]", "קקקק", 2),                            # off-paradigm, strong support -> kept
    ("מילא", "ימליכו", 4), ("[BLANK]", "ימליכו", 20),                       # off-paradigm, weak support -> not a form
]


def test_forms_v2_zones_partners_and_offparadigm(lex):
    r = L.build_forms(lex, _inv(ZONES_INV), generated="all")
    f, a = r["forms"], r["ambiguous"]
    assert "מילאו" in f["מלא.I"] and "מילאו" not in a.get("מלא.I", {})
    assert a["מלא.I"]["מלאתי"] == ["~זרק", "~מלא.S"]              # also a qal form (no Simple entry)
    assert "ממלא" not in f["מלא.I"] and any(d["host"] == "ממלא" for d in r["dropped"])
    assert a["גלה.C"]["יגלה"] == ["~גלה.S"]
    assert "קקקק" in f["מלא.I"] and "ימליכו" not in f["מלא.I"]


def test_forms_v2_fallback_policy(lex):
    """The pre-registered fallback: generated forms only for entries without a Dicta lemma, always ~form."""
    assert L.FORMS_GENERATED_POLICY == "no_own_lemma"
    r = L.build_forms(lex, _inv(ZONES_INV))
    f, a = r["forms"], r["ambiguous"]
    assert "מלאתי" not in f["מלא.I"] and "מילאו" in f["מלא.I"] and "קקקק" in f["מלא.I"]   # own lemma: attested only
    assert "יגלה" in f["גלה.C"] and "~form" in a["גלה.C"]["יגלה"]                        # no own lemma: generated, ~form
    assert all("~form" in p for p in a["גלה.C"].values())


AMB_FORMS = ("meta: {lexicon_file_sha256: null}\nforms:\n  גלה.C: [הגלה, יגלה]\n  מלא.I: [ימלא, מלאתי]\n"
             "ambiguous:\n  גלה.C: {יגלה: ['~גלה.S']}\n  מלא.I: {מלאתי: ['~זרק']}\n")


def test_form_partners_only_on_form_only_matches(tmp_path):
    (tmp_path / "lex.yaml").write_text(LEX_YAML, encoding="utf-8")
    (tmp_path / "forms.yaml").write_text(AMB_FORMS, encoding="utf-8")
    lx = L.load(tmp_path / "lex.yaml", tmp_path / "forms.yaml")
    idx = ID.build_index(lx)
    m = ID.identify(idx, "[BLANK]", "יגלה", "VERB")
    assert m["verb_key"] == "גלה.C|~גלה.S" and m["match_method"] == "form"     # kept, never dropped
    assert ID.identify(idx, "מילא", "מלאתי", "VERB")["tilde"] == []             # Dicta's own lemma: no partner
    assert ID.identify(idx, "[BLANK]", "מלאתי", "VERB")["verb_key"] == "מלא.I|~זרק"
    rows = [("s:a:1:0", 0, i, lem, host, "VERB") for i, (lem, host) in enumerate([
        ("[BLANK]", "יגלה"), ("מילא", "מלאתי"), ("[BLANK]", "מלאתי"), ("[BLANK]", "הגלה"), ("ציפה", "ציפה"), ("שלח", "וישלח")])]
    t = pa.table({"sent_id": [r[0] for r in rows], "piece_idx": pa.array([r[1] for r in rows], pa.int16()),
                  "word_idx": pa.array([r[2] for r in rows], pa.int32()), "lemma": [r[3] for r in rows],
                  "host": [r[4] for r in rows], "upos": [r[5] for r in rows]})
    con = connect()
    ID.register(con, lx)
    con.register("t", t)
    got = {r["word_idx"]: r for r in con.sql(ID.identify_sql("t")).to_arrow_table().to_pylist()}
    for r in rows:
        py = ID.identify(idx, r[3], r[4], r[5])
        g = got[r[2]]
        assert (g["verb_key"], g["match_method"], list(g["tilde"])) == (py["verb_key"], py["match_method"], py["tilde"])


def test_gold_r1b_homograph_stratum_weights_and_redraw_record(world, lex, small_design):
    m = G.draw("mikra", world["repo"], lex, out_root=world["tmp"] / "g", git=GIT, progress=False)
    assert m["sample_id"].startswith("mikra-r1b-") and m["sampler_version"] == "gold-r1b"
    assert m["supersedes"] == G.SUPERSEDES["mikra"] and m["redraw_reason"]
    assert m["allocation"]["HOMOGRAPH"] == round(40 * G.HOMOGRAPH_MAX_SHARE)    # its share (25%) is capped at 10%
    s = pq.read_table(world["tmp"] / "g" / "mikra" / m["sample_id"] / "sample.parquet").to_pylist()
    homo = [x for x in s if x["stratum"] == "HOMOGRAPH"]
    assert homo and all("~" in x["verb_key"] for x in homo) and len(homo) <= G.HOMOGRAPH_CAP_PER_KEY
    assert not any("~" in x["verb_key"] for x in s if x["stratum"] in G.CORE_STRATA)
    for st, ratio in m["weight_check"].items():                                # sum of 1/pi = population
        assert abs(ratio - 1) < 1e-9, st
    assert all(abs(x["weight_ht"] * x["pi"] - 1) < 1e-12 for x in s)


def test_frozen_sample_cannot_be_redrawn(world, lex, small_design, monkeypatch):
    monkeypatch.setattr(G, "FROZEN_SAMPLES", {"mikra": {"sample_id": "mikra-r1b-0000000000", "sha256": "x"}})
    with pytest.raises(G.GoldError, match="frozen"):
        G.draw("mikra", world["repo"], lex, out_root=world["tmp"] / "g", git=GIT, progress=False)
    m = G.draw("mikra", world["repo"], lex, out_root=world["tmp"] / "g", git=GIT, progress=False, dev=True)
    assert m["sample_id"] != "mikra-r1b-0000000000"


def test_frozen_sample_items_must_match(world, lex, small_design, monkeypatch):
    """Same id but different items (e.g. other data) is refused; identical items pass and are recorded."""
    monkeypatch.setattr(G, "FROZEN_SAMPLES", {})
    m = G.draw("mikra", world["repo"], lex, out_root=world["tmp"] / "g1", git=GIT, progress=False)
    sid, fp = m["sample_id"], m["items_sha256"]
    monkeypatch.setattr(G, "FROZEN_SAMPLES", {"mikra": {"sample_id": sid, "items_sha256": "0" * 64, "sample_sha256": "x"}})
    with pytest.raises(G.GoldError, match="different items"):
        G.draw("mikra", world["repo"], lex, out_root=world["tmp"] / "g2", git=GIT, progress=False)
    assert not (world["tmp"] / "g2" / "mikra" / sid / "manifest.json").exists()
    monkeypatch.setattr(G, "FROZEN_SAMPLES", {"mikra": {"sample_id": sid, "items_sha256": fp, "sample_sha256": "x"}})
    m3 = G.draw("mikra", world["repo"], lex, out_root=world["tmp"] / "g3", git=GIT, progress=False)
    assert m3["frozen_check"] == {"items_match": True, "sample_file_matches": False}


def test_release_freezes_the_r1b_samples():
    assert RELEASED_FROZEN["mikra"]["sample_id"] == "mikra-r1b-1cd4ee9802"
    assert RELEASED_FROZEN["modern"]["sample_id"] == "modern-r1b-5fbb5e22e7"
    assert all(len(v["items_sha256"]) == 64 for v in RELEASED_FROZEN.values())


def test_bhsa_eval_on_synthetic_aligned_verses(world, lex, monkeypatch):
    from hebloc.loc import bhsa_eval as BE
    from hebloc.pilot import experiments as EX

    lexes = {"וישלח": ("שלח", "qal"), "ימלא": ("מלא", "piel"), "הגלה": ("גלה", "hif"), "ציפה": ("צפה", "qal"),
             "אמר": ("אמר", "qal")}
    con = connect()
    toks: dict[str, list[str]] = {}
    for run in world["repo"].runs("mikra"):
        q = f"SELECT sent_id, surface FROM {world['repo'].tokens_sql(run, ('sent_id', 'surface', 'word_idx'))} ORDER BY sent_id, word_idx"
        for sid, surface in con.sql(q).fetchall():
            toks.setdefault(sid, []).append(surface)
    words, w = {}, 0
    for sid, ref in con.sql(f"SELECT sent_id, ref FROM {world['repo'].units_sql('mikra', ('sent_id', 'ref'))}").fetchall():
        ws = []
        for s in toks[sid]:
            w += 1
            lx, vs = lexes.get(s, (s, None))
            ws.append({"w": w, "g_cons_utf8": s, "trailer_utf8": " ", "qere_utf8": None, "qere_trailer_utf8": None,
                       "sp": "verb" if vs else "subs", "language": "Hebrew", "lex_utf8": lx, "vs": vs})
        words[ref] = ws
    monkeypatch.setattr(EX, "_bhsa_index", lambda: words)
    monkeypatch.setattr(Source, "repo", classmethod(lambda cls, **k: world["repo"]))
    mapping = {"שלח.S": {"שלח"}, "שלח.I": {"שלח"}, "מלא.I": {"מלא"}, "גלה.C": {"גלה"}, "צפה.I": {"צפה"}}
    r = BE.evaluate(lex, mapping, set(), progress=False)
    assert r["counts"]["truth"] == 36 and r["recall"] == 1.0                # שלח (qal), מלא (piel), גלה (hif); 12 each
    assert r["precision"] == 0.75                                           # ציפה qal 'watch' is not צפה.I (Intensive)
    assert r["breakdown"]["origin:generated|kind:clean"]["precision"] == 1.0  # הגלה, form only
    keep = {"f1": 0.9, "breakdown": {"origin:generated|kind:clean": {"precision": 0.85, "identified": 10}}}
    assert BE.decide(keep, {"f1": 0.88})["keep_generated_forms"]
    low = {"f1": 0.9, "breakdown": {"origin:generated|kind:clean": {"precision": 0.7, "identified": 10}}}
    assert not BE.decide(low, {"f1": 0.88})["keep_generated_forms"]
    assert not BE.decide(keep, {"f1": 0.95})["keep_generated_forms"]
