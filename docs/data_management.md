# Data Management: Backup and Sharing Strategy

Status: **documented strategy only** (decision D-012). Nothing here is implemented yet. It will be
implemented once the first expensive artifacts exist, which is after the M3 pilot and before the M5
full parse.

## 1. Why this is needed

`data/` is correctly kept out of git: it is large, binary and regenerable. But regenerable is not
the same as cheap. Re-running Dicta over the corpora is expected to take many CPU hours (to be
measured in M3). Losing those outputs, or being unable to hand them to project partners, would
cost days.

## 2. Artifact tiers

| Tier | Artifacts | Cost to regenerate | Backup? | Share with partners? |
|---|---|---|---|---|
| **T0 Source** | `corpora/` (original files) | Irreplaceable locally (originally downloaded via the course link) | Yes, once, as an untouched archive | Partners obtain the same corpora; identity is verified with `config/corpora_anchor.json` |
| **T1 Expensive** | `data/annotations/**` (`dicta_raw`, `tokens`, run manifests) | **Hours to days of CPU** | **Yes, after every completed corpus run** | **Yes. This is the main item partners need** |
| **T2 Cheap** | `data/catalog`, `data/units`, `data/stats`, `data/hebloc.duckdb` | Minutes, deterministic from T0 + code | Optional; included in bundles for convenience | Yes, in the bundle |
| **T3 External** | `data/external/**` (versification table, BHSA) | Re-download | No; record source URL and version instead | Via the same source URL and version |
| **Code & docs** | git repository | — | Git remote (private) | Git remote |

## 3. Backup plan (to implement before M5)

1. **Unit of backup:** one *bundle* per corpus per parse run, e.g. `hebloc-annotations-mikra-<run_id>.zip`. A bundle contains the Parquet shards (already zstd-compressed, so zip uses "store", no recompression), the run manifests and a `BUNDLE_MANIFEST.json` with:
   - the sha256 of every file in the bundle,
   - the `corpora_anchor` `manifest_sha256` the run was based on,
   - the git commit of the code,
   - the Dicta model name and pinned HF revision,
   - `norm_version`,
   - row counts per table.
2. **Targets (two copies, one off-site):**
   - an external drive or USB disk (fast restore);
   - a private cloud folder, e.g. BGU-provided OneDrive or Google Drive (off-site, shareable with partners).
3. **Schedule:**
   - after each corpus finishes parsing in M5;
   - after any schema change that re-derives `tokens`;
   - a final snapshot at submission.
4. **Verification:** a restore is valid only if every file's sha256 matches `BUNDLE_MANIFEST.json`, *and* the anchor digest in the manifest equals the git-tracked `config/corpora_anchor.json`. A future `hebloc bundle verify` command would automate this.
5. **Size expectation:** to be filled in from M3 measurements. Current rough estimate for the historical corpora: about 1–2 GB for T1 together with T2. Modern depends on the coverage decision (D-004).

## 4. Sharing with project partners

- **What partners receive:**
  - the git repository (code, docs, config, anchor);
  - the T1/T2 bundles from the shared cloud folder;
  - their own copy of `corpora/`, verified with `uv run hebloc baseline`. That command recomputes their checksums and refuses to proceed if they do not match the anchor, so everyone is provably working on identical sources.
- **Restore procedure (to document as commands later):**
  1. Clone the repo.
  2. `uv sync`.
  3. Place the corpora.
  4. `uv run hebloc baseline`, which must report an anchor match.
  5. Unpack the bundles into `data/`.
  6. Verify the bundles.
  7. `uv run hebloc catalog` to rebuild the DuckDB views.
- **No re-running Dicta** is needed by partners. All statistics and future research read the stored annotations through `hebloc.data`.

## 5. Licensing and privacy caveat

Derived artifacts embed the corpus text (`text_raw`, `text_norm` and token forms). Some sources are
copyrighted, especially the Modern sub-corpora (news sites, forums, blogs, published literature).
Therefore:
- bundles are shared **privately within the course team and with the lecturer only**;
- nothing derived is published publicly (no public GitHub, Hugging Face or Zenodo upload) without first checking each source's license;
- for public release, only aggregate statistics would be safe by default.

## 6. Options considered and not adopted (for now)

| Option | Why not now |
|---|---|
| Git LFS | Hosting quotas, and poor fit for GB-scale regenerable binaries |
| DVC | Adds tooling overhead; the bundle and manifest scheme gives the same verifiability with less to learn. We can reconsider if the team grows or artifacts change often |
| Private Hugging Face dataset repo | Possible later; the license caveat in §5 applies |
