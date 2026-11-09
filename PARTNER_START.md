# PARTNER_START: the single entry point for Claude Code on a team member's computer

**This file is an instruction script for Claude Code.** The person only cloned the repository,
opened Claude Code and asked you to follow this file. Execute it top to bottom. It:

1. finds out who the person is (Ori, Efrat or Adi);
2. sets up the environment, the corpora (from the course archive the person downloaded), the
   Dicta model and the derived data;
3. proves this computer produces exactly the same data and parser output as everyone else's;
4. runs a short **rehearsal** of the person's own workload and packages it (allowed now);
5. **only after Ori approves the plan**, runs the person's full workload and packages the results
   for Ori to merge.

Every command here was run end to end on Windows 11 (decisions D-037, D-038). *Italic timings* come
from those tests on Ori's laptop. Steps marked **(untested)** were not run on that platform.

---

## 0. For the person, before starting Claude Code (one time, ~10 min)

1. Accept the GitHub invitation to `oribitan258/hebrew-locative-verbs` (it arrives by email).
2. Download the **corpus archive from the course website** (the same archive Ori used). Leave it in
   your Downloads folder, or anywhere outside the project, and do not rename the files inside it.
   If the download comes in several parts (e.g. `…-001.zip`, `…-002.zip`), keep all parts in one folder.
3. Open PowerShell (Windows) or Terminal (macOS) and run:
   ```
   cd $HOME
   git clone https://github.com/oribitan258/hebrew-locative-verbs.git
   cd hebrew-locative-verbs
   claude
   ```
   Clone into your home folder as above, **not** into a OneDrive, Dropbox or Google Drive synced
   folder (the project grows to ~10 GB of working files), and not into a deeply nested folder.
4. In Claude Code, type: **`Read PARTNER_START.md and follow it.`**

---

## 1. Rules for Claude Code (they override everything below)

**Hard rules.**
- Work only inside this repository folder. Never edit, move or delete anything in `corpora/` or in
  the person's download.
- Never `git commit` or `git push`. A team member's session changes no tracked file; `git status`
  must stay clean. Never change `config/`, `tests/`, `src/` or this file.
- Never work around a failed check: no skipping verification, editing tests, `--force`,
  `--overwrite`, `--change`, another person's `--as`, or deleting `data/` to "start over".
- Run commands one at a time, from the repository root, and read their output before continuing.
  Every step says what success looks like and what to do otherwise.
- Talk to the person in plain, beginner-friendly English. Before a long step, say how long it takes.

**STOP conditions.** Stop, show the person the exact output, and tell them to send it, together with
`data/team/doctor.json` (if it exists), to Ori when:
- **S1**: the person is not Ori, Efrat or Adi.
- **S2**: a step's success check still fails after its recovery steps.
- **S3**: `corpora install` / `corpora verify` reports DIFFERENT or INSTALL FAILED twice for the
  right download (it is not the project's corpora).
- **S4**: `fingerprint` reports DIFFERENT, or `agreement` reports AGREEMENT NOT OK.
- **S5**: any `hebloc` command prints `REFUSED`, except the expected refusal in §11 step 1.
- **S6**: `hebloc work` prints `FAILED`.
- **S7**: continuing would break a hard rule.

**Shell.**
- Windows: run commands in **PowerShell**. In every new PowerShell window, first run
  `$env:PYTHONUTF8 = "1"`.
- macOS/Linux **(untested)**: use bash, and run `export PYTHONUTF8=1` first.

**Resuming.** This guide can be stopped and restarted at any point, by a new Claude Code session too.
Every section starts with **Skip if**: check it and skip the section when it is already done. Long
commands (`corpora install`, `models fetch`, `agreement`, `work`) can be re-run safely after an
interruption: they resume or start cleanly, and never duplicate finished work.

---

## 2. Who are you? (always first)

1. If the file `data/team/identity.json` exists, read it. It names the person this computer was set
   up for. Tell the person: "This computer is set up for NAME. I'll continue for NAME." Then go to §3.
2. Otherwise ask exactly: **"Who are you — Ori, Efrat, or Adi?"**
   - Accept the name in any capitalization. Use it in lower case as `NAME` (`ori`, `efrat` or `adi`).
   - Anything else → ask once more. Still none of the three → STOP S1.
3. Say: "I will set up this computer for NAME and run only NAME's part of the work." The name is
   saved in §5 (it needs the environment first).

Each person's slices are fixed in advance in `docs/WORK_PLAN.md` and never overlap. You never choose
slices yourself: `hebloc work` takes exactly NAME's slices from the plan.

## 3. Prerequisites (*~1–5 min*)

**Skip if** all three checks below already print a version.

| Tool | Check | Expected | Install if missing |
|---|---|---|---|
| Git | `git --version` | a version | Windows: `winget install --id Git.Git -e --scope user`; macOS: `xcode-select --install` |
| uv | `uv --version` | `uv 0.12` or newer | Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"`; macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh \| sh`. Then open a NEW terminal |
| Python 3.12 (python.org) | Windows: `py -3.12 --version` | `Python 3.12.x` | Windows: `winget install --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements` (*tested; ~1 min, no admin*). macOS **(untested)**: the 3.12 installer from python.org. Linux **(untested)**: the `python3.12` package |

After installing anything, the person must open a NEW PowerShell window (and `cd` back to the
project, run `$env:PYTHONUTF8 = "1"`). Claude Code may need to be restarted in that window. This
file then resumes at §2.

Why python.org Python on Windows: Windows 11 **Smart App Control** blocks the unsigned Python that
uv downloads ("An Application Control policy has blocked this file"); python.org's is signed (D-035).

## 4. Create the environment (*~1 min with a warm cache; a few minutes on first download*)

**Skip if** `uv run python -c "import sys, torch; print(sys.version.split()[0], torch.__version__)"`
already prints `3.12.x 2.15.0+cpu`.

Windows:
```
$env:PYTHONUTF8 = "1"
uv venv --clear --python (py -3.12 -c "import sys; print(sys.executable)")
uv sync
uv run python -c "import sys, torch; print(sys.version.split()[0], torch.__version__)"
```
macOS/Linux **(untested)**:
```
export PYTHONUTF8=1
uv venv --clear --python 3.12
uv sync
uv run python -c "import sys, torch; print(sys.version.split()[0], torch.__version__)"
```
**Success:** prints `3.12.x 2.15.0+cpu` (or `2.15.0` on macOS).
**Recovery:** "Application Control policy has blocked this file" → the environment was made with
uv's own Python: check §3 (`py -3.12 --version`) and repeat this section (`--clear` only replaces
installed packages, no data).

## 5. Save who this computer belongs to

**Skip if** `uv run hebloc whoami` prints `This computer is set up for: NAME`.
```
uv run hebloc whoami --set NAME
```
**Success:** `This computer is set up for: Name  (data/team/identity.json)`.
From now on every team command uses this name automatically and refuses to act for anyone else.
**Recovery:** `REFUSED: this computer is already set up for OTHER` → do not change it. Ask the person
whether this is really their computer. If it was set wrongly by mistake, STOP S5 (Ori decides).

## 6. Install the corpora from the course archive (*tested at full size: ~25–35 min*)

**Skip if** `uv run hebloc doctor --quick` shows `[PASS] corpora  corpora = anchor`.

1. Ask the person: **"Where is the corpus archive you downloaded from the course? Please give me the
   full path of the file — or of the folder that holds it, if it came in several parts."**
   Help if needed: in File Explorer, hold Shift, right-click the file → **Copy as path**, and paste it.
   (macOS: right-click → hold Option → **Copy … as Pathname**.) If the person already extracted it,
   the extracted folder works too, but the original archive file is preferred.
2. Check that the path exists (`Test-Path "<PATH>"` must print `True`). If not, ask again.
3. Run (keep the quotes; for a multi-part download give the folder, or repeat `--from` per part):
   ```
   uv run hebloc corpora install --from "<PATH>"
   ```
   It reads the download (never changes it); finds the corpus folders inside it at any depth,
   including archives inside the archive; checks every file NAME against the project's reference and
   automatically repairs Hebrew file names that zip tools garbled; extracts into a staging folder;
   hashes all 404,294 files; and only if every file is identical creates `corpora/`.
   Supported: `.zip` (also multi-part), `.7z`, `.rar`, `.tar`, `.tar.gz`/`.tgz`, or a folder.

**Success:** the last line is
`404,294 files, 1,126,869,300 bytes: IDENTICAL to the project's corpora (anchor OK)`.
The line before it says where the corpora were found and which file-name decoding was used (any
value is fine).

**Recovery:**
- `already exists and is not empty` → the corpora were installed before: run
  `uv run hebloc corpora verify` (same success line).
- `INSTALL FAILED … could not find a folder containing Mikra, Hazal, …` → wrong file, or an
  incomplete download (a missing part). Ask for the right path; re-download if needed.
- `INSTALL FAILED … the file names in the download are not the project's corpora` or `… sizes
  differ` → a different or modified download. Ask the person to download the archive again from the
  course, then retry once. Still failing → STOP S3.
- `INSTALL FAILED … path is too long for Windows` → the project folder is too deep. Have the person
  move it: close Claude Code, then in PowerShell `cd $HOME` and clone again as in §0 (a fresh clone
  into the home folder), and restart from §2.
- `not enough free disk space` → free space (setup needs ~10 GB) and retry.
- `DIFFERENT from the project's corpora` → nothing was installed. Re-download from the course and
  retry once; still different → STOP S3.
- Interrupted (sleep, Ctrl+C, crash) → run the same command again: it starts over cleanly
  (nothing half-installed is ever kept).

## 7. Download and verify the parser model (*tested: ~30 s on a fast connection, 0.7 GB*)

**Skip if** `uv run hebloc models verify` prints `base: … OK`.
```
uv run hebloc models fetch
```
**Success:** `base: dicta-il/dictabert-joint@7b1256fc0846 OK (all files match the pinned sha256)`.
**Recovery:** network error → run the same command again (it resumes). A sha256 problem → delete the
folder `data/models/dictabert-joint` and run it again. Still failing → STOP S2.

## 8. Build the derived data (*tested: inventory ~1.5 min, prepare ~3–5 min, fingerprint ~10 s*)

**Skip if** `uv run hebloc fingerprint` already ends with `IDENTICAL to the reference`.
```
uv run hebloc inventory
uv run hebloc prepare
uv run hebloc fingerprint
```
**Success:** `inventory` prints `Catalog: 404,294 documents -> …` with every verification flag `True`;
`prepare` prints one line per corpus ending in `ok=True`; `fingerprint` ends with
**`IDENTICAL to the reference`** (all 9,709,662 sentences are the same as on Ori's computer).
**Recovery:** `inventory` refuses (anchor) → back to §6 (`corpora verify`). Fingerprint DIFFERENT →
`uv sync`, repeat this section once; still different → STOP S4.

## 9. Check the whole setup (*tested: tests ~1 min*)

```
uv run pytest
uv run hebloc doctor
```
**Success:** `pytest` ends with `passed` and no `failed` (a few `skipped` are expected on a fresh
computer: tests that need Ori's pilot data). `doctor` ends with `ready_for_setup=True`. On its other
lines, `TODO` items are done in the next sections or wait for Ori; each `FAIL`/`TODO` prints its fix
(`->`). A `WARN` about git ("modified files") means a tracked file changed: run `git status`, tell the
person, do not commit. A `WARN` about power: tell the person to plug in before §10 and §11.

## 10. Prove this computer agrees with everyone else, then rehearse (*tested: ~3 min + ~2 min*)

**Skip if** `data/team/agreement.json` exists with `"ok": true` **and** a folder
`data/outbox/NAME-rehearsal40A` (or `…40B`) exists containing `DELIVERY.json` with `"complete": true`.

1. Cross-machine agreement:
   ```
   uv run hebloc agreement
   ```
   It parses the 1,000-sentence pilot sample with the plan's exact settings and compares every
   piece's raw parser output with the reference made on Ori's computer.
   **Success:** `AGREEMENT OK: this machine reproduces the reference output exactly`
   (`pieces_identical` = `pieces_compared` = 1161). It also prints this computer's
   `subwords_per_second`. Interrupted → run it again (it resumes). NOT OK → STOP S4.
2. Rehearsal of NAME's own workload (the first 40 sentences of each of NAME's slices; the whole
   chain: parse → validate → package):
   ```
   uv run hebloc work --rehearsal 40
   ```
   **Success:** ends with `WORK COMPLETE: … slice(s) …` and names the folder
   `data/outbox/NAME-rehearsal40A` (or `…40B` if Ori has already chosen option B).

**Setup is complete.** Tell the person to send Ori, through the team's private shared folder (§12):
the folder `data/outbox/NAME-rehearsal40A` (whole folder), plus the two small files
`data/team/doctor.json` and `data/team/agreement.json`. Ori merges the three rehearsals to prove the
whole chain before approving the full runs. None of these contain corpus text beyond the 40
rehearsal sentences per slice.

Then go to §11 step 1. If the plan is not approved yet, stop there: that is the normal end of the
first session.

---

## 11. The full run (ONLY after Ori has approved the plan)

1. Get Ori's latest plan and check readiness:
   ```
   git pull
   uv sync
   uv run hebloc doctor
   ```
   Look at the `plan approved` line. If it is `TODO` (status=draft), tell the person: **"Ori has not
   started the parsing phase yet. Nothing more to do now; when Ori says so, open Claude Code here
   again and ask me to follow PARTNER_START.md."** Stop. This is expected, not an error.
   Continue only when `plan approved` is `PASS` and the last line says `ready_to_parse=True`.
   If something else is `TODO`/`FAIL` (e.g. the agreement must be re-run after a settings change),
   run its `->` fix first.
2. Prepare the computer. Tell the person: the run takes many hours (see `your slices` in the doctor
   output and `docs/WORK_PLAN.md`); keep the laptop **plugged in and the lid open**; Windows: Settings
   → System → Power → **Power mode: Best performance**. The command itself keeps the computer
   from sleeping while it runs; screen-off is fine. Closing the lid may still sleep it. Other heavy
   programs slow it down.
3. Run NAME's whole workload:
   ```
   uv run hebloc work
   ```
   It checks the setup again, then parses each of NAME's slices in turn, validates it against this
   computer's data, and packages it (a verified `.zip` + `.zip.sha256`) into `data/outbox/NAME/`,
   updating `DELIVERY.json` after every slice. Progress bars show each slice.
   **Success:** `WORK COMPLETE: N slice(s), … units, … MiB packaged.` and the folder `data/outbox/NAME`.
   **If it stops for any reason** (sleep, crash, reboot, Ctrl+C, power cut): open PowerShell in the
   project, `$env:PYTHONUTF8 = "1"`, and run `uv run hebloc work` again. It skips packaged slices,
   resumes the current one at its first unfinished shard (≤ 500 sentences are redone), and never
   duplicates work. Never delete anything in `data/annotations/` or `data/outbox/`.
   **FAILED** → STOP S6. **REFUSED** → STOP S5.

## 12. Send the results to Ori

Send the **whole folder** `data/outbox/NAME` (for the rehearsal: `data/outbox/NAME-rehearsal40A`)
unchanged, either:
- into the team's private shared folder (Google Drive / OneDrive / Dropbox) that Ori shares with
  you: upload the folder itself, and wait until the upload has finished; or
- on a USB drive.

Never put it on GitHub. `HOW_TO_SEND.txt` inside the folder repeats this. Keep your copy until Ori
confirms that the merge reported `MERGE OK`. A partial delivery (some slices done) can be sent early;
send the folder again when `hebloc work` has finished: Ori's merge skips what it already has.

## 13. Merging everything (Ori's computer only)

Copy every received folder somewhere outside the project, e.g. `C:\hebloc-incoming\efrat`, then:
```
uv run hebloc merge "C:\hebloc-incoming"
```
(or name the folders/zips one by one). For every bundle it checks the zip against its `.sha256` file
and the `DELIVERY.json` that lists it (a missing or damaged upload fails); re-hashes every file inside;
checks the corpora anchor and the parse settings; restores it into `data/annotations/`; checks the
run's integrity; checks that the run holds **exactly** its slice's sentences on Ori's computer (same
ids, same text, no repeats, none missing); and checks that the slice's assigned owner made it.
Identical copies of the same bundle are merged once; two DIFFERENT bundles of the same slice are a
CONFLICT and neither is merged. Merging the same folder again is safe.

It ends with the completeness report per coverage:
`full coverage A: 31/31 slices OK; units 9,709,662/9,709,662; units in more than one run: 0; COMPLETE`,
followed by the slices still missing, per person. **Success:** `MERGE OK` and `COMPLETE`.
`uv run hebloc merge` with no paths prints just the completeness report.

When the full coverage is COMPLETE: `uv run hebloc plan register` (preview), then
`uv run hebloc plan register --write` (refuses unless COMPLETE), add a decision entry, run
`uv run hebloc check`, and commit `config/annotations.yaml`. Rehearsal and smoke runs are never
registered.

---

## 14. Quick recovery reference

| Symptom | Action |
|---|---|
| "An Application Control policy has blocked this file" | §3 (python.org 3.12), then §4 |
| `UnicodeEncodeError` / garbled Hebrew in the terminal | `$env:PYTHONUTF8 = "1"` in this window, repeat the command |
| `uv` / `py` / `claude` "not recognized" | Open a NEW terminal after installing (PATH refresh) |
| `REFUSED: who are you?` | §5 |
| `REFUSED: this computer is set up for X, not Y` | You are on X's computer or used the wrong name: STOP S5 |
| Any long command was interrupted | Run the same command again (see §1 Resuming) |
| `hebloc work` REFUSED `full runs are not enabled` | Expected until Ori approves: §11 step 1 |
| `hebloc work` REFUSED `not ready:` + a list | Run each listed `->` fix, then `hebloc work` again |
| Disk full | Setup needs ~10 GB; the full run adds up to ~10 GB (results + packages). Free space, then re-run the command |
| Anything else | STOP S2: send Ori the output and `data/team/doctor.json` |
