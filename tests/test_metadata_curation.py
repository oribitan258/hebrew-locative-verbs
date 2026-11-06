"""Unit tests for path-metadata parsers and curation rules (synthetic names = real patterns)."""

from __future__ import annotations

import pytest

from hebloc.curation import load_curation
from hebloc.inventory import doc_id_for
from hebloc.metadata import parse_metadata


def test_mikra():
    m = parse_metadata("mikra", "Tanakh - Writings - Song of Songs.txt")
    assert (m["section"], m["work"], m["meta_issue"]) == ("Writings", "Song of Songs", None)
    assert parse_metadata("mikra", "Genesis.txt")["meta_issue"]


def test_hazal_mishnah_and_commentary():
    m = parse_metadata("hazal", "Mishnah - Seder Moed - Mishnah Beitzah.txt")
    assert (m["subcorpus"], m["section"], m["work"], m["tractate"]) == ("Mishnah", "Seder Moed", "Mishnah Beitzah", "Beitzah")
    c = parse_metadata("hazal", "Midrash - Aggadic Midrash - Midrash Rabbah - Commentary - Yedei Moshe - Yedei Moshe on Shemot Rabbah.txt")
    assert (c["section"], c["commentary"], c["base_work"], c["series"]) == ("Aggadah", "Yedei Moshe", "Shemot Rabbah", "Midrash Rabbah")
    s = parse_metadata("hazal", "Midrash - Seder Olam Zutta.txt")
    assert s["work"] == "Seder Olam Zutta" and s["meta_issue"] is None


def test_medieval():
    r = parse_metadata("medieval", "Rambam/AHAVA/brkowt/000001td00017000091000000prk_a.txt")
    assert (r["section"], r["hilchot"], r["ext_id"], r["unit_label"]) == ("AHAVA", "brkowt", "000001", "prk_a")
    t = parse_metadata("medieval", "Thought/Jewish Thought - Rishonim - Duties of the Heart - Commentary - Pat Lechem.txt")
    assert (t["era_label"], t["base_work"], t["commentary"]) == ("Rishonim", "Duties of the Heart", "Pat Lechem")
    u = parse_metadata("medieval", "Musar/Musar - Ahavat David.txt")
    assert u["era_label"] is None and u["work"] == "Ahavat David"


def test_haskala():
    m = parse_metadata("haskala", "אברהם מאפו--אהבת ציון--שנת 1853--ספרות יפה--Ytext1044001.txt")
    assert (m["author"], m["work"], m["year"], m["genre"], m["ext_id"]) == ("אברהם מאפו", "אהבת ציון", 1853, "ספרות יפה", "Ytext1044001")
    assert "5" in parse_metadata("haskala", "bad--name.txt")["meta_issue"]


def test_modern():
    assert parse_metadata("modern", "news/themarker/20020512/1.txt")["date"] == "2002-05-12"
    a7 = parse_metadata("modern", "news/a7/articles/x/1000.txt")
    assert (a7["source"], a7["section"]) == ("a7", "articles/x")
    assert parse_metadata("modern", "kneset/16/00133504.txt")["source"] == "knesset_16"
    assert parse_metadata("modern", "literary/T.txt")["source"] == "translated"
    assert parse_metadata("modern", "blogs/0.txt")["meta_issue"] is None


@pytest.mark.parametrize(
    "corpus, rel, stratum, status",
    [
        ("hazal", "Midrash - Aggadah - Midrash Rabbah - Commentary - Rashi - Rashi on Bereshit Rabbah.txt", "hazal.commentary", "out_of_period"),
        ("hazal", "Midrash - Aggadah - Yalkut Shimoni on Torah.txt", "hazal.late_anthology", "out_of_period"),
        ("hazal", "Midrash - Aggadah - Midrash Rabbah - Bereishit Rabbah.txt", "hazal.aggadic_midrash", "in_period"),
        ("hazal", "Midrash - Halakhah - Sifra.txt", "hazal.halakhic_midrash", "in_period"),
        ("medieval", "Thought/Jewish Thought - Rishonim - Kuzari.txt", "medieval.thought_translated", "in_period"),
        ("medieval", "Thought/Jewish Thought - Rishonim - Duties of the Heart - Duties of the Heart.txt", "medieval.thought_translated", "in_period"),
        ("medieval", "Thought/Jewish Thought - Rishonim - Duties of the Heart - Commentary - Tov haLevanon.txt", "medieval.later_commentary", "out_of_period"),
        ("medieval", "Thought/Jewish Thought - Rishonim - Akeidat Yitzchak.txt", "medieval.thought", "in_period"),
        ("medieval", "Musar/Musar - Modern - Sichot Avodat Levi.txt", "medieval.post_medieval", "out_of_period"),
        ("medieval", "Musar/Musar - Letter from Ramban to his Son.txt", "medieval.musar_unverified", "needs_review"),
        ("medieval", "Musar/Musar - Orchot Chaim L'HaRosh.txt", "medieval.musar", "in_period"),
        ("haskala", "x--y--שנת 1900--ספרות מדע--Ytext1.txt", "haskala.science", "in_period"),
        ("modern", "news/haaretz/6/0.7z.log", "modern.auxiliary", "out_of_period"),
        ("modern", "news/haaretz/6/100.txt", "modern.news.haaretz", "in_period"),
        ("modern", "medical/questions/text_utf/a.txt", "modern.medical", "in_period"),
        ("modern", "something_new/x.txt", "modern.unclassified", "needs_review"),
    ],
)
def test_curation_rules(corpus, rel, stratum, status):
    rule = load_curation().classify(corpus, rel)
    assert (rule.stratum, rule.period_status) == (stratum, status)


def test_doc_id_stable():
    assert doc_id_for("Mikra/Tanakh - Torah - Genesis.txt") == doc_id_for("Mikra/Tanakh - Torah - Genesis.txt")
    assert len(doc_id_for("x")) == 12
