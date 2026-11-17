"""Standalone analysis package (D-051): templates, vendored official code, lossless checks, package self-test code."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from hebloc import pack as PK
from hebloc.stats import metrics as M

FACTS = {"STATS_ID": "final-x", "BUILT": "2026-01-01", "TOKENS": "10", "UNITS": "4", "PIECES": "5", "RUNS": 1,
         "PACK_VERSION": "1"}


def test_templates_fill_placeholders_and_vendor_official_code_verbatim(tmp_path):
    PK._copy_templates(tmp_path, FACTS)
    for name in PK.VENDORED:
        assert (tmp_path / "hebpack" / "_official" / name).read_bytes() == (PK.STATS_CODE / name).read_bytes()
    for f in tmp_path.rglob("*"):
        if f.suffix in (".md", ".toml", ".py"):
            assert "{{" not in f.read_text(encoding="utf-8"), f
    for f in ("CLAUDE.md", "README.md", "ASSIGNMENT.md", "RESEARCH_IDEAS.md", "pyproject.toml", "uv.lock",
              "docs/DATA_DICTIONARY.md", "hebpack/db.py", "hebpack/selftest.py", "hebpack/verify.py"):
        assert (tmp_path / f).exists(), f
    assert "final-x" in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")


def test_content_hash_is_order_independent_and_detects_a_change(tmp_path):
    t = pa.table({"a": [1, 2, 3], "b": ["x", None, "z"], "l": [["A"], [], ["B", "C"]]})
    pq.write_table(t, tmp_path / "src.parquet")
    pq.write_table(t.take([2, 0, 1]), tmp_path / "same.parquet")
    pq.write_table(t.set_column(1, "b", pa.array(["x", None, "y"])), tmp_path / "diff.parquet")
    con = duckdb.connect()
    h = lambda f: con.execute(PK._hash_sql([tmp_path / f], ["a", "b", "l"])).fetchone()  # noqa: E731
    assert h("src.parquet") == h("same.parquet")
    assert h("src.parquet") != h("diff.parquet")


def test_bio_spans():
    tags = ["O", "B-PER", "I-PER", "O", "B-GPE", "B-GPE", "I-LOC", "O"]
    assert PK._bio_spans(tags) == [(1, 2, "PER"), (4, 4, "GPE"), (5, 5, "GPE"), (6, 6, "LOC")]


def _tok(sid, piece, idx, surface, upos, head, valid=True, n_pieces=1):
    return dict(sent_id=sid, piece_idx=piece, n_pieces=n_pieces, word_idx=idx, surface=surface, upos=upos, head=head,
                piece_tree_valid=valid, status="ok")


def _mini_package(root: Path) -> None:
    """Two shards of one Mikra run: complete, no_words, multi_piece, invalid_tree and empty units."""
    PK._copy_templates(root, FACTS)
    sid = lambda i: f"mikra:0123456789ab:{i}:0"  # noqa: E731
    shards = {
        "shard-00000": {
            "units": [sid(1), sid(2), sid(3)],
            "pieces": [(sid(1), 0, 1), (sid(2), 0, 1), (sid(3), 0, 2), (sid(3), 1, 2)],
            "tokens": [_tok(sid(1), 0, 0, "א", "VERB", -1), _tok(sid(1), 0, 1, "ב", "NOUN", 0),
                       _tok(sid(1), 0, 2, "ג", "NOUN", 1), _tok(sid(1), 0, 3, ".", "PUNCT", 0),
                       _tok(sid(2), 0, 0, ".", "PUNCT", -1),
                       _tok(sid(3), 0, 0, "ד", "VERB", -1, n_pieces=2), _tok(sid(3), 1, 0, "ה", "NOUN", -1, n_pieces=2)],
        },
        "shard-00001": {
            "units": [sid(4), sid(5)],                                   # sid(5): empty, no pieces, no tokens
            "pieces": [(sid(4), 0, 1)],
            "tokens": [_tok(sid(4), 0, 0, "ו", "VERB", 1, valid=False), _tok(sid(4), 0, 1, "ז", "NOUN", 0, valid=False)],
        },
    }
    writers = {}
    for s, d in shards.items():
        tabs = {
            "run_units": pa.table({"sent_id": d["units"], "text_sha1": ["x"] * len(d["units"])}),
            "pieces": pa.table({"sent_id": [p[0] for p in d["pieces"]], "piece_idx": pa.array([p[1] for p in d["pieces"]], pa.int16()),
                                "n_pieces": pa.array([p[2] for p in d["pieces"]], pa.int16()), "status": ["ok"] * len(d["pieces"])}),
            "tokens": pa.Table.from_pylist(d["tokens"], schema=pa.schema([
                ("sent_id", pa.string()), ("piece_idx", pa.int16()), ("n_pieces", pa.int16()), ("word_idx", pa.int32()),
                ("surface", pa.string()), ("upos", pa.string()), ("head", pa.int32()), ("piece_tree_valid", pa.bool_()),
                ("status", pa.string())])),
        }
        for part, t in tabs.items():
            t = PK._with_ids(t, "mikra", s)
            if part not in writers:
                f = root / "data" / part / "mikra" / "r1.parquet"
                f.parent.mkdir(parents=True, exist_ok=True)
                writers[part] = pq.ParquetWriter(f, t.schema)
            writers[part].write_table(t)
    for w in writers.values():
        w.close()
    return shards


def test_package_official_runner_equals_hebloc_stats_with_shim(tmp_path):
    shards = _mini_package(tmp_path)
    # expected: the main project's code on the same shard frames
    exp = []
    for d in shards.values():
        pcs = pd.DataFrame(d["pieces"], columns=["sent_id", "piece_idx", "n_pieces"])
        raw = pcs.assign(status="ok")[["sent_id", "piece_idx", "status"]]
        tok = pd.DataFrame(d["tokens"])[M.TOKEN_COLUMNS] if d["tokens"] else pd.DataFrame(columns=M.TOKEN_COLUMNS)
        exp.append(M.unit_metrics(d["units"], pcs, raw, tok))
    expected = pd.concat(exp).sort_values("sent_id").reset_index(drop=True)
    assert set(expected.tree_status) == {"complete", "no_words", "multi_piece", "invalid_tree", "empty"}
    # actual: the package's runner, in a fresh interpreter where the main project is NOT importable (shim path)
    code = ("import sys, json; sys.modules['hebloc'] = None; sys.path.insert(0, sys.argv[1]);"
            "from hebpack import official as O; t = O.unit_metrics_run('mikra', 'r1').to_pandas();"
            "print(json.dumps(t.sort_values('sent_id').astype(object).where(t.notna(), None).to_dict('records')))")
    out = subprocess.run([sys.executable, "-c", code, str(tmp_path)], capture_output=True, text=True, check=True)
    actual = pd.DataFrame(json.loads(out.stdout.strip().splitlines()[-1]))
    assert actual["sent_id"].tolist() == expected["sent_id"].tolist()
    for c in ("n_words", "n_punct", "n_distinct_words", "n_pieces", "tree_status"):
        assert actual[c].tolist() == expected[c].astype(object).tolist(), c
    norm = lambda s: [None if pd.isna(x) else int(x) for x in s]  # noqa: E731
    assert norm(actual["depth"]) == norm(expected["depth"])
    assert actual.set_index("sent_id").loc["mikra:0123456789ab:1:0", "depth"] == 3


def test_verify_package_detects_a_changed_file(tmp_path):
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    PK.write_manifest(tmp_path, {"package": "t"})
    assert PK.verify_package(tmp_path) == []
    (tmp_path / "a.txt").write_text("two", encoding="utf-8")
    assert PK.verify_package(tmp_path) == ["changed a.txt"]


def test_refresh_updates_templates_only_and_zips_without_top_folder(tmp_path):
    import zipfile

    pkg = tmp_path / "hebloc-analysis-pack"
    (pkg / "data").mkdir(parents=True)
    (pkg / "data" / "x.parquet").write_bytes(b"data-bytes")
    PK._copy_templates(pkg, FACTS)
    (pkg / "CLAUDE.md").write_text("old instructions", encoding="utf-8")       # as if built with older templates
    (pkg / "hebpack" / "gone.py").write_text("# removed from templates", encoding="utf-8")
    (pkg / ".venv").mkdir()
    (pkg / ".venv" / "junk").write_text("local env", encoding="utf-8")         # never shipped
    PK.write_manifest(pkg, {"package": "t", "pack_version": "1", "stats_id": "final-x", "created_utc": "2026-01-01T00:00",
                            "totals": {"tokens": 10, "run_units": 4, "pieces": 5}, "per_run": {"r": {}}, "facts": FACTS,
                            "template_files": PK.template_files() + ["hebpack/gone.py"]})
    r = PK.refresh(pkg)
    assert r["data_files_unchanged"] == 1 and PK.verify_package(pkg) == []
    assert "When she types `start`" in (pkg / "CLAUDE.md").read_text(encoding="utf-8")
    assert not (pkg / "hebpack" / "gone.py").exists()
    with zipfile.ZipFile(r["zip"]) as z:
        names = z.namelist()
    assert "CLAUDE.md" in names and "data/x.parquet" in names and "MANIFEST.json" in names
    assert not any(n.startswith((".venv", "hebloc-analysis-pack/")) for n in names)


def test_every_view_of_the_package_db_builds_and_queries(tmp_path):
    """hebpack.db.connect(): every view binds (e.g. no ambiguous join columns) on a miniature package."""
    _mini_package(tmp_path)                                # templates + tokens, pieces, run_units for mikra
    sid = "mikra:0123456789ab:1:0"
    sent = pa.table({"sent_id": [sid], "corpus_id": ["mikra"], "doc_id": ["0123456789ab"], "ref": ["Genesis 1:1"],
                     "unit_type": ["verse"], "stratum": ["mikra.torah"], "aramaic": pa.array([None], pa.string()),
                     "in_full_view": [True], "in_curated_view": [True], "text_norm": ["א ב ג ."]})
    (tmp_path / "data" / "sentences" / "mikra").mkdir(parents=True)
    pq.write_table(sent, tmp_path / "data" / "sentences" / "mikra" / "part-00000.parquet")
    docs = pa.table({"doc_id": ["0123456789ab"], "corpus_id": ["mikra"], "subcorpus": ["Torah"], "source": [None],
                     "work": ["Genesis"], "author": [None], "year": pa.array([None], pa.int32()), "genre": [None],
                     "subperiod": [None], "period_status": ["in_period"], "rel_path": ["Mikra/x.txt"],
                     "stratum": ["mikra.torah"], "file_kind": ["text"]})
    pq.write_table(docs, tmp_path / "data" / "documents.parquet")
    sd = tmp_path / "official" / "stats_tables" / "final-x"
    (sd / "unit_metrics" / "mikra").mkdir(parents=True)
    um = pa.Table.from_pylist([dict(sent_id=sid, corpus_id="mikra", doc_id="0123456789ab", n_words=3, n_punct=1,
                                    n_distinct_words=3, n_pieces=1, n_error_pieces=0, tree_status="complete", depth=3)],
                              schema=M.UNIT_METRICS_SCHEMA)
    pq.write_table(um, sd / "unit_metrics" / "mikra" / "r1.parquet")
    for name in ("coverage", "lexicon", "word_freq", "lemma_freq", "sentence_stats", "distributions",
                 "depth_by_length", "tree_status", "pos", "features", "deprel"):
        pq.write_table(pa.table({"corpus_id": ["mikra"]}), sd / f"{name}.parquet")
    code = ("import sys; sys.modules['hebloc'] = None; sys.path.insert(0, sys.argv[1]);"
            "from hebpack.db import connect, OFFICIAL_TABLES; con = connect();"
            "views = ['tokens', 'words', 'sentences', 'pieces', 'run_units', 'documents', 'unit_metrics', 'sentence_info']"
            " + ['official_' + t for t in OFFICIAL_TABLES];"
            "print({v: con.execute(f'SELECT count(*) FROM {v}').fetchone()[0] for v in views});"
            "print(con.execute('SELECT ref, n_words, depth, work FROM sentence_info').fetchall())")
    out = subprocess.run([sys.executable, "-c", code, str(tmp_path)], capture_output=True, text=True, check=True)
    assert "('Genesis 1:1', 3, 3, 'Genesis')" in out.stdout
