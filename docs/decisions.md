# Decision Log

Each entry records **what** was decided, **why**, and **status**:
- `accepted`: in force.
- `hypothesis`: a default that must be validated in a pilot.
- `superseded`: replaced by a later entry.

Newest entries go at the bottom.

---

### D-001 · Active scope limited to the data foundation (2026-11-06) · accepted
Implement only inventory → units → Dicta parsing → data layer → §4 statistics, then stop for review.
Locative extraction, classifiers and LLM work stay in `docs/roadmap.md`.
*Why:* the user's instruction. Later research stages will be agreed with the project partners.

### D-002 · `corpora/` is immutable (2026-11-06) · accepted
No file under `corpora/` is ever edited, renamed, moved, deleted or written. Cleaning, normalization,
segmentation, tagging and filtering exist only in derived files under `data/`.
*Enforcement:* `tests/test_corpora_immutable.py` against a recorded baseline, which is itself
pinned by a git-tracked anchor (D-011).

### D-003 · Out-of-period texts are tagged, not dropped (2026-11-06) · accepted
- Later commentaries in `Hazal/`, the 13th-c. Yalkut Shimoni, post-medieval Musar and similar texts are kept, cataloged and parsed.
- They get stratum tags and are **excluded from the default comparison filter**.
- Statistics always report *full coverage* and *default filter* side by side.

*Why:* corpus composition affects period comparisons (~38% of Hazal's words are commentary), but
silently removing data would hurt reproducibility and transparency.

### D-004 · Modern coverage decided after benchmark (2026-11-06) · accepted
Modern is ~133M words (haaretz ~99M). The choice between full, partial and sampled coverage is made
explicitly by the user after the M3 throughput and storage benchmark, from presented options.

### D-005 · External reference data allowed for validation (2026-11-06) · accepted
- A Tanakh versification table, needed because Mikra files have no chapter:verse labels. It is validated by an exact per-book verse-count match.
- ETCBC/BHSA, an expert-annotated Hebrew Bible, used as gold to measure Dicta's accuracy on Mikra.
- Stored under `data/external/`, with the source URL and version recorded.

### D-006 · Python 3.12 via uv (2026-11-06) · accepted
The system default (3.14) is too new for reliable PyTorch/transformers wheels. `uv` pins 3.12, and
`uv.lock` makes the environment reproducible.

### D-007 · Storage: Parquet (system of record) + DuckDB (query layer) (2026-11-06) · accepted
- Columnar, typed and compressed. Append-per-shard writes give resumability.
- Readable from pandas, pyarrow, polars and DuckDB.
- DuckDB views avoid keeping a second copy of the data.
- Rejected alternatives: SQLite (slow aggregates), CoNLL-U only (offered as an export instead), a database server (overkill).

### D-008 · Keep raw Dicta responses losslessly (2026-11-06) · hypothesis (sizes to confirm in M3)
Raw JSON responses are stored in Parquet (zstd), keyed by `sent_id`, so statistics and future
research never require re-running Dicta. To test in M3: does the `json` output contain everything
in `ud`? If not, the `ud` output is stored as well.

### D-009 · Preprocessing defaults (2026-11-06) · hypothesis (validate in M2/M3) · refined by D-018
Every row below is a **hypothesis**, not a settled choice. None becomes `accepted` until the M3
pilot has compared it with its alternative and the user has approved the result.

| Choice | Default (hypothesis) |
|---|---|
| Units | Mikra: verse. Modern: source line. Other corpora: paragraph split on `. : ? !` with abbreviation guards; over-length units are chunked *(superseded: see D-018 and D-020; units are never chunked since segment v2)* |
| Diacritics | Strip niqqud and cantillation in `text_norm`; keep the vocalized text in `text_raw` |
| Ketiv/Qere (Mikra) | **HYPOTHESIS, unvalidated:** Qere in `text_norm`; Ketiv preserved in `text_raw` / `norm_flags` so either reading can be re-derived. M3 pilot test: parse the affected verses both ways and compare lemma/POS/tree plausibility (and BHSA agreement), then decide |
| Maqaf (Mikra `-`) | Replaced by a space |
| Mikra ASCII `'` `"` | Stripped (accent artifacts; Mikra only) |
| Markup and URLs | Removed from `text_norm`, and the unit is flagged |
| Encoding | Strict UTF-8 → cp1255 → flagged, decided per file |

### D-010 · Immutability guard has two levels (2026-11-06) · accepted
- **Fast default test:** file list + sizes + mtimes against the baseline. Runs in seconds.
- **Full sha256 re-verification:** marked `slow`, run with `uv run pytest -m slow`.

*Why:* re-hashing ~1 GB / ~404k files on every test run would make the test suite unusable.

### D-011 · Baseline pinned by a git-tracked anchor (2026-11-06) · accepted
The checksum baseline (`data/catalog/corpora_baseline.parquet`) is gitignored and regenerable, so on
its own it could be silently replaced. It is therefore pinned by `config/corpora_anchor.json`, which is
**tracked in git**. The anchor records:
- the expected file count (404,294),
- the total bytes (1,126,869,300),
- per-corpus file and byte counts,
- a canonical manifest digest: sha256 over the sorted lines `rel_path\tsize\tsha256\n`.

Mtimes are deliberately excluded from the digest, so the anchor identifies corpus *content* and
still validates a partner's copy.

Enforcement:
- `hebloc baseline --force` refuses to write a recomputed baseline that disagrees with the anchor.
- `hebloc anchor` refuses to re-anchor without `--force`.
- Tests check baseline ↔ anchor agreement, and check the anchor against the file counts measured
  independently during discovery.

The anchor was created from a baseline whose every checksum had already been re-verified
against the actual files (slow test, 2026-11-06).

Re-anchoring is allowed only after a deliberate, documented corpus change, recorded as a new
decision entry.

### D-012 · Backup and sharing strategy for derived data (2026-11-06) · accepted · implemented by D-033 (M4)
`data/` stays out of git. The expensive Dicta outputs will be backed up and shared as verified
per-corpus bundles: sha256 manifest plus anchor digest, code commit, model revision and
`norm_version`. Two copies are kept: an external drive and a private cloud folder. Derived data is
shared privately with the team and lecturer only, because of corpus copyright.

Full strategy: `docs/data_management.md`. Implementation is deferred until after M3 and must be in
place before M5.

### D-013 · Catalog design (M1) (2026-11-06) · accepted
- **One row per file**, including empty, duplicate, auxiliary and out-of-period files. `doc_id` is a
  BLAKE2b-48 hash of the path relative to `corpora/`, so it is stable across machines and runs.
- **Canonical text definitions** (`hebloc.textstats`), reused by M2 for line numbering:
  - *line* = `\n`-delimited. Python's `splitlines()` is deliberately not used, because it also
    splits on U+2028, U+0085 and others.
  - *token* = a whitespace run.
  - *Hebrew token* = a token with at least one letter U+05D0–U+05EA.
- **Encoding detection** is strict and per file: UTF-8, then cp1255, then a lossy fallback that is
  flagged.
- **Auxiliary files** are detected by extension *and by content*: the 7-Zip log signature caught
  `haaretz/6/60.7z.txt`.
- **Default comparison filter** = text ∧ not blank ∧ `in_period` ∧ not a duplicate copy. Every
  exclusion is recorded in `exclusion_reasons`. *(Replaced by the full and curated views, D-015.)*
- **Exact duplicates**: within a group of identical files, the first by path is canonical.
  *(Scope narrowed to stratum|source, D-015.)*
- **Write gate**: the catalog is written only if it matches the filesystem, the baseline and the
  git-tracked anchor.

### D-014 · Proposed curation tags (M1) (2026-11-06) · superseded by D-015 (approved with clarifications)
`config/curation.yaml` as described in `docs/corpus_report.md` §3 and §6. Open points:
1. Aggadic midrash stays in period.
2. Haskala files after 1881 stay in the default set, with a `subperiod` tag.
3. Seven unlabelled Musar files are `needs_review`.
4. Duplicates are excluded from the default set.
5. Modern artifacts (`prefix=`, `token=`, headers, URLs) are reconstructed or cleaned in M2.

### D-015 · Curation tags approved; full and curated views; scoped duplicates (2026-11-06) · accepted
User decisions on the M1 report (`docs/corpus_report.md` §6):
1. The strata and period tags are approved as **operational research metadata**, not definitive
   historical truth.
2. **Aggadic midrash stays in period**, because the assignment lists "מדרשים". It is documented as
   *not historically homogeneous* (Amoraic to post-Talmudic compilations).
3. **All Haskala texts are kept**, including those after 1881. The `subperiod` tag is preserved, and
   1881 is an *analytical cutoff*, not an absolute linguistic boundary.
4. The **7 undated Musar files stay `needs_review`**: they are in full-corpus analyses and outside the
   curated comparison pending verification.
5. **Exact duplicate copies are excluded from the curated view only, and only within the same
   duplicate scope** (`stratum|source`). Identical files in other corpora or source categories are
   kept and flagged (`dup_cross_scope`, `dup_cross_corpus`).

   Verified: the previous global detection had no cross-corpus or cross-source groups. The only
   cross-stratum group was three blank Haskala placeholders, so this change affects no real text.
6. **Views.** The *full view* (`in_full_view` = every supplied corpus text file) is the **primary
   reference** for all statistics. The *curated view* (`in_curated_view`) is an additional, clearly
   labelled analytical view.

   Schema change, inventory v2:
   - `include_default` → `in_curated_view`;
   - `exclusion_reasons` → `curated_exclusion_reasons`;
   - new columns `in_full_view`, `dup_scope`, `dup_count_global`, `dup_cross_scope`.

### D-016 · Modern/Rambam tokenization artifacts: investigate, do not assume (2026-11-06) · accepted
The `prefix=X` / `token=Y` artifacts (1.16M in Modern, 141 in Rambam) will be investigated in M2.
- No unvalidated reconstruction rule may be applied.
- The original text is always preserved (`text_raw`).
- Candidate rules are tested on representative and difficult examples before use: abbreviations
  (`prefix=ב token=רח'`), numbers (`prefix=כ - 20`), quotation marks (`prefix=ו ' ' דרילר`), and
  gershayim numerals in Rambam (`prefix=ל " ב`).

### D-017 · Unit table design (M2) (2026-11-06) · accepted
- **One unit per sentence or verse** for every non-empty line of every full-view document,
  out-of-period and duplicate documents included. The views are carried as columns.
- `sent_id = <corpus>:<doc_id>:<line_no>:<k>`.
- `text_raw` is the exact source slice at (`line_no`, `char_start`, `char_end`). This is asserted
  for every unit and re-verified independently by tests and by `hebloc.data.trace`.
- Extraction streams documents in parallel batches into Parquet row groups, writes each corpus
  folder atomically, and records a manifest (counts, checks, flags, versions, code commit).
- The pipeline refuses nothing silently: coverage, line counts and Mikra verse counts are checked
  for every document.
- The Tanakh versification comes from Sefaria's chapter lengths and is committed to git
  (`config/reference/tanakh_versification.json`, with source, date and digest). It is verified by an
  exact per-book verse-count match. Placing it in `config/` rather than `data/external/` refines
  D-005: the table is small and must be available without network access.

### D-018 · Segmentation and normalization rules v1 (M2) (2026-11-06) · accepted, with hypotheses
Rules and evidence are in `docs/m2_preprocessing.md`.
- **Accepted:**
  - segmentation on `. ? !` with bracket, initial and enumerator guards; the colon is not a terminator;
  - 200-token chunks *(superseded by D-020: units are complete sentences; splitting moved to parse time)*;
  - Mikra accent-quote and paragraph-marker removal;
  - Haskala markup handling, including the removal of editorial edition notes;
  - Rambam `+…+` citations converted to parentheses;
  - Haaretz header removal.
- **Hypotheses**, still unvalidated and to be tested with Dicta in M3:
  - diacritic stripping;
  - Qere in `text_norm` (with the Ketiv kept in `text_norm_alt`);
  - maqaf → space;
  - sof pasuq → `.`.

### D-019 · Artifact handling results (M2) (2026-11-06) · accepted; R5 awaiting user decision
- R1, R2 and R3 rebuilt 854,362 of 1,159,353 `prefix=` tags (73.7%).
- 304,991 tags (26.3%) are left un-rebuilt and flagged `prefix_unresolved:<class>`, in 250,149
  units. Only the tag text is removed.
- Candidate rule R5 (re-ordering a number with its punctuation) and a possible `suspect_bidi` flag
  for Haaretz, ynet and nrg are **not applied**, pending user approval.

### D-020 · Units are complete sentences; model splitting moves to parse time (M2.1) (2026-11-07) · accepted
*Problem.*
- Segment v1 cut sentences longer than 200 whitespace tokens into `chunk` units: 7,716 chunks
  from 3,000 sentences.
- The parent sentence was not stored. On 101 lines, two chunked sentences were adjacent
  (135 pairs), and the stored columns could not tell where one ended and the next began.
- Chunking ran **before** normalization, so rules that span a chunk boundary failed.
- The 200-token cap was unrelated to Dicta's real (sub-word) limit.

*Decision (user-approved M2.1 plan).*
- `units` stores only complete linguistic units: `verse` or `sentence`. `SEGMENT_VERSION` is "2".
- Normalization runs on the whole unit. No normalization rule changed, and `norm_version` stays "1".
- Splitting for a model's input limit is a parse-time step, `hebloc.pieces`, which produces
  *pieces* of `text_norm`.
  - Every piece is stored with `PIECES_SCHEMA`: parent `sent_id`, `piece_idx`, `n_pieces`,
    `norm_char_start/end`, token range, cost, budget, cost unit and `piece_version`.
  - Pieces are checked by `verify_pieces` (nothing lost or added).
  - The budget and cost unit (Dicta sub-words) are set in M3 after measurement.
- The parent sentence is the unit itself, so the adjacency ambiguity can no longer arise.

*Verification* (`hebloc verify-units-v2`, comparing against the preserved v1 copy):
- 0 differing rows on all 9,699,645 rows of lines without chunks (every column except `segment_version`).
- Counts reconcile per corpus: 9,714,378 − 7,716 + 3,000 = 9,709,662.
- Line sets are identical; v1 chunk offsets are reproduced exactly by `plan_pieces(text_raw, 200)`;
  non-whitespace characters are identical on every affected line.
- Every derived-value difference was examined. All are in **3 sentences**, and each is a v1
  boundary defect now fixed:
  - Haskala Ytext1005003, line 499: an editor's edition note had leaked into `text_norm`.
  - Haaretz 812673.txt, line 1: R2 now applies (`ב - 38` → `ב-38`).
  - nrg 174.txt, line 7: an unresolved `prefix=` tag was misclassified `eol` because the chunk ended
    right after it. It is now `number`, with the text unchanged.
- 400 further flag-count differences are once-per-unit flags (e.g. `diacritics_stripped`) that v1
  repeated per chunk.

*Identifiers.*
- Only units on the 2,710 affected lines changed id or ref: 3,682 renumbered, plus 7,716 chunks merged.
- A v1 `sent_id` on those lines can denote a different unit in v2, so v1 ids must not be used
  against v2 data. None were used downstream (no annotations existed).
- The full old→new map is in `data/migrations/segment_v1_to_v2/map.parquet`. It is derived data,
  regenerable while `data/units_v1` exists.

### D-021 · Statistics for sentences that need several pieces: PROVISIONAL (2026-11-07) · hypothesis
- Statistics are computed per **complete unit** (sentence or verse). Length and distinct-word
  counts use the whole unit, with no cap. Mikra verses are labelled as verses and never silently
  pooled with prose sentences.
- A unit parsed in more than one piece has **no complete dependency tree**. Pieces are never
  stitched under an invented root.
- Every such unit must be **reported explicitly** in any tree-based statistic (depth, roots, tree
  shape): count, share per corpus/stratum, and its length distribution. A per-piece depth may
  appear only as a separately labelled lower bound.
- **Excluding these units can cause substantial selection bias**, not necessarily a small one:
  - they are the longest sentences, and depth grows with length;
  - they are concentrated in particular corpora and works (sparsely punctuated rabbinic and
    Haskala texts);
  - how many units are affected depends on the piece budget, which is still unmeasured.
- The final treatment is decided **after the M3 Dicta pilot**, from the measured number of
  multi-piece units and from alternatives such as a larger budget or overlapping windows.


### D-022 · Pinned parser models; vendored, reviewed model code (M3) (2026-11-07) · accepted
- Both models are pinned at exact Hugging Face revisions with file sha256s in `config/models.yaml`:
  - `dicta-il/dictabert-joint` @ `7b1256fc0846`;
  - `dicta-il/dictabert-tiny-joint` @ `708026b7297f`.
- Both are licensed CC-BY-4.0. Weights (safetensors only) live in `data/models/`.
- The custom model code was reviewed before first execution: no network, file, subprocess,
  `exec`/`eval` or pickle access.
- That code is **vendored byte-identically** in `src/hebloc/parse/dicta_code/` and loaded directly.
  `trust_remote_code` is never used, and loading is offline.
- Why vendor: the tiny model's `auto_map` points at the base repository's code *without a revision*,
  which would otherwise fetch whatever code is current at run time.
- The choice between base and tiny is the user's (D-027).

### D-023 · Store `json` output only; UD is derivable (resolves D-008) (2026-11-07) · accepted
- `ud` and `iahlt_ud` CoNLL-U were checked to be exactly reproducible from the `json` output
  (`convert_output_to_ud` on a deep copy; equal for both models).
- Runs therefore store `raw_json` verbatim (`predict(output_style="json", per_token_ner=True)`)
  per piece.
- The `tokens` table is derived from it, and re-derivation is checked to be identical.

### D-024 · Runtime fix for Dicta's MST decoder (`mst_seq_len`) (2026-11-07) · proposed (applied in the pilot)
- *Bug.* `compute_mst_tree` takes each batch row's length from its first padding position. Rows
  without padding (the longest piece of every batch, or any piece parsed alone) get length 0, so
  cycle repair never runs for them. Outputs also depend on batch composition.
- *Evidence.* On the 1,000-unit pilot, the original code gave invalid word-level trees in
  **138 of 1,161 pieces (11.9%)**. The fix brings this to 24 (2.1%) and changes the output of 129
  pieces.
- *Fix.* One line in a verbatim copy of that function (`hebloc.parse.dicta_fixes`), applied at run
  time and recorded in every run manifest. A test reproduces the bug and checks the fix.
- The vendored file is unchanged.

### D-025 · Invalid word-level trees are flagged, never repaired (2026-11-07) · proposed
- Dicta decodes a valid tree over **sub-words**, then gives each word the head of its first
  sub-word. When that head is a continuation sub-word (`##…`) of another word, or of the word
  itself, the word-level graph can contain a cycle or self-loop. This was confirmed for all 24
  remaining pilot cases.
- Such pieces get `piece_tree_valid = false` in `tokens`, are counted, and must be excluded from
  tree statistics with the exclusion reported, as in D-021.
- *Option for the user:* constrained decoding (heads restricted to word-initial sub-words). This is
  a methodological change to the parser and is not implemented.

### D-026 · Normalization hypotheses (D-018): pilot evidence (2026-11-07) · proposed
| Hypothesis | Evidence (`docs/pilot_report.md` §9) | Proposal |
|---|---|---|
| Diacritic stripping | Keeping niqqud/cantillation gives **identical model input** for 144,247 of 144,247 affected units in all corpora (both tokenizers strip them). Parse outputs are identical for 60 of 60 Mikra verses | Accept (no effect on the parser) |
| Qere in `text_norm` | On K/Q words, BHSA agreement is higher with the Qere: POS 74.4% vs 69.4%, noun lemma 57.7% vs 33.2%. Changing the reading also changes 14% of the *other* words' full analysis | Accept the Qere; keep the Ketiv in `text_norm_alt` |
| Maqaf → space | Agreement with BHSA is equal within noise (POS 83.6% vs 83.0%) | Accept the default |
| Sof pasuq → `.` | Equal POS; verb Person agreement 90.8% with `.` vs 88.2% without | Accept the default |

### D-027 · Base vs tiny model (2026-11-07) · proposed: base
- Against BHSA (500 random verses), base is better:
  - POS agreement 83.6% vs 78.5%;
  - verb Person 90.8% vs 85.4%;
  - lemma blanks 7.4% vs 8.8%.
- Speed:
  - with the original lexeme code, tiny is only 1.4–1.8× faster, because a full-vocabulary sort
    dominates both models;
  - with `topk` (D-029), tiny is ≈2.9× faster than base: 1,529 vs 534 sub-words/s.
- Projected cost for the full Modern corpus with base and `topk`: 92 h.
- Tiny produced fewer invalid trees (0.3% vs 2.1%).

### D-028 · Piece budget 510 sub-words (2026-11-07) · accepted (follows from the model)
- The model input is 512 positions including `[CLS]`/`[SEP]`. Longer input is **silently truncated**
  (verified: 600 words in, 510 words out, no error).
- Units are split into pieces of at most 510 model sub-words (`hebloc.pieces` with the model's
  sub-word cost).
- Every output is checked to cover every input character.
- How many units this affects in each full corpus is in the report (piece census). The statistical
  treatment stays provisional (D-021).

### D-029 · Lexeme top-k speed-up (`lex_topk`) (2026-11-07) · proposed (off by default)
- `lex_candidates` fully sorts the 128k-word vocabulary for every sub-word in order to keep 3
  candidates. This dominates run time and memory: ~2 MB per padded sub-word.
- `torch.topk(3)` is a drop-in replacement. Measured:
  - **byte-identical raw output on 300/300 pieces for each model**;
  - base 161 → 534 sub-words/s; tiny 229 → 1,529;
  - peak RAM 3.05 → 1.61 GB (base).
- Adopting it for M5 is the user's decision.

### D-030 · M4 data layer, independent of the pending M3 gate decisions (2026-11-07) · proposed (awaiting M4 review)
*Context.* M4 was started at the user's request while the ten M3 gate decisions (pilot report §15)
were still open. M4 was therefore built so that it decides none of them:
- model (base/tiny), MST fix, `lex_topk`: run parameters, recorded in `run.json` and shown in the `runs` table;
- invalid trees and multi-piece units (D-021, D-025): exposed as columns (`piece_tree_valid`, `n_pieces`) and counted in `parse_coverage`, never filtered;
- Modern coverage (D-004): the canonical registry accepts several runs per corpus, and `parse_coverage` reports parsed vs. all units;
- `tokens` schema (gate decision 5): implemented as proposed (v1). Because `tokens` is re-derived from the stored `dicta_raw` (`hebloc tokens <run> --force`), any requested change costs minutes, not a re-parse.

*Design* (`hebloc.store`, `hebloc.data`, [data_layer.md](data_layer.md)):
- `store.io`: one crash-safe writer (temp file + atomic rename; refuses `corpora/`), used by the runner and every new writer;
- `store.schemas`: a registry of every table (schema, key, version), checked against every file on disk;
- `store.runs`: run discovery and references (`<collection>/<run_id>`), completeness, and the M5 location `data/annotations/<corpus>/runs/<run_id>/` (the M3 layout, kept);
- `store.catalog`: DuckDB views, in memory (`data.connect()`) or as a file (`hebloc catalog`). They read committed shards only, add `run`/`corpus_id`/`doc_id`, and come in all-run (`*_all`) and canonical variants;
- `store.integrity` (`hebloc check`): read-only checks of documents, units, runs and the registry. Model-quality facts are reported, never counted as integrity failures;
- `store.conllu`: export through Dicta's own converter, verified byte-identical to `predict(output_style="ud"/"iahlt_ud")` on 50 pilot pieces (10 per corpus);
- `store.bundle`: D-012, see D-033.

*Why.* M5 and M6 need one tested way to read and write annotations at full-corpus scale (Modern ≈
18k shards). The pilot code held whole runs in memory and globbed every file, including those of
interrupted shards.

### D-031 · `tokens` stored per shard; validation streams per shard (2026-11-07) · proposed (awaiting M4 review)
- `tokens/shard-NNNNN.parquet` per committed run shard, with `tokens/_shards/shard-NNNNN.json`:
  sha256 of the shard's `inputs`, `pieces` and `dicta_raw` files, `tokens_version`, rows and the
  output sha256.
- Derivation is incremental and exact, because all pieces of a unit are in one shard. Tokens files of
  uncommitted shards are removed.
- *Why:* one in-memory table per run cannot work for Modern (hundreds of millions of rows), and one
  run-level manifest rewritten after each of ~18k shards would be quadratic I/O.
- *Migration:* the 11 pilot runs' single `tokens.parquet` files were re-derived per shard, found
  **row-for-row identical**, and only then removed. Re-validation reproduced every M3 `checks.json`
  count exactly; `hebloc pilot revalidate` re-checked every run against its expected inputs (all ok).
- `validate_run` now works shard by shard (bounded memory). It adds hard checks for duplicate keys
  across shards (DuckDB), uncommitted or missing shard files, and missing tokens, and stores a
  `fingerprint` (shard keys + tokens version) so a later `hebloc check` can tell whether the report
  still describes the run.
- *Two semantic fixes* (neither affects existing data: the pilot has no `error` pieces and no
  missing heads):
  - after an `error` piece, the later pieces of the same unit get `sent_word_idx`/`head_sent` =
    null. Before, they were silently shifted by the missing piece's words;
  - a missing head gives `head_sent` = null, not `-1` (root).
- `read_run` now reads committed shards only.

### D-032 · Canonical-run registry `config/annotations.yaml` (2026-11-07) · proposed (awaiting M4 review)
- The default annotations of a corpus come only from runs explicitly registered for it,
  each restricted to that corpus's units. With nothing registered, the API raises an error; it never
  guesses.
- `hebloc check` enforces that registered runs exist, are complete, are `variant = default`, pass
  validation, and that no unit has two canonical analyses.
- Registering a run is a research decision and gets a decision entry. The registry is empty until M5.
- *Why:* the pilot alone has three analyses of the same 1,000 units (base, tiny, original MST). A
  "read all runs" default would silently double-count.

### D-033 · Backup bundles implemented (implements D-012) (2026-11-07) · proposed (awaiting M4 review)
- `hebloc bundle create|verify|restore` (`hebloc.store.bundle`). One uncompressed zip per run,
  holding every file at its path under `data/`, plus `BUNDLE_MANIFEST.json` (fields in
  [data_dictionary.md](data_dictionary.md)) and a `.sha256` sidecar.
- `create` refuses incomplete, stale or unvalidated runs. `verify` re-hashes every member, rejects
  missing, extra or unsafe paths, and requires the bundle's anchor to equal the git-tracked anchor.
  `restore` verifies first, writes only under `data/annotations/`, refuses to overwrite different
  files unless `--overwrite` is given, writes atomically, then re-validates the restored run
  read-only and compares the fingerprint.
- Measured: the `pilot/base__default` bundle is 6.1 MiB for 1,000 units and 101,368 tokens.
- *Still manual, the user's action:* copying the bundles to the two targets (external drive, private
  cloud folder).

### D-034 · Collaboration through a private GitHub repository (2026-11-08) · accepted (user, 2026-11-08)
*Context.* Two partners will join, and parsing will be split between their machines (one disjoint
slice each, merged with `hebloc bundle` and `hebloc check`; slices assigned at M5).

*What is in git:* code, configuration, docs, tests, small result tables, and the manual-audit sheets
(`annotation/pilot_audit*.csv`: 150 short sentences, 30 per corpus, needed if partners annotate).
Small quoted examples in docs and tests stay.

*What is never in git:*
- `corpora/`: each partner downloads it; `hebloc baseline` proves identity with the anchor;
- `data/`: parse results travel as verified bundles through a private shared folder;
- secrets;
- the course documents (`project.pdf`, `DoronDubnov_revised.pdf`, `nlp-intro-short.pptx`): copyrighted,
  and partners have their own copies;
- `docs/m2_sample_review.md`: 149 quoted raw corpus lines, regenerable.

*History.* The course documents and the M2 review had been committed since M0/M2. The user chose to
remove them from the **entire** history before the first push. The 16 local, never-pushed commits
were rewritten with `git filter-branch`, so every commit hash changed (old → new map in HANDOFF).
The original history is kept as a git bundle at `data/backups/git-history-pre-github.bundle`, and
the four files stay on disk, git-ignored.

*Enforcement:* `.gitignore`, and `tests/test_repo_hygiene.py`, which fails if `corpora/`, `data/`,
data or model files, files over 2 MB, the excluded documents, or secret-like strings are tracked.
Partners change code through branches and pull requests. Guide: `docs/PARTNERS.md`.

### D-035 · Signed Python 3.12 on Windows (Smart App Control) (2026-11-08) · accepted (fix of a blocker)
- *Problem.* On 2026-11-08 Windows Smart App Control (enforcing) began blocking uv's downloaded
  Python (`python.exe` from python-build-standalone is not code-signed). No project command could
  run.
- *Finding.* Smart App Control blocked only that executable; the libraries' DLLs (torch, pyarrow,
  ...) loaded.
- *Fix.*
  - The project venv is built on the python.org Python 3.12 (signed by the Python Software
    Foundation), installed per-user with `winget install Python.Python.3.12 --scope user` (no admin).
  - `pyproject.toml` sets `[tool.uv] python-preference = "system"`, so uv uses an installed 3.12
    when one exists.
  - Partners on Windows install python.org 3.12 first (`docs/PARTNERS.md`); `hebloc doctor` warns
    if a uv-managed Python is in use on Windows.
- *Verified:* full fast suite 123/123 on the new interpreter. Same uv.lock, same library versions.

### D-036 · Team work plan, gates and cross-machine checks (2026-11-08) · proposed (awaiting approval)
- *Plan.* `config/parse_plan.yaml`: proposed settings `base-topk-v1` (base, MST fix, `topk`,
  budget 510) and 31 disjoint slices.
  - The four historical corpora are whole slices.
  - Modern is split by subcorpus/source; Haaretz is split into 20 document-hash buckets
    (`int(doc_id[:8],16) % 20`). Buckets 0–1 are option B's ~10% document sample.
  - `hebloc plan check` proves every one of the 9,709,662 units is in exactly one slice.
- *Assignment.* `hebloc plan measure` counts exact model sub-words per slice and balances them
  longest-first between Ori, Efrat and Adi, for options A and B. Mikra is pinned to Ori.
  Output: `config/work_plan.json`, `docs/WORK_PLAN.md`.
- *Gate.* `status: draft` and `coverage: pending` until Ori records the M3 gate decisions.
  `hebloc parse` refuses every real slice in draft, refuses slices outside the chosen coverage, and
  refuses a slice that is assigned to someone else. Smoke runs (`--limit`) and the agreement check
  are allowed.
- *Cross-machine checks.*
  - Corpora: `hebloc corpora install/verify` (sha256 of every file vs the anchor).
  - Packages = `uv.lock` (`hebloc doctor`).
  - Rebuilt data: `hebloc fingerprint`, content digests of documents and units per corpus vs
    `config/reference/fingerprints.json`.
  - Models: sha256 pins.
  - Parser output: `hebloc agreement`, all pieces of the 1,000-unit pilot sample, md5 of raw output
    vs `config/reference/agreement_reference.json` from Ori's laptop.
- *Merge.* Bundles (D-033) are merged with `hebloc merge` (verify → restore → integrity check →
  must be a run of the current plan and settings). `hebloc plan register --write` writes the
  canonical registry, with a decision entry.

### D-037 · Clean-clone verification of the team setup (2026-11-08) · accepted (evidence)
- *Test.* A fresh `git clone` into `C:\Users\Ori\hebloc-clean-test\hebrew-locative-verbs` (ASCII
  path), following `PARTNER_START.md` as team member "efrat".
- *Results:*

  | Step | Result | Time |
  |---|---|---|
  | `uv venv --clear --python (py -3.12 …)` + `uv sync` | signed python.org 3.12.10 venv, torch 2.15.0+cpu | ~1 min |
  | `corpora install --from <corpora>` | all 404,294 files IDENTICAL to the anchor | 20 min |
  | `models fetch` | fresh download from Hugging Face, sha256 OK (0.7 GB) | 30 s |
  | `inventory` + `prepare` | 404,294 documents; 9,709,662 units; tracked reports regenerated byte-identical (`git status` clean) | 1.5 + 3 min |
  | `fingerprint` | documents and units of all 5 corpora IDENTICAL to the reference | 10 s |
  | `pytest` | 129 passed, 8 skipped (they need pilot data) | 1 min |
  | `doctor --as efrat` | all PASS; TODO = agreement (before running it) and plan approval | — |
  | `agreement --as efrat` | **1,161/1,161 pieces byte-identical** to the reference; 758 sub-words/s | 3 min |
  | `parse --slice modern-tapuz --as efrat` | **REFUSED** (plan in draft), as designed | — |
  | `parse … --limit 300` (smoke) | validation and integrity OK; bundled (0.2 MiB) | 14 s |
  | `merge` of that bundle on Ori's repo | OK; `hebloc check` OK; an altered zip FAILS on its `.sha256` | — |
  | recovery paths | re-install refused with the documented message; `corpora verify` IDENTICAL | — |

- *Gaps found and fixed:*
  - uv found a blocked uv-managed `python3.12.exe` shim on PATH and aborted. Fix: create the venv
    explicitly from `py -3.12` (now in `PARTNER_START.md` §4).
  - `corpora install` failed when the destination's parent folder was missing.
  - The doctor showed a garbled (localized) power-plan name.
  - `merge` did not check the `.zip.sha256` sidecar.
  - `WORK_PLAN.md` could not be refreshed after approval without re-measuring
    (`hebloc plan assign`).
  - The partner docs duplicated commands; `PARTNER_START.md` is now the single source.
- *Not covered by this test:*
  - another computer (same hardware here: the agreement shows reproducibility across checkouts,
    environments and model downloads, not across CPUs);
  - macOS/Linux;
  - a zip download of the full corpora (only small zips in tests);
  - cloning from GitHub (the repo is not pushed);
  - real slices (gated);
  - `plan register` on real runs (unit-tested only).
