# CLAUDE.md — Hebrew Locative Verbs (BGU NLP mini-project, 2027)

## Purpose & scope
Test Doron & Dubnov (2017) "Locative Alternation Preposition Identity" (verbs that alternate between
Frame A [Locatum = direct object] and Frame B [Location = direct object] keep the same preposition:
ב- for putting, מן/מ- for removal) on 5 Hebrew corpora, using Dicta's parser.

**CURRENT SCOPE: data foundation only** — inventory → unit extraction → Dicta parse → data layer →
assignment §4 descriptive statistics → STOP for review. Later stages (locative extraction, A/B
classification, classifiers, LLM) are roadmap-only: `docs/roadmap.md`. Do not implement them
until the user explicitly opens that scope.

- **New session? Start with `docs/HANDOFF.md`** (current state, checks to run, next milestone).
- Spec (authoritative, Hebrew): `project.pdf`. Paper: `DoronDubnov_revised.pdf`.
- Decisions log: `docs/decisions.md`. Roadmap: `docs/roadmap.md`. Corpus facts: `docs/corpus_report.md`.
- Table schemas: `docs/data_dictionary.md`. Data layer usage + M5 contract: `docs/data_layer.md`.
  Data API: `hebloc.data` (`units`, `iter_units`, `trace`, `tokens`, `iter_tokens`, `pieces`, `raw`, `sentence`,
  `trace_token`, `coverage`, `conllu`, `runs`, `connect`); storage: `hebloc.store` (io, schemas, runs, catalog,
  integrity, conllu, bundle); catalog: `hebloc.catalog.documents()`. M2 methodology: `docs/m2_preprocessing.md`.

## Non-negotiable rules
- `corpora/` is IMMUTABLE: never edit, rename, move, delete, or write into it. Guarded by
  `tests/test_corpora_immutable.py` against `data/catalog/corpora_baseline.parquet`, which is itself
  pinned by the git-tracked `config/corpora_anchor.json` (404,294 files, 1,126,869,300 bytes,
  manifest sha256). Never edit the anchor by hand; never re-anchor without a documented decision (D-011).
- `data/` is not in git; expensive outputs are backed up/shared as verified bundles — see
  `docs/data_management.md` (D-012, implemented as `hebloc bundle` in M4, D-033). Bundle every M5 run.
- Never silently drop data. Everything is cataloged; filtering = tags (`config/curation.yaml`),
  never deletion. **Full view** (`in_full_view`, every supplied text file) is the PRIMARY reference
  for statistics; the **curated view** (`in_curated_view`: in-period, non-blank, deduplicated within
  stratum|source) is an additional, clearly labelled view (D-015). Curation tags are operational
  research metadata, not historical truth. Duplicates are never removed across corpora/sources.
- Every derived row is traceable: `sent_id` → `doc_id` → `rel_path` + `line_no` + char offsets (+ sha256).
- Keep raw Dicta responses (`dicta_raw`); recomputing statistics must never require re-running Dicta.
- No large run without an approved pilot (M3 gate). Runs are sharded, resumable, manifest-logged.
- Modern corpus coverage (full vs sample) is an explicit user decision after the M3 benchmark.
- Dicta output on historical Hebrew is NOT ground truth: measure and report its accuracy.
- Talk to the user in English. End every milestone with a plain-language summary:
  what was built, why, how it works, how we know it works. User approves before the next milestone.

## Data flow
```
corpora/ (read-only)
 → data/catalog/documents.parquet        [M1 inventory]
 → data/units/<corpus>/*.parquet          [M2 prepare: complete sentences/verses, provenance + text_raw + text_norm]
 → data/annotations/<collection>/runs/<run_id>/{inputs,pieces,dicta_raw,tokens,_shards}/ + run.json, checks.json
                                          [M3: collection=pilot; M5: collection=<corpus>]
 → config/annotations.yaml: canonical run(s) per corpus (empty until M5; never guessed, D-032)
 → data/stats/*.parquet → results/stats/ (CSV + PNG)    [M6 stats]
DuckDB views over all Parquet: data/hebloc.duckdb (hebloc catalog) · Python API: hebloc.data
Readers use COMMITTED shards only (_shards/*.json exists); tokens are derived per shard from dicta_raw.
```
Key IDs: `doc_id` = stable hash of rel_path; `sent_id` = `<corpus>:<doc_id>:<line>:<k>`.
Parse-time pieces (only for over-budget units): (`sent_id`, `piece_idx`) + span in `text_norm` (`hebloc.pieces`).

## Corpus pitfalls (measured 2026-11-06)
- **Mikra** (39 books, 23,206 verses): 1 verse/line, NO chapter:verse labels (refs from an external
  versification table, count-checked per book); niqqud + te'amim; Ketiv `(…)` / Qere `[…]` — default
  Qere in `text_norm` is SUPPORTED by the M3 pilot vs BHSA (D-026, proposed — awaiting user approval);
  BHSA (data/external/bhsa, CC BY-NC) uses Latin book names (`hebloc.pilot.bhsa.BHSA_BOOKS`);
  always preserve Ketiv so either can be re-derived; maqaf written as `-`; stray ASCII `'` `"` inside words are accent artifacts; `{פ}` `{ס}` markers.
- **Hazal** (204 files): ~38% of words are 16th–19th c. commentaries; Yalkut Shimoni is a 13th c.
  anthology → stratum tags. Mixed vocalization, abbreviations (אומ'), some Aramaic.
- **Medieval** (1,128 files): Rambam has 91 empty files (all hilchot intros) and is pre-tokenized; some Musar
  works are post-medieval; several Thought works are translations from Arabic; "Letter from Ramban to his Son"
  content does NOT match its title.
- **Haskala** (320 files): metadata in filename `author--title--year--genre--YtextID`; `<…>` `{…}` markup;
  years 1755–1934 — 37% of tokens are post-1881 (`subperiod` tag); 3 one-byte placeholder files.
- **Modern** (402,603 files, 134.1M Hebrew tokens): **Windows-1255, not UTF-8** (incl. folder `text_utf`);
  pre-tokenized, ~1 sentence/line; haaretz ≈ 74% of tokens; 100 auxiliary 7-Zip logs (one named `.txt`);
  6,265 exact-duplicate copies; old-tokenizer artifacts `prefix=X token=Y` (1.16M, also in Rambam) must be
  investigated in M2 (e.g. `prefix=ב token=רח'` ≈ `ברח'`) — no unvalidated reconstruction rules;
  keep the original text; test on difficult cases first (D-016).

## Stack & commands
- Python 3.12 via `uv` (system default 3.14 is NOT used). Package: `src/hebloc/`.
- Parser: `dicta-il/dictabert-joint` @ `7b1256fc0846` (and `dictabert-tiny-joint` @ `708026b7297f`), pinned
  with sha256 in `config/models.yaml`; reviewed model code VENDORED byte-identically in
  `src/hebloc/parse/dicta_code/` (never edit; never `trust_remote_code`); runtime fixes in
  `parse/dicta_fixes.py` (D-024 MST fix on; D-029 `topk` off unless approved). torch CPU + transformers 5.
- Storage: Parquet (zstd) + DuckDB. Tests: pytest.
```
uv sync                                  # create/refresh env from uv.lock
uv run pytest                            # fast tests (immutability: file list + sizes)
uv run pytest -m slow                    # full sha256 re-verification of corpora/
uv run hebloc baseline                   # record baseline if missing / report anchor check;
                                         #   --force recomputes but refuses if it disagrees with the anchor
uv run hebloc anchor                     # pin baseline in config/corpora_anchor.json (first time only)
uv run hebloc inventory                  # M1: rebuild catalog (~75 s; refuses to write if not anchor-consistent)
uv run hebloc versification             # (one-off, network) refresh config/reference/tanakh_versification.json
uv run hebloc prepare [--corpus X] [--sample N]   # M2: units (~5 min all; --sample → data/units_sample + review)
uv run hebloc pilot <step>               # M3: fetch-models, fetch-bhsa, sample, smoke, parse, variants,
                                         #   diacritics, census, analyze, audit, audit-score, bench
uv run hebloc runs                       # M4: parse runs, completeness, canonical role
uv run hebloc tokens <run>|all           # M4: derive tokens per shard (incremental)
uv run hebloc check [--deep]             # M4: read-only integrity of the whole data layer (~5 s; deep ~25 s)
uv run hebloc catalog                    # M4: write data/hebloc.duckdb (views)
uv run hebloc export-conllu <run> [--corpus C] [--style ud|iahlt_ud]
uv run hebloc bundle create|verify|restore ...   # M4: D-012 backups
uv run hebloc <parse|stats>              # later milestones (M5/M6)
```

## Repo map
```
config/        YAML: corpora registry, curation/strata, sample plans
docs/          roadmap, decisions, data_dictionary, corpus/pilot/stats reports
src/hebloc/    cli, inventory, readers/, normalize, segment, parse/, store/, stats/, data (API)
tests/         pytest (+ fixtures/)
annotation/    small hand-labelled audit/gold sheets (versioned)
data/          derived, reproducible, gitignored
results/       small tables/figures for the report (versioned)
notebooks/     exploration only — never pipeline logic
```

## Conventions
- Pipeline logic lives in `src/hebloc`, configuration in `config/*.yaml`, never in notebooks.
- Normalization is versioned (`norm_version`); every preprocessing choice is logged in `docs/decisions.md`.
- Shard writes are atomic (write temp → rename); a shard is skipped only if its manifest matches inputs.
- Read corpus files in binary and decode explicitly (UTF-8 strict, else cp1255) — never rely on defaults.

## Status
- [x] M0 foundation (CLAUDE.md, roadmap, decisions, git, uv env, skeleton, immutability guard)
      Baseline: 404,294 files / 1,074.7 MiB, pinned by git-tracked anchor. Fast suite ~75s; deep (`-m slow`) ~11 min.
- [x] M1 inventory & catalog — `data/catalog/documents.parquet` (404,294 rows, verified vs anchor);
      report `docs/corpus_report.md`; tags approved as operational metadata (D-015). Aggadic midrash is
      in period but heterogeneous; Haskala 1881 = analytical cutoff; 7 Musar files `needs_review`.
- [x] M2 unit extraction — `data/units/<corpus>/` (9,714,378 units; verified, deterministic); methodology
      `docs/m2_preprocessing.md`; open: R5 reorder rule, bidi flag (D-019); M3 must test D-018 hypotheses.
      (Segment v1 chunks superseded by M2.1.)
- [x] M2.1 complete-sentence units — segment v2 (D-020): units are never cut; model splitting is a
      parse-time step (`hebloc.pieces`, pieces keep parent `sent_id`); 9,709,662 units, exhaustively
      verified vs v1 (`hebloc verify-units-v2`). Multi-piece tree statistics are PROVISIONAL (D-021):
      report them explicitly; exclusion may bias substantially. Awaiting user approval.
- [x] M2.1 approved. M3 Dicta pilot & benchmark DONE (2026-11-07) — report `docs/pilot_report.md`;
      **at the M3 GATE: 10 user decisions pending (report §15 / HANDOFF §6)**. Key facts: Dicta truncates
      >510 sub-words SILENTLY (pieces + coverage check); Dicta has NO binyan feature; original MST code gives
      11.9% invalid trees (fixed → 2.1%; rest flagged `piece_tree_valid`, never repaired); diacritics do not
      change model input; base > tiny on BHSA; full Modern ≈ 306 h base (92 h with `topk`).
- [x] M4 data layer & access API — DONE 2026-11-07, **awaiting user review** (D-030–D-033 proposed).
      `hebloc.store` + extended `hebloc.data`; tokens per shard (11 pilot runs migrated, identical);
      DuckDB catalog; canonical registry; integrity checker; CoNLL-U export (= Dicta's UD, 50/50);
      bundles. Built independent of the M3 gate decisions, which are STILL PENDING (HANDOFF §6).
- [ ] M5 full parsing run
- [ ] M6 descriptive statistics + parser-accuracy report
- [ ] M7 review checkpoint (STOP)
