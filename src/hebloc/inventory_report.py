"""Summary tables of the document catalog → ``results/inventory/*.csv`` and
``docs/corpus_inventory_tables.md`` (auto-generated; do not edit by hand).

The narrative interpretation lives in ``docs/corpus_report.md`` (hand-written, cites these tables).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa

from hebloc.paths import DOCS_DIR, RESULTS_DIR, assert_not_in_corpora

OUT_DIR = RESULTS_DIR / "inventory"
TABLES_MD = DOCS_DIR / "corpus_inventory_tables.md"
CORPUS_ORDER = "CASE corpus_id WHEN 'mikra' THEN 1 WHEN 'hazal' THEN 2 WHEN 'medieval' THEN 3 WHEN 'haskala' THEN 4 ELSE 5 END"

QUERIES: dict[str, tuple[str, str]] = {
    "corpus_summary": ("Per-corpus totals (all files) and the default comparison set", f"""
        SELECT corpus_id,
               count(*) AS files,
               count(*) FILTER (file_kind='text') AS text_files,
               count(*) FILTER (file_kind='empty') AS empty_files,
               count(*) FILTER (file_kind='auxiliary') AS auxiliary_files,
               count(*) FILTER (file_kind='text' AND is_blank) AS blank_files,
               count(*) FILTER (is_dup_copy) AS duplicate_copies,
               round(sum(size_bytes)/1048576.0, 1) AS mib,
               sum(n_nonempty_lines) AS nonempty_lines,
               sum(n_tokens) AS tokens,
               sum(n_hebrew_tokens) AS hebrew_tokens,
               count(*) FILTER (include_default) AS default_files,
               sum(n_hebrew_tokens) FILTER (include_default) AS default_hebrew_tokens,
               round(100.0 * sum(n_hebrew_tokens) FILTER (include_default) / sum(n_hebrew_tokens), 1) AS default_pct_tokens
        FROM docs GROUP BY corpus_id ORDER BY {CORPUS_ORDER}"""),
    "stratum_summary": ("Strata and period status (tags only — nothing is deleted)", f"""
        SELECT corpus_id, stratum, period_status,
               count(*) AS files, sum(n_nonempty_lines) AS nonempty_lines,
               sum(n_hebrew_tokens) AS hebrew_tokens,
               count(*) FILTER (include_default) AS default_files,
               coalesce(sum(n_hebrew_tokens) FILTER (include_default), 0) AS default_hebrew_tokens
        FROM docs GROUP BY corpus_id, stratum, period_status ORDER BY {CORPUS_ORDER}, stratum"""),
    "encoding_summary": ("Detected encodings", f"""
        SELECT corpus_id, coalesce(subcorpus, '') AS subcorpus, encoding, line_endings,
               count(*) AS files, round(sum(size_bytes)/1048576.0, 1) AS mib
        FROM docs GROUP BY corpus_id, coalesce(subcorpus, ''), encoding, line_endings ORDER BY {CORPUS_ORDER}, 2, encoding, line_endings"""),
    "modern_sources": ("Modern sub-corpora and sources", """
        SELECT subcorpus, coalesce(source, '') AS source, count(*) AS files,
               count(*) FILTER (is_dup_copy) AS duplicate_copies,
               count(*) FILTER (file_kind<>'text' OR is_blank) AS non_text_or_blank,
               round(sum(size_bytes)/1048576.0, 1) AS mib,
               sum(n_nonempty_lines) AS nonempty_lines, sum(n_hebrew_tokens) AS hebrew_tokens,
               round(100.0*sum(n_hebrew_tokens)/sum(sum(n_hebrew_tokens)) OVER (), 1) AS pct_of_modern_tokens
        FROM docs WHERE corpus_id='modern' GROUP BY subcorpus, coalesce(source, '') ORDER BY hebrew_tokens DESC, subcorpus, source"""),
    "haskala_subperiods": ("Haskala: publication year sub-periods (cut-off from config/curation.yaml)", """
        SELECT subperiod, genre, count(*) AS files, min(year) AS min_year, max(year) AS max_year,
               sum(n_hebrew_tokens) AS hebrew_tokens
        FROM docs WHERE corpus_id='haskala' GROUP BY subperiod, genre ORDER BY subperiod, genre"""),
    "vocalization": ("Vocalization (niqqud) and cantillation by stratum (text files)", f"""
        SELECT corpus_id, stratum, count(*) AS files,
               round(sum(n_niqqud)::DOUBLE / nullif(sum(n_hebrew_letters),0), 3) AS niqqud_per_letter,
               round(sum(n_cantillation)::DOUBLE / nullif(sum(n_hebrew_letters),0), 3) AS cantillation_per_letter,
               count(*) FILTER (niqqud_per_letter > 0.5) AS files_mostly_vocalized
        FROM docs WHERE file_kind='text' GROUP BY corpus_id, stratum ORDER BY {CORPUS_ORDER}, stratum"""),
    "duplicates": ("Exact duplicates (identical bytes, non-empty files)", f"""
        SELECT corpus_id,
               count(DISTINCT sha256) FILTER (dup_count>1) AS dup_groups,
               count(*) FILTER (is_dup_copy) AS copies,
               sum(n_hebrew_tokens) FILTER (is_dup_copy) AS hebrew_tokens_in_copies,
               count(*) FILTER (dup_cross_corpus) AS files_in_cross_corpus_groups,
               max(dup_count) AS largest_group
        FROM docs GROUP BY corpus_id ORDER BY {CORPUS_ORDER}"""),
    "anomalies": ("Anomaly counts (files affected)", f"""
        SELECT corpus_id,
               count(*) FILTER (decode_errors>0) AS lossy_decoding,
               count(*) FILTER (has_bom) AS utf8_bom,
               count(*) FILTER (n_feff>0) AS stray_feff,
               count(*) FILTER (n_control_chars>0) AS control_chars,
               count(*) FILTER (n_odd_line_separators>0) AS odd_line_separators,
               count(*) FILTER (line_endings='mixed') AS mixed_line_endings,
               count(*) FILTER (file_kind='text' AND NOT is_blank AND hebrew_ratio < 0.5) AS mostly_non_hebrew,
               count(*) FILTER (n_latin1_supplement > 0) AS latin1_supplement_chars,
               count(*) FILTER (meta_issue IS NOT NULL) AS metadata_issues,
               max(max_line_chars) AS longest_line_chars
        FROM docs GROUP BY corpus_id ORDER BY {CORPUS_ORDER}"""),
    "artifacts": ("Markup/tokenization artifacts and near-empty 'stub' files (text files; cleaned in M2)", f"""
        SELECT corpus_id, coalesce(source, subcorpus, '') AS source,
               count(*) FILTER (n_prefix_tags>0) AS files_prefix_tags, sum(n_prefix_tags) AS prefix_tags,
               sum(n_token_tags) AS token_tags, sum(n_img_tags) AS img_tags, sum(n_urls) AS urls,
               count(*) FILTER (n_hebrew_tokens BETWEEN 1 AND 15) AS stub_files_le15_hebrew_tokens,
               count(*) FILTER (n_hebrew_tokens = 0 AND NOT is_blank) AS files_without_hebrew
        FROM docs WHERE file_kind='text' GROUP BY corpus_id, coalesce(source, subcorpus, '')
        HAVING sum(n_prefix_tags)+sum(n_token_tags)+sum(n_img_tags)+sum(n_urls)
               + count(*) FILTER (n_hebrew_tokens <= 15) > 0
        ORDER BY {CORPUS_ORDER}, prefix_tags DESC, source"""),
    "needs_review": ("Documents awaiting a period decision (excluded from default until decided)", """
        SELECT corpus_id, rel_path, stratum, n_hebrew_tokens AS hebrew_tokens, n_nonempty_lines AS nonempty_lines
        FROM docs WHERE period_status='needs_review' ORDER BY hebrew_tokens DESC, rel_path"""),
    "out_of_period": ("Out-of-period documents (kept; excluded from default)", f"""
        SELECT corpus_id, stratum, curation_rule, count(*) AS files, sum(n_hebrew_tokens) AS hebrew_tokens
        FROM docs WHERE period_status='out_of_period' GROUP BY corpus_id, stratum, curation_rule ORDER BY {CORPUS_ORDER}, hebrew_tokens DESC, stratum, curation_rule"""),
    "exclusion_reasons": ("Why documents are outside the default set (a document may have several reasons)", f"""
        SELECT corpus_id, reason, count(*) AS files, sum(n_hebrew_tokens) AS hebrew_tokens
        FROM (SELECT corpus_id, unnest(exclusion_reasons) AS reason, n_hebrew_tokens FROM docs)
        GROUP BY corpus_id, reason ORDER BY {CORPUS_ORDER}, files DESC, reason"""),
}


def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        if v.is_integer():
            return f"{int(v):,}"
        return f"{v:,.3f}".rstrip("0").rstrip(".")
    return str(v).replace("|", "\\|")


def _md_table(df: pd.DataFrame, max_rows: int = 60) -> str:
    shown = df.head(max_rows)
    lines = ["| " + " | ".join(shown.columns) + " |", "|" + "---|" * len(shown.columns)]
    for row in shown.itertuples(index=False):
        lines.append("| " + " | ".join(_fmt(v.item() if hasattr(v, "item") else v) for v in row) + " |")
    if len(df) > max_rows:
        lines.append(f"\n*… {len(df) - max_rows} more rows in the CSV.*")
    return "\n".join(lines)


def summary_frames(table: pa.Table) -> dict[str, pd.DataFrame]:
    con = duckdb.connect()
    con.register("docs", table)
    return {name: con.execute(sql).df() for name, (_, sql) in QUERIES.items()}


def write_reports(table: pa.Table, out_dir: Path = OUT_DIR, md_path: Path = TABLES_MD) -> list[Path]:
    assert_not_in_corpora(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = summary_frames(table)
    written = []
    for name, df in frames.items():
        p = out_dir / f"{name}.csv"
        df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")
        written.append(p)
    parts = [
        "# Corpus inventory — summary tables",
        "",
        "> **Auto-generated** by `uv run hebloc inventory` from `data/catalog/documents.parquet`. "
        "Do not edit by hand. Full CSVs: `results/inventory/`. Interpretation: `docs/corpus_report.md`.",
        "",
        "Definitions: *line* = `\\n`-delimited; *token* = whitespace-separated run; *Hebrew token* = token "
        "containing ≥1 Hebrew letter (U+05D0–U+05EA). *Default set* = text, non-blank, in-period, non-duplicate.",
        "",
    ]
    for name, df in frames.items():
        parts += [f"## {QUERIES[name][0]}", f"`results/inventory/{name}.csv`", "", _md_table(df), ""]
    md_path.write_text("\n".join(parts), encoding="utf-8", newline="\n")
    written.append(md_path)
    return written
