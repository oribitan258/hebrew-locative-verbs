"""M3 pilot integration tests (skipped if the pilot outputs are not present). No model is loaded."""

from __future__ import annotations

import json

import pytest

from hebloc.pilot import PILOT_DIR
from hebloc.pilot import audit as A
from hebloc.pilot import sample as S

RUNS = PILOT_DIR / "runs"
pytestmark = pytest.mark.skipif(not (RUNS / "base__default" / "run.json").exists(), reason="pilot not run")


def test_sample_file_is_complete_and_balanced():
    rows = S.load()
    assert len(rows) == 1000 and len({r["sent_id"] for r in rows}) == 1000
    for c in ("mikra", "hazal", "medieval", "haskala", "modern"):
        rs = [r for r in rows if r["corpus_id"] == c]
        assert len(rs) == 200 and sum(r["selection"] == "random" for r in rs) == 120


@pytest.mark.parametrize("rid", ["base__default", "tiny__default"])
def test_pilot_runs_are_complete_and_valid(rid):
    m = json.loads((RUNS / rid / "run.json").read_text(encoding="utf-8"))
    c = json.loads((RUNS / rid / "checks.json").read_text(encoding="utf-8"))
    assert m["units"] == 1000 and m["status"]["error"] == 0 and "mst_seq_len" in m["fixes"]
    assert m["revision"] and m["code_commit"] and m["norm_version"] == "1" and m["segment_version"] == "2"
    assert c["ok"], c["checks"]                     # integrity: coverage, provenance, re-derivation
    assert c["checks"]["coverage_failures"] == 0 and c["checks"]["tokens_rederivation_differs"] == 0


def test_audit_sheets_have_no_invented_judgments():
    if not A.WORDS_SHEET.exists():
        pytest.skip("audit sheets not built")
    units = A._read(A.UNITS_SHEET)
    assert len(units) == 150
    s = A.score()
    # Judgment columns are filled only by people; until then the score must say so.
    if s["status"] == "not yet annotated":
        assert all(v["judged"] == 0 for c in s["per_corpus"].values() for v in c.values())
