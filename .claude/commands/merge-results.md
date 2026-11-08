---
description: (Ori) Verify, restore and integrate the partners' parse bundles
argument-hint: <path(s) to downloaded bundle .zip files>
---

You are helping Ori integrate parse results from the team. Follow `PARTNER_START.md` §12 (merging).

1. For every bundle in `$ARGUMENTS`, check that its `.zip.sha256` sidecar matches the zip
   (`sha256sum` / `Get-FileHash`), then run `uv run hebloc merge <zips...>`. Every line must start
   with OK. A FAIL means: do not register that run; report the problem to its owner (the line names
   the person and slice).
2. `uv run hebloc plan status` and `uv run hebloc check`. Report progress (slices complete/valid).
3. Only when the user explicitly says so: `uv run hebloc plan register` (preview), then
   `uv run hebloc plan register --write`, add a decision entry to `docs/decisions.md` naming the
   registered runs, run `uv run hebloc check` (must be OK=True), and commit `config/annotations.yaml`
   + `docs/decisions.md`.
4. Remind Ori to keep the bundles in the backup targets (D-012).

Never edit partners' run files, never force a merge with `--overwrite` unless Ori explicitly asks.
