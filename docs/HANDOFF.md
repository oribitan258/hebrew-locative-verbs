# Session Handoff: after M4, at the M4 review (M3 gate decisions still pending)

*Updated 2026-11-07 at the end of the M4 session. This file summarizes and points to other
documents; when they disagree, the linked documents win.*

---

## 1. Status

| Milestone | State | Commit |
|---|---|---|
| M0 Foundation | ✅ approved | `2b3cc63`, `b7ca5aa` |
| M1 Inventory and catalog | ✅ approved | `9d59081`, `7b20262`, `be72e1d` |
| M2 Unit extraction | ✅ approved | `96b0d1e` |
| M2.1 Complete-sentence units (segment v2, D-020) | ✅ approved | `924efd5`, `680f6b5` |
| M3 Dicta pilot and benchmark | ✅ done. **Gate decisions still pending** ([pilot_report.md §15](pilot_report.md); §6 below) | `1d2254b` |
| **M4 Data layer and access API** | ✅ done 2026-11-07. **Awaiting user review** (D-030–D-033 *proposed*) | see `git log` |
| M5 full parse, M6 statistics, M7 review | not started. **M5 is blocked on the M3 gate decisions** and on M4 approval | — |

**Do not start M5 and do not run full-corpus parsing** until the user has (a) approved M4 and
(b) decided the M3 gate items.

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

## 6. Decisions pending (do not decide them unilaterally)

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

## 7. Startup instructions for the next session

1. Read [CLAUDE.md](../CLAUDE.md), this file, [data_layer.md](data_layer.md) (§5 = M5 contract),
   [decisions.md](decisions.md) D-020–D-033, and [pilot_report.md](pilot_report.md) §11–§15.
2. Check:
   ```
   git status --short; git log --oneline -3
   uv sync
   uv run pytest                 # 118 pass; no model is loaded by the tests
   uv run hebloc baseline        # Anchor check: OK
   uv run hebloc check           # OK=True
   ```
3. Ask for the M4 approval and the M3 gate decisions if they have not been given. Record each
   one as a decision entry, and change D-030–D-033 from *proposed* to *accepted* only on approval.
4. Only then plan M5, following the contract in [data_layer.md §5](data_layer.md). Start with
   the historical corpora (≈ 36 h base, or 11 h with `topk`), and run Modern according to the D-004
   decision. Bundle every finished run.
5. Do not change `normalize.py`, `segment.py` or the vendored `dicta_code/` without an approved
   decision entry.
