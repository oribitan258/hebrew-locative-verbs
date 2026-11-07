"""M4 data layer: per-shard tokens, run validation, DuckDB catalog, canonical registry, integrity,
bundles and CoNLL-U export. Synthetic runs are built from a real Dicta output fixture (no model)."""

from __future__ import annotations

import copy
import json
import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hebloc.parse.checks import run_fingerprint, validate_run
from hebloc.parse.run import INPUTS_SCHEMA, RAW_SCHEMA, read_run
from hebloc.parse.tokens import TOKENS_SCHEMA, derive, migrate_legacy, read_tokens, tokens_status
from hebloc.pieces import PIECES_SCHEMA, piece_rows
from hebloc.store.io import atomic_write_json, atomic_write_parquet

FIX = json.loads((Path(__file__).parent / "fixtures" / "dicta_base_example.json").read_text(encoding="utf-8"))["output"]
TEXT = FIX["text"]
N_WS = len(TEXT.split())
DOC = {"mikra": "0123456789ab", "hazal": "abcdefabcdef"}


def sid(corpus: str, line: int) -> str:
    return f"{corpus}:{DOC[corpus]}:{line}:0"


def write_shard(run_dir: Path, name: str, units: list[tuple[str, str]], statuses: dict | None = None,
                commit: bool = True) -> None:
    """units: (sent_id, text). Texts are FIX text repeated → pieces of exactly FIX text (budget = N_WS)."""
    import hashlib

    statuses = statuses or {}
    inputs, pieces, raws = [], [], []
    for s, text in units:
        inputs.append({"sent_id": s, "text": text, "text_sha1": hashlib.sha1(text.encode()).hexdigest()})
        for r in piece_rows(s, text, N_WS, None, "ws_token"):
            pieces.append(r)
            st = statuses.get((s, r["piece_idx"]), "ok")
            raws.append({"sent_id": s, "piece_idx": r["piece_idx"], "status": st, "compute_mst": True,
                         "error": "boom" if st == "error" else None,
                         "raw_json": None if st == "error" else json.dumps(FIX, ensure_ascii=False)})
    atomic_write_parquet(pa.Table.from_pylist(inputs, schema=INPUTS_SCHEMA), run_dir / "inputs" / f"{name}.parquet")
    atomic_write_parquet(pa.Table.from_pylist(pieces, schema=PIECES_SCHEMA), run_dir / "pieces" / f"{name}.parquet")
    atomic_write_parquet(pa.Table.from_pylist(raws, schema=RAW_SCHEMA), run_dir / "dicta_raw" / f"{name}.parquet")
    if commit:
        atomic_write_json({"key": f"k-{name}-{len(units)}", "units": len(units)}, run_dir / "_shards" / f"{name}.json")


def make_run(root: Path, collection: str, run_id: str, shards: dict[str, list[tuple[str, str]]],
             variant: str = "default", statuses: dict | None = None) -> Path:
    from hebloc.normalize import NORM_VERSION
    from hebloc.segment import SEGMENT_VERSION

    d = root / collection / "runs" / run_id
    for name, units in shards.items():
        write_shard(d, name, units, statuses)
    atomic_write_json({"run_id": run_id, "variant": variant, "model": "base", "repo": "dicta-il/dictabert-joint",
                       "revision": "7b1256fc0846", "norm_version": NORM_VERSION, "segment_version": SEGMENT_VERSION,
                       "piece_version": "1", "runner_version": "1", "fixes": ["mst_seq_len"], "shards": len(shards),
                       "units": sum(len(u) for u in shards.values()), "status": {"error": 0}}, d / "run.json")
    return d


def make_units(root: Path, units: list[tuple[str, str]]) -> Path:
    from hebloc.normalize import NORM_VERSION
    from hebloc.segment import SEGMENT_VERSION
    from hebloc.units import UNITS_SCHEMA

    by_c: dict[str, list[dict]] = {}
    for s, text in units:
        c, doc, line, k = s.split(":")
        by_c.setdefault(c, []).append({
            "sent_id": s, "corpus_id": c, "doc_id": doc, "line_no": int(line), "k": int(k), "unit_type": "sentence",
            "char_start": 0, "char_end": len(text), "ref": f"ref {line}", "text_raw": text, "text_norm": text,
            "norm_flags": [], "is_empty_norm": False, "n_tokens_norm": len(text.split()), "stratum": f"{c}.core",
            "in_full_view": True, "in_curated_view": c == "mikra", "norm_version": NORM_VERSION,
            "segment_version": SEGMENT_VERSION})
    for c, rows in by_c.items():
        atomic_write_parquet(pa.Table.from_pylist(rows, schema=UNITS_SCHEMA), root / c / "part-00000.parquet")
        atomic_write_json({"units": len(rows)}, root / c / "_manifest.json")
    return root


@pytest.fixture
def world(tmp_path):
    """data/{units, annotations} + config with one 2-shard run over mikra and hazal units."""
    units = [(sid("mikra", 1), TEXT), (sid("mikra", 2), TEXT + " " + TEXT), (sid("hazal", 1), TEXT)]
    data = tmp_path / "data"
    make_units(data / "units", units)
    run = make_run(data / "annotations", "pilot", "r1", {"shard-00000": units[:2], "shard-00001": units[2:]})
    cfg = tmp_path / "annotations.yaml"
    cfg.write_text("canonical: {}\n", encoding="utf-8")
    return {"data": data, "run": run, "units": units, "config": cfg, "ann": data / "annotations",
            "paths": {"units_root": data / "units", "annotations_root": data / "annotations", "config": cfg,
                      "documents_path": tmp_path / "no_documents.parquet"}}


# ------------------------------------------------------------------ io / schemas

def test_atomic_writes_leave_no_temp_and_refuse_corpora(tmp_path):
    from hebloc.paths import CORPORA_DIR

    atomic_write_json({"a": 1}, tmp_path / "x" / "m.json")
    assert [p.name for p in (tmp_path / "x").iterdir()] == ["m.json"]
    with pytest.raises(PermissionError):
        atomic_write_json({}, CORPORA_DIR / "never.json")


def test_schema_registry_detects_drift(tmp_path):
    from hebloc.store.schemas import check_schema, registry

    assert set(registry()) == {"documents", "units", "inputs", "pieces", "dicta_raw", "tokens"}
    ok = tmp_path / "ok.parquet"
    pq.write_table(TOKENS_SCHEMA.empty_table(), ok)
    assert check_schema(ok, "tokens") == []
    bad = tmp_path / "bad.parquet"
    pq.write_table(TOKENS_SCHEMA.empty_table().drop(["ner"]).set_column(0, "sent_id", pa.array([], pa.int32())), bad)
    probs = check_schema(bad, "tokens")
    assert any("missing columns ['ner']" in p for p in probs) and any("wrong types" in p for p in probs)


# ------------------------------------------------------------------ tokens per shard

def test_tokens_are_derived_per_shard_and_incrementally(world):
    run = world["run"]
    s1 = derive(run)
    assert (s1["shards"], s1["derived"], s1["skipped_up_to_date"]) == (2, 2, 0)
    assert s1["rows"] == 4 * len(FIX["tokens"])           # mikra:1 (1 piece) + mikra:2 (2) + hazal:1 (1)
    assert derive(run)["derived"] == 0                     # nothing changed → nothing rewritten
    write_shard(run, "shard-00001", [(sid("hazal", 1), TEXT + " " + TEXT)])   # source changed
    s3 = derive(run)
    assert (s3["derived"], s3["skipped_up_to_date"]) == (1, 1)
    t = read_tokens(run)
    two = t.filter(pa.compute.equal(t["sent_id"], sid("mikra", 2))).to_pylist()
    assert [r["piece_idx"] for r in two] == [0] * len(FIX["tokens"]) + [1] * len(FIX["tokens"])
    assert [r["sent_word_idx"] for r in two] == list(range(2 * len(FIX["tokens"])))
    assert all(r["n_pieces"] == 2 for r in two)


def test_error_piece_makes_later_unit_indices_unknown(tmp_path):
    s = sid("mikra", 9)
    run = make_run(tmp_path, "pilot", "e", {"shard-00000": [(s, TEXT + " " + TEXT)]}, statuses={(s, 0): "error"})
    derive(run)
    rows = read_tokens(run).to_pylist()
    assert {r["piece_idx"] for r in rows} == {1}                      # the error piece has no tokens
    assert all(r["sent_word_idx"] is None for r in rows)              # offset unknown → null, not wrong
    assert all(r["head_sent"] is None or r["head_sent"] == -1 for r in rows)
    rep = validate_run(run, write=False)
    assert rep["ok"] and rep["errors_logged"] == 1                    # an error is logged, not an integrity failure


def test_uncommitted_shard_is_never_read_and_fails_validation(world):
    run = world["run"]
    write_shard(run, "shard-00002", [(sid("mikra", 3), TEXT)], commit=False)   # interrupted session
    assert read_run(run, "inputs").num_rows == 3
    rep = validate_run(run, write=False)
    assert not rep["ok"] and rep["checks"]["uncommitted_part_files"] == 3
    derive(run)
    assert tokens_status(run)["orphans"] == []


def test_orphan_tokens_are_removed(world):
    run = world["run"]
    derive(run)
    (run / "_shards" / "shard-00001.json").unlink()        # shard no longer committed
    assert tokens_status(run)["orphans"] == ["shard-00001"]
    assert derive(run)["orphans_removed"] == ["shard-00001"]
    assert not (run / "tokens" / "shard-00001.parquet").exists()


def test_migrate_legacy_single_file(world):
    run = world["run"]
    derive(run)
    legacy = read_tokens(run)
    for p in (run / "tokens").glob("shard-*.parquet"):
        p.unlink()
    pq.write_table(legacy, run / "tokens" / "tokens.parquet")
    r = migrate_legacy(run)
    assert r["identical"] and r["rows"] == legacy.num_rows and not (run / "tokens" / "tokens.parquet").exists()
    bad = legacy.slice(1)
    pq.write_table(bad, run / "tokens" / "tokens.parquet")
    with pytest.raises(RuntimeError):
        migrate_legacy(run)
    assert (run / "tokens" / "tokens.parquet").exists()     # kept when it differs


def test_validate_run_reports_fingerprint_and_rederivation(world):
    run = world["run"]
    rep = validate_run(run, expected=dict(world["units"]))
    assert rep["ok"] and rep["tokens"] == 4 * len(FIX["tokens"]) and rep["fingerprint"] == run_fingerprint(run)
    t = pq.read_table(run / "tokens" / "shard-00000.parquet")
    pq.write_table(t.set_column(t.schema.get_field_index("lemma"), "lemma", pa.array(["X"] * t.num_rows)),
                   run / "tokens" / "shard-00000.parquet")
    rep = validate_run(run, write=False, derive_tokens=False)
    assert not rep["ok"] and rep["checks"]["tokens_rederivation_differs"] == 1
    rep = validate_run(run, expected={**dict(world["units"]), sid("mikra", 1): "other"}, write=False)
    assert not rep["ok"] and rep["checks"]["text_differs_from_expected"] == 1


# ------------------------------------------------------------------ catalog / registry / API

def test_catalog_views_all_runs_and_canonical(world):
    from hebloc.store import catalog

    validate_run(world["run"])
    con = catalog.connect(**world["paths"])
    assert con.execute("SELECT count(*), count(DISTINCT run) FROM tokens_all").fetchone() == (4 * len(FIX["tokens"]), 1)
    assert con.execute("SELECT count(*) FROM tokens").fetchone()[0] == 0          # nothing canonical yet
    cols = [r[0] for r in con.execute("DESCRIBE tokens").fetchall()]
    assert cols[:4] == ["run", "corpus_id", "doc_id", "sent_id"] and "piece_tree_valid" in cols
    world["config"].write_text("canonical:\n  mikra: [pilot/r1]\n", encoding="utf-8")
    con = catalog.connect(**world["paths"])
    assert con.execute("SELECT DISTINCT corpus_id FROM tokens").fetchall() == [("mikra",)]   # restricted to its corpus
    cov = {r[0]: r[2:] for r in con.execute("SELECT * FROM parse_coverage").fetchall()}
    # units, nonempty, parsed, multi_piece, with_error, with_invalid_tree
    assert cov["mikra"] == (2, 2, 2, 1, 0, 0) and cov["hazal"] == (1, 1, 0, 0, 0, 0)
    assert con.execute("SELECT canonical_for FROM runs").fetchone()[0] == "mikra"


def test_catalog_file_is_built_atomically(world, tmp_path):
    from hebloc.store import catalog

    derive(world["run"])
    path = catalog.build(tmp_path / "cat.duckdb", **world["paths"])
    con = catalog.duckdb.connect(str(path), read_only=True)
    assert con.execute("SELECT count(*) FROM units").fetchone()[0] == 3
    assert con.execute("SELECT count(*) FROM tokens_all").fetchone()[0] == 4 * len(FIX["tokens"])
    assert not list(tmp_path.glob(".cat.duckdb*"))


def test_registry_rejects_unknown_corpus_and_missing_run(world):
    from hebloc.store.runs import canonical_runs, load_registry

    world["config"].write_text("canonical:\n  klingon: [pilot/r1]\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_registry(world["config"])
    world["config"].write_text("canonical:\n  mikra: [pilot/nope]\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        canonical_runs(root=world["ann"], config=world["config"])


def test_integrity_catches_double_canonical_analysis_and_text_mismatch(world):
    from hebloc.store.integrity import check_all

    validate_run(world["run"])
    make_run(world["ann"], "mikra", "r2", {"shard-00000": [(sid("mikra", 1), TEXT)]})
    validate_run(world["ann"] / "mikra" / "runs" / "r2")
    kw = {k: v for k, v in world["paths"].items() if k != "documents_path"}
    rep = check_all(skip_units=True, write=False, **kw)
    assert rep["ok"], rep["failed"]
    world["config"].write_text("canonical:\n  mikra: [pilot/r1, mikra/r2]\n", encoding="utf-8")
    rep = check_all(skip_units=True, write=False, **kw)
    assert not rep["canonical"]["ok"] and "more than one canonical analysis" in rep["canonical"]["problems"][0]
    # a default-variant run must have parsed exactly units.text_norm
    make_run(world["ann"], "hazal", "r3", {"shard-00000": [(sid("hazal", 1), TEXT + " X")]})
    validate_run(world["ann"] / "hazal" / "runs" / "r3")
    rep = check_all(skip_units=True, write=False, runs=["hazal/r3"], **kw)
    assert any("differ from units.text_norm" in p for p in rep["runs"]["hazal/r3"]["problems"])


def test_quick_check_requires_current_checks_json(world):
    from hebloc.store.integrity import check_all

    kw = {k: v for k, v in world["paths"].items() if k != "documents_path"}
    assert "no checks.json" in " ".join(check_all(skip_units=True, write=False, **kw)["runs"]["pilot/r1"]["problems"])
    validate_run(world["run"])
    assert check_all(skip_units=True, write=False, **kw)["runs"]["pilot/r1"]["ok"]
    atomic_write_json({"key": "changed"}, world["run"] / "_shards" / "shard-00001.json")   # content changed
    r = check_all(skip_units=True, write=False, **kw)["runs"]["pilot/r1"]
    assert not r["ok"] and any("does not describe" in p for p in r["problems"])
    assert check_all(skip_units=True, write=False, deep=True, **kw)["runs"]["pilot/r1"]["validation"]["source"] == "re-run"


# ------------------------------------------------------------------ bundles (D-012)

def test_bundle_round_trip_tamper_and_conflict(world, tmp_path):
    from hebloc.store import bundle as B
    from hebloc.store.runs import resolve

    run = resolve(world["run"])
    with pytest.raises(RuntimeError):            # not validated yet → refused
        B.create(run, tmp_path / "b", data_dir=world["data"])
    validate_run(world["run"])
    r = B.create(resolve(world["run"]), tmp_path / "b", data_dir=world["data"])
    zp = Path(r["path"])
    assert r["rows"]["tokens"] == 4 * len(FIX["tokens"]) and zp.with_name(zp.name + ".sha256").exists()
    assert B.verify(zp)["ok"]
    with zipfile.ZipFile(zp) as zf:
        assert all(i.compress_type == zipfile.ZIP_STORED for i in zf.infolist())
    out = tmp_path / "restore"
    res = B.restore(zp, out)
    assert res["written"] == r["files"] and res["validation_ok"] and res["fingerprint_matches"]
    assert B.restore(zp, out)["written"] == 0                  # idempotent
    victim = out / "annotations" / "pilot" / "runs" / "r1" / "run.json"
    victim.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        B.restore(zp, out)
    # tampered member → verification fails
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(zp) as src, zipfile.ZipFile(bad, "w") as dst:
        for i in src.infolist():
            data = src.read(i.filename)
            dst.writestr(i, data + b"x" if i.filename.endswith("run.json") else data)
    v = B.verify(bad)
    assert not v["ok"] and "sha256 mismatch" in v["problems"][0]


# ------------------------------------------------------------------ CoNLL-U

def _parse_conllu_block(block: str) -> tuple[dict, list[list[str]]]:
    meta, rows = {}, []
    for ln in block.strip("\n").split("\n"):
        if ln.startswith("# "):
            k, _, v = ln[2:].partition(" = ")
            meta[k] = v
        else:
            rows.append(ln.split("\t"))
    return meta, rows


def test_conllu_block_is_well_formed_and_carries_provenance():
    pytest.importorskip("torch")
    from hebloc.store.conllu import has_all_layers, piece_block

    block = piece_block(FIX, sent_id=sid("mikra", 2), piece_idx=1, n_pieces=2, span=(10, 40), ref="Genesis 1:1",
                        run_ref="pilot/r1", status="ok", tree_valid=True)
    meta, rows = _parse_conllu_block(block)
    assert meta["sent_id"] == sid("mikra", 2) + "~p1" and meta["hebloc_sent_id"] == sid("mikra", 2)
    assert meta["text"] == TEXT and meta["hebloc_piece"] == "1/2" and meta["hebloc_norm_span"] == "10-40"
    assert all(len(r) == 10 and all(f != "" for f in r) for r in rows)
    words = [r for r in rows if "-" not in r[0]]
    assert [int(r[0]) for r in words] == list(range(1, len(words) + 1))
    assert all(0 <= int(r[6]) <= len(words) for r in words) and sum(r[7] == "root" for r in words) == 1
    ranges = [r for r in rows if "-" in r[0]]
    assert all(r[1] in TEXT for r in ranges)
    broken = copy.deepcopy(FIX)
    del broken["tokens"][0]["morph"]
    assert has_all_layers(FIX) and not has_all_layers(broken)


def test_export_run_writes_every_piece(world, tmp_path):
    pytest.importorskip("torch")
    from hebloc.store.conllu import export_run

    r = export_run(world["run"], tmp_path / "x.conllu", units_root=world["data"] / "units")
    assert r["pieces_written"] == 4
    blocks = [b for b in (tmp_path / "x.conllu").read_text(encoding="utf-8").split("\n\n") if b.strip()]
    metas = [_parse_conllu_block(b)[0] for b in blocks]
    assert [m["sent_id"] for m in metas].count(sid("mikra", 2) + "~p0") == 1
    assert {m["hebloc_ref"] for m in metas} == {"ref 1", "ref 2"}
    assert export_run(world["run"], tmp_path / "m.conllu", corpus="hazal", units_root=world["data"] / "units")["pieces_written"] == 1


def test_pinned_models_use_default_prefix_config_if_present():
    from hebloc.parse.models import MODELS_DIR, registry

    for name, m in registry()["models"].items():
        cfg = MODELS_DIR / m["dir"] / "config.json"
        if not cfg.exists():
            pytest.skip("models not downloaded")
        assert json.loads(cfg.read_text(encoding="utf-8")).get("prefix_cfg") is None, name


# ------------------------------------------------------------------ real pilot data (skipped if absent)

def _pilot(run_id: str = "base__default"):
    from hebloc.paths import ANNOTATIONS_DIR

    d = ANNOTATIONS_DIR / "pilot" / "runs" / run_id
    if not (d / "checks.json").exists():
        pytest.skip("pilot runs not present")
    return d


def test_real_pilot_tokens_via_api_match_validation():
    from hebloc import data

    d = _pilot()
    checks = json.loads((d / "checks.json").read_text(encoding="utf-8"))
    t = data.tokens(run="pilot/base__default", columns=["sent_id", "piece_tree_valid"])
    assert len(t) == checks["tokens"]
    with pytest.raises(LookupError):
        data.tokens("mikra")                         # no canonical run before M5: never guessed
    mikra = t[t.sent_id.str.startswith("mikra:")].sent_id.iloc[0]
    tr = data.trace_token(mikra, 0, run="pilot/base__default")
    assert tr["verified"] and tr["parsed_text_is_text_norm"]


def test_real_pilot_runs_pass_quick_integrity():
    from hebloc.store.integrity import check_all

    _pilot()
    rep = check_all(skip_units=True, write=False)
    assert all(v["ok"] for v in rep["runs"].values()), {k: v["problems"] for k, v in rep["runs"].items() if not v["ok"]}
    assert rep["canonical"]["ok"]
