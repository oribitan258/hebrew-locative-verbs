"""Integration tests on the built catalog (data/catalog/documents.parquet).

They check the catalog against (a) the git-tracked anchor and (b) numbers measured INDEPENDENTLY
during project discovery (2026-11-06, PowerShell/.NET regex counts, before any project code
existed). Skipped if the catalog has not been built (`uv run hebloc inventory`).
"""

from __future__ import annotations

import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hebloc.baseline import canonical_digest, read_anchor
from hebloc.catalog import DOCUMENTS_PATH, MANIFEST_PATH, documents
from hebloc.curation import PERIOD_STATUSES

pytestmark = pytest.mark.skipif(not DOCUMENTS_PATH.exists(), reason="catalog not built")

# Discovery measurements: Hebrew tokens (regex [א-ת]\S*) and non-empty lines per corpus.
DISCOVERY_HEBREW_TOKENS = {"mikra": 267_866, "hazal": 6_493_912, "haskala": 5_336_775, "medieval": 3_459_940}
DISCOVERY_NONEMPTY_LINES = {"mikra": 23_206, "hazal": 118_481, "haskala": 72_284, "medieval": 44_457}
DISCOVERY_SUBSETS = {  # Hebrew tokens of sub-collections measured during discovery
    "hazal_commentaries": 2_465_663,
    "hazal_yalkut": 1_437_008,
    "hazal_mishnah": 192_535,
    "hazal_tosefta": 295_238,
    "hazal_halakhic_midrash": 421_430,
    "medieval_akeidat": 965_358,
    "medieval_rambam": 637_790,
}
MODERN_ESTIMATE = 133_400_000  # sampled estimate from discovery (sum over sub-corpora)


@pytest.fixture(scope="module")
def cat():
    return pq.read_table(DOCUMENTS_PATH).to_pandas()


def test_every_file_accounted_for_and_matches_anchor(cat):
    anchor = read_anchor()
    assert len(cat) == anchor["file_count"]
    per = cat.groupby(cat.rel_path.str.split("/").str[0]).agg(files=("rel_path", "size"), bytes=("size_bytes", "sum"))
    assert {k: {"files": int(r.files), "bytes": int(r.bytes)} for k, r in per.iterrows()} == anchor["per_corpus"]
    as_baseline = pa.table({"rel_path": cat.rel_path, "size": cat.size_bytes, "sha256": cat.sha256})
    assert canonical_digest(as_baseline) == anchor["manifest_sha256"]


def test_manifest_records_successful_verification():
    m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert m["verification"]["ok"] is True and m["rows"] == 404_294


def test_counts_match_independent_discovery(cat):
    t = cat[cat.file_kind != "auxiliary"]
    assert t.groupby("corpus_id").n_hebrew_tokens.sum().drop("modern").to_dict() == DISCOVERY_HEBREW_TOKENS
    assert t.groupby("corpus_id").n_nonempty_lines.sum().drop("modern").to_dict() == DISCOVERY_NONEMPTY_LINES
    s = lambda mask: int(cat[mask].n_hebrew_tokens.sum())  # noqa: E731
    got = {
        "hazal_commentaries": s(cat.stratum == "hazal.commentary"),
        "hazal_yalkut": s(cat.stratum == "hazal.late_anthology"),
        "hazal_mishnah": s(cat.stratum == "hazal.mishnah"),
        "hazal_tosefta": s(cat.stratum == "hazal.tosefta"),
        "hazal_halakhic_midrash": s(cat.stratum == "hazal.halakhic_midrash"),
        "medieval_akeidat": s(cat.rel_path.str.contains("Akeidat")),
        "medieval_rambam": s(cat.stratum == "medieval.mishneh_torah"),
    }
    assert got == DISCOVERY_SUBSETS
    modern = cat[cat.corpus_id == "modern"].n_hebrew_tokens.sum()
    assert abs(modern - MODERN_ESTIMATE) / MODERN_ESTIMATE < 0.05


def test_tagging_never_drops_and_is_explained(cat):
    assert not cat.stratum.str.endswith(".unclassified").any()
    assert set(cat.period_status) <= set(PERIOD_STATUSES)
    reasons_empty = cat.curated_exclusion_reasons.map(len) == 0
    assert (cat.in_curated_view == reasons_empty).all()
    excluded = cat[~cat.in_curated_view]
    assert excluded.curated_exclusion_reasons.map(len).gt(0).all()
    # Curated is a strict subset of full; full = every text file as supplied.
    assert (cat.in_full_view == (cat.file_kind == "text")).all()
    assert not (cat.in_curated_view & ~cat.in_full_view).any()
    # Out-of-period / needs-review documents are still present with full measurements.
    oop = cat[cat.period_status != "in_period"]
    assert len(oop) > 0 and oop.sha256.notna().all() and (oop.n_hebrew_tokens >= 0).all()


def test_kinds_encodings_and_metadata(cat):
    assert ((cat.file_kind == "empty") == (cat.size_bytes == 0)).all()
    assert (cat.decode_errors == 0).all()
    hist = cat[cat.corpus_id != "modern"]
    assert set(hist.encoding) <= {"utf-8", "ascii", "empty"}
    assert set(cat[cat.corpus_id == "modern"].encoding) <= {"cp1255", "ascii", "empty"}
    assert cat.meta_issue.isna().all()
    assert cat[cat.corpus_id == "mikra"].work.nunique() == 39
    assert cat[cat.corpus_id == "haskala"].year.notna().all()
    aux = cat[cat.file_kind == "auxiliary"]
    assert len(aux) == 100 and (aux.stratum == "modern.auxiliary").all()


def test_duplicates_consistent_and_scoped(cat):
    copies = cat[cat.is_dup_copy]
    canon = cat.set_index("doc_id")
    assert copies.dup_of.isin(canon.index).all()
    assert (canon.loc[copies.dup_of, "sha256"].values == copies.sha256.values).all()
    assert (canon.loc[copies.dup_of, "dup_rank"] == 0).all()
    # A copy is only ever excluded in favour of a canonical file in the SAME scope.
    assert (canon.loc[copies.dup_of, "dup_scope"].values == copies.dup_scope.values).all()
    assert (cat.dup_scope == cat.stratum + "|" + cat.source.fillna("")).all()


def test_documents_api_views():
    d = documents("mikra", columns=["doc_id", "work"])
    assert len(d) == 39 and list(d.columns) == ["doc_id", "work"]
    full = documents(view="full", columns=["in_full_view"])
    curated = documents(view="curated", columns=["in_curated_view"])
    assert full.in_full_view.all() and curated.in_curated_view.all()
    assert len(curated) < len(full) < 404_294
    with pytest.raises(ValueError):
        documents(view="default")
