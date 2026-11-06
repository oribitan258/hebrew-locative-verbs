# Session Handoff: after M2, before M3

*Written 2026-11-06 at the end of the M0–M2 session. The next session starts M3. This file
summarizes and points to other documents; when they disagree, the linked documents win.*

---

## 1. Status

| Milestone | State | Commit |
|---|---|---|
| M0 Foundation | ✅ approved | `2b3cc63`, `b7ca5aa` |
| M1 Inventory and catalog | ✅ approved | `9d59081`, `7b20262`, `be72e1d` |
| M2 Unit extraction | ✅ approved (2026-11-06) | `96b0d1e` |
| **M3 Dicta pilot and benchmark** | **not started. Needs the user's explicit approval of a plan first** | — |
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
  │ M2  hebloc prepare     → data/units/<corpus>/part-*.parquet + _manifest.json  (22 cols)
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
| `segment.py` | Sentence spans and 200-token chunking (`SEGMENT_VERSION = "1"`) |
| `normalize.py`, `artifacts.py` | Per-corpus `text_raw → text_norm` (`NORM_VERSION = "1"`); `prefix=`/`token=` rules R1–R4 |
| `versification.py` | Mikra references and Aramaic ranges (`config/reference/tanakh_versification.json`) |
| `units.py`, `units_review.py` | M2 extraction, per-corpus manifests, sample review |
| `data.py` | **Public API** (see below) |
| `cli.py` | `hebloc baseline / anchor / inventory / versification / prepare` |

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
- **M2.** 9,714,378 units with provenance, raw and normalized text, and change flags.
  - Method and evidence: [m2_preprocessing.md](m2_preprocessing.md).
  - Examples: [m2_sample_review.md](m2_sample_review.md).

| Corpus | Units (full view) | Curated | Unit types |
|---|---|---|---|
| Mikra | 23,206 | 23,206 | verse |
| Hazal | 419,816 | 131,884 | 418,050 sentence + 1,766 chunk |
| Medieval | 116,004 | 90,054 | 114,940 sentence + 1,064 chunk |
| Haskala | 276,531 | 276,531 | 274,316 sentence + 2,215 chunk |
| Modern | 8,878,821 | 8,744,397 | 8,876,150 sentence + 2,671 chunk |

Storage: `data/units` is 1.0 GB, `data/catalog` 39 MB, and `data/units_sample` (validation run
only) 13 MB.

## 5. Verification (state at handoff, 2026-11-06)

| Check | Command | Latest result |
|---|---|---|
| Fast tests (incl. immutability: file set, sizes, mtimes; anchor; units integrity) | `uv run pytest` | **82 passed**, 1 deselected (~75 s) |
| Deep immutability (sha256 of every corpus file) | `uv run pytest -m slow` | **1 passed** (659 s), run after M2 |
| Anchor consistency | `uv run hebloc baseline` | prints `Anchor check: OK` (no recompute) |
| Unit manifests | `data/units/<corpus>/_manifest.json` | all `ok: true`; 0 coverage failures, 0 line mismatches |
| Clean provenance | Units regenerated at handoff from the clean commit `96b0d1e`; all manifests record it | Content hash identical to the earlier run for all 5 corpora (deterministic) |

**Limitations.**
- `data/` is not in git and has no backup yet (D-012 must be implemented before M5).
- If `data/` is lost, it can be rebuilt with `uv run hebloc inventory` (~75 s) followed by
  `uv run hebloc prepare` (~3–5 min).
- `data/units_sample/` manifests may still record the earlier dirty commit. It is a validation
  sample only.

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
6. **Long-sentence chunking.** 200 whitespace tokens is a provisional cap. It must be checked
   against Dicta's real sub-word limit; see §8.

## 8. Critical statistical consideration: sentences vs chunks

A `chunk` is a **processing piece** of one over-long linguistic sentence, not a sentence. If chunks
are counted as sentences:
- sentence-length statistics are capped and biased downward;
- each chunk gets its own dependency tree, which truncates tree depth and invents extra roots.

Facts measured at handoff, by re-deriving `sentence_spans` from the source lines:

| | |
|---|---|
| Original sentences split into chunks | **3,000** (Hazal 708, Medieval 475, Haskala 850, Modern 967; Mikra none) |
| Chunks | 7,716; 2–33 per sentence, mean 2.57 |
| Two chunked sentences adjacent on one line | **135**. Here the stored columns (`line_no`, `k`, `unit_type`) **cannot** tell where one sentence ends and the next begins |

The parent sentence is still recoverable deterministically. It can be recomputed with
`segment.sentence_spans()` on the source line (segment v1), but **it is not stored**.

Before M3 parses anything, the next session should *propose* (not silently implement) one of the
following:
- (a) add a parent-sentence key (e.g. `sentence_k`) to `units`. This is a schema addition that
  changes no text or rule;
- (b) parse whole sentences when they fit Dicta's limit, and chunk only beyond it.

Statistics must then:
- compute length and depth **per original sentence**;
- report chunked sentences separately (or exclude them with a stated count);
- never treat Mikra verses and prose sentences as the same kind of unit without saying so.

## 9. Next milestone: M3 Dicta pilot and benchmark (gate)

Defined in [roadmap.md Part 1](roadmap.md) and D-008/D-009/D-018.

- **Objectives:**
  - Pin `dicta-il/dictabert-joint` at an exact Hugging Face revision; install a CPU PyTorch.
  - Inspect the `json`, `ud` and `iahlt_ud` outputs; test whether `json` contains everything in `ud` (D-008).
  - Finalize the `tokens` schema: features, binyan, lemma convention, prefixes and suffixes, heads and relations.
  - Measure Dicta's sub-word limit and set the chunk policy (§8).
  - Test the D-018 hypotheses as A/B comparisons on Mikra and Mishnah.
  - Align pilot verses with BHSA (POS and lemma agreement).
  - Run a manual audit of ~30 units per corpus (`annotation/pilot_audit.csv`).
- **Inputs:**
  - A stratified sample of ~200 units per corpus (~1,000 in total) from `data/units`.
  - The sample must include difficult cases: Ketiv/Qere verses, Aramaic, chunks, `prefix_unresolved`, the longest units, vocalized Mishnah.
  - Skip `is_empty_norm` units.
- **Outputs:**
  - `data/annotations/pilot/{dicta_raw,tokens,runs}`.
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
     - the chunk and parent-sentence policy;
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
   git status --short          # expect clean; git log -1 = the handoff commit
   uv sync
   uv run pytest               # expect 82 passed, 1 deselected
   uv run hebloc baseline      # expect "Anchor check: OK"
   ```
   Then confirm that `data/units/<corpus>/_manifest.json` exists for all 5 corpora, with `ok: true`
   and the unit counts in §4. If `data/` is missing, rebuild it with `hebloc inventory` and then
   `hebloc prepare`, and re-check the counts. Optionally run `uv run pytest -m slow` (~11 min).
3. **Then:**
   - Present a concise M3 plan: sample design, outputs, measurements, the chunk-policy proposal
     (§8), and how each hypothesis will be tested.
   - Ask for approval. **Do not download the model or run Dicta before approval.**
   - Do not change `normalize.py` or `segment.py` rules, or bump `norm_version`/`segment_version`,
     without a decision-log entry approved by the user.
