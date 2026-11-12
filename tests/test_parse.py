"""M3 parse layer: checks, token derivation, the MST fix, variants, BHSA reader — no model needed."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from hebloc.parse.checks import coverage_problems, tree_problems
from hebloc.parse.tokens import derive_rows

FIX = json.loads((Path(__file__).parent / "fixtures" / "dicta_base_example.json").read_text(encoding="utf-8"))["output"]


def test_real_output_passes_checks():
    assert coverage_problems(FIX["text"], FIX) == []
    assert tree_problems(FIX) == []
    rows = derive_rows(FIX["text"], {"sent_id": "x", "piece_idx": 0, "n_pieces": 1, "norm_char_start": 0}, FIX, "ok", 0)
    assert all(r["piece_tree_valid"] for r in rows)


def test_truncated_output_is_detected():
    out = copy.deepcopy(FIX)
    out["tokens"] = out["tokens"][:-2]            # model silently dropped the end of the input
    out["root_idx"] = 1
    assert any("uncovered" in p for p in coverage_problems(FIX["text"], out))


def _spans_out(text: str, spans: list[tuple[int, int]]) -> dict:
    return {"text": text, "tokens": [{"token": text[s:e], "offsets": {"start": s, "end": e}} for s, e in spans]}


def test_d043_diaeresis_pair_is_excused_and_reported():
    # exactly what Dicta returned for modern:de177c697f4e:1564:1 (tapuz): "¨¨" -> one [UNK] on the 2nd "¨"
    text = ".·:*¨¨*:·."
    out = _spans_out(text, [(0, 1), (1, 2), (2, 3), (3, 4), (5, 6), (6, 7), (7, 8), (8, 9), (9, 10)])
    excused: list[int] = []
    assert coverage_problems(text, out, excused) == []
    assert excused == [4]


@pytest.mark.parametrize("text, spans", [
    ("א ¨ ב", [(0, 1), (4, 5)]),                    # a single uncovered "¨"
    ("*¨¨*", [(0, 1), (3, 4)]),                      # the pair dropped entirely
    ("*¨¨¨*", [(0, 1), (3, 4), (4, 5)]),             # a triple: not the verified shape
    ("*¨¨*", [(0, 1), (2, 4)]),                      # 2nd "¨" not a one-character word
    ("*¨*", [(0, 1), (2, 3)]),                       # another character in the same place
    ("*´´*", [(0, 1), (2, 3), (3, 4)]),              # a different spacing accent (U+00B4)
    ("אב¨¨", [(0, 1), (3, 4)]),                      # an uncovered letter is never excused
])
def test_d043_exception_is_strictly_limited(text, spans):
    excused: list[int] = []
    assert any("uncovered" in p for p in coverage_problems(text, _spans_out(text, spans), excused))


def test_cycle_and_two_roots_are_detected():
    out = copy.deepcopy(FIX)
    out["tokens"][2]["syntax"]["dep_head_idx"] = 3
    out["tokens"][3]["syntax"]["dep_head_idx"] = 2
    assert "cycle" in tree_problems(out)
    out = copy.deepcopy(FIX)
    out["tokens"][0]["syntax"]["dep_head_idx"] = -1
    assert any(p.startswith("roots=") for p in tree_problems(out))


def test_derive_rows_keeps_provenance():
    text = "XX " + FIX["text"]                       # the piece starts at offset 3 of its unit
    piece = {"sent_id": "modern:abc:1:0", "piece_idx": 0, "n_pieces": 1, "norm_char_start": 3}
    rows = derive_rows(text, piece, json.dumps(FIX, ensure_ascii=False), "ok", 0)
    assert len(rows) == len(FIX["tokens"])
    assert all(text[r["char_start"]:r["char_end"]] == r["surface"] for r in rows)
    assert rows[0]["surface"] == "הילד" and rows[0]["prefix"] == "ה" and rows[0]["host"] == "ילד"
    assert rows[0]["ws_idx"] == 1 and rows[1]["head"] == -1 and rows[1]["head_sent"] == -1
    assert rows[1]["upos"] == "VERB" and rows[1]["feats"] == "Gender=Masc|Number=Sing|Person=3|Tense=Past"


def test_mst_fix_repairs_cycle_in_unpadded_row():
    torch = pytest.importorskip("torch")
    from hebloc.parse import dicta_fixes
    from hebloc.parse.dicta_code import BertForSyntaxParsing as S

    # [CLS] w1 w2 w3 [SEP], no padding. Best heads: w1→w2, w2→w1 (a cycle), w3→root.
    big, small = 9.0, 0.0
    sc = torch.full((1, 5, 5), small)
    sc[0, 1, 2] = big; sc[0, 2, 1] = big; sc[0, 3, 0] = big
    sc[0, 1, 3] = 5.0; sc[0, 2, 3] = 4.0
    mask = torch.zeros((1, 1, 5))
    orig = dicta_fixes._ORIGINAL["mst_seq_len"](sc.clone(), mask.clone())[0].tolist()
    fixed = dicta_fixes.compute_mst_tree_fixed(sc.clone(), mask.clone())[0].tolist()

    def has_cycle(h):
        for i in (1, 2, 3):
            j, steps = i, 0
            while j != 0 and steps < 6:
                j, steps = h[j], steps + 1
            if steps >= 6:
                return True
        return False
    assert has_cycle(orig)            # the upstream bug: no repair when the row has no padding
    assert not has_cycle(fixed)
    # with padding, the fixed function behaves exactly like the original
    sc2 = torch.cat([sc, torch.full((1, 5, 1), small)], dim=2)
    sc2 = torch.cat([sc2, torch.full((1, 1, 6), small)], dim=1)
    mask2 = torch.tensor([[[0, 0, 0, 0, 0, -1e9]]])
    assert dicta_fixes._ORIGINAL["mst_seq_len"](sc2.clone(), mask2).tolist() == dicta_fixes.compute_mst_tree_fixed(sc2.clone(), mask2).tolist()
    assert S.compute_mst_tree is not None


def test_tf_reader_and_ortho_groups(tmp_path):
    from hebloc.pilot.bhsa import _spec, ortho_groups, read_tf

    p = tmp_path / "f.tf"
    p.write_text("@node\n@valueType=str\n\nא\n3\tב\n5-6\tג\\tד\n", encoding="utf-8")
    data, is_edge = read_tf(p)
    assert not is_edge and data == {1: "א", 3: "ב", 5: "ג\tד", 6: "ג\tד"}
    assert _spec("1-3,7") == [1, 2, 3, 7]
    words = [  # וַיֹּאמֶר אֱלֹהִים ; ketiv/qere on the last word
        {"w": 1, "g_cons_utf8": "ו", "trailer_utf8": "", "sp": "conj"},
        {"w": 2, "g_cons_utf8": "יאמר", "trailer_utf8": " ", "sp": "verb"},
        {"w": 3, "g_cons_utf8": "אלהים", "trailer_utf8": " ", "sp": "subs"},
        {"w": 4, "g_cons_utf8": "וילונו", "trailer_utf8": " ", "qere_utf8": "וַיַּלִּינוּ", "qere_trailer_utf8": " ", "sp": "verb"},
    ]
    q = ortho_groups(words, "qere")
    assert [g["cons"] for g in q] == ["ויאמר", "אלהימ", "וילינו"] and q[0]["prefix_cons"] == "ו" and q[2]["is_kq"]
    assert [g["cons"] for g in ortho_groups(words, "ketiv")][-1] == "וילונו"


def test_mikra_variants_reproduce_defaults():
    from hebloc.normalize import normalize_mikra
    from hebloc.pilot.variants import mikra_text, strip_points

    raw = "וַיָּשֻׁ֗בוּ (וילונו) [וַיַּלִּ֤ינוּ] עָלָיו֙ וַֽיְהִי-אֽוֹר׃ {פ}"
    n = normalize_mikra(raw)
    assert mikra_text(raw) == n.text and mikra_text(raw, qere=False) == n.alt
    assert mikra_text(raw, maqaf="keep").count("-") == 1 and not mikra_text(raw, sof_pasuq="drop").endswith(".")
    voc = mikra_text(raw, strip_points=False)
    assert voc != n.text and strip_points(voc) == n.text


def test_pinned_models_verify_if_present():
    from hebloc.parse import models as M

    for name, m in M.registry()["models"].items():
        if (M.MODELS_DIR / m["dir"] / "model.safetensors").exists():
            assert M.verify(name) == [], name
