# Data Dictionary

One section per persisted table. Tables are added milestone by milestone: `units` in M2;
`dicta_raw`, `tokens` and `runs` in M3/M4; statistics in M6.

## `documents`: `data/catalog/documents.parquet` (M1, inventory v2)

One row per file under `corpora/`, **including** empty, duplicate, auxiliary and out-of-period
files. The primary key is `doc_id`. Schema: `hebloc.catalog.DOCUMENTS_SCHEMA`. Load with
`hebloc.catalog.documents(view=None | "full" | "curated")`.

**Views (D-015):**
- **full** (`in_full_view`) is the *primary reference*: every corpus text file as supplied.
- **curated** (`in_curated_view`) is an *additional* analytical view: full minus blank files,
  documents not tagged `in_period`, and duplicate copies within the same stratum|source.

| Column | Type | Meaning |
|---|---|---|
| `doc_id` | string | Stable 12-hex BLAKE2b hash of `rel_path`. The key used by all later tables |
| `corpus_id` | string | `mikra` \| `hazal` \| `medieval` \| `haskala` \| `modern` |
| `rel_path` | string | Path relative to `corpora/`, with `/` separators (e.g. `Mikra/Tanakh - Torah - Genesis.txt`) |
| `file_name`, `ext` | string | File name; lower-case extension |
| `size_bytes` | int64 | File size |
| `sha256` | string | SHA-256 of the file bytes. Equals the baseline, and is pinned by the anchor |
| `file_kind` | string | `text` \| `empty` (0 bytes) \| `auxiliary` (non-corpus file, e.g. a 7-Zip log) |
| `aux_reason` | string | Why a file is auxiliary (extension or content signature) |
| `is_blank` | bool | The decoded text is whitespace only |
| `encoding` | string | `utf-8` \| `utf-8-sig` \| `ascii` \| `cp1255` \| `empty` \| `*-lossy`. Strict detection; see `hebloc.textstats` |
| `has_bom`, `n_feff` | bool, int32 | UTF-8 BOM at the start of the file; count of U+FEFF characters inside the text |
| `decode_errors` | int32 | Replacement characters introduced by lossy decoding (0 for every current file) |
| `line_endings` | string | `lf` \| `crlf` \| `mixed` \| `none` |
| `n_control_chars`, `n_odd_line_separators`, `n_latin1_supplement` | int32 | Anomaly counters. Odd line separators are a lone `\r`, U+0085, U+2028 and U+2029 |
| `n_prefix_tags`, `n_token_tags`, `n_img_tags`, `n_urls` | int32 | Old-tokenizer artifacts (`prefix=`, `token=`), `[ IMG ]` markers and URLs, to be cleaned in M2 |
| `n_lines`, `n_nonempty_lines`, `max_line_chars` | int64 | Lines are delimited by `\n` only (`hebloc.textstats.split_lines`) |
| `n_chars` | int64 | Decoded characters (BOM excluded) |
| `n_tokens`, `n_hebrew_tokens` | int64 | Whitespace tokens, and tokens with at least one Hebrew letter. These are raw orthographic counts, not linguistic words |
| `n_hebrew_letters`, `n_niqqud`, `n_cantillation`, `n_latin_letters`, `n_digits` | int64 | Character-class counts |
| `hebrew_ratio` | float32 | Hebrew letters ÷ (Hebrew + Latin letters) |
| `niqqud_per_letter` | float32 | Niqqud marks per Hebrew letter. Roughly 0.8 means fully vocalized |
| `dup_scope` | string | Duplicate scope = `stratum|source`. Duplicates are resolved only inside a scope |
| `dup_count`, `dup_rank` | int32 | Size of the identical-bytes group *within the scope*; rank by `rel_path` (0 = canonical) |
| `is_dup_copy`, `dup_of` | bool, string | A non-canonical copy within its scope; `doc_id` of the canonical file in the same scope |
| `dup_count_global` | int32 | Number of identical files anywhere in `corpora/` |
| `dup_cross_scope`, `dup_cross_corpus` | bool | Identical bytes also exist in another scope or corpus. Such copies are **kept**, only flagged |
| `subcorpus`, `source`, `section`, `work`, `base_work`, `commentary`, `era_label`, `author`, `year`, `genre`, `ext_id`, `date` | various | Generic metadata parsed from the path. What each field means per corpus is described in `hebloc.metadata` |
| `meta_issue` | string | Set when a file name did not match its corpus pattern (none at present) |
| `meta_json` | string (JSON) | Corpus-specific extras, e.g. `tractate`, `series`, `hilchot`, `unit_label`, `text_only_edition` |
| `stratum` | string | Curation stratum (e.g. `hazal.commentary`), from `config/curation.yaml` |
| `period_status` | string | `in_period` \| `out_of_period` \| `needs_review` |
| `curation_rule` | string | Id of the rule that assigned the tags |
| `subperiod` | string | Haskala only: `haskala` (year ≤ cutoff, 1881) or `post_haskala` |
| `in_full_view` | bool | Full view (primary reference): `file_kind == 'text'` and not blank (the file contains text) |
| `in_curated_view` | bool | Curated view (additional): text, not blank, `in_period`, not a duplicate copy within its scope |
| `curated_exclusion_reasons` | list<string> | Every reason the file is outside the curated view (empty list ⇔ included) |
| `inventory_version`, `curation_hash` | string | Provenance: inventory code version, and a hash of the curation YAML |

Companion file: `data/catalog/documents.manifest.json` records the creation time, code commit,
curation hash, per-corpus counts and verification results.
