# Session Handoff: after M3, at the M3 review gate

*Updated 2026-11-07 at the end of the M3 session. This file summarizes and points to other
documents; when they disagree, the linked documents win.*

---

## 1. Status

| Milestone | State | Commit |
|---|---|---|
| M0 Foundation | ✅ approved | `2b3cc63`, `b7ca5aa` |
| M1 Inventory and catalog | ✅ approved | `9d59081`, `7b20262`, `be72e1d` |
| M2 Unit extraction | ✅ approved | `96b0d1e` |
| M2.1 Complete-sentence units (segment v2, D-020) | ✅ approved | `924efd5`, `680f6b5` |
| **M3 Dicta pilot and benchmark** | ✅ done 2026-11-07. **At the review gate: user decisions pending** ([pilot_report.md §15](pilot_report.md)) | see `git log` |
| M4 Data layer, M5 full parse, M6 statistics, M7 review | not started. **Blocked on the M3 gate decisions** (and D-012 backups before M5) | — |

## 2. Active scope

Corpus processing → Dicta parsing → persistent linguistic data → descriptive statistics
(`project.pdf` §3–§4) → **stop for review (M7)**.

Locative-verb extraction, A/B frame classification, classifiers, word2vec and LLM work remain
**deferred** (D-001; [roadmap.md](roadmap.md) Part 2). The unapproved R5 reordering rule is not
applied.

## 3. Architecture

```
corpora/  (IMMUTABLE, 404,294 files; never written)
  │ M1  hebloc inventory     → data/catalog/documents.parquet
  │ M2  hebloc prepare       → data/units/<corpus>/  (complete sentences/verses, segment v2)
  │ M3  hebloc pilot <step>  → data/models/ (pinned weights), data/external/bhsa/,
  │                            data/annotations/pilot/{runs,results,bench,exploration}/
  │ M5  parse (planned)      → data/annotations/<corpus>/… (same run layout as the pilot)
  ▼ M6  stats (planned)      → data/stats/ → results/stats/
```

| Module | Role |
|---|---|
| `parse/models.py` | Pinned model registry (`config/models.yaml`), sha256 verification, offline load via the vendored class, sub-word cost |
| `parse/dicta_code/` | **Vendored, unmodified** Dicta model code (reviewed; checksums pinned). Do not edit |
| `parse/dicta_fixes.py` | Runtime fixes: `mst_seq_len` (correctness, on) and `lex_topk` (speed, off unless approved) |
| `parse/run.py` | Sharded, resumable, atomic runner: `inputs/`, `pieces/`, `dicta_raw/` (verbatim JSON), `_shards/`, `run.json` |
| `parse/tokens.py` | `tokens` table derived from raw output only (proposed schema) |
| `parse/checks.py` | Integrity checks (coverage/truncation, provenance, pieces, re-derivation) and model-tree validity |
| `pieces.py` | Splitting into ≤ 510-sub-word pieces linked to `sent_id` |
| `pilot/` | `sample`, `runs`, `variants` (normalization variants), `bhsa` (fetch, Text-Fabric reader, alignment), `experiments`, `analyze`, `audit`, `bench`, `benchmark_plan`, `memprobe`, `examples`, `steps` (CLI) |

Schemas: [data_dictionary.md](data_dictionary.md) (units, pieces, parse runs, tokens).

## 4. What M3 established (details: [pilot_report.md](pilot_report.md))

- **Models:**
  - `dictabert-joint` @ `7b1256fc0846` and `dictabert-tiny-joint` @ `708026b7297f`, CC-BY-4.0;
  - code reviewed and vendored (D-022);
  - **store `json` only**, since UD is derivable (D-023).
- **Model limit:** 510 sub-words, truncated **silently** beyond that.
  - Pieces plus a full character-coverage check guard against it (D-028).
  - Census over all units: multi-piece units are 0–0.075% of units but **1.2–2.9% of the words**
    of Hazal, Medieval and Haskala.
- **Dicta problems:**
  - the MST bug gave 11.9% invalid trees; fixed to 2.1% (D-024);
  - the sub-word→word head mapping leaves 2.1% invalid trees, which are flagged and never repaired
    (D-025);
  - the full-vocabulary sort dominates cost (D-029);
  - Dicta predicts **no binyan**.
- **Quality vs BHSA** (500 verses, base):
  - POS 83.6% strict / 88.5% tolerant; prefix split 95.2%; verb person/number/gender 91/97/94%;
  - noun lemma 71%; Aramaic POS 48%.
  - Base clearly beats tiny.
  - Base–tiny head agreement is only 57–71% on historical corpora, vs 89% on Modern.
- **Normalization:**
  - all four D-018 defaults are supported;
  - diacritics make **no** difference to the model (144,247/144,247 units identical input).
- **Manual audit:** sheets ready (`annotation/pilot_audit*.csv`, guide), **not annotated**.
- **Benchmark** (Modern, 3,000 units):
  - base 161 sub-words/s, or **534 with `topk`** (output identical, 600/600 pieces);
  - tiny 229, or 1,529 with `topk`;
  - peak RAM 1.1–3.4 GB; storage ≈ 64 B per sub-word.
- **Projections** (base):
  - historical corpora 36 h (11 h with `topk`);
  - full Modern 306 h (92 h with `topk`), 11.4 GB.
  - Modern options A/B/C are in the report §12.
  - One shard stalled tenfold (likely system power or idle throttling), so check power settings
    before M5.

## 5. Verification at handoff

| Check | Command | Result |
|---|---|---|
| Fast tests | `uv run pytest` | **99 passed**, 1 deselected (~77 s) |
| Anchor | `uv run hebloc baseline` | `Anchor check: OK` |
| Deep immutability | `uv run pytest -m slow` | **1 passed**, after all M3 runs (2026-11-07) |
| Pilot runs | `data/annotations/pilot/runs/*/checks.json` | all `ok: true` (integrity); invalid-tree counts reported separately |
| Models | `uv run python -c "from hebloc.parse import models as M; print(M.verify('base'), M.verify('tiny'))"` | `[] []` |

**Environment.**
- Windows 11, 16 GB RAM, 14 threads, no CUDA. Set `PYTHONUTF8=1`.
- Hugging Face loading is forced offline (`HF_HUB_OFFLINE=1` inside `models.load`).
- DuckDB 2.0: `con.execute(...).to_arrow_table()`, not `con.sql(...)`, after an open result.
- Peak memory on Windows is a *process-lifetime* peak, so use `pilot/memprobe.py` (one config per
  process).

**Data not in git** (D-012 backups still to implement before M5):
- `data/models/` (0.9 GB, re-fetch with `hebloc pilot fetch-models`);
- `data/external/bhsa/` (47 MB);
- `data/annotations/pilot/`;
- `data/units_v1/` and `data/units_sample_v1/` (superseded, deletable since M2.1 was approved).

## 6. Decisions pending at the M3 gate (do not decide them unilaterally)

From [pilot_report.md §15](pilot_report.md):
1. base or tiny;
2. keep the MST fix;
3. adopt `lex_topk`;
4. invalid word-level trees: flag and exclude, or constrained decoding;
5. the `tokens` schema;
6. normalization defaults (D-026);
7. treatment of multi-piece statistics (D-021: a/b/c);
8. R5 and `suspect_bidi` (still open from M2);
9. **Modern coverage** (D-004, §12 options);
10. who annotates the audit.

Then implement the D-012 backups, then M4.

## 7. Startup instructions for the next session

1. Read [CLAUDE.md](../CLAUDE.md), this file, [pilot_report.md](pilot_report.md),
   [decisions.md](decisions.md) D-020–D-029, and [data_dictionary.md](data_dictionary.md)
   (parse runs, tokens).
2. Check:
   ```
   git status --short; git log --oneline -3
   uv sync
   uv run pytest                 # all pass; no model is loaded by the tests
   uv run hebloc baseline        # Anchor check: OK
   ```
   Confirm that `data/models/*` verify (§5) and that the pilot `checks.json` files say `ok: true`.
3. Ask for the gate decisions (§6) if they have not been given. Record each one as a decision
   entry, and do not start M4/M5 work that depends on an undecided item.
4. Do not change `normalize.py`, `segment.py` or the vendored `dicta_code/` without an approved
   decision entry.
