"""M2.1 — exhaustive verification of the segment v1 → v2 regeneration, and the old→new id map.

Segment v2 (D-020) stops cutting over-long sentences into ``chunk`` units. This module compares a
preserved copy of the v1 units (``data/units_v1``) with the regenerated v2 units (``data/units``)
and checks, without assuming what the differences will be:

* **Unaffected lines** (no v1 chunk on the line): every row is identical in every column except
  ``segment_version`` (compared column by column in DuckDB, all rows).
* **Affected lines** (≥ 1 v1 chunk): the source line is re-read from ``corpora/`` (read-only) and
    - the v2 units are exactly ``segment.sentence_spans(line)``, with ``text_raw == line[s:e]``;
    - every v1 unit lies inside exactly one v2 unit; a v2 unit built from several v1 units was
      chunked in v1, and the v1 chunk offsets equal ``pieces.plan_pieces(text_raw, 200)``;
    - non-whitespace characters are identical (nothing lost or added);
    - single-v1-unit sentences are identical except id/k/ref/segment_version;
    - for merged sentences, ``text_norm`` is compared with the v1 chunk norms joined by a space,
      and ``norm_flags`` / token counts with their v1 aggregates. EVERY difference is recorded
      (not only the known ones) for investigation.
* Unit counts reconcile per corpus: v2 = v1 − chunks + chunked sentences; line sets are equal.

Outputs (``data/migrations/segment_v1_to_v2/``): ``map.parquet`` (every v1 unit on an affected line
→ its v2 unit; elsewhere ids are identical), ``differences.parquet`` and ``report.json``.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from hebloc.catalog import DOCUMENTS_PATH
from hebloc.inventory import _git_commit
from hebloc.paths import CORPORA, CORPORA_DIR, DATA_DIR, UNITS_DIR, assert_not_in_corpora
from hebloc.pieces import plan_pieces
from hebloc.segment import sentence_spans
from hebloc.textstats import decode_bytes, split_lines
from hebloc.units import UNITS_SCHEMA

V1_DIR = DATA_DIR / "units_v1"
OUT_DIR = DATA_DIR / "migrations" / "segment_v1_to_v2"
V1_CHUNK_TOKENS = 200
CONTENT_COLS = [f.name for f in UNITS_SCHEMA if f.name != "segment_version"]
# Columns that legitimately change when a line's units are renumbered.
ID_COLS = {"sent_id", "k", "ref"}

MAP_SCHEMA = pa.schema([
    ("old_sent_id", pa.string()), ("old_unit_type", pa.string()), ("old_ref", pa.string()),
    ("old_char_start", pa.int32()), ("old_char_end", pa.int32()),
    ("new_sent_id", pa.string()), ("new_ref", pa.string()),
    ("new_char_start", pa.int32()), ("new_char_end", pa.int32()),
    ("relation", pa.string()),   # merged_into | renumbered | same_id
    ("piece_idx", pa.int16()), ("n_pieces", pa.int16()),
])
DIFF_SCHEMA = pa.schema([
    ("new_sent_id", pa.string()), ("rel_path", pa.string()), ("line_no", pa.int32()),
    ("kind", pa.string()), ("detail", pa.string()),
])


def _nonws(s: str) -> str:
    return "".join(s.split())


def _glob(root: Path, corpus: str) -> str:
    return (root / corpus / "*.parquet").as_posix()


def _compare_unaffected(con: duckdb.DuckDBPyConnection, corpus: str, old: Path, new: Path) -> dict:
    con.execute(f"CREATE OR REPLACE TEMP VIEW o AS SELECT * FROM read_parquet('{_glob(old, corpus)}')")
    con.execute(f"CREATE OR REPLACE TEMP VIEW n AS SELECT * FROM read_parquet('{_glob(new, corpus)}')")
    con.execute("CREATE OR REPLACE TEMP TABLE aff AS SELECT DISTINCT doc_id, line_no FROM o WHERE unit_type = 'chunk'")
    unaff = "NOT EXISTS (SELECT 1 FROM aff a WHERE a.doc_id = {t}.doc_id AND a.line_no = {t}.line_no)"
    n_old = con.execute(f"SELECT count(*) FROM o WHERE {unaff.format(t='o')}").fetchone()[0]
    n_new = con.execute(f"SELECT count(*) FROM n WHERE {unaff.format(t='n')}").fetchone()[0]
    diff_expr = " + ".join(f"(o.{c} IS DISTINCT FROM n.{c})::INT" for c in CONTENT_COLS if c != "sent_id")
    joined, differing = con.execute(
        f"SELECT count(*), coalesce(sum(CASE WHEN {diff_expr} > 0 THEN 1 ELSE 0 END), 0) "
        f"FROM o JOIN n USING (sent_id) WHERE {unaff.format(t='o')}").fetchone()
    versions = con.execute("SELECT (SELECT list(DISTINCT segment_version) FROM o), "
                           "(SELECT list(DISTINCT segment_version) FROM n), "
                           "(SELECT list(DISTINCT unit_type) FROM n), "
                           "(SELECT count(*) - count(DISTINCT sent_id) FROM n)").fetchone()
    lines = con.execute("SELECT (SELECT count(*) FROM (SELECT DISTINCT doc_id, line_no FROM o)), "
                        "(SELECT count(*) FROM (SELECT DISTINCT doc_id, line_no FROM n)), "
                        "(SELECT count(*) FROM (SELECT doc_id, line_no FROM o EXCEPT SELECT doc_id, line_no FROM n)) "
                        "+ (SELECT count(*) FROM (SELECT doc_id, line_no FROM n EXCEPT SELECT doc_id, line_no FROM o))").fetchone()
    return {"unaffected_rows_old": n_old, "unaffected_rows_new": n_new, "unaffected_rows_joined": joined,
            "unaffected_rows_differing": int(differing), "segment_versions_old": versions[0],
            "segment_versions_new": versions[1], "unit_types_new": versions[2], "duplicate_sent_ids_new": versions[3],
            "lines_old": lines[0], "lines_new": lines[1], "lines_symmetric_difference": lines[2]}


def _affected(con: duckdb.DuckDBPyConnection, corpus: str) -> tuple[dict, list[dict], list[dict]]:
    cols = ", ".join(CONTENT_COLS)
    old_rows = con.execute(f"SELECT o.*, d.rel_path FROM (SELECT {cols} FROM o JOIN aff USING (doc_id, line_no)) o "
                           f"JOIN (SELECT doc_id, rel_path FROM read_parquet('{DOCUMENTS_PATH.as_posix()}')) d USING (doc_id) "
                           f"ORDER BY rel_path, line_no, k").to_arrow_table().to_pylist()
    new_rows = con.execute(f"SELECT {cols} FROM n JOIN aff USING (doc_id, line_no) ORDER BY doc_id, line_no, k").to_arrow_table().to_pylist()
    old_by = defaultdict(list)
    for r in old_rows:
        old_by[(r["doc_id"], r["line_no"])].append(r)
    new_by = defaultdict(list)
    for r in new_rows:
        new_by[(r["doc_id"], r["line_no"])].append(r)

    st: Counter = Counter()
    maps: list[dict] = []
    diffs: list[dict] = []
    lines_cache: tuple[str, list[str]] | None = None
    for key in sorted(old_by, key=lambda k: (old_by[k][0]["rel_path"], k[1])):
        olds, news = old_by[key], new_by.get(key, [])
        rel = olds[0]["rel_path"]
        if lines_cache is None or lines_cache[0] != rel:
            lines_cache = (rel, split_lines(decode_bytes((CORPORA_DIR / rel).read_bytes())[0]))
        line = lines_cache[1][key[1] - 1]
        st["lines"] += 1

        def diff(new_id: str, kind: str, detail: str) -> None:
            diffs.append({"new_sent_id": new_id, "rel_path": rel, "line_no": key[1], "kind": kind, "detail": detail})

        spans = sentence_spans(line)
        if [(u["char_start"], u["char_end"]) for u in news] != spans or [u["k"] for u in news] != list(range(len(news))):
            st["new_spans_mismatch"] += 1
            diff("", "new_spans_mismatch", json.dumps(spans))
        if any(line[u["char_start"]:u["char_end"]] != u["text_raw"] for u in news):
            st["new_text_raw_mismatch"] += 1
        if any(line[u["char_start"]:u["char_end"]] != u["text_raw"] for u in olds):
            st["old_text_raw_mismatch"] += 1
        if _nonws("".join(u["text_raw"] for u in olds)) != _nonws("".join(u["text_raw"] for u in news)) \
                or _nonws("".join(u["text_raw"] for u in news)) != _nonws(line):
            st["nonws_chars_mismatch"] += 1
            diff("", "nonws_chars_mismatch", "")

        for nu in news:
            members = [o for o in olds if o["char_start"] >= nu["char_start"] and o["char_end"] <= nu["char_end"]]
            st["new_units"] += 1
            if not members:
                st["new_unit_without_old"] += 1
                diff(nu["sent_id"], "new_unit_without_old", "")
                continue
            if len(members) == 1:  # unchanged sentence on an affected line (maybe renumbered)
                o = members[0]
                if (o["char_start"], o["char_end"]) != (nu["char_start"], nu["char_end"]) or o["unit_type"] == "chunk":
                    st["single_member_span_mismatch"] += 1
                    diff(nu["sent_id"], "single_member_span_mismatch", o["sent_id"])
                bad = [c for c in CONTENT_COLS if c not in ID_COLS and o[c] != nu[c]]
                if bad:
                    st["single_member_content_diff"] += 1
                    diff(nu["sent_id"], "single_member_content_diff", ",".join(bad))
                rel_kind = "same_id" if o["sent_id"] == nu["sent_id"] else "renumbered"
                st[rel_kind] += 1
                maps.append(_map_row(o, nu, rel_kind, 0, 1))
                continue
            # merged: v1 chunks of one sentence
            st["merged_sentences"] += 1
            st["merged_from_chunks"] += len(members)
            if any(o["unit_type"] != "chunk" for o in members) or nu["unit_type"] != "sentence":
                st["merged_type_mismatch"] += 1
                diff(nu["sent_id"], "merged_type_mismatch", "")
            expect = [(p.start + nu["char_start"], p.end + nu["char_start"])
                      for p in plan_pieces(nu["text_raw"], V1_CHUNK_TOKENS)]
            if expect != [(o["char_start"], o["char_end"]) for o in members]:
                st["chunk_offsets_not_reproduced"] += 1
                diff(nu["sent_id"], "chunk_offsets_not_reproduced", "")
            for i, o in enumerate(members):
                maps.append(_map_row(o, nu, "merged_into", i, len(members)))
            # --- exhaustive comparison of derived columns
            joined = " ".join(o["text_norm"] for o in members if o["text_norm"])
            if nu["text_norm"] != joined:
                st["text_norm_diff"] += 1
                i = next((j for j, (a, b) in enumerate(zip(nu["text_norm"], joined)) if a != b),
                         min(len(nu["text_norm"]), len(joined)))
                diff(nu["sent_id"], "text_norm", json.dumps({
                    "v2": nu["text_norm"][max(0, i - 80):i + 120], "v1_joined": joined[max(0, i - 80):i + 120],
                    "v2_flags": sorted(set(nu["norm_flags"])),
                    "v1_flags": sorted({f for o in members for f in o["norm_flags"]})}, ensure_ascii=False))
            new_flags = set(nu["norm_flags"])
            old_flags = {f for o in members for f in o["norm_flags"]}
            if new_flags != old_flags:
                st["flag_set_diff"] += 1
                diff(nu["sent_id"], "flag_set", json.dumps({"only_v2": sorted(new_flags - old_flags),
                                                            "only_v1": sorted(old_flags - new_flags)}, ensure_ascii=False))
            if Counter(nu["norm_flags"]) != Counter(f for o in members for f in o["norm_flags"]):
                st["flag_multiset_diff"] += 1  # expected for per-unit flags (e.g. diacritics_stripped once)
            for c, agg in (("n_tokens_norm", sum(o["n_tokens_norm"] for o in members)),
                           ("n_hebrew_tokens_norm", sum(o["n_hebrew_tokens_norm"] for o in members)),
                           ("is_empty_norm", all(o["is_empty_norm"] for o in members))):
                if nu[c] != agg:
                    st[f"{c}_diff"] += 1
                    diff(nu["sent_id"], c, f"v2={nu[c]} v1_aggregate={agg}")
            for c in ("text_norm_alt", "aramaic", "stratum", "in_full_view", "in_curated_view", "norm_version", "doc_id", "corpus_id"):
                if any(o[c] != nu[c] and not (o[c] is None and nu[c] is None) for o in members):
                    st[f"{c}_diff"] += 1
                    diff(nu["sent_id"], c, "")
        mapped = sum(1 for m in maps if m["old_sent_id"] in {o["sent_id"] for o in olds})
        if mapped != len(olds):
            st["old_units_unmapped"] += len(olds) - mapped
    return dict(st), maps, diffs


def _map_row(o: dict, n: dict, relation: str, piece_idx: int, n_pieces: int) -> dict:
    return {"old_sent_id": o["sent_id"], "old_unit_type": o["unit_type"], "old_ref": o["ref"],
            "old_char_start": o["char_start"], "old_char_end": o["char_end"],
            "new_sent_id": n["sent_id"], "new_ref": n["ref"], "new_char_start": n["char_start"],
            "new_char_end": n["char_end"], "relation": relation, "piece_idx": piece_idx, "n_pieces": n_pieces}


def run(old: Path = V1_DIR, new: Path = UNITS_DIR, out: Path = OUT_DIR) -> dict:
    assert_not_in_corpora(out)
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    report: dict = {"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "code_commit": _git_commit(), "old_root": old.as_posix(), "new_root": new.as_posix(),
                    "corpora": {}}
    all_maps: list[dict] = []
    all_diffs: list[dict] = []
    for c in CORPORA:
        m_old = json.loads((old / c / "_manifest.json").read_text(encoding="utf-8"))
        m_new = json.loads((new / c / "_manifest.json").read_text(encoding="utf-8"))
        r = _compare_unaffected(con, c, old, new)
        st, maps, diffs = _affected(con, c)
        old_chunks = m_old["unit_types"].get("chunk", 0)
        r.update({
            "manifest_new_ok": m_new["ok"], "manifest_new_commit": m_new["code_commit"],
            "manifest_new_segment_version": m_new["segment_version"],
            "units_old": m_old["units"], "units_new": m_new["units"], "chunks_old": old_chunks,
            "chunked_sentences": st.get("merged_sentences", 0),
            "count_reconciles": m_new["units"] == m_old["units"] - old_chunks + st.get("merged_sentences", 0)
                                and st.get("merged_from_chunks", 0) == old_chunks,
            "affected": st,
        })
        report["corpora"][c] = r
        all_maps += maps
        all_diffs += diffs
    pq.write_table(pa.Table.from_pylist(all_maps, schema=MAP_SCHEMA), out / "map.parquet", compression="zstd")
    pq.write_table(pa.Table.from_pylist(all_diffs, schema=DIFF_SCHEMA), out / "differences.parquet", compression="zstd")
    bad_keys = ("new_spans_mismatch", "new_text_raw_mismatch", "old_text_raw_mismatch", "nonws_chars_mismatch",
                "new_unit_without_old", "single_member_span_mismatch", "single_member_content_diff",
                "merged_type_mismatch", "chunk_offsets_not_reproduced", "old_units_unmapped")
    report["structural_ok"] = all(
        r["unaffected_rows_differing"] == 0 and r["unaffected_rows_old"] == r["unaffected_rows_new"] == r["unaffected_rows_joined"]
        and r["segment_versions_new"] == ["2"] and "chunk" not in r["unit_types_new"] and r["duplicate_sent_ids_new"] == 0
        and r["lines_symmetric_difference"] == 0 and r["lines_old"] == r["lines_new"] and r["count_reconciles"]
        and r["manifest_new_ok"] and not any(r["affected"].get(k) for k in bad_keys)
        for r in report["corpora"].values())
    report["difference_counts"] = dict(Counter(d["kind"] for d in all_diffs))
    report["map_rows"] = len(all_maps)
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
                                     encoding="utf-8", newline="\n")
    return report
