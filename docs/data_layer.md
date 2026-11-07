# The Data Layer (M4): How to Use It

This is the practical guide to reading the project's data. Table schemas are in
[data_dictionary.md](data_dictionary.md); backups and sharing are in
[data_management.md](data_management.md); the design decisions are D-030 to D-033 in
[decisions.md](decisions.md).

## 1. What is where

```
corpora/                         original files, read-only, pinned by config/corpora_anchor.json
data/catalog/documents.parquet   one row per file (M1)
data/units/<corpus>/             one row per complete sentence or verse (M2)
data/annotations/<collection>/runs/<run_id>/
                                 one parse run: inputs, pieces, dicta_raw (verbatim), tokens, manifests
config/annotations.yaml          which run is the canonical analysis of each corpus (empty until M5)
data/hebloc.duckdb               SQL views over all of the above (no copies; rebuild with hebloc catalog)
```

`<collection>` is `pilot` for the M3 pilot runs and the corpus id for M5 runs. A run is named
`"<collection>/<run_id>"`, e.g. `"pilot/base__default"`.

**Canonical vs explicit runs.** Several runs can analyse the same unit (base, tiny, normalization
variants…). To keep statistics from silently mixing them:
- `run=None` (the default) means the canonical run(s) registered for the corpus in
  `config/annotations.yaml`, restricted to that corpus, so there is at most one analysis per unit;
- with nothing registered, the API raises an error. It never picks a run on its own;
- `run="pilot/base__default"` reads one run explicitly.

## 2. Python

```python
from hebloc import data

data.runs()                                    # every parse run: model, variant, completeness, canonical role
data.units("mikra", columns=["sent_id", "ref", "text_norm"])
t = data.tokens("mikra", run="pilot/base__default",
                columns=["sent_id", "sent_word_idx", "surface", "lemma", "upos", "deprel"])
v = data.tokens(run="pilot/base__default", view="curated", where="upos = 'VERB'")
for batch in data.iter_tokens("modern", batch_size=100_000): ...   # Arrow batches, bounded memory
data.pieces("haskala", run="pilot/base__default", where="n_pieces > 1")

s = data.sentence(sid, run="pilot/base__default")   # unit + pieces + tokens + complete_tree flag
data.raw(sid, run="pilot/base__default")            # Dicta's verbatim JSON per piece
print(data.conllu(sid, run="pilot/base__default"))  # CoNLL-U with provenance comments
data.trace(sid)                                     # unit → file, line, offsets; re-read and verified
data.trace_token(sid, 3, run="pilot/base__default") # word → unit → source, every step verified
data.coverage()                                     # per corpus × stratum: parsed, multi-piece, errors, invalid trees

con = data.connect()                                # in-memory DuckDB with all views
con.sql("SELECT corpus_id, upos, count(*) FROM tokens_all WHERE run = 'pilot/base__default' GROUP BY ALL")
```

Annotation results carry `run`, `corpus_id` and `doc_id`. The `view` argument ("full" or
"curated") filters through `documents`, as for units (D-015).

**Never silently applied** (D-021, D-025). These are columns for statistics code to filter on and
report:
- `n_pieces > 1`: the unit was parsed in several pieces and has no single tree;
- `piece_tree_valid = false`: the piece's word-level tree is not a tree;
- `status = 'error'` pieces have no tokens, and later pieces of that unit have a null `sent_word_idx`.

`coverage()` / the `parse_coverage` view gives the counts that every statistic must report.

## 3. Commands

| Command | What it does |
|---|---|
| `uv run hebloc runs` | List runs: model, variant, units, shards, completeness, tokens status, canonical role |
| `uv run hebloc tokens <run>\|all [--force]` | Derive `tokens` from `dicta_raw`, only for shards whose sources changed. Migrates an M3 single-file `tokens.parquet` after checking it is identical |
| `uv run hebloc catalog` | Write `data/hebloc.duckdb` (views and the small `runs` table, about 0.5 MB). Usable from any DuckDB client |
| `uv run hebloc check [--deep] [--run R] [--skip-units]` | Read-only integrity of documents, units, runs and the canonical registry → `data/catalog/integrity.json`. About 5 s quick; `--deep` re-validates every run (pilot: about 25 s) |
| `uv run hebloc export-conllu <run> [--corpus C] [--style ud\|iahlt_ud] [--valid-only]` | CoNLL-U files in `data/exports/conllu/` |
| `uv run hebloc bundle create <run>\|pilot\|all` | Verified backup zip(s) in `data/bundles/` (D-012) |
| `uv run hebloc bundle verify <zip>` / `restore <zip> [--overwrite]` | Re-hash every member and check the anchor / unpack safely and re-validate |
| `uv run hebloc pilot revalidate` | Re-validate the pilot runs against their expected inputs (stores fingerprinted `checks.json`) |

## 4. Guarantees, and how they are checked

| Guarantee | Mechanism | Checked by |
|---|---|---|
| No half-written file is ever read | Temp file + atomic rename for every write; readers use committed shards only | `check`: orphan/missing shard files |
| Tokens are a pure function of the raw output | Per-shard derivation; manifests of source hashes | `check`: tokens up to date (sha256); `validate_run`: stored = fresh re-derivation |
| Every annotation traces to the source | `sent_id` → unit → `rel_path` + line + offsets (+ file sha256); token offsets in the parsed text | `trace` / `trace_token` re-read and compare; `check`: parsed text = `units.text_norm` |
| At most one default analysis per unit | Canonical registry, restricted per corpus | `check`: no unit in two canonical runs |
| Schemas do not drift | `hebloc.store.schemas` registry | `check`: every Parquet file's schema |
| Backups restore exactly | Bundle manifest with per-file sha256 and the anchor | `bundle verify` / `restore` |

## 5. Contract for M5 (full parse)

M5 adds no new storage code. It must:
1. Write each corpus run to `hebloc.store.runs.run_dir_for(corpus, run_id)` with
   `hebloc.parse.run.run` and `variant="default"`, parsing `units.text_norm`, with the model and
   fixes decided at the M3 gate.
2. Run `validate_run(run_dir, expected=<sent_id → text_norm>)` after each session. This writes
   per-shard tokens and a fingerprinted `checks.json`.
3. Run `hebloc check --run <corpus>/<run_id>`, then register the run under its corpus in
   `config/annotations.yaml` with a decision entry. `hebloc check` must stay OK.
4. Run `hebloc bundle create <corpus>/<run_id>` and copy the zip and its `.sha256` to the two
   backup targets (D-012).
