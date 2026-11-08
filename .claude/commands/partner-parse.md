---
description: Parse your assigned slices of the corpora and package the results (partners)
argument-hint: <your name: ori | efrat | adi>
---

Read `PARTNER_START.md` at the repository root. Apply its section 1 (rules and STOP conditions),
then execute sections 10 and 11 for the team member **$ARGUMENTS** (use `--as $ARGUMENTS`). That
file is the single source of the tested commands and checks: follow it exactly. Parse only the
slices that `hebloc doctor --as $ARGUMENTS` and `docs/WORK_PLAN.md` list for $ARGUMENTS, and stop
at any `REFUSED`. If the plan is not approved yet, tell the user and stop: that is expected.

Finish with a report: each slice's result (`validation_ok`, `integrity_ok`, hours), the bundle
files created in `data/bundles/`, and the upload reminder from section 11.
