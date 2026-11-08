---
description: Parse your assigned slices of the corpora and package the results (partners)
argument-hint: <your name: ori | efrat | adi>
---

You are helping **$ARGUMENTS** run their assigned parsing work for the team project. Follow
`docs/PARTNERS.md` §7–§8. Talk to the user in plain English.

Rules (non-negotiable; see CLAUDE.md):
- Parse ONLY the slices assigned to $ARGUMENTS in `docs/WORK_PLAN.md` for the plan's coverage
  option. `hebloc parse` enforces this; never try to bypass a REFUSED message (do not edit
  `config/parse_plan.yaml`, `config/work_plan.json` or pass another person's name).
- Never edit `corpora/`; never commit `data/`; never upload results to GitHub.
- Never delete or "clean up" anything under `data/annotations/`: an interrupted run resumes from it.

Procedure:
1. `git pull`, then `uv sync`, then `uv run hebloc doctor --as $ARGUMENTS`. Continue only if
   `ready_to_parse=True`. If it says the plan is not approved, stop: Ori has not given the go-ahead.
2. Read `docs/WORK_PLAN.md` and list $ARGUMENTS's slices with their estimated hours. Remind the user:
   laptop plugged in, power mode "Best performance", sleep disabled.
3. For each slice, run `uv run hebloc parse --slice <slice> --as $ARGUMENTS`. Long slices take hours;
   if a run stops (sleep, crash, reboot), run the SAME command again: it resumes.
4. After each slice, check the JSON printed at the end: `validation_ok` and `integrity_ok` must be
   true. Then run the printed `next` command (`uv run hebloc bundle create ...`).
5. Tell the user to upload each `data/bundles/*.zip` AND its `.zip.sha256` to the team's private
   shared folder, and to tell Ori which slices are done.
