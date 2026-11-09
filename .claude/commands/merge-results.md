---
description: (Ori) Verify, restore and integrate the team's result folders
argument-hint: <folder(s) holding the received outbox folders, or bundle .zip files>
---

You are helping Ori integrate results from the team. Follow `PARTNER_START.md` §12 exactly.

1. Run `uv run python -m hebloc merge $ARGUMENTS` (folders are searched for every bundle and `DELIVERY.json`).
   Every bundle line must start with `OK` and the run must end with `MERGE OK`. A `FAIL` or
   `CONFLICT` means: do not register; report the problem to the person it names (the line names the
   slice and person). `MISSING` means an upload is incomplete: ask that person to upload again.
2. Report the completeness lines (slices OK, units present/expected, units in more than one run,
   and the missing slices per person). Then run `uv run python -m hebloc check`.
3. Only when Ori explicitly says so and the full coverage is `COMPLETE`:
   `uv run python -m hebloc plan register` (preview), then `uv run python -m hebloc plan register --write`, add a decision
   entry to `docs/decisions.md` naming the registered runs, run `uv run python -m hebloc check` (must be OK),
   and commit `config/annotations.yaml` + `docs/decisions.md`.
4. Remind Ori to keep the received folders as backups (D-012).

Never edit the team's run files; never use `--overwrite` unless Ori explicitly asks.
