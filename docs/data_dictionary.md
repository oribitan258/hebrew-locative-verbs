# Data Dictionary

One section per persisted table. Tables are added milestone by milestone: `documents` (M1),
`units` (M2); parse runs (`inputs`, `pieces`, `dicta_raw`, `tokens`) in M3/M4; statistics in M6.
Every table is registered in `hebloc.store.schemas` (schema, key, version), and `hebloc check`
verifies every file on disk against it. How to *use* the data layer: [data_layer.md](data_layer.md).

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

## `units`: `data/units/<corpus>/part-*.parquet` (M2/M2.1; norm v1, segment v2)

One row per **complete** sentence or verse of every document in the full view. Units are never cut for a model's input limit (segment v2, D-020). The primary key is
`sent_id`; `doc_id` links to `documents`. Each corpus folder has a `_manifest.json` (counts,
checks, flag counts, versions, code commit). Schema: `hebloc.units.UNITS_SCHEMA`. Methodology:
`docs/m2_preprocessing.md`.

Read with `hebloc.data.units(corpus, view=None|"full"|"curated", columns=[...])` (pandas), or
`hebloc.data.iter_units(...)` to stream Arrow batches (Modern). `hebloc.data.trace(sent_id)`
maps a unit back to its source and verifies it. `hebloc.data.connect()` returns DuckDB with the
views `documents`, `units` and the annotation views (see "DuckDB catalog" below).

| Column | Type | Meaning |
|---|---|---|
| `sent_id` | string | `<corpus>:<doc_id>:<line_no>:<k>`. Stable unit id |
| `corpus_id`, `doc_id` | string | Corpus; link to `documents` |
| `line_no` | int32 | 1-based line in the decoded source file (split on `
` only) |
| `k` | int16 | 0-based position of the unit within its line |
| `unit_type` | string | `verse` (Mikra) \| `sentence`. (Segment v1 also had `chunk`; removed by D-020.) |
| `char_start`, `char_end` | int32 | Offsets in the decoded line: `line[char_start:char_end] == text_raw` |
| `ref` | string | Human reference: `Genesis 2:7`; `<work> ¶<line>[.<k+1>]`; Rambam `Mishneh Torah/<sefer>/<hilchot>/<chapter> ¶<line>`; Haskala `<Ytext id> ¶…`; Modern `<path> ¶…` |
| `text_raw` | string | **Exact source text** of the unit, never modified (incl. niqqud and markup) |
| `text_norm` | string | Normalized model input (rules: `hebloc.normalize`, `hebloc.artifacts`) |
| `text_norm_alt` | string | Alternative reading where one exists: Mikra **Ketiv** (the Qere is in `text_norm`); otherwise null |
| `norm_flags` | list<string> | Every normalization rule that fired (e.g. `ketiv_qere`, `diacritics_stripped`, `prefix_R2`, `prefix_unresolved:hyphen_punct`) |
| `is_empty_norm` | bool | Normalization left no text (separator lines; Joshua 21:36–37 placeholders) |
| `n_tokens_norm`, `n_hebrew_tokens_norm` | int32 | Whitespace tokens of `text_norm`, and how many contain a Hebrew letter (orthographic; not linguistic word counts) |
| `aramaic` | string | Mikra only: `aramaic` \| `aramaic_partial` \| null |
| `stratum`, `in_full_view`, `in_curated_view` | string, bool, bool | Copied from `documents`, for convenient filtering |
| `norm_version`, `segment_version` | string | Rule versions used (currently `1`, `2`) |

## `pieces` metadata (defined in M2.1; written by parse runs from M3)

A *piece* is a span of a unit's `text_norm`, cut only when the whole unit exceeds the parser's
input budget. It is a processing artifact, not a linguistic unit. Every parse run stores one row
per piece next to the raw parser output. Schema: `hebloc.pieces.PIECES_SCHEMA`. Rule:
`hebloc.pieces.plan_pieces` (`piece_version` 1). Primary key: (`sent_id`, `piece_idx`).

| Column | Type | Meaning |
|---|---|---|
| `sent_id` | string | Parent unit (complete sentence or verse) |
| `piece_idx`, `n_pieces` | int16 | Position of the piece, and the number of pieces of the unit. `n_pieces = 1` means the unit was parsed whole (complete tree) |
| `norm_char_start`, `norm_char_end` | int32 | Span in the unit's `text_norm`. Pieces are separated only by whitespace, and together they contain every token (`verify_pieces`) |
| `tok_start`, `tok_end` | int32 | Whitespace-token range `[tok_start, tok_end)` of `text_norm` |
| `cost`, `budget`, `cost_unit` | int32, int32, string | Cost of the piece and the budget, in `cost_unit` (e.g. Dicta sub-words, set in M3). A single token over budget is isolated and logged, never truncated |
| `piece_version` | string | Rule version |

## `migrations/segment_v1_to_v2`: `data/migrations/segment_v1_to_v2/` (M2.1)

Written by `hebloc verify-units-v2`, which compares `data/units_v1` (the preserved v1 output)
with `data/units`.

| File | Contents |
|---|---|
| `report.json` | Per-corpus checks and counts; `structural_ok` |
| `map.parquet` | One row per v1 unit on a line that had chunks (14,733 rows). Columns: `old_sent_id`, `old_unit_type`, `old_ref`, `old_char_start/end`, `new_sent_id`, `new_ref`, `new_char_start/end`, `relation` (`merged_into` \| `renumbered` \| `same_id`), and `piece_idx`/`n_pieces` (the chunk's position in its sentence). On all other lines, v1 and v2 ids are identical |
| `differences.parquet` | Every derived-value difference found (`new_sent_id`, `rel_path`, `line_no`, `kind`, `detail`). All are explained in D-020 |


## Parse runs: `data/annotations/<collection>/runs/<run_id>/` (M3 layout, final for M5 in M4)

`<collection>` is `pilot` for the M3 runs and the corpus id for M5 runs
(`hebloc.store.runs.run_dir_for(corpus, run_id)`). A run is referred to as `"<collection>/<run_id>"`.
Written by `hebloc.parse.run.run` (sharded, resumable, atomic). Every run is self-contained:

| Path | Contents |
|---|---|
| `inputs/shard-*.parquet` | `sent_id`, `text` (the exact text parsed; for default runs = `units.text_norm`, checked), `text_sha1`. Key: `sent_id` |
| `pieces/shard-*.parquet` | `PIECES_SCHEMA` rows (above); budget 510 model sub-words; `cost_unit` names the tokenizer and revision. Key: (`sent_id`, `piece_idx`) |
| `dicta_raw/shard-*.parquet` | One row per piece: `sent_id`, `piece_idx`, `status` (`ok` \| `mst_fallback` \| `error`), `compute_mst`, `error`, `raw_json` (**verbatim** `predict(output_style="json", per_token_ner=True)` output). Key: (`sent_id`, `piece_idx`) |
| `_shards/shard-*.json` | Shard manifest: resume key, counts, statuses, seconds, peak memory. Written last: **a shard exists only if this file exists** |
| `tokens/shard-*.parquet` | Derived from that shard's three files only (schema below). Key: (`sent_id`, `piece_idx`, `word_idx`) |
| `tokens/_shards/shard-*.json` | sha256 of the three source files, `tokens_version`, rows, sha256 of the tokens file. A shard is re-derived only when one of these changes (`hebloc tokens`) |
| `run.json` | Run manifest: model repo and revision, applied runtime fixes, code commit, norm/segment/piece versions, budget, batch settings, threads, library versions, totals, throughput |
| `checks.json` | `hebloc.parse.checks.validate_run` report, with `fingerprint` (hash of the committed shard keys + tokens version). A later `hebloc check` trusts the report only while the fingerprint is current |

All pieces of a unit are in the unit's shard, so per-shard derivation and validation are exact and
memory is bounded by one shard. Readers (`read_run`, DuckDB views, exports, bundles) use
**committed shards only**: files of an interrupted shard are never read as data, and
`hebloc check` reports them.

`ud` / `iahlt_ud` CoNLL-U can be regenerated exactly from `raw_json`
(`convert_output_to_ud`, verified in M3 and again in M4 on 50 pieces), so they are not stored
(D-023). `hebloc export-conllu` writes them on demand.

*Change in M4 (D-031):* the M3 runs stored one `tokens/tokens.parquet` per run. They were
re-derived per shard, checked row-for-row identical (all 11 pilot runs), and the single file was
removed (`hebloc.parse.tokens.migrate_legacy`).

### `tokens` (PROPOSED; `hebloc.parse.tokens.TOKENS_SCHEMA`, tokens_version 1)

One row per Dicta word. Dicta words follow the tokenizer's pre-tokenization: punctuation is split
from words, and Hebrew acronyms (`ל"ב`) and the listed abbreviations stay whole.

| Column | Meaning |
|---|---|
| `sent_id`, `piece_idx`, `n_pieces` | Parent unit and piece. `n_pieces = 1` means one complete tree |
| `word_idx`, `sent_word_idx` | Position in the piece; position in the unit. `sent_word_idx` is **null** for the pieces that follow an `error` piece of the same unit (the offset is unknown, so it is never guessed) |
| `char_start`, `char_end`, `surface` | Span in the parsed unit text, and the exact slice. Provenance: → unit → source line |
| `ws_idx` | Index of the whitespace token of the unit that contains the word |
| `form` | The model's normalized word string (NFD, diacritics stripped, foreign characters → `UNK`) |
| `prefix`, `host` | Segmented proclitic letters (e.g. `וב`) and the rest of the word |
| `lemma`, `lemma_blank` | Dicta lexeme. `[BLANK]` (the model abstained) is kept verbatim and flagged |
| `upos`, `feats`, `gender`, `number`, `person`, `tense` | UD POS. The **only** morphological features Dicta predicts are Gender, Number, Person and Tense: **no binyan, no definiteness, no construct state** |
| `prefix_upos` | POS of the prefixes (e.g. `["CCONJ","ADP","DET"]`) |
| `suffix`, `suffix_feats` | `PRON` or `ADP_PRON` with its features, or null |
| `head`, `head_sent`, `deprel` | Head as piece-local index and as unit index (`-1` = root), and the UD relation. `head_sent` is null where `sent_word_idx` is (above), or when the model gave no head |
| `ner` | Per-word NER label |
| `status` | `ok`, or `mst_fallback` (tree decoded without the MST step) |
| `piece_tree_valid` | False if the piece's **word-level** tree is not a tree (cycle, self-loop or ≠ 1 root). Dicta's sub-word tree is valid, but the sub-word → word head mapping can break it (D-025). Never repaired: exclude these pieces from tree statistics and report the count |

## Canonical runs: `config/annotations.yaml` (M4; git-tracked; D-032)

`canonical: {<corpus>: [<collection>/<run_id>, …]}`. The default annotations of a corpus
(`hebloc.data.tokens(corpus)` and the DuckDB views `tokens`, `pieces`, `dicta_raw`, `inputs`)
come only from the runs listed for it, each restricted to that corpus's units. **Empty until M5.**
Pilot runs are read explicitly (`run="pilot/<run_id>"`). `hebloc check` requires every listed run
to exist, be complete, have `variant = default` and pass validation, and requires that no unit has
two canonical analyses.

## DuckDB catalog: `data/hebloc.duckdb` (M4; `hebloc catalog`; views, no copies)

The same definitions back `hebloc.data.connect()` in memory (`hebloc.store.catalog`).

| View | Contents |
|---|---|
| `documents`, `units` | The M1/M2 tables |
| `runs` | Small table: one row per parse run (model, revision, variant, fixes, versions, units, completeness, tokens status, `canonical_for`) |
| `inputs_all`, `pieces_all`, `dicta_raw_all`, `tokens_all` | Every run (pilot included), committed shards only, with `run`, `corpus_id` and `doc_id` columns. **Always filter on `run`**: several pilot runs parse the same units |
| `inputs`, `pieces`, `dicta_raw`, `tokens` | Canonical runs only, with the same extra columns. Typed and empty until M5 |
| `piece_status` | Canonical pieces with parse `status`, word count and word-level `tree_valid` |
| `parse_coverage` | Per `corpus_id` × `stratum`: `units`, `units_nonempty`, `units_parsed`, `units_multi_piece`, `units_with_error_piece`, `units_with_invalid_tree` (what every statistic must report, D-021/D-025) |

`corpus_id` and `doc_id` are taken from `sent_id`, so annotations join `documents` (views, strata,
metadata) without scanning `units`. The file stores absolute paths, so rebuild it after moving the
project.

## Integrity report: `data/catalog/integrity.json` (M4; `hebloc check`)

Read-only checks:
- `documents`: schema, unique `doc_id`, row count = anchor;
- `units` per corpus: schema, rows = `_manifest.json`, unique well-formed `sent_id` consistent with its columns, every `doc_id` a full-view document of the same corpus, current versions;
- every run: no orphan or missing shard files, schemas, tokens up to date by hash, parsed `sent_id`s are units, default-variant runs parsed exactly `text_norm`, versions, `checks.json` ok and current (`--deep` re-validates);
- the canonical registry.

Model-output facts (invalid trees, error pieces) are reported, but they are not integrity failures.

## CoNLL-U exports: `data/exports/conllu/` (M4; `hebloc export-conllu`; regenerable)

One CoNLL-U sentence per piece, produced by Dicta's own `convert_output_to_ud` from `raw_json`
(byte-identical to `predict(output_style="ud" | "iahlt_ud")`, verified on 50 pieces). Header:
`# sent_id` (`<sent_id>`, or `<sent_id>~p<piece_idx>` for multi-piece units), `# text`, and
`# hebloc_sent_id`, `# hebloc_piece = <idx>/<n>`, `# hebloc_norm_span`, `# hebloc_ref`,
`# hebloc_run`, `# hebloc_status`, `# hebloc_tree_valid`. The only change to Dicta's lines: an
empty field is written as `_`. `--valid-only` skips pieces with an invalid word-level tree (counted).

## Bundles: `data/bundles/hebloc-annotations-<collection>-<run_id>.zip` (M4; D-012, D-033)

An uncompressed zip of every file of one run, at its path under `data/`, plus `BUNDLE_MANIFEST.json`:
- sha256 and size of every file;
- the corpora anchor (`manifest_sha256`, file count, bytes);
- code commits (run and bundle), model repo and revision, runtime fixes;
- norm/segment/piece/runner/tokens versions;
- row counts per table; validation result and fingerprint.

A `<zip>.sha256` sidecar holds the digest of the zip itself. See [data_management.md](data_management.md).

## Statistics: `data/stats/<status>-<YYYYMMDD>-<hash>/` (M6; `hebloc stats run`; D-046)

One folder per computation. It is never overwritten: a different run set, code commit or stats code
gives a new id. The folder is assembled as `<id>.partial` and renamed only after every
reconciliation check passed. `status` is `provisional` for an explicit run list and `final` only for
the registered runs of all five corpora (D-045). Design and definitions: [m6_design.md](m6_design.md).
Python: `hebloc.stats.compute.load(<folder>)`; `hebloc stats verify <folder>` re-hashes every file.

| File | One row per | Content |
|---|---|---|
| `manifest.json` | — | Runs and their fingerprints, completeness checks, code commit, `stats_code_sha256`, stats version, decisions, timings, row count and sha256 of every file |
| `unit_metrics/<corpus>/<run_id>.parquet` | unit | `sent_id`, `corpus_id`, `doc_id`, `n_words` (non-punctuation Dicta words), `n_punct`, `n_distinct_words` (distinct `surface`), `n_pieces`, `n_error_pieces`, `tree_status` (`complete` \| `multi_piece` \| `invalid_tree` \| `parse_error` \| `no_words` \| `empty`), `depth` (root = 1; null unless `complete`) |
| `coverage.parquet` | corpus | Units by status, tokens, words, punctuation, blank lemmas, pieces, `mst_fallback` pieces, words excluded from depth |
| `lexicon.parquet` | corpus × kind | Tokens, types and types occurring once, for words and lemmas (R1) |
| `word_freq.parquet` / `lemma_freq.parquet` | corpus × type | `rank`, `word`/`lemma`, `n`, `share`. Every type; `[BLANK]` lemmas excluded (R1) |
| `sentence_stats.parquet` | corpus × measure | `length`, `distinct_words`, `depth`: units, mean, sd, min, p5/p25/p50/p75/p95/p99, max (R2–R4) |
| `distributions.parquet` | corpus × measure × value | Number and share of units with that value (R2–R4) |
| `depth_by_length.parquet` | corpus × length band | Units, mean length, mean/median/min/max depth (R4) |
| `tree_status.parquet` | corpus × status | Units and words per tree status: what depth excludes (D-021, D-025) |
| `pos.parquet` | corpus × UPOS | `n`, share of tokens, share of words (R5) |
| `features.parquet` | corpus × UPOS × feature × value | Every Dicta inflection feature: Gender, Number, Person, Tense, `Suffix` (PRON/ADP_PRON), `Suffix.Gender/Number/Person`, `Definite (DET prefix)`. `(none)` = not marked; UPOS `(all words)` = all words (R5) |
| `deprel.parquet` | corpus × relation | `n`, share of tokens, `n_words`, share of words (R6) |

A provisional folder also holds `report/` (CSV, `figures/*.png`, `stats_report.md`), which is local
only. The final run writes these to `results/stats/` and `docs/stats_report.md`. Parser accuracy
(final) is in `results/stats/accuracy/`: `mikra_vs_bhsa.json`, `layers.csv`, `pos_confusion.csv`,
`tense_confusion.csv` and `excluded_verses.csv` (references only, no corpus text).
