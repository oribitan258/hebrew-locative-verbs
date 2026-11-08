---
description: Set up this machine for the Hebrew locative-verbs project and verify it (partners)
argument-hint: <your name: ori | efrat | adi>
---

You are helping **$ARGUMENTS**, a member of a three-person course team (Ori, Efrat, Adi), set up
this repository on their computer. Follow `docs/PARTNERS.md` sections 1–6 exactly, in order. Talk to
the user in plain, beginner-friendly English.

Rules (non-negotiable; see CLAUDE.md):
- Never edit, move or delete anything in `corpora/`. Never commit `corpora/`, `data/` or any
  downloaded/generated file. Never change `config/parse_plan.yaml`, `config/annotations.yaml`,
  `config/corpora_anchor.json` or anything under `config/reference/`.
- Do not start parsing a real slice. Setup only. (The agreement check in step 6 is allowed.)
- Never work around a failed check (e.g. by skipping a verification, editing a test, or forcing a
  command). If a step fails, stop, show the full error, and explain the fix from `docs/PARTNERS.md`
  §9 (Troubleshooting). If it is not covered there, ask the user to send the error to Ori.

Procedure:
1. Check the prerequisites (Git, Python 3.12 from python.org, uv) and run `uv sync`, then
   `uv run python -c "print('ok')"`. If Windows reports "An Application Control policy has blocked
   this file", follow PARTNERS.md §1 (python.org Python 3.12) and retry.
2. Ask the user where the downloaded corpora are (a folder or a .zip). Run
   `uv run hebloc corpora install --from "<path>"`. It must end with "IDENTICAL to the project's corpora".
3. `uv run hebloc models fetch` (must print OK).
4. `uv run hebloc inventory`, then `uv run hebloc prepare`.
5. `uv run hebloc fingerprint` (must print IDENTICAL), `uv run pytest` (must end with "passed" and no
   "failed"), and `uv run hebloc doctor --as $ARGUMENTS`.
6. `uv run hebloc agreement --as $ARGUMENTS` (several minutes). It must print "AGREEMENT OK".
7. Report to the user: each step's result, the doctor summary line, the agreement line, and remind
   them to send `data/team/doctor.json` and `data/team/agreement.json` to Ori (small JSON files; no
   corpus text).

On Windows, set `$env:PYTHONUTF8 = "1"` in the shell before running the commands.
