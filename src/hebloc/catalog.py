"""The document catalog: schema and read access.

``data/catalog/documents.parquet`` has one row per file under ``corpora/`` (every file, including
empty, duplicate, auxiliary and out-of-period ones). Later stages select their inputs from it,
typically with ``documents(default_only=True)`` or by ``file_kind == 'text'``.

Column groups:
  identity     doc_id, corpus_id, rel_path, file_name, ext, size_bytes, sha256
  kind/quality file_kind, aux_reason, is_blank, encoding, has_bom, n_feff, decode_errors,
               line_endings, n_control_chars, n_odd_line_separators, n_latin1_supplement,
               n_prefix_tags, n_token_tags, n_img_tags, n_urls (markup artifacts to clean in M2)
  size         n_lines, n_nonempty_lines, max_line_chars, n_chars, n_tokens, n_hebrew_tokens,
               n_hebrew_letters, n_niqqud, n_cantillation, n_latin_letters, n_digits,
               hebrew_ratio, niqqud_per_letter
  duplicates   dup_count, dup_rank, is_dup_copy, dup_of, dup_cross_corpus
  metadata     subcorpus, source, section, work, base_work, commentary, era_label, author, year,
               genre, ext_id, date, meta_issue, meta_json (corpus-specific extras as JSON)
  curation     stratum, period_status, curation_rule, subperiod, include_default, exclusion_reasons
  provenance   inventory_version, curation_hash
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hebloc.paths import CATALOG_DIR

DOCUMENTS_PATH: Path = CATALOG_DIR / "documents.parquet"
MANIFEST_PATH: Path = CATALOG_DIR / "documents.manifest.json"
INVENTORY_VERSION = "1"

FILE_KINDS = ("text", "empty", "auxiliary")

DOCUMENTS_SCHEMA = pa.schema(
    [
        ("doc_id", pa.string()),
        ("corpus_id", pa.string()),
        ("rel_path", pa.string()),
        ("file_name", pa.string()),
        ("ext", pa.string()),
        ("size_bytes", pa.int64()),
        ("sha256", pa.string()),
        ("file_kind", pa.string()),
        ("is_blank", pa.bool_()),
        ("encoding", pa.string()),
        ("has_bom", pa.bool_()),
        ("n_feff", pa.int32()),
        ("decode_errors", pa.int32()),
        ("line_endings", pa.string()),
        ("n_control_chars", pa.int32()),
        ("n_odd_line_separators", pa.int32()),
        ("n_latin1_supplement", pa.int32()),
        ("n_prefix_tags", pa.int32()),
        ("n_token_tags", pa.int32()),
        ("n_img_tags", pa.int32()),
        ("n_urls", pa.int32()),
        ("aux_reason", pa.string()),
        ("n_lines", pa.int64()),
        ("n_nonempty_lines", pa.int64()),
        ("max_line_chars", pa.int64()),
        ("n_chars", pa.int64()),
        ("n_tokens", pa.int64()),
        ("n_hebrew_tokens", pa.int64()),
        ("n_hebrew_letters", pa.int64()),
        ("n_niqqud", pa.int64()),
        ("n_cantillation", pa.int64()),
        ("n_latin_letters", pa.int64()),
        ("n_digits", pa.int64()),
        ("hebrew_ratio", pa.float32()),
        ("niqqud_per_letter", pa.float32()),
        ("dup_count", pa.int32()),
        ("dup_rank", pa.int32()),
        ("is_dup_copy", pa.bool_()),
        ("dup_of", pa.string()),
        ("dup_cross_corpus", pa.bool_()),
        ("subcorpus", pa.string()),
        ("source", pa.string()),
        ("section", pa.string()),
        ("work", pa.string()),
        ("base_work", pa.string()),
        ("commentary", pa.string()),
        ("era_label", pa.string()),
        ("author", pa.string()),
        ("year", pa.int32()),
        ("genre", pa.string()),
        ("ext_id", pa.string()),
        ("date", pa.string()),
        ("meta_issue", pa.string()),
        ("meta_json", pa.string()),
        ("stratum", pa.string()),
        ("period_status", pa.string()),
        ("curation_rule", pa.string()),
        ("subperiod", pa.string()),
        ("include_default", pa.bool_()),
        ("exclusion_reasons", pa.list_(pa.string())),
        ("inventory_version", pa.string()),
        ("curation_hash", pa.string()),
    ]
)


def documents(
    corpus: str | list[str] | None = None,
    *,
    default_only: bool = False,
    text_only: bool = False,
    columns: list[str] | None = None,
    path: Path = DOCUMENTS_PATH,
):
    """Load the catalog as a pandas DataFrame, optionally filtered.

    ``default_only`` keeps the default comparison set (include_default); ``text_only`` keeps all
    text files (file_kind == 'text'), regardless of period or duplication.
    """
    if not path.exists():
        raise FileNotFoundError(f"No catalog at {path}. Run: uv run hebloc inventory")
    filters = []
    if corpus is not None:
        filters.append(("corpus_id", "in", [corpus] if isinstance(corpus, str) else list(corpus)))
    if default_only:
        filters.append(("include_default", "==", True))
    if text_only:
        filters.append(("file_kind", "==", "text"))
    table = pq.read_table(path, columns=columns, filters=filters or None)
    return table.to_pandas()
