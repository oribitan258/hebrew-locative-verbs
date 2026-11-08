# Partner Setup Guide

This guide takes you from nothing to a working copy of the project in about one hour, mostly
waiting. You need no prior experience with these tools: copy the commands exactly. If anything
fails, stop and send Ori the full error message.

**What you will do:**
1. Install two tools.
2. Download the code.
3. Add the corpora.
4. Build the data.
5. Run the checks.
6. Later: parse your assigned part and share the result.

**What you need:**
- a laptop with 16 GB RAM and at least 15 GB free disk (30 GB if you will parse Modern);
- a GitHub account (send Ori your username to be invited);
- the corpora files (from the course link or from Ori).

---

## 1. Install the tools (once)

**Git** (downloads the code):
- Windows: install from <https://git-scm.com/download/win>; keep all default options.
- macOS: run `xcode-select --install` in Terminal.

**uv** (installs the right Python and every library automatically):
- Windows, in PowerShell:
  ```
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
- macOS / Linux:
  ```
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

Close and reopen the terminal afterwards. Check that `git --version` and `uv --version` both
print a version.

> **Windows 11 note: Smart App Control.** If you later see *"An Application Control policy has
> blocked this file"*, Windows' Smart App Control is blocking the Python that uv installs (it is
> not code-signed). It cannot be fixed inside the project. The options are turning Smart App
> Control off (Windows Security → App & browser control; check first whether it can be turned
> on again) or working inside WSL (Linux on Windows). Talk to Ori before changing it.

## 2. Download the code

Accept the GitHub invitation (it arrives by email), then:

```
git clone https://github.com/oribitan258/hebrew-locative-verbs.git
cd hebrew-locative-verbs
```

From now on, run every command **inside this folder**. On Windows, also run this once per terminal
window, because the data contains Hebrew text:

```
$env:PYTHONUTF8 = "1"        # PowerShell  (macOS/Linux: export PYTHONUTF8=1)
```

## 3. Add the corpora and course documents

The corpora are **not** in GitHub (they are large and partly copyrighted). Get them from the course
link or from Ori and place them so the folder looks exactly like this:

```
hebrew-locative-verbs/
  corpora/
    Mikra/  Hazal/  Medieval/  Haskala/  Modern/
```

**Never edit, rename or delete anything inside `corpora/`.** Everything the project produces goes
to `data/`.

The course documents (`project.pdf`, `DoronDubnov_revised.pdf`) are also not in GitHub. Put your
own copies in the main folder if you want them next to the code.

## 4. Install and build (about 15 minutes, plus downloads)

```
uv sync                            # installs Python 3.12 and all libraries (~1 GB)
uv run hebloc baseline             # checks that your corpora are identical to ours
```

`baseline` must end with **`Matches anchor`** or **`Anchor check: OK`**. If it says *REFUSING*,
your corpora differ from ours (missing, extra or changed files). Stop and tell Ori, because
nothing else is valid until this passes.

```
uv run hebloc inventory            # catalog of all 404,294 files        (~2 min)
uv run hebloc prepare              # sentences and verses → data/units/  (~5-10 min)
uv run hebloc pilot fetch-models   # the Dicta parser models, ~0.9 GB, checksum-verified
```

## 5. Run the checks

```
uv run pytest                      # should end with "passed" and no "failed" (~2 min)
uv run hebloc check                # should end with "OK=True"
```

Send Ori a screenshot or copy of the last lines of both. You are now set up.

## 6. Your parsing task (not yet: wait for Ori)

Parsing starts only after the project decisions at the M3/M5 gate (model, speed setting, how much
of Modern to parse). Ori will then assign each partner a **slice**: a part of the corpora that
nobody else parses. Slice sizes in model sub-words (they set the run time; ~534 sub-words/s with
the planned settings on a laptop like Ori's, i.e. 1 M sub-words ≈ 30 min):

| Slice | Sub-words | Approx. time |
|---|---|---|
| Mikra | 0.4 M | 12 min |
| Hazal | 8.6 M | 4.5 h |
| Medieval | 4.3 M | 2.2 h |
| Haskala | 7.4 M | 3.9 h |
| Modern, each source except Haaretz (Knesset, a7, blogs, medical, ynet, Tapuz, literature, TheMarker, nrg) | ≈ 47 M in total (Knesset and a7 ≈ 16 M each) | ≈ 24 h in total |
| Modern, Haaretz | ≈ 130 M (all) or ≈ 13 M (10% sample) | ≈ 68 h or ≈ 7 h |

These times are extrapolated from Ori's laptop benchmark; yours may differ. The historical
sub-word counts are measured; the Modern per-source counts are estimated from whitespace tokens
(× 1.08, Modern's average).

When your slice is assigned, you will get **one command** to run (added in M5). Before your real
slice, you will run a short **agreement check**, parsing the 1,000-sentence pilot sample (~10 min),
so we can confirm that your computer produces the same parser output as Ori's.

While a parse runs:
- keep the laptop **plugged in**;
- set Windows to **Best performance** (Settings → System → Power);
- disable sleep.

If it stops for any reason, run the same command again. It resumes where it stopped and never redoes
finished work.

## 7. Share your results (never through GitHub)

When your slice is finished and `uv run hebloc check` says `OK=True`:

```
uv run hebloc bundle create <your-run>     # e.g. modern/base_v1_knesset
```

This writes two files to `data/bundles/`: a `.zip` and a `.zip.sha256`. Upload **both** to the
project's private shared folder (link from Ori). Ori then runs `hebloc bundle verify` and
`hebloc bundle restore`, which re-check every file against its checksum and against our corpora.

## 8. Rules

- **Never** edit `corpora/`. **Never** commit or upload `corpora/` or `data/` to GitHub. Git already
  ignores them, and a test (`tests/test_repo_hygiene.py`) fails if they are ever tracked.
- Corpus text and parser outputs are for the course team and lecturer only. Do not post them
  anywhere public.
- Code changes: make a branch, push it, and open a Pull Request. Do not push to `main` directly:
  ```
  git switch -c my-change
  git add <files> ; git commit -m "what and why"
  git push -u origin my-change
  ```
- Getting updates from the others: `git pull` (then `uv sync` if `uv.lock` changed).

## 9. Where to read more

- [README.md](../README.md): overview. [CLAUDE.md](../CLAUDE.md): project rules and status.
- [docs/HANDOFF.md](HANDOFF.md): current state and pending decisions.
- [docs/data_layer.md](data_layer.md): how to read the data in Python.
- [docs/pilot_report.md](pilot_report.md): what we learned about the Dicta parser.
