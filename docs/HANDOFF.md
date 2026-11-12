# Session Handoff: Ori's M5 share complete; next is the M6 design (`start statistics`)

*Updated 2026-11-12 (Ori's M5 share complete; D-043 coverage exception, D-044 Smart App Control pins,
D-045 agreed M6 workflow). Earlier: M5 approved 2026-11-09 (D-041), M4 finished 2026-11-07.
This file summarizes and points to other documents; when they disagree, the linked documents win.*

---

## 0. Read first

1. **Next step: M6 planning.** When Ori types **`start statistics`**, follow §7. Present the M6 design
   for approval; **implement nothing before Ori approves it** (D-045).
2. **Agreed M6 workflow (D-040, D-045).**
   - Final statistics are computed ONCE on Ori's computer, after `hebloc merge` reports 31/31 COMPLETE
     and `plan register --write`, over the registered runs of all five corpora.
   - Never per person, never by combining partial results. Efrat and Adi only parse and send their
     `data/outbox/<name>` folder.
   - Develop now: design → approval → code that takes an explicit run list (later: the registered runs)
     → validation on the complete local corpora (Mikra, Hazal). Their numbers are PROVISIONAL until the
     final run. Ori's Modern slices are a scale test only, never reported. Parser accuracy (Mikra vs
     BHSA) can be final now.
3. **Keep all data (D-045).** Never delete or "clean up" `dicta_raw`, `inputs`, `pieces`, manifests,
   `checks.json`, `tokens`, bundles or outboxes. §5–§8 need them. 797 GB were free on 2026-11-12.
4. **Smart App Control (D-035, D-044).**
   - The venv uses the signed python.org Python 3.12.10 (D-035).
   - Since the 2026-11-11 Windows updates, SAC blocks some UNSIGNED library DLLs. `pyproject.toml`
     pins `pyarrow>=17,<26` (25.0.1) and `pandas>=2.2,<=3.0.2` (3.0.2), which load.
   - If a new "An Application Control policy has blocked this file" appears: find the file in the
     Code Integrity log (events 3033/3077), test other versions in a scratch venv, pin one that loads,
     record it in D-044. Never disable SAC, never work around it.
   - Always `uv run python -m hebloc …` / `uv run python -m pytest` (D-038).
5. **Git history was rewritten twice** (D-034, D-042): old `code_commit` values in early manifests map
   to new hashes via §8 and `data/backups/pre-public-clean-2026-11-09/commit_map.txt`.
6. **Current sections:** §0, §1, §5 (top), §7. §2–§4 are background; §6 and §8–§13 are the historical
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
| **M6 statistics + parser accuracy** | **next: design for approval (`start statistics`, §7)**; workflow D-045 | — |
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
  ▼ M6  stats (planned)       → data/stats/ → results/stats/
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

## 7. Startup instructions for the next session: `start statistics` (M6 planning)

**Goal of that session:** a written M6 design that Ori approves. No statistics code, no statistics
runs, no data changes before approval. Talk to Ori in English; end with a plain-language summary.

1. **Read:**
   - [CLAUDE.md](../CLAUDE.md) and this file (§0, §1, §5, §7);
   - [decisions.md](decisions.md): D-015 (full/curated views), D-021 (multi-piece units), D-025
     (invalid trees flagged), D-026 (normalization), D-031/D-032 (tokens, registry), D-040, D-041,
     D-043, D-044, D-045;
   - [data_layer.md](data_layer.md) and [data_dictionary.md](data_dictionary.md) (the `tokens` schema);
   - [roadmap.md](roadmap.md) (the M6 row; R1–R8 only to see what later stages will need);
   - [pilot_report.md](pilot_report.md) §11–§15 (parser accuracy on Mikra vs BHSA, invalid trees);
   - **`project.pdf` §3, §4 and §9** (Hebrew, local only, not in git). If it is missing, ask Ori.
2. **Check the environment and data (read-only):**
   ```
   git status --short; git log --oneline -3
   uv sync
   uv run python -c "import pandas, pyarrow, duckdb, torch; print('imports OK')"   # SAC check (§0.4)
   uv run python -m pytest -q          # expected result: §5
   uv run python -m hebloc check       # OK=True
   uv run python -m hebloc runs        # which runs exist
   uv run python -m hebloc merge       # completeness report only (no paths = no changes)
   ```
   If partners' folders have arrived but are not merged, tell Ori (merging is his action,
   PARTNER_START §12); do not merge without his go-ahead.
3. **Write the M6 design** as `docs/m6_design.md` and present a short summary. It must cover:
   - **Every §4 requirement, per corpus** (Mikra, Hazal, Medieval, Haskala, Modern): words/lemmas and
     their frequencies; sentence lengths; distinct words per sentence; sentence depth from the
     dependency tree (define what it means); morphological categories (POS) and inflection features;
     dependency-relation types; plus proposed additional statistics (§4 "any statistic you can think
     of", §11 personal initiative).
   - **Methodological decisions for Ori**, each with options and a recommendation: what a "word" is
     (whitespace token vs Dicta word vs segment with prefixes split); punctuation, `[UNK]`, blank
     lemmas; the depth definition; multi-piece units (D-021 a/b/c) and invalid trees (D-025); full
     view (primary) vs curated view (D-015); breakdowns (Hazal strata, Haskala before/after 1881,
     Modern by source/genre, Medieval by genre); size-dependent measures (type/token) across corpora
     of very different size; how parse coverage is reported with every statistic.
   - **Parser accuracy** (Mikra vs BHSA, final now) and whether/how a manual audit is done (deferred
     by D-041; audit sheets are local only, D-042).
   - **Validation:** unit tests on fixtures; totals reconciled with `units`/`tokens`; determinism;
     sanity checks against known facts; provisional Mikra/Hazal outputs reviewed before the final run.
   - **Output formats:** `data/stats/*.parquet` with a manifest (runs used, code commit, provisional or
     final), `results/stats/` CSV + PNG, `docs/stats_report.md`; how the final run after the merge
     replaces the provisional outputs.
   - **Workflow** per D-045: explicit run lists now, registered runs after the merge, one code path.
4. **Stop and wait for Ori's approval.** Record his decisions as decision entries (D-046 onward), then
   implement in the approved order.
5. **Never:** delete or rewrite parse data or bundles (D-045); change `normalize.py`, `segment.py` or
   the vendored `dicta_code/` without an approved decision; compute final statistics before the merge
   is COMPLETE and registered.

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
