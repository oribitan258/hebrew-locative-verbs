"""Team collaboration layer: work plan, partition, assignment, gate, corpora install, fingerprints,
doctor helpers and canonical registration (no model is loaded)."""

from __future__ import annotations

import json
import random
import zipfile
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hebloc.team import plan as P

PLAN_YAML = """
status: draft
coverage: pending
settings: {settings_id: t1, model: base, mst_fix: true, lex_topk: true, budget: 510, batch_size: 32,
           max_batch_subwords: 1024, shard_size: 500}
people: [ori, efrat, adi]
pins: {mikra: ori}
slices:
  mikra: {corpus: mikra}
  hazal: {corpus: hazal}
  medieval: {corpus: medieval}
  haskala: {corpus: haskala}
  modern-blogs: {corpus: modern, subcorpus: [blogs]}
  modern-news-b0: {corpus: modern, subcorpus: [news], bucket: 0, buckets: 2}
  modern-news-b1: {corpus: modern, subcorpus: [news], bucket: 1, buckets: 2, coverage: [A]}
"""


def _plan(tmp_path, text=PLAN_YAML) -> P.Plan:
    p = tmp_path / "plan.yaml"
    p.write_text(text, encoding="utf-8")
    return P.load(p)


def _world(tmp_path, n_news: int = 40, extra_news_subcorpus: str | None = None):
    """documents + units: one unit per document; Modern has blogs and news."""
    docs, units = [], {}
    rnd = random.Random(1)
    def add(corpus, sub=None, src=None):
        doc_id = f"{rnd.getrandbits(48):012x}"
        docs.append({"doc_id": doc_id, "corpus_id": corpus, "subcorpus": sub, "source": src})
        units.setdefault(corpus, []).append({"sent_id": f"{corpus}:{doc_id}:1:0", "doc_id": doc_id,
                                            "text_norm": "א ב", "is_empty_norm": False, "n_tokens_norm": 2})
    for c in ("mikra", "hazal", "medieval", "haskala"):
        add(c)
    for _ in range(3):
        add("modern", "blogs")
    for _ in range(n_news):
        add("modern", "news", "haaretz")
    if extra_news_subcorpus:
        add("modern", extra_news_subcorpus)
    pq.write_table(pa.Table.from_pylist(docs), tmp_path / "documents.parquet")
    for c, rows in units.items():
        (tmp_path / "units" / c).mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(rows), tmp_path / "units" / c / "part-00000.parquet")
    return {"units_root": tmp_path / "units", "documents_path": tmp_path / "documents.parquet"}


# ------------------------------------------------------------------ plan

def test_bucket_function_matches_sql():
    rnd = random.Random(7)
    ids = [f"{rnd.getrandbits(48):012x}" for _ in range(500)]
    con = duckdb.connect()
    sql = con.execute(f"SELECT {P.bucket_sql('d', 20)} FROM (SELECT unnest(?::VARCHAR[]) AS d)", [ids]).fetchall()
    assert [r[0] for r in sql] == [P.doc_bucket(i, 20) for i in ids]


def test_plan_validation(tmp_path):
    p = _plan(tmp_path)
    assert p.status == "draft" and not p.approved and p.slice("modern-news-b1").coverage == ("A",)
    assert p.run_ref(p.slice("mikra")) == "mikra/t1__mikra"
    for bad in (PLAN_YAML.replace("{corpus: hazal}", "{corpus: klingon}"),
                PLAN_YAML.replace("bucket: 0, buckets: 2", "bucket: 0"),
                PLAN_YAML.replace("pins: {mikra: ori}", "pins: {mikra: zed}"),
                PLAN_YAML.replace("status: draft", "status: maybe")):
        with pytest.raises(ValueError):
            _plan(tmp_path, bad)


def test_partition_complete_and_disjoint(tmp_path):
    w = _world(tmp_path)
    r = P.check_partition(_plan(tmp_path), **w)
    assert r["ok"] and r["per_corpus"]["modern"] == {"units": 43, "in_no_slice": 0, "in_several_slices": 0}
    assert r["coverage_B_excludes"] == ["modern-news-b1"]


def test_partition_detects_uncovered_and_overlapping_units(tmp_path):
    w = _world(tmp_path, extra_news_subcorpus="tapuz")              # tapuz is in no slice
    assert P.check_partition(_plan(tmp_path), **w)["per_corpus"]["modern"]["in_no_slice"] == 1
    overlap = PLAN_YAML + "  modern-all-news: {corpus: modern, subcorpus: [news]}\n"
    r = P.check_partition(_plan(tmp_path, overlap), **_world(tmp_path))
    assert not r["ok"] and r["per_corpus"]["modern"]["in_several_slices"] == 40


def test_slice_units_are_ordered_and_selected(tmp_path):
    w = _world(tmp_path)
    p = _plan(tmp_path)
    b0 = P.slice_units(p.slice("modern-news-b0"), **w)
    b1 = P.slice_units(p.slice("modern-news-b1"), **w)
    assert len(b0) + len(b1) == 40 and not {s for s, _ in b0} & {s for s, _ in b1}
    assert [s for s, _ in b0] == sorted(s for s, _ in b0)
    assert all(P.doc_bucket(s.split(":")[1], 2) == 0 for s, _ in b0)
    assert len(P.slice_units(p.slice("modern-news-b0"), limit=3, **w)) == 3


def test_assignment_is_balanced_pinned_and_deterministic(tmp_path):
    p = _plan(tmp_path)
    sizes = {s.id: {"subwords": n} for s, n in zip(p.slices, [5, 90, 40, 70, 10, 60, 60])}
    a = P.assign(p, sizes, "A")
    assert "mikra" in a["people"]["ori"]["slices"]
    got = sorted(x for d in a["people"].values() for x in d["slices"])
    assert got == sorted(s.id for s in p.slices)                          # every slice exactly once
    assert a["imbalance"] <= 1.15 and a == P.assign(p, sizes, "A")
    b = P.assign(p, sizes, "B")
    assert "modern-news-b1" not in [x for d in b["people"].values() for x in d["slices"]]


def test_parse_refuses_in_draft_and_for_wrong_owner(tmp_path, monkeypatch):
    from hebloc.team import work as W

    draft = _plan(tmp_path)
    approved = _plan(tmp_path, PLAN_YAML.replace("status: draft", "status: approved").replace("coverage: pending", "coverage: B"))
    monkeypatch.setattr(P, "load", lambda *a, **k: draft)
    with pytest.raises(W.PlanRefusal, match="not approved"):
        W.run_slice("hazal", "efrat")
    with pytest.raises(W.PlanRefusal, match="not in the plan"):
        W.run_slice("hazal", "mallory")
    monkeypatch.setattr(P, "load", lambda *a, **k: approved)
    monkeypatch.setattr(P, "load_work_plan", lambda *a, **k: {"assignment": {"B": {"people": {
        "ori": {"slices": ["mikra", "hazal"]}, "efrat": {"slices": ["medieval"]}, "adi": {"slices": []}}}}})
    with pytest.raises(W.PlanRefusal, match="assigned to 'ori'"):
        W.run_slice("hazal", "efrat")
    with pytest.raises(W.PlanRefusal, match="not part of coverage option B"):
        W.run_slice("modern-news-b1", "adi")


def test_register_rewrites_only_the_real_key(tmp_path, monkeypatch):
    from hebloc.store import runs as R
    from hebloc.team import work as W

    cfg = tmp_path / "annotations.yaml"
    cfg.write_text("# header\n# Example:\n#   canonical:\n#     mikra: [x]\n\ncanonical: {}\n", encoding="utf-8")
    monkeypatch.setattr(R, "ANNOTATIONS_CONFIG", cfg)
    approved = _plan(tmp_path, PLAN_YAML.replace("status: draft", "status: approved").replace("coverage: pending", "coverage: A"))
    monkeypatch.setattr(P, "load", lambda *a, **k: approved)
    monkeypatch.setattr(P, "status", lambda plan, *a, **k: [
        {"slice": "mikra", "run": "mikra/t1__mikra", "complete": True, "checks_ok": True},
        {"slice": "hazal", "run": "hazal/t1__hazal", "complete": False, "checks_ok": False}])
    incomplete = {"complete": False, "missing": ["hazal"], "invalid_or_duplicate": [], "units_in_more_than_one_run": 0,
                  "units_present": 1, "units_expected": 2}
    monkeypatch.setattr(W, "completeness", lambda *a, **k: incomplete)
    monkeypatch.setattr(P, "load_work_plan", lambda *a, **k: {})
    with pytest.raises(W.PlanRefusal, match="not complete"):
        W.register(write=True)
    assert R.load_registry(cfg) == {}
    assert W.register(write=False)["entries"] == {"mikra": ["mikra/t1__mikra"]}      # preview still works
    monkeypatch.setattr(W, "completeness", lambda *a, **k: incomplete | {"complete": True})
    r = W.register(write=True)
    text = cfg.read_text(encoding="utf-8")
    assert r["slices_not_ready"] == ["hazal"] and text.startswith("# header\n# Example:\n#   canonical:")
    assert R.load_registry(cfg) == {"mikra": ["mikra/t1__mikra"]}


# (corpora install and identity: tests/test_corpora_install.py)


# ------------------------------------------------------------------ fingerprints / doctor

def test_fingerprint_is_order_independent_and_change_sensitive(tmp_path):
    from hebloc.team import fingerprint as F

    w = _world(tmp_path)
    a = F.compute(**w)
    t = pq.read_table(w["units_root"] / "modern" / "part-00000.parquet")
    pq.write_table(t.take(list(reversed(range(t.num_rows)))), w["units_root"] / "modern" / "part-00000.parquet")
    assert F.compute(**w) == a and F.compare(a, a) == []
    rows = t.to_pylist()
    rows[0]["text_norm"] = "א ג"
    pq.write_table(pa.Table.from_pylist(rows), w["units_root"] / "modern" / "part-00000.parquet")
    b = F.compute(**w)
    assert b["tables"]["units/modern"] != a["tables"]["units/modern"]
    assert any(p.startswith("units/modern") for p in F.compare(b, a))


def test_installed_packages_match_uv_lock():
    from importlib import metadata

    from hebloc.team.doctor import KEY_PACKAGES, _locked_versions

    locked = _locked_versions()
    for p in KEY_PACKAGES:
        assert metadata.version(p).split("+")[0] == locked[p], p


# ------------------------------------------------------------------ real repository data (skipped if absent)

def test_real_plan_partitions_all_units():
    from hebloc.catalog import DOCUMENTS_PATH

    if not DOCUMENTS_PATH.exists():
        pytest.skip("no catalog")
    r = P.check_partition(P.load())
    assert r["ok"], r["per_corpus"]


def test_real_work_plan_matches_census():
    from hebloc.paths import ANNOTATIONS_DIR

    census = ANNOTATIONS_DIR / "pilot" / "results" / "piece_census.json"
    if not (P.WORK_PLAN_JSON.exists() and census.exists()):
        pytest.skip("no work plan or census")
    wp, cen = P.load_work_plan(), json.loads(census.read_text(encoding="utf-8"))["per_corpus"]
    for c, d in cen.items():
        assert sum(s["subwords"] for s in wp["sizes"].values() if s["corpus"] == c) == d["subwords"], c
    assert wp["sizes_key"] == P.load().sizes_key, "slices/model changed: run hebloc plan measure"


def test_reassign_reuses_sizes_and_refuses_when_slices_change(tmp_path):
    p = _plan(tmp_path)
    sizes = {s.id: {"corpus": s.corpus, "units": 1, "ws_tokens": 1, "subwords": n, "units_over_budget": 0}
             for s, n in zip(p.slices, [5, 90, 40, 70, 10, 60, 60])}
    j, md = tmp_path / "wp.json", tmp_path / "wp.md"
    P.write_work_plan(p, {"tokenizer": "t", "sizes": sizes}, j, md)
    approved = _plan(tmp_path, PLAN_YAML.replace("status: draft", "status: approved").replace("coverage: pending", "coverage: B"))
    wp = P.reassign(approved, j, md)
    assert wp["sizes"] == sizes and "Plan status: `approved`, coverage: `B`" in md.read_text(encoding="utf-8")
    changed = _plan(tmp_path, PLAN_YAML.replace("buckets: 2", "buckets: 3"))
    with pytest.raises(ValueError, match="re-measure"):
        P.reassign(changed, j, md)


def test_merge_reports_damaged_or_conflicting_bundles_without_crashing(tmp_path, monkeypatch):
    """Regression (D-038 test): a corrupted member used to crash `hebloc merge` instead of failing it."""
    from hebloc.store.bundle import MANIFEST_NAME
    from hebloc.store.io import file_sha256
    from hebloc.team import work as W

    monkeypatch.setattr(W, "MERGE_REPORT", tmp_path / "merge_report.json")

    def fake_bundle(path, run, payload=b"x" * 1000):
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(MANIFEST_NAME, json.dumps({"run": run, "files": {"annotations/a.parquet": {"sha256": "0"}}}))
            zf.writestr("annotations/a.parquet", payload)

    good = tmp_path / "in" / "a.zip"
    good.parent.mkdir()
    fake_bundle(good, "rehearsal/r1")
    (tmp_path / "in" / "a.zip.sha256").write_text("0" * 64 + "  a.zip\n")      # sidecar mismatch
    crc = tmp_path / "in" / "b.zip"
    fake_bundle(crc, "rehearsal/r2")
    data = bytearray(crc.read_bytes())
    i = data.index(b"annotations/a.parquet") + len(b"annotations/a.parquet") + 5    # inside the compressed member
    data[i] ^= 0xFF
    crc.write_bytes(bytes(data))
    other = tmp_path / "in2" / "c.zip"
    other.parent.mkdir()
    fake_bundle(other, "rehearsal/r3")
    shutil_copy = (tmp_path / "in2" / "d.zip")
    fake_bundle(shutil_copy, "rehearsal/r3", payload=b"y" * 1000)                  # same run, different bytes
    rep = W.merge([tmp_path / "in", tmp_path / "in2"])
    rows = {Path(r["bundle"]).name: r for r in rep["bundles"]}
    assert not rep["ok"]
    assert "does not match its .sha256" in str(rows["a.zip"]["problems"])
    assert not rows["b.zip"]["ok"]                                            # failed, did not raise
    assert "CONFLICT" in str(rows["c.zip"]["problems"]) and "CONFLICT" in str(rows["d.zip"]["problems"])
    assert file_sha256(other) != file_sha256(shutil_copy)
