# Data Dictionary of the Analysis Package

All tables are Parquet. Open them through `hebpack.db.connect()` (DuckDB views, below) or with pandas/pyarrow.
Every row traces back to the source: `sent_id` → `doc_id` → `documents.rel_path` + `sentences.line_no` + offsets.

**Keys:**
- `sent_id` = `<corpus>:<doc_id>:<line_no>:<k>`: one unit, i.e. a verse in Mikra and a sentence elsewhere.
- `doc_id` = one corpus file.
- A token is identified by (`sent_id`, `piece_idx`, `word_idx`).

## `tokens` (`data/tokens/<corpus>/<run_id>.parquet`): every word Dicta produced

{{TOKENS}} rows, including punctuation. One file per parse run: Mikra, Hazal, Medieval and Haskala have one run
each, and Modern has 27 runs (slices of the corpus). Inside a file, each Parquet row group is one parse shard.
The **words** view = tokens with `upos <> 'PUNCT'`; this is the official definition of a word.

| Column | Meaning |
|---|---|
| `sent_id`, `corpus_id`, `doc_id` | Unit, corpus, document |
| `piece_idx`, `n_pieces` | Piece of the unit (`n_pieces = 1`: parsed whole, one tree) |
| `word_idx`, `sent_word_idx` | Position in the piece; position in the unit (null after an `error` piece; there are none) |
| `char_start`, `char_end`, `surface` | Span in the unit's `text_norm` and the exact slice. **`surface` = the official word type** |
| `ws_idx` | Index of the whitespace token of `text_norm` containing the word |
| `form` | Dicta's own string for the word (differs from `surface` only for 16 `[UNK]` words) |
| `prefix`, `host` | Proclitic letters (e.g. `וב`) and the rest of the word. Dicta never splits a word into more than 2 parts |
| `lemma`, `lemma_blank` | Dicta's lemma (dictionary form; for verbs it includes the binyan, not the root). `[BLANK]` = the model abstained |
| `upos` | Universal POS (16 values) |
| `feats` | All of Dicta's word features as a string, e.g. `Gender=Masc\|Number=Plur\|Person=3\|Tense=Past` |
| `gender`, `number`, `person`, `tense` | The same features as columns (multi-values such as `Fem,Masc` or `1,2,3` kept as Dicta gives them) |
| `prefix_upos` | POS of each prefix, a list (e.g. `["CCONJ","ADP","DET"]`). `DET` in it = definite article |
| `suffix`, `suffix_feats` | Pronominal suffix: `PRON` (possessive/object, e.g. ספרו) or `ADP_PRON` (on a preposition, e.g. לו), with its features |
| `head`, `head_sent`, `deprel` | Head of the word as piece-local index and as unit index (`-1` = root); UD relation (e.g. `nsubj`, `obj`, `obl`, `compound:smixut`) |
| `ner` | Named-entity tag, BIO format (`B-PER`, `I-PER`, `B-GPE`, … or `O`). Entity spans = a `B-` tag followed by `I-` tags of the same label |
| `status` | `ok` (or `mst_fallback`: never occurs) |
| `piece_tree_valid` | False when the word-level tree of the piece is not a tree (excluded from depth; never repaired) |
| `tokens_version`, `shard` | Bookkeeping: derivation version; parse shard |

**What Dicta does not provide:** construct state (only visible as the relation `compound:smixut`), binyan, and
verbal form (participle, infinitive).

**Derivable, not stored:**
- the head's word: join on `head_sent` (= `sent_word_idx` of the head);
- the root: `head = -1`;
- entity spans: from the BIO `ner` tags (checked identical to Dicta's own entity list).

## `sentences` (`data/sentences/<corpus>/part-*.parquet`): every unit

{{UNITS}} rows. Byte-identical copies of the project's unit tables.

| Column | Meaning |
|---|---|
| `sent_id`, `corpus_id`, `doc_id`, `line_no`, `k` | Unit id, corpus, document, 1-based line in the source file, position in the line |
| `unit_type`, `ref` | `verse` (Mikra) or `sentence`; readable reference (e.g. `Genesis 2:7`, `Mishnah Beitzah ¶11`) |
| `char_start`, `char_end` | Offsets in the source line |
| `text_raw` | **Exact original text** (with niqqud and markup) |
| `text_norm` | The normalized text that Dicta parsed: niqqud and cantillation stripped; Mikra uses the Qere |
| `text_norm_alt` | Mikra: the Ketiv reading where it differs; otherwise null |
| `norm_flags` | Every normalization rule applied to the unit |
| `is_empty_norm`, `n_tokens_norm`, `n_hebrew_tokens_norm` | Empty after normalization; whitespace tokens; tokens containing a Hebrew letter |
| `aramaic` | Mikra: `aramaic`, `aramaic_partial` or null (Daniel, Ezra, Jer 10:11, Gen 31:47) |
| `stratum` | Sub-corpus tag, e.g. `hazal.mishnah`, `medieval.thought_translated`, `modern.news.haaretz` (31 values) |
| `in_full_view`, `in_curated_view` | Full view = everything (official statistics); curated = in period, not blank, deduplicated |
| `norm_version`, `segment_version` | Rule versions |

## `unit_metrics` (official): one row per unit

| Column | Meaning |
|---|---|
| `n_words`, `n_punct`, `n_distinct_words` | Words (non-punctuation), punctuation tokens, distinct `surface` values among words |
| `n_pieces`, `n_error_pieces` | Pieces of the unit; pieces Dicta failed on (0 everywhere) |
| `tree_status` | `complete` (one valid tree) · `invalid_tree` · `multi_piece` · `no_words` (only punctuation) · `empty` · `parse_error` |
| `depth` | Levels from the root to the deepest word (root = 1), only when `tree_status = 'complete'` |

**Official usage:**
- length (R2) and distinct words (R3) use the statuses `complete`, `invalid_tree` and `multi_piece`;
- depth (R4) uses `complete` only.

## `documents` (`data/documents.parquet`): one row per corpus file (66 columns; the useful ones)

| Column | Meaning |
|---|---|
| `doc_id`, `corpus_id`, `rel_path`, `file_name` | File identity (path relative to the corpora folder) |
| `subcorpus`, `source`, `section`, `work`, `base_work`, `commentary` | Parsed from the path (e.g. Modern `source` = haaretz, a7, blogs, …) |
| `author`, `year`, `genre`, `ext_id`, `date`, `meta_json` | Haskala: from the file name `author--title--year--genre--id` |
| `era_label` | Period label where known |
| `stratum`, `period_status`, `subperiod` | Sub-corpus tag; `in_period` / `out_of_period` / `needs_review`; Haskala `haskala` (≤1881) / `post_haskala` |
| `in_full_view`, `in_curated_view`, `curated_exclusion_reasons` | Views and why a file is outside the curated view |
| `is_dup_copy`, `dup_of`, `dup_count`, … | Exact duplicate files (kept, flagged) |
| `encoding`, `n_lines`, `n_tokens`, `n_hebrew_tokens`, `n_niqqud`, `hebrew_ratio`, … | File statistics |
| `file_kind`, `is_blank`, `aux_reason` | `text`, `empty` or `auxiliary` (7-Zip logs) |

## `pieces` and `run_units` (processing, rarely needed)

- **`pieces`:** one row per parser piece.
  - Columns: `n_pieces`, span in `text_norm` (`norm_char_start/end`), whitespace-token range, `cost` in model
    sub-words (budget 510), and Dicta's `status` / `compute_mst` / `error`.
  - Only 733 units have more than one piece.
- **`run_units`:** which run holds each unit, with `text_sha1` = sha1 of the parsed text (= `text_norm`).

## Official tables (`official/stats_tables/{{STATS_ID}}/`, views `official_<name>`)

| Table | Content |
|---|---|
| `coverage` | units by status, words, punctuation, blank lemmas, exclusions |
| `lexicon` | tokens, types and types occurring once, for words and for lemmas |
| `word_freq`, `lemma_freq` | every word type / lemma with its frequency and rank (complete lists) |
| `sentence_stats`, `distributions` | length, distinct words and depth: summary statistics and full distributions |
| `depth_by_length`, `tree_status` | mean depth per length band; units and words per tree status |
| `pos`, `features`, `deprel` | POS counts; every inflection feature value per POS; relation counts |

CSV versions (top 1,000 for frequency lists) are in `official/results/`, figures in `official/results/figures/`.
Definitions: `docs/m6_design.md` §2.2.
