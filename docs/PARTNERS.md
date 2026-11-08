# Partner Overview (Ori, Efrat, Adi)

**The exact, tested procedure is in [`PARTNER_START.md`](../PARTNER_START.md)** at the repository
root. It is written for Claude Code to execute step by step, and a human can follow it the same way.
This page explains the big picture.

## What we are doing

We parse five Hebrew corpora (9.7 million sentences) with the Dicta parser. That is too much for one
laptop, so the work is split into **slices**: parts of the corpora that never overlap. Each person
parses their own slices on their own computer and sends the results to Ori, who merges them.
- Who parses what: [`docs/WORK_PLAN.md`](WORK_PLAN.md), generated from `config/parse_plan.yaml`.
  It is balanced to within 1% between the three of us.
- Parsing starts only when Ori approves the plan. Until then, set up and verify your computer.

## Why so many checks

Results from three computers are combined into one dataset, so each computer must be provably
equivalent:

| Check | What it proves |
|---|---|
| `hebloc corpora install/verify` | Your corpora are byte-identical to the project's (sha256 of all 404,294 files vs `config/corpora_anchor.json`) |
| `uv sync` + `hebloc doctor` | Same Python and library versions as `uv.lock` |
| `hebloc models fetch` | The exact pinned Dicta model files (sha256) |
| `hebloc fingerprint` | Your rebuilt catalog and sentences have the same content as Ori's |
| `hebloc agreement` | Your computer produces byte-identical parser output on 1,161 test pieces |
| `hebloc parse` (gated) | You parse only your own slices, with the agreed settings, and every run is validated |
| `hebloc merge` | Every received file is intact, from the same corpora, valid, and part of the plan |

## What goes where

- **GitHub (private):** code, configuration, docs, small reference files. No corpora, no
  generated data, no course documents.
- **Your computer only:** `corpora/` (from the course link) and `data/` (everything generated).
- **The private shared folder:** your result bundles (`.zip` + `.zip.sha256`).
- **Ori:** your `data/team/doctor.json` and `data/team/agreement.json` after setup.

## Using Claude Code

Open the repository folder, start `claude`, and type:
`Read PARTNER_START.md and run it for me. I am <your name>.`
Slash commands are also available: `/partner-setup <name>` and `/partner-parse <name>`.

## Changing code

Work on a branch and open a pull request: never push to `main` directly. A partner's setup and
parsing session changes no tracked file.
