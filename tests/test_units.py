"""Integration tests on the extracted units (data/units/<corpus>/). Skipped if not built.

Includes an independent provenance check: a random sample of units is re-read from the ORIGINAL
files and compared character-for-character with the stored text_raw.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

import duckdb
import pytest

from hebloc import data
from hebloc.catalog import DOCUMENTS_PATH
from hebloc.paths import CORPORA, CORPORA_DIR, UNITS_DIR
from hebloc.textstats import decode_bytes, split_lines

pytestmark = pytest.mark.skipif(
    not all((UNITS_DIR / c / "_manifest.json").exists() for c in CORPORA), reason="units not built"
)
UNITS_GLOB = (UNITS_DIR / "*" / "*.parquet").as_posix()


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect()
    c.execute(f"CREATE VIEW u AS SELECT * FROM read_parquet('{UNITS_GLOB}')")
    c.execute(f"CREATE VIEW d AS SELECT * FROM read_parquet('{DOCUMENTS_PATH.as_posix()}')")
    return c


def test_manifests_ok_and_full_runs():
    for c in CORPORA:
        m = json.loads((UNITS_DIR / c / "_manifest.json").read_text(encoding="utf-8"))
        assert m["ok"] and m["sample"] is None and m["coverage_failures"] == 0 and m["n_problems"] == 0, c


def test_every_source_line_and_document_accounted_for(con):
    got = dict(con.execute("SELECT corpus_id, count(DISTINCT (doc_id, line_no)) FROM u GROUP BY 1").fetchall())
    want = dict(con.execute("SELECT corpus_id, sum(n_nonempty_lines) FROM d WHERE in_full_view GROUP BY 1").fetchall())
    assert got == {k: int(v) for k, v in want.items()}
    missing = con.execute("SELECT count(*) FROM d WHERE in_full_view AND doc_id NOT IN (SELECT DISTINCT doc_id FROM u)").fetchone()[0]
    assert missing == 0
    orphan = con.execute("SELECT count(*) FROM u WHERE doc_id NOT IN (SELECT doc_id FROM d WHERE in_full_view)").fetchone()[0]
    assert orphan == 0


def test_ids_unique_and_views_consistent(con):
    n, distinct = con.execute("SELECT count(*), count(DISTINCT sent_id) FROM u").fetchone()
    assert n == distinct
    bad = con.execute("""SELECT count(*) FROM u JOIN d USING (doc_id)
                         WHERE u.in_curated_view <> d.in_curated_view OR u.stratum <> d.stratum OR NOT u.in_full_view""").fetchone()[0]
    assert bad == 0


def test_normalized_text_is_clean(con):
    # No tool tags, diacritics or invisible characters remain in text_norm.
    assert con.execute(r"SELECT count(*) FROM u WHERE text_norm LIKE '%prefix=%' OR text_norm LIKE '%token=%'").fetchone()[0] == 0
    assert con.execute(r"SELECT count(*) FROM u WHERE regexp_matches(text_norm, '[\x{0591}-\x{05BD}\x{05BF}\x{05C1}\x{05C2}\x{05C4}\x{05C5}\x{05C7}\x{200E}\x{200F}\x{FEFF}]')").fetchone()[0] == 0
    assert con.execute("SELECT count(*) FROM u WHERE text_raw = '' OR text_raw <> trim(text_raw)").fetchone()[0] == 0


def test_mikra_references(con):
    refs = dict(con.execute("SELECT ref, text_norm FROM u WHERE corpus_id='mikra'").fetchall())
    assert len(refs) == 23_206
    assert refs["Genesis 1:1"].startswith("בראשית ברא אלהים את השמים")
    assert refs["Exodus 20:13"].startswith("לא תרצח")
    assert refs["Psalms 23:1"].startswith("מזמור לדוד")
    assert "Joel 4:1" in refs and "Malachi 3:24" in refs and "II Chronicles 36:23" in refs   # Hebrew versification
    assert refs["Joshua 21:36"] == ""                                                         # placeholder verse
    assert con.execute("SELECT count(*) FROM u WHERE corpus_id='mikra' AND aramaic='aramaic'").fetchone()[0] > 250


def test_random_units_match_original_files_exactly(con):
    sample = con.execute("""SELECT u.doc_id, d.rel_path, u.line_no, u.char_start, u.char_end, u.text_raw
                            FROM (SELECT * FROM u USING SAMPLE 3000 ROWS) u JOIN d USING (doc_id)""").fetchall()
    by_doc = defaultdict(list)
    for doc_id, rel, ln, s, e, raw in sample:
        by_doc[rel].append((ln, s, e, raw))
    for rel, items in by_doc.items():
        lines = split_lines(decode_bytes((CORPORA_DIR / rel).read_bytes())[0])
        for ln, s, e, raw in items:
            assert lines[ln - 1][s:e] == raw, (rel, ln)


def test_trace_api_verifies_provenance():
    df = data.units("mikra", columns=["sent_id", "ref"])
    sid = df[df.ref == "Genesis 1:1"].sent_id.iloc[0]
    t = data.trace(sid)
    assert t["verified"] and t["line_no"] >= 1 and t["rel_path"].endswith("Genesis.txt")
    assert re.sub("[֑-ׇ]", "", t["text_raw"]).startswith("בראשית ברא")
