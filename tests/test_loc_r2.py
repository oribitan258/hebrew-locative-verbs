"""Tests of the R2 code built in Phase B (S56-v1; D-059): verb units and function predicates, the extractor (lexicon
mode = a filter of all-verbs rows; repo = package; determinism), the resolver (every rule; rule zero by permutation),
classes and identity, the exposure-protected scoring, the final-test lock, and the supplemental sampler."""

from __future__ import annotations

import csv
import json
import random
import shutil
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hebloc.loc import classify as C
from hebloc.loc import extract as X
from hebloc.loc import gold as G
from hebloc.loc import lexicon as L
from hebloc.loc import resolve as R
from hebloc.loc import score as S
from hebloc.loc import units as U
from hebloc.loc.manifest import table_of, verify
from hebloc.loc.source import TOKEN_COLUMNS, Source
from hebloc.parse.tokens import TOKENS_SCHEMA
from hebloc.store.io import file_sha256

TSCHEMA = pa.schema([TOKENS_SCHEMA.field(c) for c in TOKEN_COLUMNS])
GIT = {"git_commit": "test", "git_tag": None, "git_describe": "test", "dirty": False, "dev_override": False}


@pytest.fixture(autouse=True)
def _empty_supplement_registry(monkeypatch):
    """The synthetic worlds start with no registered supplement (the real registry, G3 / D-068 / D-069, would refuse a
    synthetic s1 and make the screen look for its sample); tests that need entries set them."""
    monkeypatch.setattr(G, "FROZEN_SUPPLEMENTS", {})

LEX_YAML = """
meta: {methodology: S56-v1, stated_counts: {A: 1, A/B: 1, B: 1}, discrepancies: []}
entries:
- {id: שלח.S, root: שלח, template: Simple, citation: שלח, gloss: send, class: A, status: core, putting_removal: UNKNOWN,
   dicta_lemmas: [{lemma: שלח, voice: active}, {lemma: נשלח, voice: passive}], flags: [template_ambiguous],
   nonlocative_idioms: [{noun: יד, note: "שלח יד"}]}
- {id: שלח.I, root: שלח, template: Intensive, citation: שילח, gloss: send, class: A/B, status: core, putting_removal: BOTH,
   dicta_lemmas: [{lemma: שלח, voice: active}], flags: [template_ambiguous]}
- {id: מלא.I, root: מלא, template: Intensive, citation: מילא, gloss: fill, class: A/B, status: core, putting_removal: PUTTING,
   dicta_lemmas: [{lemma: מילא, voice: active}, {lemma: מולא, voice: passive}]}
"""
FORMS_YAML = "meta: {lexicon_file_sha256: null}\nforms:\n  מלא.I: [ימלא]\n"
FUNC_YAML = """meta: {status: proposed}
classes:
  EXISTENTIAL: [יש]
  MODAL_IMPERSONAL: [צריך]
pending: []
"""
TYPES_YAML = """nouns:
- {lemma: מיכל, type: LOCATION, reviewed_by: test}
- {lemma: מים, type: LOCATUM, reviewed_by: test}
- {lemma: ספר, type: LOCATUM, reviewed_by: test}
- {lemma: עיר, type: LOCATION, reviewed_by: test}
- {lemma: בית, type: LOCATION, reviewed_by: test}
- {lemma: איש, type: ANIMATE, reviewed_by: test}
- {lemma: דם, type: LOCATUM, reviewed_by: test}
"""


def _tok(sid, w, form, lemma, upos, head, deprel, prefix=None, prefix_upos=(), suffix=None, suffix_feats=None,
         gender=None, number=None, person=None, tense=None):
    return {"sent_id": sid, "piece_idx": 0, "n_pieces": 1, "word_idx": w, "sent_word_idx": w, "char_start": 0,
            "char_end": 0, "ws_idx": w, "form": form, "surface": form, "prefix": prefix,
            "host": form[len(prefix or ""):], "lemma": lemma, "lemma_blank": lemma == "[BLANK]", "upos": upos,
            "feats": None, "gender": gender, "number": number, "person": person, "tense": tense,
            "prefix_upos": list(prefix_upos), "suffix": suffix, "suffix_feats": suffix_feats, "head": head,
            "head_sent": head, "deprel": deprel, "piece_tree_valid": True}


def _sentences() -> list[list[dict]]:
    """One case per unit (doc d0 has units 1..12 in order; unit 9 follows unit 8 for the antecedent)."""
    S_ = []
    # 1 מילא את המיכל במים: DO LOCATION + PP LOCATUM -> B
    S_.append([("מילא", "מילא", "VERB", -1, "root", {}), ("את", "את", "ADP", 2, "case:acc", {}),
               ("המיכל", "מיכל", "NOUN", 0, "obj", {"prefix": "ה", "prefix_upos": ["DET"]}),
               ("במים", "מים", "NOUN", 0, "obl", {"prefix": "ב", "prefix_upos": ["ADP"]})])
    # 2 שלח את הספר אל העיר: DO LOCATUM + PP LOCATION -> A
    S_.append([("שלח", "שלח", "VERB", -1, "root", {}), ("את", "את", "ADP", 2, "case:acc", {}),
               ("הספר", "ספר", "NOUN", 0, "obj", {"prefix": "ה", "prefix_upos": ["DET"]}),
               ("אל", "אל", "ADP", 4, "case", {}), ("העיר", "עיר", "NOUN", 0, "obl", {"prefix": "ה", "prefix_upos": ["DET"]})])
    # 3 נשלח מכתב: passive lexicon lemma -> PASSIVE_SUBJ
    S_.append([("נשלח", "נשלח", "VERB", -1, "root", {}), ("מכתב", "מכתב", "NOUN", 0, "nsubj", {})])
    # 4 רואה את הבית (participle lemma) ; 5 ראה את הבית (finite)
    S_.append([("רואה", "רואה", "VERB", -1, "root", {"tense": "Pres", "gender": "Masc", "number": "Sing"}),
               ("את", "את", "ADP", 2, "case:acc", {}), ("הבית", "בית", "NOUN", 0, "obj", {"prefix": "ה", "prefix_upos": ["DET"]})])
    S_.append([("ראה", "ראה", "VERB", -1, "root", {"tense": "Past"}), ("את", "את", "ADP", 2, "case:acc", {}),
               ("הבית", "בית", "NOUN", 0, "obj", {"prefix": "ה", "prefix_upos": ["DET"]})])
    # 6 יש ללכת: existential with a clausal complement -> function_use
    S_.append([("יש", "יש", "VERB", -1, "root", {}), ("ללכת", "הלך", "VERB", 0, "xcomp", {})])
    # 7 צריך כסף: a lexical use (an object) -> NOT function_use
    S_.append([("צריך", "צריך", "VERB", -1, "root", {}), ("כסף", "כסף", "NOUN", 0, "obj", {})])
    # 8 האיש בא  ; 9 ושלחו אל העיר (object suffix, antecedent איש)
    S_.append([("האיש", "איש", "NOUN", 1, "nsubj", {"prefix": "ה", "prefix_upos": ["DET"], "gender": "Masc", "number": "Sing"}),
               ("בא", "בא", "VERB", -1, "root", {})])
    S_.append([("ושלחו", "שלח", "VERB", -1, "root", {"prefix": "ו", "prefix_upos": ["CCONJ"], "suffix": "PRON",
                                                      "suffix_feats": "Gender=Masc|Number=Sing|Person=3"}),
               ("אל", "אל", "ADP", 2, "case", {}), ("העיר", "עיר", "NOUN", 0, "obl", {"prefix": "ה", "prefix_upos": ["DET"]})])
    # 10 מילא מן הדם: partitive (no DO, one MIN phrase) -> A ; 11 מילא מן הבית: LOCATION -> elided object
    S_.append([("מילא", "מילא", "VERB", -1, "root", {}), ("מן", "מן", "ADP", 2, "case", {}),
               ("הדם", "דם", "NOUN", 0, "obl", {"prefix": "ה", "prefix_upos": ["DET"]})])
    S_.append([("מילא", "מילא", "VERB", -1, "root", {}), ("מן", "מן", "ADP", 2, "case", {}),
               ("הבית", "בית", "NOUN", 0, "obl", {"prefix": "ה", "prefix_upos": ["DET"]})])
    # 12 שלח את הספר אל העיר אל הבית: two typed PPs -> AMBIGUOUS
    S_.append([("שלח", "שלח", "VERB", -1, "root", {}), ("את", "את", "ADP", 2, "case:acc", {}),
               ("הספר", "ספר", "NOUN", 0, "obj", {"prefix": "ה", "prefix_upos": ["DET"]}),
               ("אל", "אל", "ADP", 4, "case", {}), ("העיר", "עיר", "NOUN", 0, "obl", {"prefix": "ה", "prefix_upos": ["DET"]}),
               ("אל", "אל", "ADP", 6, "case", {}), ("הבית", "בית", "NOUN", 0, "obl", {"prefix": "ה", "prefix_upos": ["DET"]})])
    # 13 שלח יד: a listed idiom -> NON_LOCATIVE ; 14 מילא את המיכל מים: DO + indefinite bare NP -> B
    S_.append([("שלח", "שלח", "VERB", -1, "root", {}), ("יד", "יד", "NOUN", 0, "obj", {})])
    S_.append([("מילא", "מילא", "VERB", -1, "root", {}), ("את", "את", "ADP", 2, "case:acc", {}),
               ("המיכל", "מיכל", "NOUN", 0, "obj", {"prefix": "ה", "prefix_upos": ["DET"]}), ("מים", "מים", "NOUN", 0, "xcomp", {})])
    return S_


def _rows() -> list[dict]:
    rows = []
    for u, sent in enumerate(_sentences(), 1):
        sid = f"mikra:d0:{u}:0"
        pos = 0
        for w, (form, lemma, upos, head, deprel, kw) in enumerate(sent):
            t = _tok(sid, w, form, lemma, upos, head, deprel, **{k: v for k, v in kw.items()})
            t["char_start"], t["char_end"] = pos, pos + len(form)
            pos += len(form) + 1
            rows.append(t)
    return rows


@pytest.fixture()
def r2world(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "FROZEN_SAMPLES", {})
    (tmp_path / "lex.yaml").write_text(LEX_YAML, encoding="utf-8")
    (tmp_path / "forms.yaml").write_text(FORMS_YAML, encoding="utf-8")
    (tmp_path / "func.yaml").write_text(FUNC_YAML, encoding="utf-8")
    (tmp_path / "types.yaml").write_text(TYPES_YAML, encoding="utf-8")
    lex = L.load(tmp_path / "lex.yaml", tmp_path / "forms.yaml")
    rows = _rows()
    sids = sorted({r["sent_id"] for r in rows}, key=lambda s: int(s.split(":")[2]))
    text = {sid: " ".join(r["surface"] for r in rows if r["sent_id"] == sid) for sid in sids}
    units = pa.table({"sent_id": sids, "corpus_id": ["mikra"] * len(sids), "doc_id": ["d0"] * len(sids),
                      "ref": [f"Genesis 1:{i + 1}" for i in range(len(sids))], "text_norm": [text[s] for s in sids],
                      "stratum": ["mikra.torah"] * len(sids), "in_full_view": [True] * len(sids),
                      "in_curated_view": [i % 2 == 0 for i in range(len(sids))], "is_empty_norm": [False] * len(sids)})
    docs = pa.table({"doc_id": ["d0"], "corpus_id": ["mikra"], "subcorpus": ["torah"], "source": [None], "stratum": ["mikra.torah"],
                     "in_full_view": [True], "in_curated_view": [True]})
    ann = tmp_path / "ann"
    run = ann / "mikra" / "runs" / "r1"
    half = len(rows) // 2
    for k, part in enumerate((rows[:half], rows[half:])):
        (run / "_shards").mkdir(parents=True, exist_ok=True)
        (run / "_shards" / f"shard-0000{k}.json").write_text(json.dumps({"key": k}), encoding="utf-8")
        (run / "tokens").mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist([{c: r[c] for c in TOKEN_COLUMNS} for r in part], schema=TSCHEMA),
                       run / "tokens" / f"shard-0000{k}.parquet")
    reg = tmp_path / "annotations.yaml"
    reg.write_text("canonical:\n  mikra: [mikra/r1]\n", encoding="utf-8")
    (tmp_path / "units" / "mikra").mkdir(parents=True)
    pq.write_table(units, tmp_path / "units" / "mikra" / "part-00000.parquet")
    pq.write_table(docs, tmp_path / "documents.parquet")
    repo = Source.repo(annotations_root=ann, registry=reg, units_root=tmp_path / "units", documents=tmp_path / "documents.parquet")
    pkg = tmp_path / "pkg"
    (pkg / "data" / "tokens" / "mikra").mkdir(parents=True)
    ptab = [{**{c: r[c] for c in TOKEN_COLUMNS}, "corpus_id": "mikra", "doc_id": "d0", "shard": f"shard-0000{0 if i < half else 1}"}
            for i, r in enumerate(rows)]
    pkg_schema = pa.schema(list(TSCHEMA) + [pa.field("corpus_id", pa.string()), pa.field("doc_id", pa.string()),
                                            pa.field("shard", pa.string())])
    pq.write_table(pa.Table.from_pylist(list(reversed(ptab)), schema=pkg_schema), pkg / "data" / "tokens" / "mikra" / "r1.parquet")
    (pkg / "data" / "sentences" / "mikra").mkdir(parents=True)
    pq.write_table(units, pkg / "data" / "sentences" / "mikra" / "part-00000.parquet")
    pq.write_table(docs, pkg / "data" / "documents.parquet")
    (pkg / "VERIFICATION.json").write_text('{"ok": true}', encoding="utf-8")
    # unit map: one automatic link (audit pending) רואה -> ראה
    umap_path = tmp_path / "units.yaml"
    inv = pa.table({"lemma": ["ראה", "רואה", "רצה", "רוצה", "ריצה", "שבע", "נשבע", "ממלא", "מילא"],
                    "host": ["ראה", "רואה", "רצה", "רוצה", "ריצה", "שבע", "נשבע", "ממלא", "מילא"],
                    "tcat": ["FIN", "PRES", "FIN", "PRES", "FIN", "FIN", "FIN", "PRES", "FIN"],
                    "n": [100, 80, 50, 60, 30, 50, 60, 40, 70], "corpus": ["modern"] * 9})
    built = U.build_links(lex, inv)
    U.write_map(built, lex, {"test": True}, umap_path)
    return {"lex": lex, "repo": repo, "package": Source.from_package(pkg), "tmp": tmp_path, "umap_path": umap_path,
            "flist": U.FunctionList.load(tmp_path / "func.yaml"), "types": tmp_path / "types.yaml", "built": built}


def _cfg(tmp_path) -> dict:
    cfg = R.load_config()
    return cfg


def _extract(w, source, mode, sub, *, provisional=True):
    umap = U.UnitMap.load(w["umap_path"], allow_unaudited=provisional)
    return X.extract("mikra", source, w["lex"], umap, w["flist"], mode=mode, git=GIT, out_root=w["tmp"] / sub, progress=False)


def _folder(w, sub, m) -> Path:
    return w["tmp"] / sub / "mikra" / m["output_id"]


def _table(folder: Path, name: str) -> list[dict]:
    return pa.concat_tables([pq.read_table(p) for p in sorted((folder / name).glob("*.parquet"))]).to_pylist()


# ============================================================================================ units
@pytest.mark.parametrize("v,kind,base", [("רואה", "participle", "ראה"), ("מגיע", "participle", "הגיע"),
                                         ("מקים", "participle", "הקים"), ("מוציא", "participle", "הוציא"),
                                         ("נשבע", "passive", "שבע"), ("הושלך", "passive", "השליך"),
                                         ("התפזר", "middle", "פיזר"), ("מקיים", "participle", "קיים")])
def test_paradigm_readings(v, kind, base):
    assert (kind, base) in {(a.kind, a.base) for a in U.analyses(v)}


def test_passive_and_middle_readings_are_never_participles():
    assert not [a for a in U.analyses("נשבע") if a.kind == "participle"]
    assert not [a for a in U.analyses("התלבש") if a.kind == "participle"]
    assert not [a for a in U.analyses("מקים") if a.base == "קיים"]          # MH spells a hollow pi'el with יי


def test_build_links_auto_only_for_unambiguous_participles(r2world):
    links = r2world["built"]["links"]
    assert links["רואה"]["status"] == "auto" and links["רואה"]["base"] == "ראה"
    assert links["רוצה"]["status"] == "proposed"                            # qal participle of רצה or pu'al of ריצה
    assert {c["base"] for c in links["רוצה"]["candidates"]} == {"רצה", "ריצה"}
    assert links["נשבע"]["status"] == "proposed"                            # passive shape: reviewed, never automatic
    assert links["ממלא"]["status"] == "paper_variant"                       # participle of the paper verb מילא: Ori (P5)
    assert "מילא" not in links                                              # lexicon lemmas are never in the map


def test_unit_map_audit_gate_review_and_voice(r2world, tmp_path):
    p = r2world["umap_path"]
    m = U.UnitMap.load(p)
    assert m.audit["status"] == "pending"
    assert m.unit_of("רואה") == "רואה" and m.status("רואה") == "auto_inactive"     # not in force before the audit
    m2 = U.UnitMap.load(p, allow_unaudited=True)
    assert m2.unit_of("רואה") == "ראה" and m2.status("רואה") == "auto"
    rev = tmp_path / "rev.csv"
    rev.write_text("lemma,decision,base,proposed_by,reviewed_by,note\nנשבע,accept,שבע,claude_code,claude_code,\n", encoding="utf-8")
    assert not U.merge_review(rev, p)["ok"]                                    # a machine is not a reviewer
    rev.write_text("lemma,decision,base,proposed_by,reviewed_by,note\nרוצה,accept,כנס,human,efrat,\n", encoding="utf-8")
    assert not U.merge_review(rev, p)["ok"]                                    # the base must be a candidate
    rev.write_text("lemma,decision,base,proposed_by,reviewed_by,note\nרוצה,accept,רצה,claude_code,efrat,\nנשבע,reject,,claude_code,efrat,\n",
                   encoding="utf-8")
    r = U.merge_review(rev, p)
    assert r["ok"] and r["accepted"] == 1
    m3 = U.UnitMap.load(p)
    assert m3.unit_of("רוצה") == "רצה" and m3.status("רוצה") == "reviewed"
    assert m3.unit_of("נשבע") == "נשבע"                                         # rejected: stays its own unit
    assert U.voice_by_shape("הושלך") == "passive" and U.voice_by_shape("נכנס") == "unknown"


def test_audit_requires_the_preregistered_links(r2world, tmp_path):
    p = r2world["umap_path"]
    links = U.load_raw(p)["links"]
    sample = U.audit_sample(links)
    sheet = tmp_path / "audit.csv"
    sheet.write_text("lemma,correct,reviewed_by\n" + "".join(f"{v},Y,ori\n" for v in sample), encoding="utf-8")
    r = U.record_audit(sheet, p)
    assert r["ok"] and r["status"] == ("passed" if len(sample) >= U.AUDIT_MIN_CORRECT else "failed")
    sheet.write_text("lemma,correct,reviewed_by\nזר,Y,ori\n", encoding="utf-8")
    assert not U.record_audit(sheet, p)["ok"]


def test_function_list_tags_only_decided_lemmas(r2world):
    f = U.FunctionList.load()
    assert f.classes["יש"] == "EXISTENTIAL" and f.classes["היי"] == "COPULA"
    # STOP-B (Ori, 2026-11-21, D-060): חייב and ניתן listed; נראה not listed but kept for the unit-link safeguard
    assert f.classes["חייב"] == f.classes["ניתן"] == "MODAL_IMPERSONAL" and "נראה" not in f.classes
    assert "נראה" in f.all_lemmas() and f.describe()["not_listed"] == ["נראה"] and not f.describe()["pending"]
    assert f.status == "approved"


# ============================================================================================ extractor
def test_extract_rows_identical_across_modes_sources_and_runs(r2world):
    w = r2world
    a = _extract(w, w["repo"], "all-verbs", "a")
    b = _extract(w, w["package"], "all-verbs", "b")
    lx = _extract(w, w["repo"], "lexicon", "l")
    fa, fb, fl = _folder(w, "a", a), _folder(w, "b", b), _folder(w, "l", lx)
    for t in ("instances", "arguments"):
        for f in sorted((fa / t).glob("*.parquet")):
            assert file_sha256(f) == file_sha256(fb / t / f.name), f"repo != package: {t}/{f.name}"
    ia, il = _table(fa, "instances"), _table(fl, "instances")
    assert il == [r for r in ia if r["in_lexicon"]]                            # lexicon mode = a filter of all-verbs rows
    keep = {r["instance_id"] for r in il}
    assert _table(fl, "arguments") == [r for r in _table(fa, "arguments") if r["instance_id"] in keep]
    c = _extract(w, w["repo"], "all-verbs", "c")
    for t in ("instances", "arguments"):
        for f in sorted((fa / t).glob("*.parquet")):
            assert file_sha256(f) == file_sha256(_folder(w, "c", c) / t / f.name)    # deterministic
    assert verify(fa) == [] and table_of("instances/r1.parquet") == "instances"


def test_extract_columns_units_voice_function_and_flags(r2world):
    w = r2world
    m = _extract(w, w["repo"], "all-verbs", "a")
    inst = {r["sent_id"].split(":")[2]: r for r in _table(_folder(w, "a", m), "instances")
            if r["upos"] == "VERB" and r["word_idx"] == (1 if r["sent_id"].split(":")[2] == "8" else 0)}
    assert inst["1"]["verb_key"] == "מלא.I" and inst["1"]["signature"] == "V+DO+PP[B]"
    assert inst["2"]["verb_key"] == "שלח.I|שלח.S" and inst["2"]["paper_class"] == "A|A/B"
    assert inst["3"]["voice"] == "passive" and inst["3"]["do_kind"] == "passive_subject"
    assert inst["4"]["verb_key"] == "lemma:רואה" and inst["4"]["unit_id"] == "unit:ראה" and inst["4"]["link_status"] == "auto"
    assert inst["5"]["unit_id"] == "unit:ראה"
    assert inst["6"]["function_class"] == "EXISTENTIAL" and inst["6"]["function_use"] is True
    assert inst["7"]["function_class"] == "MODAL_IMPERSONAL" and inst["7"]["function_use"] is False   # צריך כסף stays lexical
    assert "partitive_candidate" in inst["10"]["flags"] and inst["10"]["lone_min_complement"] is True
    args = [a for a in _table(_folder(w, "a", m), "arguments") if a["instance_id"] == inst["9"]["instance_id"]]
    suf = [a for a in args if a["do_kind"] == "suffix"][0]
    assert suf["ante_lemma"] == "איש"                                           # previous unit, gender/number match


# ============================================================================================ resolver
def _resolve_all(w, folder, variants=("R0", "R2")):
    cfg = R.load_config()
    R.induce(folder, w["lex"], cfg, git=GIT)
    out = {}
    for v in variants:
        R.resolve(folder, v, w["lex"], cfg, git=GIT, noun_types_path=w["types"],
                  induced_folder=None if v == "R0" else folder / "induced", progress=False)
        out[v] = {r["instance_id"]: r for r in _table(folder / f"roles-{v}", "roles")}
    return out


def test_resolver_rules(r2world):
    w = r2world
    m = _extract(w, w["repo"], "all-verbs", "a")
    folder = _folder(w, "a", m)
    roles = _resolve_all(w, folder)
    r0, r2 = roles["R0"], roles["R2"]
    by = lambda u, wi=0: f"mikra:d0:{u}:0|0|{wi}"  # noqa: E731
    assert (r0[by(1)]["outcome"], r0[by(1)]["reason"]) == ("B", "complementary")
    assert (r0[by(2)]["outcome"], r0[by(2)]["reason"]) == ("A", "complementary")
    assert (r0[by(10)]["outcome"], r0[by(10)]["reason"]) == ("A", "partitive")
    assert r0[by(10)]["location_arg_idx"] is None                               # a partitive has no Location PP
    assert (r0[by(11)]["outcome"], r0[by(11)]["reason"]) == ("UNDETERMINED", "elided_object")   # D-059 guard
    assert (r0[by(12)]["outcome"], r0[by(12)]["reason"]) == ("AMBIGUOUS", "several_typed_pps")
    assert (r0[by(13)]["outcome"], r0[by(13)]["reason"]) == ("NON_LOCATIVE", "idiom")
    assert (r0[by(14)]["outcome"], r0[by(14)]["reason"]) == ("B", "bare_np")
    assert (r0[by(6)]["outcome"], r0[by(6)]["reason"]) == ("NON_LOCATIVE", "clausal_complement")
    # the pronoun object of unit 9: R0 cannot type it; R2 types it by its antecedent (איש, ANIMATE) -> A via עיר
    assert r0[by(9)]["outcome"] == "A" and "antecedent" not in r0[by(9)]["decided_by"]
    assert r2[by(9)]["outcome"] == "A" and "antecedent" in r2[by(9)]["decided_by"]


def test_resolver_reads_no_preposition():
    banned = {"p_exact", "p_family", "signature", "flags"}
    assert not banned & set(R.INSTANCE_COLUMNS) and not banned & set(R.ARGUMENT_COLUMNS)
    sql = R._types_sql(True, True) + R._decide_sql("R2", 0.2)
    for b in banned:
        assert b not in sql, b


def test_rule_zero_by_permuting_every_preposition(r2world):
    """Shuffle the prepositions of every PP (and the extractor's lone_min_complement that derives from them): no
    outcome changes except partitive-decided ones, and those never enter the identity test."""
    w = r2world
    m = _extract(w, w["repo"], "all-verbs", "a")
    folder = _folder(w, "a", m)
    perm = w["tmp"] / "perm" / folder.name
    shutil.copytree(folder, perm)
    rng = random.Random(7)
    for f in sorted((perm / "arguments").glob("*.parquet")):
        t = pq.read_table(f).to_pylist()
        pps = [r for r in t if r["slot"] == "PP"]
        fam = [(r["p_exact"], r["p_family"]) for r in pps]
        rng.shuffle(fam)
        fam = [(("מן", "MIN") if (pe, pf) != ("מן", "MIN") else ("ב", "B")) for pe, pf in fam]   # every PP changes
        for r, (pe, pf) in zip(pps, fam):
            r["p_exact"], r["p_family"] = pe, pf
        pq.write_table(pa.Table.from_pylist(t, schema=X.ARGUMENTS_SCHEMA), f)
    for f in sorted((perm / "instances").glob("*.parquet")):
        args = pq.read_table(perm / "arguments" / f.name).to_pylist()
        rows = pq.read_table(f).to_pylist()
        for r in rows:
            a = [x for x in args if x["instance_id"] == r["instance_id"]]
            pp = [x for x in a if x["slot"] == "PP"]
            r["lone_min_complement"] = (r["do_kind"] == "none" and len(pp) == 1 and pp[0]["p_family"] == "MIN"
                                        and not r["has_bare_np"] and r["voice"] not in ("passive", "middle"))
        pq.write_table(pa.Table.from_pylist(rows, schema=X.INSTANCES_SCHEMA), f)
    base = _resolve_all(w, folder, ("R0",))["R0"]
    shuf = _resolve_all(w, perm, ("R0",))["R0"]
    for k, r in base.items():
        s = shuf[k]
        if "partitive" in r["decided_by"] or "partitive" in s["decided_by"] or "partitive_guard" in r["decided_by"] + s["decided_by"]:
            assert r["location_arg_idx"] is None and s["location_arg_idx"] is None
            continue
        assert (r["outcome"], r["reason"], r["locatum_arg_idx"], r["location_arg_idx"]) == \
               (s["outcome"], s["reason"], s["locatum_arg_idx"], s["location_arg_idx"]), k


# ============================================================================================ classes and identity
@pytest.mark.parametrize("a,b,nl,amb,nobj,k,expected", [
    (2, 1, 0, 0, 3, 1, "A/B"), (2, 0, 0, 0, 3, 1, "A"), (0, 3, 0, 0, 3, 1, "B"), (0, 0, 1, 0, 3, 1, "NON_LOCATIVE"),
    (0, 0, 0, 0, 25, 1, "NON_LOCATIVE"), (0, 0, 0, 2, 25, 1, "AMBIGUOUS"), (0, 0, 0, 0, 3, 1, "INSUFFICIENT_EVIDENCE"),
    (5, 1, 0, 0, 9, 2, "INSUFFICIENT_EVIDENCE")])
def test_class_precedence(a, b, nl, amb, nobj, k, expected):
    import duckdb

    cls, _ = C._class_sql(str(a), str(b), str(nl), str(amb), str(nobj), k, 20)
    assert duckdb.sql(f"SELECT {cls}").fetchall()[0][0] == expected


@pytest.mark.parametrize("fa,fb,expected", [(["B"], ["B", "MIN"], "IDENTITY_ATTESTED"), (["MIN"], ["AL"], "COUNTEREXAMPLE"),
                                            (["B"], [], "NOT_TESTABLE"), (["OTHER:עם"], ["OTHER:תחת"], "COUNTEREXAMPLE")])
def test_identity_verdicts(fa, fb, expected):
    import duckdb

    lit = lambda x: "[" + ", ".join(f"'{v}'" for v in x) + "]::VARCHAR[]"  # noqa: E731
    assert duckdb.sql(f"SELECT {C._identity_sql(lit(fa), lit(fb))}").fetchall()[0][0] == expected


def test_classify_end_to_end_and_partitive_never_decides_identity(r2world):
    w = r2world
    m = _extract(w, w["repo"], "all-verbs", "a")
    folder = _folder(w, "a", m)
    _resolve_all(w, folder, ("R0",))
    cm = C.classify(folder, "R0", w["lex"], R.load_config(), git=GIT, progress=False)
    vc = pq.read_table(folder / "classes-R0" / "verb_classes.parquet").to_pylist()
    prim = {r["verb_key"]: r for r in vc if (r["level"], r["view"], r["scope"], r["k"]) == ("unit", "full", "all", 1)}
    assert prim["מלא.I"]["class"] == "A/B" and prim["מלא.I"]["n_a_partitive"] == 1
    assert prim["מלא.I"]["class_without_partitive"] == "B"                      # D-059 P7 sensitivity
    assert prim["מלא.I"]["families_frame_a"] == []                              # the partitive A has no Location PP
    assert prim["מלא.I"]["identity_verdict"] == "NOT_TESTABLE"
    assert "unit:ראה" in prim and prim["unit:ראה"]["n_tokens"] == 2           # רואה + ראה: one unit (provisional link)
    lem = {r["verb_key"] for r in vc if r["level"] == "lemma"}
    assert {"lemma:רואה", "lemma:ראה"} <= lem                                   # the raw-lemma level is always kept
    nf = {r["verb_key"]: r for r in vc if (r["level"], r["view"], r["scope"], r["k"]) == ("unit", "full", "no_function_use", 1)}
    assert "unit:צריך" in nf and "unit:יש" not in nf                           # only function_use tokens are dropped
    assert verify(folder / "classes-R0") == [] and cm["rows"]["verb_classes"] > 0


# ============================================================================================ scoring
def _gold_file(d: Path, corpus: str, split: str, rows: list[dict]) -> None:
    cols = ["sample_id", "item_id", "instance_key", "split", "stratum", "agreement", "annotator", "guideline_version",
            "is_target_verb", "member", "locative", "frame", "do", "pps", "bare_np", "locatum", "location", "has_notes"]
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{corpus}_{split}_ori.csv", "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        wr.writeheader()
        for r in rows:
            wr.writerow({**{c: "" for c in cols}, **r})


def test_scoring_clean_sets_ledgers_and_test_lock(r2world, monkeypatch):
    w = r2world
    m = _extract(w, w["repo"], "all-verbs", "a")
    folder = _folder(w, "a", m)
    _resolve_all(w, folder, ("R0", "R2"))
    gd = w["tmp"] / "goldfiles"
    rows = [{"item_id": "MI0001", "instance_key": "mikra:d0:1:0|0|0", "is_target_verb": "Y", "locative": "Y", "frame": "B", "do": "2", "pps": "3:ב"},
            {"item_id": "MI0002", "instance_key": "mikra:d0:2:0|0|0", "is_target_verb": "Y", "locative": "Y", "frame": "A", "do": "2", "pps": "4:אל"},
            {"item_id": "MI0003", "instance_key": "mikra:d0:12:0|0|0", "is_target_verb": "Y", "locative": "Y", "frame": "A", "do": "2"}]
    for sp in ("dev", "validation", "test"):
        _gold_file(gd, "mikra", sp, [{**r, "split": sp} for r in rows])
    ex = gd / "EXPOSURE.csv"
    ex.write_text("item_id,sample_id,corpus,split,agreement,level,source,note\nMI0003,x,mikra,test,False,TOKEN,paper,\n", encoding="utf-8")
    dev = S.score("mikra", "dev", folder, gold_dir=gd, exposure_path=ex, label_source="human")
    assert dev["primary"] == "full" and dev["sets"]["full"]["extraction"]["do_recall"] == 1.0
    assert dev["sets"]["full"]["variants"]["R0"]["A"]["fn"] == 1                 # MI0003 is AMBIGUOUS: a miss
    with pytest.raises(S.ScoreError):
        S.score("mikra", "test", folder, gold_dir=gd, exposure_path=ex, label_source="human")   # test needs --final-test
    with pytest.raises(S.ScoreError):
        S.load_gold("mikra", "validation", gold_dir=gd, label_source="human")   # validation only via the choice
    monkeypatch.setattr(S, "FINAL_LEDGER", gd / "FINAL_TEST.json")
    t = S.score("mikra", "test", folder, final_test=True, gold_dir=gd, exposure_path=ex, label_source="human")
    assert t["primary"] == "clean" and t["exposed_excluded"] == 1
    assert t["sets"]["clean"]["variants"]["R0"]["n"] == 2
    with pytest.raises(S.ScoreError):
        S.score("mikra", "test", folder, final_test=True, gold_dir=gd, exposure_path=ex, label_source="human")   # read once
    ch = S.choose({"mikra": folder}, ledger=gd / "CHOICE.json", gold_dir=gd, exposure_path=ex, label_source="human")
    assert ch["chosen"] == "R0"                                                 # equal F1: the simpler variant wins
    with pytest.raises(S.ScoreError):
        S.choose({"mikra": folder}, ledger=gd / "CHOICE.json", gold_dir=gd, exposure_path=ex, label_source="human")


def test_mcnemar_and_kappa():
    assert S.mcnemar_exact(0, 0) == 1.0 and S.mcnemar_exact(10, 0) < 0.01
    assert S.cohen_kappa(["A", "B", "A"], ["A", "B", "A"]) == 1.0


# ============================================================================================ supplement
def test_supplement_needs_approval_and_is_disjoint_from_r1(r2world, tmp_path):
    w = r2world
    with pytest.raises(S.ScoreError):
        S.supplement("mikra", w["repo"], w["lex"], w["lex"], approval=None, size=4, git=GIT, out_root=tmp_path / "s")
    new_yaml = LEX_YAML.replace("{lemma: מולא, voice: passive}", "{lemma: מולא, voice: passive}, {lemma: צריך, voice: active}")
    (tmp_path / "new.yaml").write_text(new_yaml, encoding="utf-8")
    new = L.load(tmp_path / "new.yaml", tmp_path / "forms.yaml")
    m = S.supplement("mikra", w["repo"], w["lex"], new, approval="D-TEST", size=4, git=GIT, out_root=tmp_path / "s", progress=False)
    s = pq.read_table(tmp_path / "s" / "mikra" / m["sample_id"] / "sample.parquet").to_pylist()
    assert m["sample_id"].startswith("mikra-s1-") and {x["lemma"] for x in s} == {"צריך"}   # only the NEW tokens


def test_r1_lexicon_unchanged_since_the_frozen_draw():
    from hebloc.paths import DATA_DIR

    man = DATA_DIR / "loc" / "gold" / "mikra" / "mikra-r1b-1cd4ee9802" / "manifest.json"
    if not man.exists():
        pytest.skip("the frozen Mikra sample is not on this computer")
    assert json.loads(man.read_text(encoding="utf-8"))["lexicon_sha256"] == L.load().sha256


def test_link_safeguards_function_bases_and_junk(r2world):
    inv = pa.table({"lemma": ["אפשר", "מאפשר", "##זגו", "מוזג", "סובב"], "host": ["אפשר", "מאפשר", "זגו", "מוזג", "סובב"],
                    "tcat": ["FIN", "PRES", "FIN", "FIN", "PRES"], "n": [100, 60, 50, 80, 40], "corpus": ["modern"] * 5})
    plain = U.build_links(r2world["lex"], inv)["links"]
    assert plain["מאפשר"]["status"] == "auto"                                   # morphologically a clean participle
    guarded = U.build_links(r2world["lex"], inv, {"אפשר"})["links"]
    assert guarded["מאפשר"]["status"] == "proposed"                             # base is a function predicate: reviewed
    assert "##זגו" not in guarded                                              # Dicta sub-word junk is never linked
    assert "סובב" not in guarded                                               # a polel with no attested base: own unit


def test_scoring_silver_reports_agreement_and_leaves_abstentions_out(r2world, tmp_path):
    """D-061: SILVER is read only from a frozen, recorded file; every figure is agreement with silver; abstained
    items are left out of the frame metrics (D-g) and an agreed_only set is reported."""
    from hebloc.store.io import file_sha256

    w = r2world
    m = _extract(w, w["repo"], "all-verbs", "a")
    folder = _folder(w, "a", m)
    _resolve_all(w, folder, ("R0",))
    final = tmp_path / "silverfinal"
    (final / "dev").mkdir(parents=True)
    cols = ["item_id", "instance_key", "split", "label_source", "silver_status", "is_target_verb", "locative", "frame", "do", "pps"]
    f = final / "dev" / "mikra_dev_silver.csv"
    with open(f, "w", encoding="utf-8-sig", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=cols)
        wr.writeheader()
        wr.writerow({"item_id": "MI0001", "instance_key": "mikra:d0:1:0|0|0", "split": "dev", "label_source": "ai",
                     "silver_status": "agreed", "is_target_verb": "Y", "locative": "Y", "frame": "B", "do": "2", "pps": "3:ב"})
        wr.writerow({"item_id": "MI0002", "instance_key": "mikra:d0:2:0|0|0", "split": "dev", "label_source": "ai",
                     "silver_status": "abstained", "is_target_verb": "Y", "locative": "?", "frame": "AMBIGUOUS"})
        wr.writerow({"item_id": "MI0003", "instance_key": "mikra:d0:12:0|0|0", "split": "dev", "label_source": "ai",
                     "silver_status": "adjudicated", "is_target_verb": "Y", "locative": "Y", "frame": "A", "do": "2"})
    frozen = tmp_path / "FROZEN_SILVER.json"
    with pytest.raises(S.ScoreError):                                   # not recorded yet: refused (SG2)
        S.score("mikra", "dev", folder, gold_dir=final, frozen_path=frozen)
    frozen.write_text(json.dumps({"jobs": {"sentence-mikra-dev": {"placed": {f.name: file_sha256(f)}}}}), encoding="utf-8")
    r = S.score("mikra", "dev", folder, gold_dir=final, frozen_path=frozen)
    assert r["label_source"] == "silver" and "not validated accuracy" in r["measure"]
    full = r["sets"]["full"]
    assert full["abstained_excluded"] == 1 and full["variants"]["R0"]["n"] == 2
    assert r["sets"]["agreed_only"]["variants"]["R0"]["n"] == 1
    assert "accuracy" not in json.dumps({k: v for k, v in r.items() if k != "measure"})


# ============================================================================================ Phase C build (C0, D-065)
def test_i2_lemma_partner_python_equals_sql(r2world, tmp_path):
    """I-2: a LEMMA-ONLY match on a host that is a form of another template of the same root gets ~<root>.<T>; a form
    match does not; a partner already covered by a member is never added. Python == SQL."""
    import duckdb

    from hebloc.loc import identify as ID

    fy = tmp_path / "forms_i2.yaml"
    fy.write_text("meta: {lexicon_file_sha256: null}\nforms:\n  מלא.I: [ימלא]\nlemma_partners:\n  מלא.I: {מלא: ['~מלא.S']}\n"
                  "  שלח.I: {שלח: ['~שלח.S']}\n", encoding="utf-8")
    lex = L.load(tmp_path / "lex.yaml", fy)
    idx = ID.build_index(lex)
    cases = [("מילא", "מלא"), ("מילא", "ימלא"), ("שלח", "שלח"), ("מילא", "מילא")]
    py = [ID.identify(idx, lem, host, "VERB")["verb_key"] for lem, host in cases]
    assert py == ["מלא.I|~מלא.S", "מלא.I", "שלח.I|שלח.S", "מלא.I"]
    con = duckdb.connect()
    con.register("tk", pa.table({"sent_id": [f"s{i}" for i in range(len(cases))], "piece_idx": [0] * len(cases),
                                 "word_idx": [0] * len(cases), "lemma": [c[0] for c in cases], "host": [c[1] for c in cases],
                                 "upos": ["VERB"] * len(cases)}))
    ID.register(con, lex)
    sql = {r[0]: r[1] for r in con.sql(f"SELECT sent_id, verb_key FROM ({ID.identify_sql('tk')})").fetchall()}
    assert [sql[f"s{i}"] for i in range(len(cases))] == py
    r1 = ID.build_index(r2world["lex"])                                          # R1 (no lemma_partners): unchanged
    assert ID.identify(r1, "מילא", "מלא", "VERB")["verb_key"] == "מלא.I"


I3_LEX = LEX_YAML + """- {id: צרר.S, root: צרר, template: Simple, citation: צרר, gloss: bind, class: null, status: paper_other,
   putting_removal: UNKNOWN, flags: [no_own_lemma]}
"""


def _inv(rows):
    return pa.table({"lemma": [r[0] for r in rows], "host": [r[1] for r in rows], "n": [r[2] for r in rows],
                     "corpus": ["modern"] * len(rows)})


def test_forms_candidates_i2_i3_i4(tmp_path):
    from hebloc.loc import morph

    (tmp_path / "lex.yaml").write_text(I3_LEX, encoding="utf-8")
    lex = L.load(tmp_path / "lex.yaml", tmp_path / "none.yaml")
    simple_m, int_m = morph.forms("מלא", "Simple"), morph.forms("מלא", "Intensive")
    g_clean, g_amb = sorted(int_m - simple_m)[:2]                                 # Intensive-only generated shapes
    inv = _inv([("צריך", "צריך", 60), ("צריך", "צריכ1", 1), ("צריך", "צריכ2", 1),          # an established self-lemma
                ("מילא", "מלא", 10), ("מילא", "מילא", 10),                                # own lemma of מלא.I
                ("[BLANK]", g_clean, 5),                                                   # a clean generated host
                ("אחר", g_amb, 3), ("[BLANK]", g_amb, 7), ("אחר", "x1", 30), ("אחר", "x2", 30), ("אחר", "x3", 30)])
    r1 = L.build_forms(lex, inv)
    assert "צריך" in r1["forms"]["צרר.S"] and "~form" in r1["ambiguous"]["צרר.S"]["צריך"]     # R1: self-copy is neutral
    i3 = L.build_forms(lex, inv, established_self_foreign=True)
    assert "צריך" not in i3["forms"]["צרר.S"]                                     # I-3: foreign -> dropped
    assert g_clean not in r1["forms"]["מלא.I"]                                    # R1: no generated forms (own lemma)
    i4 = L.build_forms(lex, inv, generated="clean_keys")
    assert g_clean in i4["forms"]["מלא.I"] and g_clean not in i4["ambiguous"].get("מלא.I", {})
    assert g_amb not in i4["forms"]["מלא.I"]                                       # I-4: only clean generated hosts
    assert i4["forms"]["צרר.S"] == r1["forms"]["צרר.S"]                           # no own lemma: R1 treatment kept
    i2 = L.build_forms(lex, inv, lemma_partners=True)
    want = sorted(f"~מלא.{L.TEMPLATE_CODE[t]}" for t in ("Simple", "Causative") if "מלא" in morph.forms("מלא", t, exclude_kinds=("inf_n",) if t == "Simple" else ()))
    assert i2["lemma_partners"]["מלא.I"]["מלא"] == want and "~מלא.S" in want
    assert i2["forms"] == r1["forms"] and i2["ambiguous"] == r1["ambiguous"]     # I-2 changes no form


def test_ident_build_candidate_folder_and_i1_draft(r2world, tmp_path):
    from hebloc.loc import ident as IDN

    w = r2world
    inv = _inv([("מילא", "מלא", 10), ("מילא", "מילא", 10), ("שלח", "שלח", 20)])
    m = IDN.build(["I-2"], w["lex"], inv, git=GIT, out_root=tmp_path / "ident", lexicon_path=tmp_path / "lex.yaml")
    folder = tmp_path / "ident" / m["candidate_id"]
    cand = IDN.load(folder)
    assert m["candidates"] == ["I-2"] and cand.lemma_partners and not L.forms_stale(cand, folder / IDN.LEXICON_NAME)
    assert verify(folder) == [] and (folder / "changes.csv").exists()
    with pytest.raises(IDN.IdentError):                                          # built once
        IDN.build(["I-2"], w["lex"], inv, git=GIT, out_root=tmp_path / "ident", lexicon_path=tmp_path / "lex.yaml")
    with pytest.raises(IDN.IdentError):
        IDN.parse_candidates("I-5")                                              # report only: no folder
    ev = [{"lemma": "ממלא", "agree": "True", "suggestion": "dicta_lemma:מלא.I", "voice_a": "active", "voice_b": "active"},
          {"lemma": "נשלח2", "agree": "False", "suggestion": "undecided"},
          {"lemma": "שולח", "agree": "True", "suggestion": "shared_lemma:שלח.S"}]
    text, summ = IDN.lexicon_v2_draft(LEX_YAML, ev)
    assert summ["applied"] == {"dicta_lemma": 1, "shared_lemma": 1} and summ["skipped"] == {"undecided": 1}
    import yaml as Y

    ent = {e["id"]: e for e in Y.safe_load(text)["entries"]}
    assert {"lemma": "ממלא", "voice": "active"} in ent["מלא.I"]["dicta_lemmas"]
    # D-067: the variant job writes the chosen BASE; it is mapped through the unit map's paper_entries, exactly
    links = {"ממלא": {"candidates": [{"base": "מילא", "paper_entries": ["מלא.I"]}, {"base": "מלא", "kind": "participle"}]},
             "ששלח": {"candidates": [{"base": "שלח", "paper_entries": ["שלח.S", "שלח.I"]}]}}
    ev2 = [{"lemma": "ממלא", "agree": "True", "suggestion": "dicta_lemma:מילא", "voice_a": "active", "voice_b": "active"},
           {"lemma": "ממלא", "agree": "True", "suggestion": "shared_lemma:מלא"},                   # base with no paper entry
           {"lemma": "ששלח", "agree": "True", "suggestion": "dicta_lemma:שלח"}]                    # two entries
    text2, summ2 = IDN.lexicon_v2_draft(LEX_YAML, ev2, links=links)
    assert summ2["applied"] == {"dicta_lemma": 1}
    assert summ2["skipped"] == {"no_paper_entry": 1, "several_entries": 1}
    assert {"lemma": "ממלא", "voice": "active"} in {e["id"]: e for e in Y.safe_load(text2)["entries"]}["מלא.I"]["dicta_lemmas"]
    assert IDN.lexicon_v2_draft(LEX_YAML, ev2)[1]["skipped"] == {"unknown_entry": 3}          # without the map: nothing
    bad = [{"lemma": "מילא", "agree": "True", "suggestion": "dicta_lemma:שלח.S"}]   # one lemma, two entries, no flag
    evp = tmp_path / "ev.csv"
    with open(evp, "w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["lemma", "agree", "suggestion"])
        wr.writeheader()
        wr.writerows(bad)
    with pytest.raises(IDN.IdentError):                                          # never fixed silently (Ori's G4)
        IDN.build(["I-1"], w["lex"], inv, git=GIT, out_root=tmp_path / "ident2", lexicon_path=tmp_path / "lex.yaml",
                  variant_evidence=evp)


def test_ident_dev_effects_dev_only_and_rekey_labels(r2world, tmp_path, monkeypatch):
    """C1 (D-067): only dev items and dev paper examples are read; R1 vs the candidate per token; a re-keyed item
    carries its dev SILVER label (is_target_verb N = R1 wrong) and a paper example counts as R1 right."""
    from hebloc.loc import ident as IDN

    w = r2world
    t1, t2, t3 = "mikra:d0:1:0|0|0", "mikra:d0:2:0|0|0", "mikra:d0:3:0|0|0"
    sd = tmp_path / "gold" / "mikra" / "S1"
    sd.mkdir(parents=True)
    with open(sd / "sample.csv", "w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["item_id", "instance_key", "stratum", "verb_key", "split"])
        wr.writeheader()
        wr.writerows([{"item_id": "MI1", "instance_key": t1, "stratum": "lemma_only", "verb_key": "מלא.I", "split": "dev"},
                      {"item_id": "MI2", "instance_key": t2, "stratum": "both", "verb_key": "שלח.I|שלח.S", "split": "dev"},
                      {"item_id": "MI3", "instance_key": t3, "stratum": "both", "verb_key": "שלח.S", "split": "validation"},
                      {"item_id": "MI4", "instance_key": "mikra:d0:4:0|0|0", "stratum": "NONPAPER", "verb_key": "lemma:רואה",
                       "split": "dev"}])
    paper = tmp_path / "paper.csv"
    with open(paper, "w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["instance_key", "entry_id", "frame", "where", "ref", "status", "frozen_split"])
        wr.writeheader()
        wr.writerows([{"instance_key": t1, "entry_id": "מלא.I", "frame": "B", "where": "ex. 1", "ref": "Genesis 1:1", "status": "dev"},
                      {"instance_key": t3, "entry_id": "שלח.S", "frame": "A", "where": "ex. 2", "ref": "Genesis 1:3",
                       "status": "excluded_frozen_test", "frozen_split": "test"}])
    monkeypatch.setattr(G, "FROZEN_SAMPLES", {"mikra": {"sample_id": "S1"}})
    items = IDN.dev_items(gold_dir=tmp_path / "gold", paper_path=paper)
    assert sorted(x["item_id"] for x in items) == ["MI1", "MI2", "MI4", "paper:ex. 1:Genesis 1:1"]   # never validation/test
    cf = tmp_path / "cand"
    cf.mkdir()
    (cf / IDN.LEXICON_NAME).write_text(LEX_YAML, encoding="utf-8")
    (cf / IDN.FORMS_NAME).write_text("meta: {lexicon_file_sha256: null}\nforms:\n  מלא.I: [ימלא]\n"
                                     "lemma_partners:\n  מלא.I: {מילא: ['~מלא.S']}\n", encoding="utf-8")
    (cf / "manifest.json").write_text("{}", encoding="utf-8")
    labels = {"mikra": [{"instance_key": t1, "is_target_verb": "N", "silver_status": "agreed"},
                        {"instance_key": t2, "is_target_verb": "Y", "silver_status": "agreed"}]}
    m = IDN.dev_effects(cf, w["repo"], w["lex"], git=GIT, labels=labels, gold_dir=tmp_path / "gold", paper_path=paper)
    rows = {r["item_id"]: r for r in csv.DictReader(open(cf / "dev" / "dev_effects.csv", encoding="utf-8-sig"))}
    assert rows["MI1"]["effect"] == "rekeyed" and rows["MI1"]["cand_key"] == "מלא.I|~מלא.S" and rows["MI1"]["r1_wrong"] == "yes"
    assert rows["MI2"]["effect"] == "same" and rows["MI2"]["r1_wrong"] == "no"
    assert rows["MI4"]["r1_key"] == "" and rows["MI4"]["effect"] == "same"                          # NONPAPER: no R1 key
    assert rows["paper:ex. 1:Genesis 1:1"]["effect"] == "rekeyed" and rows["paper:ex. 1:Genesis 1:1"]["r1_wrong"] == "no"
    assert m["summary"]["sample:mikra"]["changed_r1_wrong"] == {"yes": 1, "no": 0, "unknown": 0}
    assert verify(cf / "dev") == []
    # R1 against itself: no effect at all
    (cf / IDN.FORMS_NAME).write_text(FORMS_YAML, encoding="utf-8")
    shutil.rmtree(cf / "dev")
    m0 = IDN.dev_effects(cf, w["repo"], w["lex"], git=GIT, labels=labels, gold_dir=tmp_path / "gold", paper_path=paper)
    assert all(v["effects"]["same"] == v["n"] for v in m0["summary"].values())


def test_supplement_strata_by_candidate_registry_and_ordinal(r2world, tmp_path, monkeypatch):
    w = r2world
    new_yaml = LEX_YAML.replace("{lemma: מולא, voice: passive}", "{lemma: מולא, voice: passive}, {lemma: צריך, voice: active}")
    (tmp_path / "new.yaml").write_text(new_yaml, encoding="utf-8")
    new = L.load(tmp_path / "new.yaml", tmp_path / "forms.yaml")
    m = S.supplement("mikra", w["repo"], w["lex"], new, approval="D-TEST", size=4, git=GIT, out_root=tmp_path / "s", progress=False)
    s = pq.read_table(tmp_path / "s" / "mikra" / m["sample_id"] / "sample.parquet").to_pylist()
    assert {x["candidate"] for x in s} == {"I-1"} and all(x["stratum"].startswith("I-1/") for x in s)
    assert all(0 < x["pi"] <= 1 for x in s) and m["items_sha256"] == G.items_fingerprint(s)
    sid = m["sample_id"]
    monkeypatch.setattr(G, "FROZEN_SUPPLEMENTS", {"mikra": {sid: {"items_sha256": "WRONG"}}})
    with pytest.raises(S.ScoreError):                                            # registered, other items: STOP
        S.supplement("mikra", w["repo"], w["lex"], new, approval="D-TEST", size=4, git=GIT, out_root=tmp_path / "s2", progress=False)
    monkeypatch.setattr(G, "FROZEN_SUPPLEMENTS", {"mikra": {sid: {"items_sha256": m["items_sha256"]}}})
    m2 = S.supplement("mikra", w["repo"], w["lex"], new, approval="D-TEST", size=4, git=GIT, out_root=tmp_path / "s3", progress=False)
    assert m2["frozen_check"] == {"items_match": True}                           # a second draw (e.g. the package) matches
    with pytest.raises(S.ScoreError):                                            # an ordinal is never reused
        S.supplement("mikra", w["repo"], w["lex"], new, approval="D-TEST", size=5, git=GIT, out_root=tmp_path / "s4", progress=False)
    assert S._allocate(10, {"I-1/A": 50, "I-1/HOMOGRAPH": 50}) == {"I-1/HOMOGRAPH": 1, "I-1/A": 9}   # HOMOGRAPH <= 10%


def test_screen_draw_is_outside_every_sample_and_deterministic(r2world, tmp_path, monkeypatch):
    from hebloc.loc import draws as DR

    w = r2world
    gd = tmp_path / "gold"
    (gd / "mikra" / "mikra-test").mkdir(parents=True)
    pq.write_table(pa.table({"sent_id": ["mikra:d0:1:0"]}), gd / "mikra" / "mikra-test" / "sample.parquet")
    monkeypatch.setattr(G, "FROZEN_SAMPLES", {"mikra": {"sample_id": "mikra-test"}})
    aff = {"מלא.I": {"מילא"}}
    with pytest.raises(DR.DrawError):
        DR.screen("mikra", w["repo"], w["lex"], aff, approval=None, git=GIT, candidate_sha256="c", gold_dir=gd,
                  quality_dir=tmp_path / "q", out_root=tmp_path / "d1", progress=False)
    m = DR.screen("mikra", w["repo"], w["lex"], aff, approval="D-TEST", git=GIT, candidate_sha256="c", gold_dir=gd,
                  quality_dir=tmp_path / "q", out_root=tmp_path / "d1", progress=False)
    rows, _ = DR.read_ids(tmp_path / "d1" / "screen" / "mikra" / m["draw_id"])
    assert rows and not any(r["instance_key"].startswith("mikra:d0:1:0|") for r in rows)     # the sample's sentence is out
    assert m["shortfall"] == {"מלא.I": DR.SCREEN_PER_KEY - len(rows)}
    m2 = DR.screen("mikra", w["package"], w["lex"], aff, approval="D-TEST", git=GIT, candidate_sha256="c", gold_dir=gd,
                   quality_dir=tmp_path / "q", out_root=tmp_path / "d2", progress=False)
    assert m2["items_sha256"] == m["items_sha256"] and m2["draw_id"] == m["draw_id"]     # repo == package


def test_review_template_audit_draws_and_the_i5_report(r2world, tmp_path):
    from hebloc.loc import draws as DR
    from hebloc.loc import report as RP

    w = r2world
    m = _extract(w, w["repo"], "all-verbs", "a")
    folder = _folder(w, "a", m)
    _resolve_all(w, folder, ("R0",))
    C.classify(folder, "R0", w["lex"], R.load_config(), git=GIT, progress=False)
    for k in (1, 2):
        rv = DR.review(folder, "R0", git=GIT, out_root=tmp_path / f"r{k}")
        tp = DR.template(folder, git=GIT, out_root=tmp_path / f"t{k}", size=4, min_tokens=1, min_per_value=1)
        au = DR.audit(folder, "R0", git=GIT, out_root=tmp_path / f"a{k}")
    assert rv["items_sha256"] == DR.review(folder, "R0", git=GIT, out_root=tmp_path / "r3")["items_sha256"]
    rows, _ = DR.read_ids(tmp_path / "r1" / "review" / "mikra" / rv["draw_id"])
    assert all(not r["verb_key"] or ":" in r["verb_key"] for r in rows)          # non-lexicon units only
    trows, tman = DR.read_ids(tmp_path / "t1" / "template" / "mikra" / tp["draw_id"])
    assert len(trows) == 4 and tman["population_by_value"]
    adir = tmp_path / "a1" / "audit" / "mikra" / au["draw_id"]
    head = open(adir / "ids.csv", encoding="utf-8-sig").readline()
    assert "outcome" not in head and (adir / "audit_key.csv").exists()          # outcomes stay in the local key file
    RP.report(folder, "R0", w["lex"], git=GIT)
    fl = list(csv.DictReader(open(folder / "report-R0" / "function_lemma.csv", encoding="utf-8-sig")))
    cov = {r["what"] for r in csv.DictReader(open(folder / "report-R0" / "coverage.csv", encoding="utf-8-sig"))}
    assert "function_lemma" in cov and isinstance(fl, list)


def test_exposure_covers_supplements_and_screen_readings(r2world, tmp_path, monkeypatch):
    from hebloc.loc import exposure as EX

    w = r2world
    gd = tmp_path / "gold"
    cols = {"sample_id": [], "item_id": [], "sent_id": [], "piece_idx": [], "word_idx": [], "verb_key": [], "split": [], "agreement": []}
    for sid, item, unit in (("mikra-test", "MI0001", 1), ("mikra-s1-x", "MIS1001", 10)):
        (gd / "mikra" / sid).mkdir(parents=True)
        t = {k: list(v) for k, v in cols.items()}
        for k, v in (("sample_id", sid), ("item_id", item), ("sent_id", f"mikra:d0:{unit}:0"), ("piece_idx", 0), ("word_idx", 0),
                     ("verb_key", "מלא.I"), ("split", "dev"), ("agreement", False)):
            t[k].append(v)
        pq.write_table(pa.table(t), gd / "mikra" / sid / "sample.parquet")
    monkeypatch.setattr(EX, "FROZEN_SAMPLES", {"mikra": {"sample_id": "mikra-test"}})
    monkeypatch.setattr(EX, "FROZEN_SUPPLEMENTS", {"mikra": {"mikra-s1-x": {"items_sha256": "x"}}})
    dd = tmp_path / "draws" / "screen" / "mikra" / "mikra-screen-x"
    dd.mkdir(parents=True)
    (dd / "ids.csv").write_text("item_id,instance_key,verb_key,stratum\nSCMI0001,mikra:d0:10:0|0|2,x,y\n", encoding="utf-8")
    rows = EX.compute(w["lex"], w["repo"], gold_dir=gd, quality_dir=tmp_path / "q", manual_path=tmp_path / "none.csv",
                      draws_dir=tmp_path / "draws")
    hit = {(r["item_id"], r["level"]) for r in rows}
    assert ("MIS1001", "SENTENCE") in hit and not any(r["item_id"] == "MI0001" for r in rows)
