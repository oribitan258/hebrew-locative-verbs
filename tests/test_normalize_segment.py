"""Unit tests for M2 preprocessing — cases taken from real corpus lines (incl. difficult ones)."""

from __future__ import annotations

import pytest

from hebloc.artifacts import reconstruct
from hebloc.normalize import (
    normalize_haskala,
    normalize_hazal,
    normalize_medieval,
    normalize_mikra,
    normalize_modern,
)
from hebloc.pieces import plan_pieces, piece_rows, verify_pieces
from hebloc.segment import segment_line, sentence_spans
from hebloc import versification as V


# ----------------------------------------------------------------------------- artifacts
@pytest.mark.parametrize(
    "raw, expected, flags",
    [
        ("השנה prefix=ה - 13 - חסר", "השנה ה-13 - חסר", ["prefix_R2"]),                       # hyphen+number
        ("קבע prefix=ו - T&AT עלו", "קבע ו-T&AT עלו", ["prefix_R2"]),                         # hyphen+Latin
        ("ולו prefix=ב token=רח' פנלון", "ולו ברח' פנלון", ["prefix_R1"]),                    # token=
        ("והמזבח prefix=ל \" ב , והכבש", "והמזבח ל\"ב , והכבש", ["prefix_R3"]),              # Rambam numeral
        ("נסענו prefix=ל ' עמידר ' בחולון", "נסענו ל'עמידר ' בחולון", ["prefix_R3"]),         # quoted word
        ("token=פרופ' שמעון", "פרופ' שמעון", ["token_R4"]),
        ("בני נוער ; ו-token=פרופ' דני", "בני נוער ; ו-פרופ' דני", ["token_R4"]),           # literary: inside token
        ('כחולה " , prefix= ו " המשמר', 'כחולה " , ו"המשמר', ["prefix_spaced", "prefix_R3"]),  # nrg: spaced tag
    ],
)
def test_artifact_rules_confident(raw, expected, flags):
    assert reconstruct(raw) == (expected, flags)


@pytest.mark.parametrize(
    "raw, cls",
    [
        ("הוא נקנס prefix=ב - דולר וכל", "hyphen_hebrew"),     # the number was lost in the source
        ("בקומה prefix=ה - , 17 בטוח", "hyphen_punct"),         # punctuation reordered before number
        ("מתחזק prefix=ב ?", "punct"),
        ("ירד מאז אוקטובר prefix=מ - prefix=ל - .", "hyphen_prefix"),
        ("עוד בעמוד prefix=ב 7", "number"),                     # no hyphen: original form unknown
        ("להרוויח prefix=כ - - 200 300 אלף", "hyphen_punct"),
    ],
)
def test_artifact_ambiguous_is_not_reconstructed(raw, cls):
    out, flags = reconstruct(raw)
    assert f"prefix_unresolved:{cls}" in flags
    assert "prefix=" not in out
    # Nothing joined, added or reordered: same tokens as the input minus the tag text.
    assert out.split() == [t.removeprefix("prefix=") for t in raw.split()]


def test_artifacts_untouched_text():
    assert reconstruct("שלום עולם , מה נשמע ?") == ("שלום עולם , מה נשמע ?", [])


# ----------------------------------------------------------------------------- Mikra
def test_mikra_basic_and_flags():
    raw = "וַיֹּ֥אמֶר אֱלֹהִ֖ים יְהִ֣י א֑וֹר וַֽיְהִי-אֽוֹר׃ {פ}"
    n = normalize_mikra(raw)
    assert n.text == "ויאמר אלהים יהי אור ויהי אור ."
    assert "parasha_marker:פ" in n.flags and "maqaf_to_space" in n.flags and n.alt is None


@pytest.mark.parametrize(
    "raw, qere, ketiv",
    [
        ("וַיָּשֻׁ֗בוּ (וילונו) [וַיַּלִּ֤ינוּ] עָלָיו֙", "וישבו וילינו עליו", "וישבו וילונו עליו"),       # (K) [Q]
        ("אֶת-[צְפִיעֵ֣י] (צפועי) הַבָּקָ֔ר", "את צפיעי הבקר", "את צפועי הבקר"),                        # [Q] (K)
        ("בִּֽנְהַר-[פְּרָֽת]׃", "בנהר פרת .", "בנהר ."),                                                  # qere only
        ("כִּ֥י (אם) גֹאֵ֖ל", "כי גאל", "כי אם גאל"),                                                     # ketiv only
    ],
)
def test_mikra_ketiv_qere(raw, qere, ketiv):
    n = normalize_mikra(raw)
    assert n.text == qere and n.alt == ketiv


def test_mikra_accent_quotes_and_divine_name():
    n = normalize_mikra("וֵֽאלֹהִ\"ים פָּקֹ֧ד עַל-יְהֹוָ֖ה הַמַּ'יִם׃")
    assert n.text == "ואלהים פקד על יהוה המים ." and "accent_quotes_removed" in n.flags


def test_versification_and_aramaic():
    assert V.verse_refs("Genesis")[0] == (1, 1) and len(V.verse_refs("Genesis")) == 1533
    assert V.aramaic_status("Daniel", 2, 4) == "aramaic_partial"
    assert V.aramaic_status("Daniel", 7, 28) == "aramaic" and V.aramaic_status("Daniel", 8, 1) is None
    assert V.aramaic_status("Ezra", 7, 12) == "aramaic" and V.aramaic_status("Jeremiah", 10, 11) == "aramaic"


# ----------------------------------------------------------------------------- other corpora
def test_hazal_enumerator_entities_and_vocalization():
    n = normalize_hazal("(ב) מגזירה שוה כיצד?", line_start=True)
    assert n.text == "מגזירה שוה כיצד?" and n.flags == ["enumerator_removed"]
    assert normalize_hazal("(השב) את", line_start=True).text == "(השב) את"   # not a numeral
    assert normalize_hazal("חרסן &lt;ושל&gt; וזבה").text == "חרסן <ושל> וזבה"
    assert normalize_hazal("בֵּיצָה שֶׁנּוֹלְדָה").text == "ביצה שנולדה"


def test_rambam_citation_and_numeral():
    n = normalize_medieval('שנאמר + דברים prefix=כ " ד + וכתב', rambam=True)
    assert n.text == 'שנאמר ( דברים כ"ד ) וכתב'
    assert "citation_plus_to_parens" in n.flags and "prefix_R3" in n.flags


def test_haskala_markup():
    raw = "<span style='background-color:#fae6c5'><פרק ה></span> ה"
    assert normalize_haskala(raw).text == "פרק ה ה"
    n = normalize_haskala("על חרבונה, בי <במהד' ב': כי גם> בלי הַכִּיר <!> את {ההשכלה} <> #\"צדק\"#")
    assert n.text == 'על חרבונה, בי בלי הכיר את ההשכלה "צדק"'
    assert {"edition_note_removed", "sic_marker_removed", "braces_removed", "hash_marker_removed"} <= set(n.flags)


def test_modern_header_img_and_whitespace():
    raw = "עדכון  אחרון  -  23:58  28/02/01  ביילין  שוקל  [ IMG ]  להתמודד"
    n = normalize_modern(raw, line_start=True, haaretz=True)
    assert n.text == "ביילין שוקל להתמודד"
    assert {"haaretz_header_removed", "img_marker_removed"} <= set(n.flags)
    # header removal only applies to the first text line of a Haaretz file
    assert normalize_modern(raw, line_start=True, haaretz=False).text.startswith("עדכון אחרון")


# ----------------------------------------------------------------------------- segmentation
def _texts(line, corpus):
    return [line[s:e] for s, e, _ in segment_line(line, corpus)]


def test_segmentation_rules():
    assert _texts("א אומרים, תאכל. ב אומרים, לא תאכל.", "hazal") == ["א אומרים, תאכל.", "ב אומרים, לא תאכל."]
    assert _texts("נאמר (שמות כח, יז. ועוד) כך. סוף", "hazal") == ["נאמר (שמות כח, יז. ועוד) כך.", "סוף"]
    assert _texts("אמר י. ל. מגידוביץ' .", "modern") == ["אמר י. ל. מגידוביץ' ."]          # initials
    assert _texts("1 . פריט . מה ! ! עוד . . . סוף", "modern") == ["1 . פריט .", "מה ! !", "עוד . . .", "סוף"]
    assert _texts("פתח (לא נסגר. שני.", "haskala") == ["פתח (לא נסגר.", "שני."]              # unmatched (
    assert _texts("שנאמר: ויאמר. אחר", "hazal") == ["שנאמר: ויאמר.", "אחר"]                  # colon not a terminator
    assert _texts("  פסוק. עם נקודה׃ {פ} ", "mikra") == ["פסוק. עם נקודה׃ {פ}"]               # verse never split


def test_units_are_never_chunked():
    # segment v2: an over-long sentence stays ONE unit (splitting is a parse-time step)
    line = " ".join(["מילה"] * 407) + ". ועוד משפט."
    units = segment_line(line, "hazal")
    assert [t for *_, t in units] == ["sentence", "sentence"]
    assert sum(len(line[s:e].split()) for s, e, _ in units) == len(line.split())
    assert sentence_spans("   ") == []


# ----------------------------------------------------------------------------- parse-time pieces
def test_pieces_reconstruct_text_and_respect_budget():
    text = " ".join(f"w{i}" for i in range(407))
    ps = plan_pieces(text, 200)
    verify_pieces(text, ps)
    assert [p.tok_end - p.tok_start for p in ps] == [200, 200, 7] and all(p.cost <= 200 for p in ps)
    assert plan_pieces(text, 1000)[0] == plan_pieces(text, 1000)[-1]          # fits → one piece
    assert plan_pieces("   ", 5) == []


def test_pieces_prefer_soft_break_in_second_half():
    toks = [f"w{i}" for i in range(10)]
    toks[7] += ","          # soft break in the second half of the first 9-token window
    toks[2] += ";"          # first half: ignored
    ps = plan_pieces(" ".join(toks), 9)
    assert [(p.tok_start, p.tok_end) for p in ps] == [(0, 8), (8, 10)]


def test_pieces_with_subword_cost_and_oversized_token():
    text = "א בבבבבבבבבב ג ד"
    ps = plan_pieces(text, 4, cost=len)               # cost = characters, as a stand-in for sub-words
    verify_pieces(text, ps)
    assert [text[p.start:p.end] for p in ps] == ["א", "בבבבבבבבבב", "ג ד"]
    assert ps[1].cost == 10 > 4                        # oversized token is isolated, never truncated


def test_piece_rows_link_to_parent_sentence():
    rows = piece_rows("hazal:abc:5:0", "  א, ב ג  ", 2)
    assert [r["sent_id"] for r in rows] == ["hazal:abc:5:0"] * 2 and {r["n_pieces"] for r in rows} == {2}
    assert [(r["norm_char_start"], r["norm_char_end"]) for r in rows] == [(2, 6), (7, 8)]
    with pytest.raises(AssertionError):
        verify_pieces("א ב ג", plan_pieces("א ב", 5))
