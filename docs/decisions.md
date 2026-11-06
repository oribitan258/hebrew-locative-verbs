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

### D-009 · Preprocessing defaults (2026-11-06) · hypothesis (validate in M2/M3)
Every row below is a **hypothesis**, not a settled choice. None becomes `accepted` until the M3
pilot has compared it with its alternative and the user has approved the result.

| Choice | Default (hypothesis) |
|---|---|
| Units | Mikra: verse. Modern: source line. Other corpora: paragraph split on `. : ? !` with abbreviation guards; over-length units are chunked |
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

### D-012 · Backup and sharing strategy for derived data (2026-11-06) · accepted (documentation only)
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
