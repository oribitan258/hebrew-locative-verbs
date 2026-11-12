# Session Handoff: M6 built; waiting for Efrat's and Adi's outputs; next is `finish statistics`

*Updated 2026-11-12, end of session (M6 design approved D-046; `hebloc.stats` built, tested, committed; parser
accuracy final; provisional Mikra + Hazal statistics; D-047 matplotlib; next: `finish statistics`, §7). Before: Ori's M5 share complete; D-043, D-044, D-045. Earlier: M5 approved 2026-11-09 (D-041), M4 finished 2026-11-07.
This file summarizes and points to other documents; when they disagree, the linked documents win.*

---

## 0. Read first

1. **State on 2026-11-12, end of session.**
   - **M5:** Ori's share is complete (12/12 slices). **Waiting for Efrat's (9 slices) and Adi's
     (10 slices) `data/outbox/<name>` folders.**
   - **M6:** built, tested and committed.
     - Parser accuracy is FINAL.
     - Mikra and Hazal statistics are PROVISIONAL.
     - The final statistics for all five corpora need the merged, registered dataset.
   - **Ori's instruction:** stop here; do not go beyond M6.
2. **Next step: when Ori types `finish statistics`** (in a fresh session, in Plan Mode), follow **§7**.
   - Review the state, then present the plan for the remaining steps: merge and validate all 31 slices,
     register the complete dataset, compute the final §4 statistics for all five corpora, and write the
     final report.
   - **Execute nothing before Ori approves that plan.**
3. **M6 as built** ([m6_design.md](m6_design.md), D-046, D-047).
   - Part A = exactly `project.pdf` §4 (R1–R6), per corpus, full view:
     - R1: words and lemmas with frequencies;
     - R2: sentence length;
     - R3: distinct words per sentence;
     - R4: depth;
     - R5: POS and every inflection feature Dicta outputs (verified in the model's label set);
     - R6: relation types.
   - Parser accuracy: Mikra vs BHSA.
   - **Part B (R7 extras) is deferred.** Do not build it unless Ori opens it.
   - Code: `src/hebloc/stats/` (runset, metrics, tables, compute, report, accuracy), `tests/test_stats.py`,
     CLI `hebloc stats run|accuracy|report|verify`.
   - **One code path:** `--runs <list>` now, `--registered` for the final run. It refuses incomplete corpora.
   - **Parser accuracy (FINAL):** `results/stats/accuracy/` (in git). On 297,324 aligned Hebrew words: POS
     83.5% strict / 88.8% tolerant; prefix segmentation 95.8%; noun lemma 73.4%; verb person/number/gender
     90.9/96.4/94.1%. Restricted to the pilot's 500 verses, it reproduces pilot report §8.1 exactly.
   - **Provisional Mikra + Hazal:** `data/stats/provisional-20261112-27bb4080cf/` (report:
     `report/stats_report.md`, local only).
     - Computed with the then-uncommitted code (`code_commit` 966ec2f…+dirty; `stats_code_sha256`
       identifies the code).
     - `provisional-20261112-e7d1a787d9` (before two formatting fixes) is superseded but kept.
     - Both are superseded by the final run; do not delete them without Ori's approval.
   - **Open question for Ori** (raised 2026-11-12, not decided): very long Hazal "sentences" (whole
     paragraphs; up to 1,955 words; one 362-word Tosefta unit has depth 187, verified) stay in the depth
     statistics as defined (recommended: keep, and discuss in the report). The alternative is to exclude
     units above a length from depth only, which would need a decision entry. Ask at `finish statistics`.
4. **Agreed workflow (D-040, D-045).**
   - Final statistics are computed ONCE on Ori's computer, after `hebloc merge` reports 31/31 COMPLETE
     and `plan register --write`, over the registered runs of all five corpora.
   - Never per person, never by combining partial results.
   - Efrat and Adi only parse and send their folder. Ori's partial Modern slices are a scale test only,
     never reported.
5. **Keep all data (D-045).** Never delete or "clean up":
   - `dicta_raw`, `inputs`, `pieces`, manifests, `checks.json`, `tokens`;
   - bundles, outboxes, received partner folders;
   - `data/stats/*`.

   §5–§8 of the assignment need them. 797 GB were free on 2026-11-12.
6. **Smart App Control (D-035, D-044, D-047).**
   - The venv uses the signed python.org Python 3.12.10.
   - Pins that load: `pyarrow` 25.0.1 (<26), `pandas` 3.0.2 (≤3.0.2), `matplotlib` 3.11.2 (≤3.11.2, with
     pillow 13.0.0).
   - If "An Application Control policy has blocked this file" appears: find the file in the Code
     Integrity log (events 3033/3077), test other versions in a scratch venv, pin one that loads, record
     it in a decision entry. Never disable SAC, never work around it.
   - Always `uv run python -m hebloc …` / `uv run python -m pytest` (D-038).
7. **Git history was rewritten twice** (D-034, D-042): old `code_commit` values in early manifests map
   to new hashes via §8 and `data/backups/pre-public-clean-2026-11-09/commit_map.txt`.
8. **Current sections:** §0, §1, §5 (top), §7. §2–§4 are background; §6 and §8–§13 are the historical
   record of earlier milestones (their to-do lists are done or superseded).

## 1. Status

| Milestone | State | Commit |
|---|---|---|
| M0–M2.1 Foundation, inventory, units | ✅ approved | see §8 |
| M3 Dicta pilot + gate | ✅ decided 2026-11-09 (D-041) | `2e50976` |
| M4 Data layer and access API | ✅ approved (D-030–D-033, D-041) | `2b6f2b1` |
| Team workflow (D-034–D-042) | ✅ public repo, PARTNER_START.md, `hebloc work`/`merge` | up to `730cdbd` |
| **M5 full parse: Ori's share** | ✅ **complete 2026-11-12**: 12/12 slices, 3,504,707 units, 12 verified bundles in `data/outbox/ori` (3.8 GB) | `4938012`, `c5f4627` |
| M5: Efrat's share (9 slices) and Adi's (10 slices) | ⏳ on their computers; status unknown to this repo | — |
| M5 merge + `plan register --write` | ⏳ after both folders arrive (PARTNER_START §12) | — |
| **M6 statistics + parser accuracy** | design approved (D-046); built + tested; accuracy FINAL; Mikra + Hazal PROVISIONAL; **final run after merge + register: `finish statistics` (§7)** | "M6: …" (2026-11-12) |
| M7 review checkpoint | STOP after M6 | — |

**M5 events on 2026-11-12.**
- `modern-tapuz` first failed validation with 7 coverage failures: forum signatures `.·:*¨¨*:·.`. Dicta
  turns "¨¨" into one `[UNK]` word covering only the 2nd "¨". **D-043** excuses exactly that shape
  (counted in `checks.json` as `coverage_excused_diaeresis_pairs`); tapuz was re-validated and packaged
  without re-parsing (0 shard files rewritten; the 11 earlier bundles byte-identical).
- Smart App Control began blocking pyarrow 26.0.1 and pandas 3.1.1 DLLs: **D-044** pins.
- PARTNER_START §10b tells a partner's Claude to `git pull` + `uv sync` + resume once if their run
  stopped for either reason.

**Data on Ori's computer now (what M6 can use before the merge).**

| Corpus | Parsed by | Local state | Run |
|---|---|---|---|
| Mikra | Ori | **complete** (23,206 units) | `mikra/base-topk-v1__mikra` |
| Hazal | Ori | **complete** (418,758 units) | `hazal/base-topk-v1__hazal` |
| Medieval | Efrat | not yet (after merge) | — |
| Haskala | Adi | not yet (after merge) | — |
| Modern | all three | **partial**: Ori's 9 slices, 3,062,743 of 8,877,117 units (34%) | `modern/base-topk-v1__modern-<slice>` |

`config/annotations.yaml` (canonical registry) is **empty** until `plan register --write` (D-032).
Until then pass runs explicitly: `hebloc.data.tokens(corpus, run='<collection>/<run_id>')` takes one
run; `hebloc.data.coverage()` needs the registry.

## 2. Active scope

Corpus processing → Dicta parsing → persistent linguistic data → descriptive statistics
(`project.pdf` §3–§4) → **stop for review (M7)**. Locative-verb extraction, A/B frame
classification, classifiers, word2vec and LLM work remain **deferred** (D-001;
[roadmap.md](roadmap.md) Part 2). The unapproved R5 reordering rule is not applied.

## 3. Architecture

```
corpora/  (IMMUTABLE, 404,294 files; never written)
  │ M1  hebloc inventory      → data/catalog/documents.parquet
  │ M2  hebloc prepare        → data/units/<corpus>/   (complete sentences/verses)
  │ M3  hebloc pilot <step>   → data/annotations/pilot/runs/<run_id>/   (+ models, BHSA)
  │ M5  (planned)             → data/annotations/<corpus>/runs/<run_id>/   same layout
  │ M4  hebloc tokens|check|catalog|export-conllu|bundle|runs  (the data layer below)
  ▼ M6  hebloc stats          → data/stats/<id>/ → results/stats/ + docs/stats_report.md (final run)
```

**M4 data layer** ([data_layer.md](data_layer.md): usage guide and the **M5 contract**;
schemas in [data_dictionary.md](data_dictionary.md)):

| Module | Role |
|---|---|
| `store/io.py` | One crash-safe writer (temp + atomic rename, refuses `corpora/`); sha256; SQL quoting |
| `store/schemas.py` | Registry of every table: schema, key, version, location |
| `store/runs.py` | Run discovery/references (`<collection>/<run_id>`), completeness, `run_dir_for(corpus, run_id)`, canonical registry `config/annotations.yaml` (**empty until M5**) |
| `store/catalog.py` | DuckDB views: `documents`, `units`, `runs`, all-run `*_all`, canonical `inputs`/`pieces`/`dicta_raw`/`tokens`, `piece_status`, `parse_coverage`. In memory (`data.connect()`) or `data/hebloc.duckdb` |
| `store/integrity.py` | `hebloc check`: read-only checks of documents, units, runs and the registry → `data/catalog/integrity.json` |
| `store/conllu.py` | CoNLL-U via Dicta's own converter (byte-identical to `predict(ud/iahlt_ud)`, 50/50 pieces) + provenance comments |
| `store/bundle.py` | D-012 backups: create / verify / restore |
| `parse/tokens.py` | Tokens **per shard**, incremental (source-hash manifests); `migrate_legacy` |
| `parse/checks.py` | `validate_run` streams per shard; fingerprint in `checks.json` |
| `data.py` | Public API: `tokens`, `iter_tokens`, `pieces`, `raw`, `sentence`, `trace_token`, `coverage`, `conllu`, `runs`, `connect` (+ M2 `units`, `iter_units`, `trace`) |

M3 modules are unchanged in behaviour (`parse/run.py` now uses `store.io`; `read_run` reads
committed shards only; pilot code reads per-shard tokens; `hebloc pilot revalidate` was added).

## 4. What M4 established

- **Pilot tokens migrated:** each of the 11 pilot runs' single `tokens.parquet` was re-derived per
  shard, found **row-for-row identical**, and only then removed.
- **Re-validation:** reproduces every M3 `checks.json` count, e.g. invalid trees 24 (base),
  138 (original MST), 3 (tiny). `hebloc pilot revalidate` re-checked every run against its
  expected inputs: all ok.
- **Integrity of the existing data** (`hebloc check --deep`, ~25 s; quick ~5 s): all OK.
  - documents: 404,294 rows = anchor;
  - units: 9,709,662 rows over 5 corpora, matching their manifests, unique, well-formed ids, every doc a full-view document;
  - all 11 runs;
  - registry empty.
- **CoNLL-U:** the export path is byte-identical to Dicta's `predict(output_style="ud")` and
  `"iahlt_ud"` on 50 pilot pieces (10 per corpus). Re-parsing those pieces reproduced the stored
  `raw_json` exactly (50/50).
- **Bundles:** the `pilot/base__default` bundle is 6.1 MiB (1,000 units, 101,368 tokens).
  Create → verify → restore round trip is exact and idempotent; tampering and overwrite conflicts
  are detected (tests).
- **Two latent `tokens` fixes** (no effect on existing data): after an `error` piece, later pieces'
  unit-level indices are null instead of shifted; a missing head is null, not root (D-031).

## 5. Verification at handoff

**2026-11-12, end of session (M6 built):**

| Check | Command | Result |
|---|---|---|
| Fast tests | `uv run python -m pytest -q` | **178 passed**, 1 deselected (~130 s); 11 new in `tests/test_stats.py` |
| Data layer | `uv run python -m hebloc check` | `OK=True`, registry empty |
| Accuracy cross-check | `hebloc stats accuracy` | full Mikra restricted to the pilot's 500 verses = pilot §8.1, **identical** |
| Depth cross-check | `tests/test_stats.py::test_depth_matches_pilot_tree_depths` | = the M3 recursive depth on every valid pilot piece |
| Reconciliation | inside `hebloc stats run` | Mikra + Hazal: 0 problems |
| Determinism | recompute into a scratch folder | 13/13 files byte-identical; `hebloc stats verify` OK |
| Extremes | `hebloc.data.trace` on the 8 longest/deepest units | all trace to their source line; depth 187 confirmed independently |

**2026-11-12** (after Ori's M5 share, D-043/D-044; pandas 3.0.2, pyarrow 25.0.1):

| Check | Command | Result |
|---|---|---|
| Fast tests | `uv run python -m pytest -q` | **167 passed**, 1 deselected (~107 s) |
| Data layer | `uv run python -m hebloc check` | `OK=True`, registry empty (`registered=none`) |
| Derived data | `uv run python -m hebloc fingerprint` | IDENTICAL to the reference |
| Machine | `uv run python -m hebloc doctor` | 0 FAIL |
| Ori's bundles | `hebloc bundle verify` on each of the 12 zips | all `ok: True` |
| Completeness | `uv run python -m hebloc merge` (no paths) | 12/31 slices, 3,504,707/9,709,662 units, 0 duplicates; missing exactly Efrat's 9 and Adi's 10 slices |

**2026-11-08, morning** (before the D-035 fix; checked with git and the signed system Python). Evening results: §10.

| Check | How | Result |
|---|---|---|
| Repo hygiene (`tests/test_repo_hygiene.py`) | its 5 test functions run with stdlib Python | **5/5 pass** |
| History clean | `git log main --name-only` for the 4 removed files | 0 occurrences in all commits |
| Rewrite changed nothing else | `git ls-tree -r` of old vs new HEAD, minus the 4 files | identical |
| Removed files kept locally | `cmp` against `data/backups/files/` | identical, git-ignored |

**2026-11-07** (end of M4, before Smart App Control blocked Python):

| Check | Command | Result |
|---|---|---|
| Fast tests | `uv run pytest` | **118 passed**, 1 deselected (~81 s); 19 new in `tests/test_store.py` |
| Data layer | `uv run hebloc check` (and `--deep`) | `OK=True` |
| Anchor | `uv run hebloc baseline` | `Anchor check: OK` |
| Deep immutability | `uv run pytest -m slow` | **1 passed** (9 min), after all M4 work (2026-11-07) |
| Models | `uv run python -c "from hebloc.parse import models as M; print(M.verify('base'), M.verify('tiny'))"` | `[] []` |

**Environment.**
- Windows 11, 16 GB RAM, 14 threads, no CUDA. Set `PYTHONUTF8=1`.
- DuckDB 2.0:
  - after an open result, use `con.execute(...).to_arrow_table()`, not `con.sql(...)`;
  - for streaming, use `con.sql(q).to_arrow_reader(n)`; `execute(...).to_arrow_reader` copies the rows;
  - `fetch_record_batch` no longer exists.
- Shell heredocs containing Hebrew quotes can break the Bash tool. Put such scripts in the scratchpad.

**Data not in git:**
- `data/models/` (0.9 GB, re-fetch with `hebloc pilot fetch-models`);
- `data/external/bhsa/`;
- `data/annotations/pilot/`;
- `data/bundles/` (one pilot bundle);
- `data/exports/` (regenerable);
- `data/hebloc.duckdb`;
- `data/units_v1/` and `data/units_sample_v1/` (superseded, deletable since M2.1 was approved).

## 6. Decisions (decided 2026-11-09, D-041)

**All M3 gate items and the M4 review are decided in [D-041](decisions.md)**: base, MST fix, `topk`,
invalid trees flagged (D-025), `tokens` schema as proposed, D-026 normalization, R5 not applied,
**coverage A**; multi-piece statistics (D-021) and the manual audit are deferred to the M6 design.
The list below is kept as the historical record of what was pending.

**M4 review** (new): approve D-030 (design, independent of the M3 gate), D-031 (per-shard tokens,
null-index semantics), D-032 (canonical registry), D-033 (bundles). Also, where bundles should be
copied (external drive and cloud folder: the user's action).

**M3 gate** (unchanged, from [pilot_report.md §15](pilot_report.md)):
1. base or tiny;
2. keep the MST fix;
3. adopt `lex_topk`;
4. invalid word-level trees: flag and exclude, or constrained decoding;
5. the `tokens` schema. M4 implements the proposal; a change only needs `hebloc tokens all --force`, no re-parse;
6. normalization defaults (D-026);
7. multi-piece statistics (D-021: a/b/c);
8. R5 and `suspect_bidi`;
9. **Modern coverage** (D-004, §12 options);
10. who annotates the audit.

Also check the machine's power and sleep settings before M5 (one benchmark shard stalled tenfold).

**Parsing speed (investigated 2026-11-08 at the professor's question; analysis only, nothing run).**
- *Measured* (M3 benchmark): base + `topk` runs at 534 sub-words/s → 92 h for full Modern.
- *Derived* from the model configs and the two measured rates:
  - the lemma head (128k-word vocabulary) is ~54% of base's compute and ~90% of tiny's;
  - the CPU is ~86% busy with real computation, and Python post-processing (Dicta's and ours) is ~14%;
  - so the pipeline is not overcomplicated.
- *Assumed* gains:
  - CPU tuning (2–3 processes × 4 threads, power plan, lemma head only on word starts): 1.2–1.5×, so ~55–75 h;
  - a GPU (university server, Colab/Kaggle): ~2–25 h, limited by CPU post-processing.
- Splitting slices across the 3 partners' laptops divides wall-clock time by ~3.
- Recommended: approve `topk`; ask the professor about a GPU and about full-Modern expectations;
  measure (profile, multi-process, batch size, GPU smoke test with an output-agreement check) once
  Python runs again.

## 7. `finish statistics`: final M6 run (fresh session, Plan Mode)

**Goal of that session:** an approved plan for the remaining M6 steps, then its execution in order,
stopping at M7. Talk to Ori in English. In Plan Mode, change nothing until he approves (read-only
checks are fine).

### 7.1 Review the state (read-only)

1. **Read:**
   - [CLAUDE.md](../CLAUDE.md), this file (§0, §1, §5, §7);
   - [m6_design.md](m6_design.md);
   - [decisions.md](decisions.md): D-040, D-045, D-046, D-047, and any newer entries;
   - `PARTNER_START.md` §12 (merge);
   - `project.pdf` §4 and §9 (local only).
2. **Environment and data:**
   ```
   git status --short; git log --oneline -3; git pull
   uv sync
   uv run python -c "import pandas, pyarrow, duckdb, torch, matplotlib; print('imports OK')"
   uv run python -m pytest -q                 # expected: 178 passed, 1 deselected (or more if tests were added)
   uv run python -m hebloc check              # OK=True
   uv run python -m hebloc runs
   uv run python -m hebloc merge              # completeness report only (no paths = no changes)
   ```
3. **Ask Ori where Efrat's and Adi's folders are.**
   - If they have not arrived, report that and stop. Nothing else can be finalized.
   - If only one has arrived, it may be merged (merging is incremental and safe to repeat), but the
     final statistics still wait for 31/31.

### 7.2 The plan to present (adapt to what 7.1 found)

1. **Merge** (PARTNER_START §12).
   - Ori copies each received folder outside the project, e.g. `C:\hebloc-incoming\efrat` and
     `…\adi`.
   - Run `uv run python -m hebloc merge "C:\hebloc-incoming"`.
   - Success = `MERGE OK` and `full coverage A: 31/31 slices OK; units 9,709,662/9,709,662; units in
     more than one run: 0; COMPLETE`.
   - Any FAIL or CONFLICT: stop and report to Ori with the merge report (`data/team/merge_report.json`);
     never work around it. If a partner's agreement check failed, use
     `hebloc agreement --compare <zip>`.
2. **Validate:**
   - `uv run python -m hebloc check` (OK=True);
   - `hebloc runs`: every run complete, tokens up to date. If tokens are missing:
     `hebloc tokens <run>`; never re-parse.
   - optionally `hebloc check --deep` (re-validates every run).
3. **Register:**
   - `uv run python -m hebloc plan register` (preview), then `… plan register --write`. It refuses
     unless COMPLETE.
   - Add a decision entry (D-048 or the next free number) listing the registered runs.
   - Run `hebloc check` again: the registry must be ok, with no unit in two canonical runs.
   - Commit `config/annotations.yaml`.
4. **Settle the open question** (§0.3): long Hazal units in depth. Default: keep, as designed.
5. **Optional timing check** before the full run:
   - Hazal took 48 s for 418,758 units; full Modern (8.9M units) is estimated at ≈20–35 min for unit
     metrics, plus a few minutes of tables.
   - No separate scale test is needed once Modern is complete: the final run is the test.
6. **Final statistics:**
   - Run `uv run python -m hebloc stats run --registered`, with code committed first so that
     `code_commit` has no `+dirty`.
   - It writes `data/stats/final-<date>-<hash>/`, then `results/stats/*.csv`,
     `results/stats/figures/*.png` and `docs/stats_report.md`.
   - Any reconciliation problem stops it before publishing.
7. **Verify the final output:**
   - `hebloc stats verify <folder>`;
   - status `final` in `manifest.json`;
   - 5 corpora, with Mikra and Hazal numbers identical to the provisional ones;
   - determinism: recompute into a scratch `--out` folder and compare sha256;
   - trace the extreme units (longest, deepest per corpus) with `hebloc.data.trace`;
   - read the figures (charts contain no Hebrew; Hebrew only in tables).
8. **Report:** `docs/stats_report.md` is generated (tables, figures, definitions, coverage, accuracy).
   Add a short, hand-written analysis section per §9 ("present and analyse the §4 data"), clearly
   separated from the generated part. Show it to Ori for wording.
9. **Bundle and keep:** back up `data/stats/final-*` (D-012). Keep every earlier stats folder.
10. **Close M6:**
    - update CLAUDE.md, this file, [roadmap.md](roadmap.md), [data_dictionary.md](data_dictionary.md)
      if schemas changed;
    - commit and push (Ori's go-ahead);
    - give the plain-language milestone summary;
    - **STOP at M7** (review with the partners). Do not start §5 (locative verbs) or anything later.

### 7.3 Never

- delete or rewrite parse data, bundles, received folders or stats folders (D-045);
- register runs before 31/31 COMPLETE, or compute final statistics from partial data;
- build Part B (R7 extras) unless Ori opens it;
- change `normalize.py`, `segment.py` or the vendored `dicta_code/` without an approved decision;
- go beyond M6/M7.

*History: the `start statistics` step (M6 design) was done on 2026-11-12. The design was approved as
D-046, and its implementation is commit "M6: …" of that day.*

## 8. Commit hashes before and after the D-034 history rewrite

Manifests and bundles created before 2026-11-08 record the old hashes as `code_commit`.

| Old | New | Commit |
|---|---|---|
| `2b3cc63` | `d332468` | M0: project foundation and immutability guard |
| `b342614` | `1bff748` | Mark M0 complete in CLAUDE.md |
| `b7ca5aa` | `9ffea6a` | M0 follow-up: pin corpus baseline with git-tracked anchor |
| `9d59081` | `7a27434` | M1: corpus inventory and document catalog |
| `3318985` | `50dee12` | Make inventory summary tables deterministic |
| `7b20262` | `abb8f1d` | M1 decisions: full/curated views, scoped duplicates |
| `be72e1d` | `31fdf67` | Full view: exclude whitespace-only placeholders |
| `96b0d1e` | `49247c0` | M2: sentence/verse extraction, normalization and provenance |
| `40d9306` | `ef7d5c8` | Session handoff after M2 |
| `924efd5` | `19e56f2` | M2.1 code: complete-sentence units, parse-time pieces |
| `304182e` | `b93ee12` | units_migrate: fix ambiguous join and DuckDB 2.0 Arrow API |
| `34587d3` | `7521928` | units_migrate: revert to execute() |
| `680f6b5` | `9ae5dd6` | M2.1: regenerate units as complete sentences |
| `1d2254b` | `2e50976` | M3: Dicta pilot and benchmark |
| `3aad371` | `2b6f2b1` | M4: data layer and access API |
| `30c493e` | `77f9aa5` | Prepare private GitHub collaboration |

## 9. Collaboration (D-034)

- **Repository:** GitHub `oribitan258/hebrew-locative-verbs`, created 2026-11-09 (D-039), made
  **public** by Ori (D-041). No invitations; partners clone the public URL and cannot push.
- **In git:** code, config, docs, tests, small result tables, the audit sheets.
- **Never in git:** `corpora/` (partners download it themselves and prove identity with
  `hebloc baseline`), `data/`, secrets, the course documents, `docs/m2_sample_review.md`.
  `tests/test_repo_hygiene.py` enforces this.
- **Partner execution guide (for Claude Code): [PARTNER_START.md](../PARTNER_START.md).** It is the single
  source of the tested commands. [PARTNERS.md](PARTNERS.md) is the human overview. Slash commands:
  `/partner-setup`, `/partner-parse`, `/merge-results`.
- **Built (D-036):** `hebloc parse --slice` (gated), `config/parse_plan.yaml`, the agreement check,
  `hebloc merge`, `hebloc plan register`.
- **To do (user):**
  - fill the two placeholders in `PARTNER_START.md` (corpora link; shared folder);
  - approve the upload list and the GitHub push;
  - send Efrat's and Adi's GitHub usernames;
  - approve the plan (§11).

## 10. Team readiness: what is verified (2026-11-08, D-037)

**Verified on this laptop, from a clean clone at an ASCII path, as "efrat":**
- signed-Python venv;
- corpora installed and sha256-identical (20 min);
- fresh model download, sha256 OK;
- rebuilt catalog and units with content fingerprints identical to the reference;
- tests: 129 passed, 8 skipped;
- doctor all PASS;
- **agreement 1,161/1,161 pieces byte-identical** (758 sub-words/s);
- a real slice REFUSED in draft;
- a smoke slice parsed, bundled and merged into the working repo (`hebloc check` OK);
- an altered bundle rejected;
- documented recovery paths;
- `git status` clean throughout.

**Also verified:**
- the slice partition covers every one of the 9,709,662 units exactly once;
- slice sub-word totals equal the M3 census per corpus;
- `topk` output is byte-identical to the original code on all 1,161 pilot pieces (D-029 evidence;
  M3 had 600).

**Not verified:**
- a different computer or CPU (the agreement shows equality across checkouts, environments and
  downloads on the SAME hardware);
- macOS/Linux;
- a full-size corpora `.zip`;
- cloning from GitHub (not pushed);
- real slices;
- `plan register` with real runs (unit-tested);
- partners' internet speed and download format of the course corpora.

**Speed note.** The agreement run measured 758 sub-words/s with base + `topk` (pilot sample, nothing
else running). The work plan uses the more conservative M3 Modern benchmark (534/s), so the hours in
`WORK_PLAN.md` are an upper estimate on this laptop.

## 11. How to start the parsing phase (Ori, after the gate decisions)

**Steps 1–4 done on 2026-11-09 (D-041).** Remaining: 5 (tell Efrat and Adi; start Ori's own share)
and 6 (merge).

1. Record the gate decisions (decision entries).
2. In `config/parse_plan.yaml`, set the final `settings`.
   - If anything changes, change `settings_id` too, then run `uv run hebloc agreement --as ori` and
     `uv run hebloc agreement --write-reference agreement/<settings_id>__ori`.
   - If the model or budget changes, also run `uv run hebloc plan measure`.
3. Set `status: approved` and `coverage: A|B`, then `uv run hebloc plan assign`.
4. Run `uv run python -m pytest`, commit, `git push`.
5. Tell Efrat and Adi to open their folder in VS Code and ask Claude Code to follow `PARTNER_START.md`.
   It does `git pull`, sees the approval in `work --status`, and starts `hebloc work --detach`
   (§10b). Ori starts his own share the same way.
6. Merge the received `data/outbox/<name>` folders with `uv run python -m hebloc merge <folder>`
   (PARTNER_START §12). When COMPLETE, run `plan register --write`, add a decision entry, then M6.

## 12. Automatic partner workflow: what is verified (2026-11-09, D-038)

- **Full-size archive install.** A zip built read-only from `corpora/`, with UTF-8 names and no
  UTF-8 flag (so the Hebrew names come out garbled), installed in a fresh clone. Names were repaired
  automatically, IDENTICAL to the anchor, 11.2 min. The real course archive was not available (Ori:
  test with the installed corpora). The installer also accepts multi-part zips, nested archives,
  tar.*, 7z/rar and folders (unit-tested; .rar and a Hebrew-named .7z not exercised).
- **Efrat** (fresh clone, every PARTNER_START command as written): all setup steps OK, agreement
  1,161/1,161, rehearsal packaged, `git status` clean.
- **Adi** (first clone): agreement 1,161/1,161; a rehearsal killed mid-slice resumed with no rework.
- **Ori** (this repo, identity `ori`): rehearsal packaged (12 slices).
- **Merge** of the three outbox folders: 31/31 slices, 12,840/12,840 units, 0 duplicated units,
  COMPLETE. Missing, damaged, conflicting and duplicate deliveries are all handled correctly.
- **Test leftovers:** deleted on 2026-11-09 (D-039 cleanup):
  - the two test clones, the test zip, and the merge-test copies (~9.7 GB);
  - this repo's rehearsal/smoke runs and outbox.

  Only `C:\c\` (two stray test files) remains: delete it by hand (Claude Code's safety check blocks it).

## 13. Final M5 workflow (2026-11-09, D-039, D-040)

- **Partner path:** identity → prerequisites → environment → corpora from the course
  archive → model → derived data → pytest + doctor → agreement → *wait for approval* →
  `work --detach` → `work --status` → completion message → send `data/outbox/<name>`.
  No rehearsal (Ori's choice).
- **Workload:** the equal sub-word split in `docs/WORK_PLAN.md` (Ori's choice), for option A or B.
- **Verified on this laptop:**
  - the full suite (also without `PYTHONUTF8`);
  - detached start from a Claude Code shell, lock refusal, kill → status "stopped" → resume →
    complete;
  - `agreement --compare` (101,368/101,368 tokens identical).
- **Not verified:**
  - partners' machines and CPUs (their agreement check is the test);
  - the real course archive;
  - macOS/Linux;
  - a Claude Code window actually closed during a run;
  - full runs, and `register --write` on real runs.
- **Kept on purpose:**
  - `data/units_v1` + `data/units_sample_v1` (1 GB, superseded M2 v1 units, used only by
    `verify-units-v2`);
  - `data/bundles` (pilot backup bundle);
  - `data/annotations/pilot` and `agreement/…__ori` (the reference);
  - `data/backups`.
- **Data volume:** ~1.4 KB per sentence, so ~13–14 GB of results for option A (~4.5 GB per person),
  ~5–6 GB for option B. Ori needs about twice that free while merging.
- **GitHub:** public repo `oribitan258/hebrew-locative-verbs` (D-041); no invitations needed.
- **Transfer:** at completion each person sends `data/outbox/<name>` (~4–5 GB) to Ori by Google
  Drive, OneDrive or USB, and keeps the complete local results until MERGE OK.
