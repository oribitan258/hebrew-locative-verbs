# CLAUDE.md — Hebrew Locative Verbs (BGU NLP mini-project, 2027)

## Purpose & scope
Test Doron & Dubnov (2017) "Locative Alternation Preposition Identity" (verbs that alternate between
Frame A [Locatum = direct object] and Frame B [Location = direct object] keep the same preposition:
ב- for putting, מן/מ- for removal) on 5 Hebrew corpora, using Dicta's parser.

**CURRENT SCOPE: data foundation only** — inventory → unit extraction → Dicta parse → data layer →
assignment §4 descriptive statistics → STOP for review. Later stages (locative extraction, A/B
classification, classifiers, LLM) are roadmap-only: `docs/roadmap.md`. Do not implement them
until the user explicitly opens that scope.

- Spec (authoritative, Hebrew): `project.pdf`. Paper: `DoronDubnov_revised.pdf`.
- Decisions log: `docs/decisions.md`. Roadmap: `docs/roadmap.md`. Corpus facts: `docs/corpus_report.md`.
- Table schemas: `docs/data_dictionary.md`. Catalog API: `hebloc.catalog.documents()`.

## Non-negotiable rules
- `corpora/` is IMMUTABLE: never edit, rename, move, delete, or write into it. Guarded by
  `tests/test_corpora_immutable.py` against `data/catalog/corpora_baseline.parquet`, which is itself
  pinned by the git-tracked `config/corpora_anchor.json` (404,294 files, 1,126,869,300 bytes,
  manifest sha256). Never edit the anchor by hand; never re-anchor without a documented decision (D-011).
- `data/` is not in git; expensive outputs are backed up/shared as verified bundles — see
  `docs/data_management.md` (D-012; to implement before M5).
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
 → data/units/<corpus>/*.parquet          [M2 prepare: provenance + text_raw + text_norm]
 → data/annotations/<corpus>/{dicta_raw,tokens,runs}/   [M3 pilot, M5 parse]
 → data/stats/*.parquet → results/stats/ (CSV + PNG)    [M6 stats]
DuckDB views over all Parquet: data/hebloc.duckdb · Python API: hebloc.data
```
Key IDs: `doc_id` = stable hash of rel_path; `sent_id` = `<corpus>:<doc_id>:<line>:<k>`.

## Corpus pitfalls (measured 2026-11-06)
- **Mikra** (39 books, 23,206 verses): 1 verse/line, NO chapter:verse labels (refs from an external
  versification table, count-checked per book); niqqud + te'amim; Ketiv `(…)` / Qere `[…]` — default
  Qere in `text_norm` is an UNVALIDATED HYPOTHESIS (D-009) until the M3 pilot compares both readings;
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
- Parser: `dicta-il/dictabert-joint` (pinned HF revision, recorded in run manifests).
- Storage: Parquet (zstd) + DuckDB. Tests: pytest.
```
uv sync                                  # create/refresh env from uv.lock
uv run pytest                            # fast tests (immutability: file list + sizes)
uv run pytest -m slow                    # full sha256 re-verification of corpora/
uv run hebloc baseline                   # record baseline if missing / report anchor check;
                                         #   --force recomputes but refuses if it disagrees with the anchor
uv run hebloc anchor                     # pin baseline in config/corpora_anchor.json (first time only)
uv run hebloc inventory                  # M1: rebuild catalog (~75 s; refuses to write if not anchor-consistent)
uv run hebloc <prepare|pilot|parse|stats|catalog>   # later milestones
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
      Baseline: 404,294 files / 1,074.7 MiB, pinned by git-tracked anchor. Fast guard ~19s; deep (`-m slow`) ~5 min.
- [x] M1 inventory & catalog — `data/catalog/documents.parquet` (404,294 rows, verified vs anchor);
      report `docs/corpus_report.md`; tags approved as operational metadata (D-015). Aggadic midrash is
      in period but heterogeneous; Haskala 1881 = analytical cutoff; 7 Musar files `needs_review`.
- [ ] M2 unit extraction with provenance
- [ ] M3 Dicta pilot & benchmark (GATE — needs user approval)
- [ ] M4 data layer & access API
- [ ] M5 full parsing run
- [ ] M6 descriptive statistics + parser-accuracy report
- [ ] M7 review checkpoint (STOP)
