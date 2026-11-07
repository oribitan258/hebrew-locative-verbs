# M3 plan: Dicta pilot and benchmark (approved in principle, NOT started)

*Presented 2026-11-07 and approved in principle by the user. Implementation requires the user's
explicit go-ahead in the M3 session. The prerequisite, complete-sentence units (M2.1, D-020), is
done: parse runs must split over-budget units with `hebloc.pieces` and store `PIECES_SCHEMA` rows.
The statistical treatment of multi-piece units is provisional (D-021).*

**Spec note.** `project.pdf` §3 links the `dictabert` collection, **`dictabert-tiny-joint`** (the
morphology demo) and the `joint-demo` space. CLAUDE.md pins `dictabert-joint`. M3 benchmarks both
and the user chooses.

## Steps

Code goes in `src/hebloc/parse/` (`model.py`, `run.py`, `tokens.py`, `checks.py`; splitting reuses the existing `hebloc.pieces`),
plus `src/hebloc/pilot.py` and `src/hebloc/bhsa.py`, with CLI `hebloc pilot <step>`. The pilot uses
the **same runner M5 will use**, so it tests the real pipeline and not a throwaway script. It
reuses `hebloc.data.iter_units`, `units._git_commit`, the `paths.assert_not_in_corpora` guard, and
the atomic write and manifest pattern from `units.prepare_corpus`.

**Step 1. Environment and model pinning.** *Purpose: reproducible, safe model setup.*
- Add CPU `torch`, `transformers` and `psutil` via uv (locked).
- Download `dicta-il/dictabert-joint` and `dictabert-tiny-joint` at exact HF commit hashes into
  `data/models/` (gitignored, ~0.7 GB + small).
- The models use `trust_remote_code`, so **read the remote modeling code at the pinned revision
  before running it**.
- Record revision, file sha256s and licence.

**Step 2. Output exploration on ~20 hand-picked units.** *Purpose: learn exactly what Dicta returns.*
- Compare `json`, `ud` and `iahlt_ud` field by field, to settle D-008 (is `json` ⊇ `ud`?).
- Check whether **binyan** is output. It matters for the later template work; if absent, document
  it as a limitation.
- Check how prefixes and suffixes and the lemma convention are represented.
- **Measure the real sub-word limit, and test whether over-long input is silently truncated.**
  This is critical: a truncated parse would drop words without an error.
- Output: a draft `tokens` schema.

**Step 3. Pilot sample (~1,000 units, fixed seed, saved as `annotation/pilot_sample.csv` with the
reason each unit was selected).** *Purpose: cover normal and hard text in every corpus.*
- Per corpus: 120 random (full view, proportional to stratum/source) + 80 targeted hard cases:
  - Mikra: Ketiv/Qere verses, Aramaic, poetry, the longest verses.
  - Hazal: vocalized Mishnah, abbreviations (`אומ'`), the commentary stratum, Aramaic.
  - Medieval: Rambam (pre-tokenized), translated Thought works, the longest units.
  - Haskala: heavy markup, post-1881, the longest units.
  - Modern: every source, `prefix_unresolved`, reversed-number lines, URLs, and units that need
    more than one piece.
- `is_empty_norm` units are skipped and counted.

**Step 4. Pilot parse.** *Purpose: run end to end and store the data.*
- Output goes to `data/annotations/pilot/{dicta_raw,tokens,runs}`: raw responses verbatim, keyed
  by `(sent_id, piece_idx, style)`.
- `tokens` are derived only from `dicta_raw`.
- Writes are sharded and atomic, and runs are resumable.
- The manifest records model revision, code commit, norm/segment/piece versions, timings and failures.

**Step 5. Automatic validation.** *Purpose: prove nothing was lost or corrupted.* Each check runs
as a pytest test against small saved Dicta fixtures, so the tests need no model.
- Every sampled unit is parsed or has a logged failure.
- Re-deriving `tokens` from `dicta_raw` gives identical output.
- Each piece's tree has one root, no cycles, and heads in range.
- Dicta's words align back to `text_norm` (no dropped or added words; a truncation detector).
- Pieces concatenate to `text_norm`.
- Corpora are unchanged.

**Step 6. Normalization experiments (D-018 hypotheses).** *Purpose: decide each cleaning choice on
evidence.* The same units are parsed under each variant and compared, using agreement with BHSA
(Mikra) and tokenization sanity (sub-words per word; words Dicta splits oddly).

| Hypothesis | Variants | Units |
|---|---|---|
| Diacritics | stripped vs vocalized | 300 Mikra verses + 200 vocalized Mishnah units |
| Ketiv/Qere | Qere vs Ketiv | all ~1,075 affected verses (cheap) |
| Maqaf | space vs kept | 300 Mikra verses |
| Sof pasuq | `.` vs removed | 300 Mikra verses |

Variants are produced by a parameterized normalizer in the pilot only. `normalize.py` defaults
stay unchanged until you decide.

**Step 7. Accuracy on Biblical Hebrew vs ETCBC/BHSA (approved by D-005).** *Purpose: measure
parser quality on the oldest, hardest layer instead of trusting it.*
- Fetch BHSA through `text-fabric` into `data/external/bhsa/`, recording version and URL.
- Align words per verse (consonantal form, with the Qere/Ketiv handled).
- Report agreement on POS (mapped to UPOS), lemma, and binyan (if Dicta outputs it).
- Dependency trees cannot be compared against BHSA (it has phrase structure, not UD); the manual
  audit covers trees.

**Step 8. Manual audit (~30 units per corpus = 150), in `annotation/pilot_audit.csv`.** *Purpose: a
human check of quality on every corpus, especially the trees.*
- The sheet comes pre-filled with Dicta's analysis.
- A native speaker marks:
  - segmentation and normalization OK?
  - lemma errors and POS errors (counts);
  - main-verb and subject/object/oblique attachment errors;
  - free notes.
- I write the instructions and compute error rates with confidence intervals.

**Step 9. Benchmark.** *Purpose: cost of full parsing, and whether full Modern coverage is feasible.*
- Run on ~5k Modern units (stratified by source) for each configuration:
  - base vs tiny;
  - batch sizes 8, 16, 32 and 64;
  - number of CPU threads.
- Intel Arc XPU is tried only if it works without effort.
- Measure words/s, peak RAM, and bytes per word for `dicta_raw` and `tokens` (zstd Parquet).
- Project hours and GB per corpus, and for Modern under 3 options:
  - (A) full, 134M tokens;
  - (B) all sources, with Haaretz sampled;
  - (C) a stratified sample per source.
- Give the statistical consequence of each option.

**Step 10. Report and decisions.** *Purpose: give you everything needed for the gate.*
- `docs/pilot_report.md`, in plain language, with tables and examples.
- Proposed `tokens` schema in `data_dictionary.md`.
- New decision entries marked *proposed*.
- Updated `HANDOFF.md`, `CLAUDE.md` status, and a commit.
- **STOP for your gate decisions.**

**Rough effort.** About 1–2 sessions of work. Compute is small: ~1k pilot units + ~2k variant
parses + ~40k benchmark units ≈ minutes to ~1–2 h of CPU, depending on the measured speed.

---

## Decisions still open before implementation

1. ~~Chunk correction~~: done in M2.1 (D-020).
2. Statistics for multi-piece sentences: **provisional** (D-021). Decided after the pilot; exclusion may bias substantially.
3. **Downloads and dependencies.**
   - CPU torch, transformers, psutil and text-fabric.
   - Both Dicta models (base and tiny) at pinned revisions, into `data/models/`.
   - BHSA data.
   - Running the models' pinned remote code after I review it.
4. **Sample design** (§3 Step 3): ~200 units per corpus plus the hypothesis sets.
5. **Manual audit.** Who fills in `pilot_audit.csv`? Recommended: you or a partner (native judgment),
   using my prepared sheet.

**Decided after the pilot (not now).** These are listed so nothing is forgotten:
- the `tokens` schema;
- each normalization hypothesis;
- base vs tiny;
- the piece budget;
- R5 and the `suspect_bidi` flag;
- Modern coverage (D-004).

D-012 backups are still required before M5.
