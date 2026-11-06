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
