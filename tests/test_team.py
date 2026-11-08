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
    r = W.register(write=True)
    text = cfg.read_text(encoding="utf-8")
    assert r["slices_not_ready"] == ["hazal"] and text.startswith("# header\n# Example:\n#   canonical:")
    assert R.load_registry(cfg) == {"mikra": ["mikra/t1__mikra"]}


# ------------------------------------------------------------------ corpora install

def _fake_corpora(root: Path) -> None:
    for i, f in enumerate(("Mikra", "Hazal", "Medieval", "Haskala", "Modern")):
        (root / f / "sub").mkdir(parents=True)
        (root / f / "sub" / f"{i}.txt").write_bytes(f"text {i}\n".encode())


def test_corpora_install_from_folder_and_zip(tmp_path):
    from hebloc.baseline import compute_baseline, make_anchor, write_anchor
    from hebloc.team import corpora as C

    src = tmp_path / "download" / "inner"
    _fake_corpora(src)
    (tmp_path / "download" / "README.txt").write_text("not a corpus file")
    anchor = tmp_path / "anchor.json"
    write_anchor(make_anchor(compute_baseline(src, workers=1, progress=False)), anchor)
    kw = {"baseline_path": tmp_path / "b1.parquet", "anchor_path": anchor, "workers": 1}
    r = C.install(tmp_path / "download", tmp_path / "c1" / "corpora", **kw)
    assert r["verify"]["ok"] and r["verify"]["files"] == 5 and (src / "Mikra").is_dir()   # original kept
    with pytest.raises(FileExistsError):
        C.install(tmp_path / "download", tmp_path / "c1" / "corpora", **kw)
    z = tmp_path / "corpora.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in src.rglob("*"):
            if f.is_file():
                zf.write(f, "top/" + f.relative_to(src).as_posix())
    kw["baseline_path"] = tmp_path / "b2.parquet"
    assert C.install(z, tmp_path / "c2" / "corpora", **kw)["verify"]["ok"]
    (tmp_path / "c2" / "corpora" / "Mikra" / "sub" / "0.txt").write_bytes(b"edited\n")
    assert not C.verify(tmp_path / "c2" / "corpora", workers=1, write=False, anchor_path=anchor)["ok"]


def test_corpora_install_rejects_zip_slip(tmp_path):
    from hebloc.team import corpora as C

    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("../evil.txt", "x")
    with pytest.raises(ValueError, match="unsafe"):
        C.install(z, tmp_path / "corpora", verify_after=False)


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
