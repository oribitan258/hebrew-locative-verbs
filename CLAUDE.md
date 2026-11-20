# CLAUDE.md — Hebrew Locative Verbs (BGU NLP mini-project, 2027)

## Purpose & scope
Test Doron & Dubnov (2017) "Locative Alternation Preposition Identity" (verbs that alternate between
Frame A [Locatum = direct object] and Frame B [Location = direct object] keep the same preposition:
ב- for putting, מן/מ- for removal) on 5 Hebrew corpora, using Dicta's parser.

**CURRENT SCOPE (2026-11-20): stage 3, release R1 = tag `s56-r1` DONE (provisional, D-057); STOP before Phase B.**
- **R1** (`docs/S56_R1.md`): the lexicon, the guideline, the gold sampler with **frozen** samples, and the noun lists.
  - Released as a provisional infrastructure milestone. Its identification limits are in §0.1.
  - Identification must be improved and validated on the **dev** gold before R2 is frozen. No retuning against BHSA;
    test is read once, at the end.
  - Recovered instances enter the gold only by the supplemental sampling procedure (§3).
  - **Phase B (the R2 code) starts only with Ori's explicit approval** (Plan Mode).
- **Earlier: CHECKPOINT 1 reached (2026-11-19).**
- **What was approved.** The shared §5–§6 methodology **`S56-v1`** (D-053–D-056).
  - It is written in full in **`docs/EFRAT_SECTION_6.md`** §5, which is normative for Ori, Adi and Efrat.
  - That document is also Efrat's self-contained §6 handoff.
- **Next stage (Ori's computer).** Stage 3 = **plan, then implement, §5 on Mikra**: release R1, then the shared code
  and validation, then CHECKPOINT 2 (tag `s56-v1`).
  - Plan it in a **fresh session in Plan Mode**.
  - **Nothing is implemented without Ori's explicit approval of that plan.**
- **Never use a paid external API** (no LLM API), D-054. External API use would need Ori's separate approval.
  Claude Code may assist only with human-reviewed steps (noun-type proposals, code and docs, reading audits); never
  gold labels or run-time labelling.
- **Still roadmap-only** (`docs/roadmap.md`) until Ori explicitly opens them: §7 classifiers, the rest of §8, and §4
  R7/Part B.

- **New session? Start with `docs/HANDOFF.md`** (current state, checks to run, next milestone).
  **Next session on Ori's computer: PLAN stage 3 (§5 on Mikra, release R1 first) in Plan Mode**, strictly per
  `S56-v1` (`docs/EFRAT_SECTION_6.md` §5), `project.pdf` and the paper. `project.pdf` is the source of truth.
- **Agreed §5–§6 workflow (Ori, 2026-11-19; details in HANDOFF and EFRAT_SECTION_6.md §3):**
  - **Ori leads §5.**
    - **Stage 1:** Ori implements and validates Mikra first.
    - **Stage 2:** Ori and **Adi** divide the remaining corpora **by corpus**, with a reasonably **balanced
      workload**, and work **in parallel**. **The split is decided at CHECKPOINT 2** (D-056).
    - **Adi's workflow** is prepared exactly like M5: assignments, data, automated detached execution, validation,
      outbox packaging, and a verified merge on Ori's computer.
    - Central statistics are computed once, on Ori's computer.
    - Adi uses her EXISTING folder and repo clone (no separate project, no duplicate code). Her data today is
      Haskala + 9 Modern slices.
    - Her Claude Code handoff is `docs/ADI_SECTION_5.md`, and CLAUDE.md will be updated so that she types `start`.
      Both are written only after Mikra is validated (**CHECKPOINT 2**: STOP, tell Ori it is ready for Adi).
  - **Efrat is responsible for §6 on Modern**, on her computer, following `docs/EFRAT_SECTION_6.md`. She reuses the
    shared code and definitions: no frame definitions or extractor of her own.
  - §7 is out of scope.
  - **One shared methodology `S56-v1`** for §5 and §6, written in `docs/EFRAT_SECTION_6.md`, which is
    self-contained. It contains:
    - the exact §5/§6 requirements;
    - the division of work and dependencies;
    - the methodology;
    - AI-tool policy;
    - interfaces and output formats;
    - data;
    - what Efrat may do now and what must wait;
    - answers to her Claude Code's six points;
    - STOP rules.
  - **CHECKPOINT 1: DONE 2026-11-19.** The methodology was approved, and the document is committed and pushed.
  - **Releases.**
    - **R1** (early stage 3): lexicon, annotation guideline, gold sampler, noun lists.
    - **R2 = tag `s56-v1`** = CHECKPOINT 2: frozen, Mikra-validated code plus noun types.
    - Adi and Efrat run only R2.
  - **Compatibility:** Ori, Adi and Efrat use the same methodology, the same pinned code version and the same
    output schemas and manifests. Cross-checks: repo input = package input, and partners' rows are byte-identical
    to Ori's.
  - **Session management:** separate sessions, one stage at a time, each ending at an explicit approval
    checkpoint. At the end of each stage, update the docs (CLAUDE.md, HANDOFF, roadmap, decisions) and memory:
    what is complete, what was decided, what comes next.
- **On Efrat's computer, for §6: follow `docs/EFRAT_SECTION_6.md`** (see "Team" below).
- **On Adi's computer, or on any fresh setup: execute `PARTNER_START.md`** (tested, step-by-step: identify the
  partner, set up, verify, parse only their slices, package results).
- Spec (authoritative, Hebrew): `project.pdf`. Paper: `DoronDubnov_revised.pdf`. Both are local copies in the
  repo root, NOT in git (copyright, D-034); partners use their own course copies. Partner guide: `docs/PARTNERS.md`.
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
  Keep ALL parse data (`dicta_raw`, `inputs`, `pieces`, manifests, `checks.json`, `tokens`) and every bundle,
  also after M6: §5–§8 use the same data. No cleanup/deletion without Ori's explicit approval (D-045).
- No large run without an approved pilot (M3 gate). Runs are sharded, resumable, manifest-logged.
- Modern corpus coverage: decided by the user — **Option A, all of Modern** (D-041).
- Dicta output on historical Hebrew is NOT ground truth: measure and report its accuracy.
- Talk to the user in English. End every milestone with a plain-language summary:
  what was built, why, how it works, how we know it works. User approves before the next milestone.

## Team (Ori, Efrat, Adi) — read if you are helping a partner
- **Workflow (plan approved, coverage A, D-041):** each person clones the PUBLIC repo (no invitation),
  opens it in VS Code + Claude Code and says "Read PARTNER_START.md and follow it". Claude Code sets up
  and verifies the computer, then runs that person's share automatically (`hebloc work --detach`,
  resumable). Each person keeps the complete results locally; at completion they get simple
  instructions to send `data/outbox/<name>` to Ori by Google Drive, OneDrive or USB. No shared folder
  is set up in advance. Ori merges; M6 statistics are computed centrally (D-040, D-045).
  **A partner's part ends when they send `data/outbox/<name>`: partners never compute statistics.**
- **On ORI's computer (`data/team/identity.json` = ori):** M5 is COMPLETE (all 31 slices merged and registered,
  D-049) and the final M6 statistics exist (2026-11-16). `start`/`status` there = a read-only status check
  (31/31, registry, final stats; M7 review pending; §5–§6 CHECKPOINT 1 done). The two rules below apply on
  Efrat's and Adi's computers.
- **On EFRAT's computer (`data/team/identity.json` = efrat): §6 is AUTHORIZED, staged as in
  `docs/EFRAT_SECTION_6.md` §9** (D-055, D-056).
  - Her M5 share is complete; never re-run it.
  - **If her whole message is "start"** (or "go", "continue", "status"), or she asks about §6: read
    `docs/EFRAT_SECTION_6.md` and follow its §9 "Start here".
    - First `git status`: if tracked files are modified, STOP and report; never discard them.
    - Then `git pull`, `uv sync`, tests, `whoami`.
    - Then report which stage is unlocked (after CHECKPOINT 1 / after R1 / after R2 = tag `s56-v1`) and do only the
      steps of that stage.
  - Plan Mode for non-trivial steps.
  - Obey the STOP rules in §12:
    - no own extractor or frame rules;
    - no BHSA;
    - no paid API;
    - no `config/` edits;
    - no AI pre-labelling of gold;
    - no git commits.
  - Results go in `data/outbox/efrat-s6/`.
- **If the person's whole message is "start"** (or "go", "continue", "status") **on ADI's computer** (or on a fresh
  partner setup): until CHECKPOINT 2 it still means *run or check this computer's share of M5*.
  - Read `PARTNER_START.md` and follow it from §2: identity from `data/team/identity.json`; skip every section whose
    "Skip if" holds.
  - Then §10b (`git pull`, `uv sync`, `work --status`, and `work --detach` if not started/stopped), or §11 if
    complete. Adi's share is complete, so it is a status check.
  - Never run it in the foreground; never run anyone else's slices.
  - At CHECKPOINT 2 this rule changes to Adi's §5 stage-2 workflow (`docs/ADI_SECTION_5.md`).
- Execution guide for Claude Code: **`PARTNER_START.md`** (single source of the tested commands);
  overview: `docs/PARTNERS.md`; who parses what: `docs/WORK_PLAN.md` (generated).
  Slash commands: `/partner-setup`, `/partner-parse`, `/merge-results` (Ori).
- Identity: PARTNER_START §2 asks "Who are you — Ori, Efrat, or Adi?"; `hebloc whoami --set <name>` stores it
  (`data/team/identity.json`) and every team command then refuses to act for anyone else.
- Never parse a slice that is not assigned to that person; never bypass a `hebloc parse` REFUSED.
  Only Ori edits `config/parse_plan.yaml` (status/coverage/settings), `config/annotations.yaml`,
  `config/reference/*` and the anchor, each with a decision entry.
- Results travel as the folder `data/outbox/<name>` (bundles + `DELIVERY.json`, made by `hebloc work`)
  by Google Drive, OneDrive or USB, NEVER git. Ori runs `hebloc merge <folder>`. Only Ori pushes to git.
- A failed check (corpora, fingerprint, models, agreement, integrity) is never worked around:
  stop and report to Ori with `data/team/doctor.json`.
- Windows: use python.org Python 3.12 (Smart App Control blocks uv's Python, D-035). PYTHONUTF8 is not
  required (all I/O names its encoding; the suite passes without it, D-039).
  In a NEW environment SAC may also block the generated `hebloc.exe`/`pytest.exe` launchers: use
  `uv run python -m hebloc …` and `uv run python -m pytest` (D-038).

## M6 statistics workflow (Ori's computer only; D-040, D-045)
- **Final statistics are computed ONCE, centrally**, after `hebloc merge` reports 31/31 COMPLETE and
  `plan register --write`, over the registered runs of all five corpora. Never per person, never by
  combining partial results (most §4 statistics are not additive; Modern is split across shares).
- **Develop now:** design → Ori's approval → code (takes an explicit run list now, the registered runs
  later; one code path) → validation. Mikra and Hazal are complete locally: real but PROVISIONAL numbers.
  Ori's Modern slices are a scale test only, never reported. Parser accuracy (Mikra vs BHSA) can be final now.
  Do not register runs early; do not tune on partial Modern.
- **Design approved 2026-11-12 (D-046, `docs/m6_design.md`):** Part A = exactly the §4 items (R1–R6), per
  corpus, full view; R5 covers EVERY Dicta inflection feature; Part B (R7 extras) deferred — do not build
  it unless Ori opens it. Built, tested and committed; parser accuracy FINAL; Mikra + Hazal + Medieval PROVISIONAL.
- **`finish statistics`** (Ori's message, in a fresh session, in Plan Mode) means: do `docs/HANDOFF.md` §7 —
  review the state read-only (docs, env, tests, `hebloc check`, `hebloc merge` report = 21/31, where Adi's
  folder is; Efrat's is already merged), then present the plan for: merge Adi (check for a split upload) +
  validate all 31 slices → `plan register --write` (+ decision)
  → `hebloc stats run --registered` (final, all five corpora, §4) → verify → report → STOP at M7.
  **Execute nothing before Ori approves that plan.** If Adi's folder has not arrived, report and stop.
- HANDOFF §7A (merge Efrat + provisional Medieval) was done 2026-11-15; `finish statistics` was done 2026-11-16
  (Adi merged → 31/31, registered D-049, final statistics `data/stats/final-20261116-565826e3c1`).

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
  Qere in `text_norm` is SUPPORTED by the M3 pilot vs BHSA (D-026, accepted D-041);
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
  `parse/dicta_fixes.py` (D-024 MST fix on; D-029 `topk` on, approved D-041). torch CPU + transformers 5.
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
uv run hebloc corpora install --from P | verify   # team: install the course archive (zip/multi-part/7z/rar/tar/folder;
                                         #   Hebrew names repaired) into corpora/ only if identical to the anchor
uv run hebloc whoami [--set NAME]        # team: who this computer belongs to
uv run hebloc models fetch|verify        # team: pinned Dicta models (sha256)
uv run hebloc fingerprint                # team: rebuilt data == reference content
uv run hebloc doctor                     # team: end-to-end machine check -> data/team/doctor.json
uv run hebloc agreement                  # team: pilot-sample parse == reference output (1,161 pieces)
uv run hebloc plan show|check|measure|assign|status|register   # team: work plan (gated)
uv run hebloc work --detach | --status   # M5: ALL of this person's slices in its own window -> data/outbox/<name>
                                         #   (refused in draft; one per computer; resumable; keeps it awake)
                                         #   --rehearsal N: diagnostic on N units/slice, allowed in draft
uv run hebloc parse --slice S [--limit N]   # one assigned slice (refused in draft) / smoke test
uv run hebloc merge [<folder|zip>...]    # Ori: verify + restore + exact-units check + completeness report
uv run hebloc stats run --runs <run,…>   # M6 (D-046): §4 statistics; refuses partial corpora; provisional → data/stats/<id>/
uv run hebloc stats run --registered     # M6 FINAL (after merge 31/31 + plan register) → results/stats + docs/stats_report.md
uv run hebloc stats accuracy             # M6: Mikra vs BHSA on all of Mikra → results/stats/accuracy/ (final)
uv run hebloc stats report|verify <dir>  # M6: re-render / re-hash a data/stats/<id> folder
uv run hebloc pack analysis|verify       # D-051: standalone analysis package (data/share/, private, never git)
uv run python -m hebloc loc lexicon check|forms|inventory|bhsa-eval   # §5 R1: lexicon (forms/bhsa-eval: Ori only)
uv run python -m hebloc loc gold sample|check · loc nouns list|merge · loc verify   # §5 R1 (docs/S56_R1.md §7)
```

## Repo map
```
config/        YAML: corpora registry, curation/strata, sample plans
docs/          roadmap, decisions, data_dictionary, corpus/pilot/stats reports
src/hebloc/    cli, inventory, readers/, normalize, segment, parse/, store/, stats/, data (API)
tests/         pytest (+ fixtures/)
annotation/    audit guide + pilot sample ids (versioned); audit sheets quote corpus text: local only (D-042)
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
- [x] Collaboration setup (D-034, 2026-11-08): private GitHub repo, `docs/PARTNERS.md`, repo-hygiene test;
      course docs + `m2_sample_review.md` removed from ALL history (hashes changed: HANDOFF §8).
      Smart App Control blocker FIXED by a signed python.org 3.12 venv (D-035).
- [x] Team readiness (D-036, D-037, 2026-11-08): `hebloc.team` (work plan, doctor, corpora install,
      fingerprints, agreement, gated `parse --slice`, `merge`), `PARTNER_START.md`; verified from a clean
      clone. Plan is DRAFT until the M3 gate decisions; partners not invited yet.
- [x] Automatic partner workflow (D-038, 2026-11-09): PARTNER_START.md is the single entry point (identity
      question, course-archive install with name repair, `hebloc work` + outbox, exact `merge`); tested at full
      size and with a three-person rehearsal merge. Full runs still gated on Ori's approval.
- [x] Final M5 workflow (D-039, D-040, 2026-11-09): detached run + lock + `work --status`, pinned threads,
      agreement mismatch packaging + `agreement --compare`, partner flow without rehearsal; M6 statistics
      will be computed centrally after the merge. Private GitHub repo prepared.
- [x] M3 gate + M4 approved; plan approved with coverage A (D-041, 2026-11-09): settings base-topk-v1
      (base, MST fix, `topk`, D-025 flags, D-026 normalization; R5 not applied; D-021 + audit deferred to M6).
      GitHub repo is PUBLIC (no invitations; partners cannot push). Corpus-text audit sheets removed
      from git and from all history (D-042; local copies + pre-clean history bundle in data/backups/).
- [x] M5 full parsing run — **COMPLETE 2026-11-16**: Adi's 10 slices merged (MERGE OK, 31/31 slices,
      9,709,662/9,709,662 units, 0 overlap, COMPLETE); `hebloc check --deep` OK; 31 canonical runs registered
      (`config/annotations.yaml`, D-049). Earlier history:
      Ori's share COMPLETE 2026-11-12 (12/12 slices, 3,504,707 units, `data/outbox/ori`); D-043 (excused
      "¨¨" tokenizer artifact in the coverage check) and D-044 (pandas ≤3.0.2, pyarrow <26: Smart App
      Control blocks newer DLLs). **Efrat's 9 slices MERGED 2026-11-15** (MERGE OK, combined copy in
      `C:\hebloc-incoming\efrat`, deleted 2026-11-17 per D-052; originals kept in `data/efrat-data1` + `data/efrat-data2`): **21/31 slices,
      6,512,144/9,709,662 units, 0 overlap**; `hebloc check` OK=True. **Waiting for Adi's 10 slices** → merge
      31/31 → register (done inside `finish statistics`, HANDOFF §7).
- [x] M6 descriptive statistics + parser-accuracy report — **DONE 2026-11-16** (only the analysis wording awaits Ori) — design approved (D-046, `docs/m6_design.md`: Part A =
      exactly §4; Part B deferred), `hebloc.stats` built + tested (D-047 matplotlib). DONE 2026-11-12: parser accuracy
      (final, `results/stats/accuracy/`), PROVISIONAL Mikra + Hazal (`data/stats/provisional-20261112-27bb4080cf`).
      2026-11-15: PROVISIONAL Mikra + Hazal + Medieval (`data/stats/provisional-20261115-49160596a7`; Mikra/Hazal
      tables identical to 2026-11-12; reconciliation 0 problems; verify OK).
      **2026-11-16: FINAL statistics, all five corpora** (`hebloc stats run --registered` →
      `data/stats/final-20261116-565826e3c1`, `results/stats/`, `docs/stats_report.md`; reconciliation 0 problems;
      `stats verify` OK; Mikra/Hazal/Medieval identical to provisional; backup `data/backups/stats/`).
      Hand-written analysis: `docs/stats_analysis.md` (separate file: re-rendering overwrites stats_report.md).
      **Closeout of assignment §2–§4 (2026-11-16, D-050):** verified and committed; CSVs UTF-8 with BOM; summary for
      the professor `docs/SECTIONS_2-4.md`. Ori's instruction: do not go beyond M6.
      **Analysis package for Efrat (D-051):** `uv run python -m hebloc pack analysis` → `data/share/hebloc-analysis-pack/`
      + zip (5.15 GiB; all tokens/sentences/catalog/pieces + official stats + `hebpack` tools + its own CLAUDE.md;
      lossless-verified; self-test reproduces the official tables). Private Drive transfer only, NEVER git. Her
      additional statistics (§4 R7) come back as `analyses/` + REPORT.md for Ori's review.
- [ ] M7 review checkpoint (STOP): Ori + partners review the §4 results and `docs/stats_analysis.md` (wording
      not yet approved). D-052 (2026-11-17): disk cleanup of duplicates only. 2026-11-19: §5–§6 workflow agreed (Ori leads §5,
      Adi runs part of stage 2 via `docs/ADI_SECTION_5.md`; Efrat: §6 via `docs/EFRAT_SECTION_6.md`; §7 out of scope).
      Assignment status per project.pdf section: `docs/roadmap.md` (table at the top).
- [x] **§5–§6 CHECKPOINT 1 (2026-11-19).**
  - Shared methodology `S56-v1` approved (D-053 local-first methodology; D-054 local role resolver, no paid API;
    D-055 §6 = Modern, all verbs, D-051 package, no BHSA in §6; D-056 interfaces, releases, transfers, balanced
    stage-2 split decided at CHECKPOINT 2).
  - `docs/EFRAT_SECTION_6.md` (the self-contained handoff, answering Efrat's Claude Code's six points) committed
    and pushed.
- [x] **Stage 3, Phase A = release R1 (`s56-r1`, 2026-11-20, D-057; provisional).** It contains:
  - the lexicon (210 entries; forms-v2 with the pre-registered fallback);
  - `annotation/S56_GUIDELINE.md`;
  - the sampler `gold-r1b`, with the frozen samples `mikra-r1b-1cd4ee9802` and `modern-r1b-5fbb5e22e7`;
  - the noun lists (option A);
  - the BHSA identification baseline (Mikra), with its limits in `docs/S56_R1.md` §0.1.

  Efrat's R1 steps: `docs/EFRAT_SECTION_6.md` §9.2.
- [ ] **Stage 3, rest (Phase B needs Ori's approval):**
  - §5 on Mikra: R1 (lexicon, guideline, gold sampler, noun lists), then the shared extractor, local resolver,
    classes, identity and statistics, then Mikra validation (BHSA identification + human gold);
  - then **CHECKPOINT 2**: tag `s56-v1`, decide the balanced Ori/Adi split, build and test Adi's M5-style workflow,
    `docs/ADI_SECTION_5.md`, Adi's `start`.
  - Still closed until Ori opens them: §7, the rest of §8, §4 R7 extras (Part B); later §1 summaries, §9 report,
    §10 submission.
