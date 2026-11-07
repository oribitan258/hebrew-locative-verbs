# Session Handoff: after M2.1, before M3

*Written 2026-11-06 at the end of the M0–M2 session; updated 2026-11-07 after M2.1. The next session starts M3. This file
summarizes and points to other documents; when they disagree, the linked documents win.*

---

## 1. Status

| Milestone | State | Commit |
|---|---|---|
| M0 Foundation | ✅ approved | `2b3cc63`, `b7ca5aa` |
| M1 Inventory and catalog | ✅ approved | `9d59081`, `7b20262`, `be72e1d` |
| M2 Unit extraction | ✅ approved (2026-11-06) | `96b0d1e` |
| M2.1 Complete-sentence units (segment v2, D-020) | ✅ done 2026-11-07, **awaiting user approval** | `924efd5` (code), docs commit after it |
| **M3 Dicta pilot and benchmark** | **not started. Plan approved in principle; implementation needs explicit go-ahead after M2.1 review** | — |
| M4–M7 | not started | — |

## 2. Active scope

Corpus processing → Dicta parsing → persistent linguistic data → descriptive statistics
(`project.pdf` §3–§4) → **stop for review (M7)**.

Locative-verb extraction, A/B frame classification, classifiers, word2vec and LLM work are
**deferred**. They live only in [roadmap.md](roadmap.md) Part 2 and must not be implemented until
the user opens that scope (D-001).

## 3. Architecture

```
corpora/  (IMMUTABLE, 404,294 files; never written)
  │ M1  hebloc inventory   → data/catalog/documents.parquet   (1 row per file, 66 cols)
  │ M2  hebloc prepare     → data/units/<corpus>/part-*.parquet + _manifest.json  (22 cols; complete sentences, segment v2)
  │ M2.1 verify-units-v2   → data/migrations/segment_v1_to_v2/{report.json,map.parquet,differences.parquet}
  │ M3  pilot              → data/annotations/pilot/…          (planned)
  │ M5  parse              → data/annotations/<corpus>/{dicta_raw,tokens,runs}/ (planned)
  ▼ M6  stats              → data/stats/*.parquet → results/stats/ (planned)
```

| Module (`src/hebloc/`) | Role |
|---|---|
| `paths.py` | All locations; `assert_not_in_corpora()` guard |
| `baseline.py` | sha256 baseline and the git-tracked anchor (`config/corpora_anchor.json`) |
| `textstats.py` | Decoding (strict UTF-8 → cp1255 → flagged), canonical line split (`\n` only), profiles |
| `metadata.py`, `curation.py` | Per-corpus filename metadata; strata and period tags from `config/curation.yaml` |
| `inventory.py`, `catalog.py`, `inventory_report.py` | M1 catalog: build, verification gate, `documents()` reader |
| `segment.py` | Sentence spans; units are never cut (`SEGMENT_VERSION = "2"`) |
| `pieces.py` | Parse-time splitting of `text_norm` into pieces linked to `sent_id` (`PIECES_SCHEMA`, `verify_pieces`) |
| `units_migrate.py` | M2.1 exhaustive v1→v2 verification and old→new id map (`hebloc verify-units-v2`) |
| `normalize.py`, `artifacts.py` | Per-corpus `text_raw → text_norm` (`NORM_VERSION = "1"`); `prefix=`/`token=` rules R1–R4 |
| `versification.py` | Mikra references and Aramaic ranges (`config/reference/tanakh_versification.json`) |
| `units.py`, `units_review.py` | M2 extraction, per-corpus manifests, sample review |
| `data.py` | **Public API** (see below) |
| `cli.py` | `hebloc baseline / anchor / inventory / versification / prepare / verify-units-v2` |

**Identifiers.**
- `doc_id` = blake2b-48 of `rel_path`.
- `sent_id = <corpus>:<doc_id>:<line_no>:<k>`.
- `text_raw == decoded_line[char_start:char_end]`, checked for every unit.

**Schemas.** Every column is described in [data_dictionary.md](data_dictionary.md).

**Python access.**
```python
from hebloc.catalog import documents          # documents(corpus, view="full"|"curated", columns=[…])
from hebloc.data import units, iter_units, connect, trace
units("mikra", view="curated", columns=["sent_id", "ref", "text_norm"])   # pandas
con = connect(); con.sql("select corpus_id, count(*) from units group by 1")  # DuckDB views: documents, units
trace("mikra:7ed0fd1ad789:113:0")             # re-reads the original file, returns verified=True
```

## 4. Completed work

- **M0.**
  - uv environment (Python 3.12) and git.
  - [CLAUDE.md](../CLAUDE.md), [roadmap.md](roadmap.md) and [decisions.md](decisions.md).
  - Immutability guard: a sha256 baseline pinned by the git-tracked anchor.
  - Backup and sharing strategy, documented only: [data_management.md](data_management.md).
- **M1.**
  - Catalog of all 404,294 files: encoding, counts, metadata, strata and period tags, duplicates
    scoped by `stratum|source`, plus the full and curated views.
  - Findings and decisions: [corpus_report.md](corpus_report.md).
  - Tables: [corpus_inventory_tables.md](corpus_inventory_tables.md).
- **M2.** Units with provenance, raw and normalized text, and change flags.
- **M2.1.** Units are complete sentences (segment v2); model splitting moved to parse time; the
  3 chunk-boundary defects fixed (2 in `text_norm`, 1 flag label); exhaustively verified ([m2_preprocessing.md §8](m2_preprocessing.md), D-020).
  Total units: 9,709,662.
  - Method and evidence: [m2_preprocessing.md](m2_preprocessing.md).
  - Examples: [m2_sample_review.md](m2_sample_review.md).

| Corpus | Units (full view) | Curated | Unit types |
|---|---|---|---|
| Mikra | 23,206 | 23,206 | verse |
| Hazal | 418,758 | 131,113 | sentence |
| Medieval | 115,415 | 89,508 | sentence |
| Haskala | 275,166 | 275,166 | sentence |
| Modern | 8,877,117 | 8,742,706 | sentence |

(Segment v1 counts were 9,714,378 including 7,716 chunks; see D-020.)

Storage: `data/units` is 1.0 GB, `data/catalog` 39 MB, and `data/units_sample` (validation run
only) 13 MB.

## 5. Verification (state at handoff, updated 2026-11-07 after M2.1)

| Check | Command | Latest result |
|---|---|---|
| Fast tests (incl. immutability: file set, sizes, mtimes; anchor; units integrity; segment v2; pieces) | `uv run pytest` | **87 passed**, 1 deselected (~70 s) |
| Deep immutability (sha256 of every corpus file) | `uv run pytest -m slow` | **1 passed** (1,338 s), run after the M2.1 regeneration (2026-11-07) |
| Anchor consistency | `uv run hebloc baseline` | prints `Anchor check: OK` (no recompute) |
| Unit manifests | `data/units/<corpus>/_manifest.json` | all `ok: true`, `segment_version` 2, code commit `924efd5` (clean); 0 coverage failures, 0 line mismatches |
| M2.1 regeneration vs v1 | `uv run hebloc verify-units-v2` (needs `data/units_v1`) | report at clean commit `34587d3`: `structural_ok: true`; 0 differing rows on unaffected lines; all derived-value differences in 3 explained sentences (D-020) |
| Validation sample | `data/units_sample/*/_manifest.json` | regenerated with segment v2 at clean commit `924efd5`. The stale pre-M2 sample (`be72e1d+dirty`) is kept as `data/units_sample_v1` |

**Limitations.**
- `data/` is not in git and has no backup yet (D-012 must be implemented before M5).
- If `data/` is lost, it can be rebuilt with `uv run hebloc inventory` (~75 s) followed by
  `uv run hebloc prepare` (~4 min).
- `data/units_v1/` (1.0 GB) and `data/units_sample_v1/` are the preserved segment-v1 outputs.
  They are kept until the user approves M2.1, because `verify-units-v2` and the migration map need
  them. Afterwards they can be deleted (derived, superseded data).

**Environment.**
- Windows 11, 16 GB RAM, Intel Arc iGPU (no CUDA).
- The project path contains Hebrew, so set `PYTHONUTF8=1` for console scripts.
- Windows multiprocessing needs scripts saved to a file, not piped through stdin.
- DuckDB 2.0 differences: lambda syntax is `lambda x: …`; use `connect().execute()` rather than
  `duckdb.sql().fetchone()`.

## 6. Key decisions ([decisions.md](decisions.md))

| ID | What it decides |
|---|---|
| D-001 | Data-foundation scope only |
| D-002, D-010, D-011 | `corpora/` is immutable; two-level guard; git-tracked anchor; never re-anchor without a documented decision |
| D-003, D-015 | Nothing dropped. The **full view is the primary reference**; the curated view (in-period, non-blank, deduplicated within `stratum\|source`) is an additional, labelled view. Tags are operational metadata, not historical truth |
| D-004 | Modern coverage is the user's decision after the M3 benchmark |
| D-005 | External data approved: Tanakh versification (done) and ETCBC/BHSA as gold (M3/M6) |
| D-007, D-008 | Parquet + DuckDB; raw Dicta responses kept losslessly (sizes to confirm in M3) |
| D-009, D-018 | Preprocessing rules; which are accepted and which are **hypotheses** |
| D-012 | Backup bundles before M5 |
| D-016, D-019 | `prefix=` artifact policy and results |
| D-020 | Units are complete sentences (segment v2); model splitting is a parse-time step (`hebloc.pieces`) |
| D-021 | **Provisional** statistical treatment of multi-piece sentences; possibly substantial selection bias; to be finalized after M3 |

## 7. Open M2 issues (none decided; do not decide them unilaterally)

Details: [m2_preprocessing.md §7](m2_preprocessing.md).

1. **Unresolved `prefix=` artifacts:**
   - 304,991 tags (26.3%) in 250,149 units, flagged `prefix_unresolved:<class>`;
   - only the tag text was removed.
2. **Candidate rule R5 (not applied).** It would rebuild `prefix=X - P N` as `X-N P` (≈100k cases)
   by reordering tokens. It needs user approval, after a manual check of ~100 cases.
3. **Reversed numbers and Latin text** in Haaretz, ynet and nrg, a source defect (e.g. `% 20.3`).
   Option: add a `suspect_bidi` unit flag. Not applied.
4. **Preprocessing hypotheses for M3 to test:**
   - diacritic stripping;
   - Qere in `text_norm` (Ketiv in `text_norm_alt`);
   - maqaf → space;
   - sof pasuq → `.`.
5. **Empty after normalization:** 306 units (`is_empty_norm`), to be skipped by the parser and
   counted in its manifest.
6. **Piece budget.** Units are complete (M2.1). The piece budget, in Dicta sub-words, must be
   measured in M3; see §8.

## 8. Critical statistical consideration: sentences vs pieces (resolved structurally by M2.1)

**State after M2.1 (D-020).**
- `units` holds only complete sentences and verses.
- A unit too long for the parser is split **at parse time** into pieces with
  `hebloc.pieces.plan_pieces`.
- Each piece row (`PIECES_SCHEMA`) carries the parent `sent_id`, `piece_idx`, `n_pieces` and its
  exact span in `text_norm`.
- Parse runs must store these rows and run `verify_pieces`.
- The parent sentence is always the unit itself.

Long units, for orientation (whitespace tokens of `text_norm`):
- In v1, 3,000 sentences exceeded 200 tokens (median 272, p99 1,281, max 6,437).
- Units over 150 tokens: Modern 2,864, Hazal 1,801, Haskala 2,255, Medieval 1,169.
- The longest Mikra verse has 44 tokens.

**Statistics (D-021, provisional).**
- Compute length and distinct words per complete unit.
- A unit parsed in more than one piece has no complete tree. Report such units explicitly in every
  tree statistic, and never stitch pieces under an invented root.
- Excluding them **may cause substantial selection bias**: they are the longest sentences, and they
  are concentrated in certain corpora and works.
- The final treatment is decided after the M3 pilot measures how many units need several pieces.
  Alternatives include a larger budget or overlapping windows.
- Never treat Mikra verses and prose sentences as the same kind of unit without saying so.

## 9. Next milestone: M3 Dicta pilot and benchmark (gate)

Defined in [roadmap.md Part 1](roadmap.md) and D-008/D-009/D-018. **Detailed step plan: [m3_plan.md](m3_plan.md)** (approved in principle 2026-11-07).

- **Objectives:**
  - Pin `dicta-il/dictabert-joint` at an exact Hugging Face revision; install a CPU PyTorch.
  - Inspect the `json`, `ud` and `iahlt_ud` outputs; test whether `json` contains everything in `ud` (D-008).
  - Finalize the `tokens` schema: features, binyan, lemma convention, prefixes and suffixes, heads and relations.
  - Measure Dicta's sub-word limit; set the piece budget and cost unit for `hebloc.pieces` (§8).
  - Test explicitly whether over-long input is silently truncated by the model.
  - Test the D-018 hypotheses as A/B comparisons on Mikra and Mishnah.
  - Align pilot verses with BHSA (POS and lemma agreement).
  - Run a manual audit of ~30 units per corpus (`annotation/pilot_audit.csv`).
- **Inputs:**
  - A stratified sample of ~200 units per corpus (~1,000 in total) from `data/units`.
  - The sample must include difficult cases: Ketiv/Qere verses, Aramaic, units needing several pieces, `prefix_unresolved`, the longest units, vocalized Mishnah.
  - Skip `is_empty_norm` units.
- **Outputs:**
  - `data/annotations/pilot/{dicta_raw,pieces,tokens,runs}`.
  - [pilot_report.md](pilot_report.md), to be created.
  - New decision-log entries, marked *proposed*.
- **Validation:**
  - Every sampled unit is parsed or has a logged failure.
  - `tokens` re-derived from `dicta_raw` are identical.
  - Tree integrity: one root, no cycles, heads in range.
  - Every token aligns to `text_norm`.
  - The run manifest records the model revision, code commit and norm/segment versions.
  - Corpora are unchanged.
- **Resource measurements:**
  - Words per second: base vs tiny model; CPU vs Intel XPU only if it works easily.
  - Peak RAM.
  - Bytes per word: raw responses and the `tokens` table.
  - Projected hours and GB per corpus.
- **Approval gates:**
  1. The user approves the M3 plan **before** any model download or Dicta run.
  2. After the pilot, the user decides:
     - the `tokens` schema;
     - each preprocessing hypothesis;
     - R5 and the bidi flag;
     - the piece budget and the statistical treatment of multi-piece units (D-021);
     - **Modern coverage** (options with hours, GB and statistical implications; D-004).
  3. Before M5, the backup bundles (D-012) must exist.
  4. No full-corpus run happens before both gates above are passed.

## 10. Startup instructions for the next session

1. **Read:**
   - [CLAUDE.md](../CLAUDE.md) (loaded automatically) and this file;
   - [decisions.md](decisions.md): D-001–D-004, D-008, D-009, D-015–D-019;
   - [m2_preprocessing.md](m2_preprocessing.md) §4–§7;
   - [roadmap.md](roadmap.md) Part 1;
   - the `units` section of [data_dictionary.md](data_dictionary.md);
   - `project.pdf` §3 (the Dicta requirements) and §4 (the statistics);
   - [data_management.md](data_management.md).
2. **Check** (all must pass; report any discrepancy before doing anything else):
   ```
   git status --short          # expect clean; git log -1 = the M2.1 docs commit
   uv sync
   uv run pytest               # expect 87 passed, 1 deselected
   uv run hebloc baseline      # expect "Anchor check: OK"
   ```
   Then confirm that `data/units/<corpus>/_manifest.json` exists for all 5 corpora, with `ok: true`,
   `segment_version` 2 and the unit counts in §4. If `data/` is missing, rebuild it with `hebloc inventory` and then
   `hebloc prepare`, and re-check the counts. Optionally run `uv run pytest -m slow` (~11 min).
3. **Then:**
   - The M3 plan (sample design, outputs, measurements, hypothesis tests, BHSA, audit, benchmark)
     was presented on 2026-11-07 and approved *in principle*. Confirm the user's explicit go-ahead
     and the open choices (dependencies and downloads, the two models `dictabert-joint` and
     `dictabert-tiny-joint` (the spec links the tiny one), sample design, who fills the manual audit)
     before starting.
   - **Do not download a model, install M3 dependencies, or run Dicta before that go-ahead.**
   - Do not change `normalize.py` or `segment.py` rules, or bump `norm_version`/`segment_version`,
     without a decision-log entry approved by the user.
