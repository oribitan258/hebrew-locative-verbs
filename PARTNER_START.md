# PARTNER_START: the single entry point for Claude Code on a team member's computer

**This file is an instruction script for Claude Code.** The person cloned the repository, opened it
in VS Code with Claude Code, and asked you to follow this file. Execute it top to bottom. It:

1. finds out who the person is (Ori, Efrat or Adi);
2. installs and verifies everything: Python environment, corpora (from the course archive the person
   downloaded), the pinned Dicta model, the derived data;
3. proves this computer produces exactly the same parser output as Ori's (agreement check);
4. **only after Ori approves the plan**, runs the person's assigned slices in a separate window that
   survives closing VS Code. It reports progress, resumes after any interruption, and packages
   checksum-verified results;
5. ends with a clear message: what was produced and exactly what to send Ori.

Each person's slices are fixed in advance in `docs/WORK_PLAN.md`. They are equal in size, never
overlap, and together cover every sentence once. You never choose slices: the commands take exactly
the person's slices from the plan.

Every command here was run end to end on Windows 11 (decisions D-037–D-039). *Italic timings* come
from Ori's laptop. Steps marked **(untested)** were not run on that platform.

---

## 0. For the person, before starting (one time, ~15 min)

1. Accept the GitHub invitation to `oribitan258/hebrew-locative-verbs` (it arrives by email).
2. Install, if missing:
   - **Git for Windows** (https://git-scm.com/download/win; Claude Code on Windows needs it);
   - **VS Code** (https://code.visualstudio.com) with the **Claude Code** extension (Extensions → search
     "Claude Code");
   - and sign in to your own Claude account in it.
3. Download the **corpus archive from the course website** (the same archive Ori used). Leave it in
   Downloads (or anywhere outside the project). Don't rename the files inside. If it comes in several
   parts, keep all parts in one folder.
4. Open PowerShell and clone the project into your home folder. Not into OneDrive, Dropbox or Google
   Drive: it grows to ~10–15 GB of working files.
   ```
   cd $HOME
   git clone https://github.com/oribitan258/hebrew-locative-verbs.git
   ```
5. In VS Code: **File → Open Folder… →** `hebrew-locative-verbs` (in your home folder). Open the
   Claude Code panel and type: **`Read PARTNER_START.md and follow it.`** Claude Code asks before
   running commands: approve them. A few take several minutes.

---

## 1. Rules for Claude Code (they override everything below)

**Hard rules.**
- Work only inside this repository folder. Never edit, move or delete anything in `corpora/` or in
  the person's download.
- Never `git commit` or `git push`. A team member's session changes no tracked file, so
  `git status` stays clean. Never change `config/`, `tests/`, `src/` or this file.
- Never work around a failed check:
  - no skipping verification, editing tests, `--force`, `--overwrite`, `--change` or `--threads`;
  - no other person's `--as`;
  - no deleting `data/` to "start over".
- Run commands from the repository root, one at a time, and read the output before continuing.
  Every step says what success looks like and what to do otherwise.
- Talk to the person in plain, beginner-friendly English. Before a long step, say how long it takes.

**STOP conditions.** Stop, show the person the exact output, and tell them to send it, together with
`data/team/doctor.json` (if it exists), to Ori when:
- **S1**: the person is not Ori, Efrat or Adi.
- **S2**: a step's success check still fails after its recovery steps.
- **S3**: `corpora install` / `corpora verify` reports DIFFERENT, or INSTALL FAILED twice for the
  right download (it is not the project's corpora).
- **S4**: `fingerprint` reports DIFFERENT, or `agreement` reports AGREEMENT NOT OK.
- **S5**: any command prints `REFUSED`, except the expected refusals named in §10.
- **S6**: the parsing run (§10) ends with `FAILED`.
- **S7**: continuing would break a hard rule.

**Commands.**
- Windows: PowerShell. macOS/Linux **(untested)**: bash.
- Always write project commands as **`uv run python -m hebloc …`** and tests as
  **`uv run python -m pytest`**. When a program's message suggests `uv run hebloc X`, run
  `uv run python -m hebloc X`. Reason: Windows Smart App Control blocks the `hebloc.exe` /
  `pytest.exe` launchers of a new environment ("An Application Control policy has blocked this
  file"), but not the signed Python (D-038).
- Commands that take longer than your command time limit (`corpora install`, `prepare`,
  `agreement`): run them in the background and wait for them to finish before continuing.
- The parsing run itself is always started with `--detach` (§10). Never run it in the foreground.

**Resuming.** This guide can be stopped and restarted at any point, by a new Claude Code session too.
Every section starts with **Skip if**: check it and skip the section when it is already done.

---

## 2. Who are you? (always first)

1. If `data/team/identity.json` exists, read it: it names the person this computer was set up for.
   Tell the person "This computer is set up for NAME; I'll continue for NAME", then go to §3.
2. Otherwise ask exactly: **"Who are you — Ori, Efrat, or Adi?"**
   - Accept any capitalization. Use the name in lower case as `NAME` (`ori`, `efrat` or `adi`).
   - Anything else → ask once more. Still none of the three → STOP S1.
3. Say: "I will set up this computer for NAME and run only NAME's part of the work." (§5 saves it.)

## 3. Prerequisites (*~1–5 min*)

**Skip if** all three checks below print a version.

| Tool | Check | Expected | Install if missing |
|---|---|---|---|
| Git | `git --version` | a version | (§0) Windows: `winget install --id Git.Git -e --scope user`; macOS: `xcode-select --install` |
| uv | `uv --version` | `uv 0.12` or newer | the command below the table |
| Python 3.12 (python.org) | Windows: `py -3.12 --version` | `Python 3.12.x` | Windows: `winget install --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements` (*~1 min, no admin*). macOS **(untested)**: the 3.12 installer from python.org. Linux **(untested)**: the `python3.12` package |

Install uv, if missing (Windows PowerShell):
```
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
macOS/Linux **(untested)**: `curl -LsSf https://astral.sh/uv/install.sh | sh`

After installing anything, a NEW terminal is needed for PATH to update. If a check still says "not
recognized", ask the person to close and reopen VS Code (same folder), then say "follow
PARTNER_START.md" again: this guide resumes at §2.

Why python.org Python on Windows: Smart App Control blocks the unsigned Python that uv downloads;
python.org's is signed (D-035).

## 4. Create the environment (*~1 min with a warm cache; a few minutes the first time*)

**Skip if** `uv run python -c "import sys, torch; print(sys.version.split()[0], torch.__version__)"`
prints `3.12.x 2.15.0+cpu`.

Windows:
```
uv venv --clear --python (py -3.12 -c "import sys; print(sys.executable)")
uv sync
uv run python -c "import sys, torch; print(sys.version.split()[0], torch.__version__)"
```
macOS/Linux **(untested)**: `uv venv --clear --python 3.12`, then the same two lines.

**Success:** prints `3.12.x 2.15.0+cpu` (or `2.15.0` on macOS).
**Recovery:** "Application Control policy has blocked this file" on `python`/`uv venv` → check §3
(`py -3.12 --version`) and repeat this section. `--clear` only replaces installed packages, no data.

## 5. Save who this computer belongs to

**Skip if** `uv run python -m hebloc whoami` prints `This computer is set up for: NAME`.
```
uv run python -m hebloc whoami --set NAME
```
**Success:** `This computer is set up for: Name  (data/team/identity.json)`. From now on every team
command uses this name and refuses to act for anyone else.
**Recovery:** `REFUSED: this computer is already set up for OTHER` → do not change it; STOP S5.

**Only for Efrat and Adi** (not Ori): make accidental pushes impossible (pulling still works):
```
git remote set-url --push origin DISABLED
```
**Success:** `git remote -v` shows `(push)` → `DISABLED`.

## 6. Install the corpora from the course archive (*tested at full size: ~11–35 min*)

**Skip if** `uv run python -m hebloc doctor --quick` shows `[PASS] corpora  corpora = anchor`.

1. Ask the person: **"Where is the corpus archive you downloaded from the course? Please give me the
   full path of the file — or of the folder that holds it, if it came in several parts."**
   Help if needed: in File Explorer, hold Shift, right-click the file → **Copy as path**, paste it.
   (macOS: right-click → hold Option → **Copy … as Pathname**.) An already-extracted folder also
   works, but the original archive is preferred.
2. Check that the path exists (`Test-Path "<PATH>"` must print `True`). If not, ask again.
3. Run it in the background and wait (keep the quotes; for a multi-part download give the folder,
   or repeat `--from` per part):
   ```
   uv run python -m hebloc corpora install --from "<PATH>"
   ```
   The command:
   - only reads the download, never changes it;
   - finds the corpus folders at any depth, including archives inside the archive;
   - checks every file NAME against the project's reference, repairing Hebrew names that zip tools
     garbled;
   - extracts into a staging folder and hashes all 404,294 files;
   - creates `corpora/` only if every file is identical.

   Supported: `.zip` (also multi-part), `.7z`, `.rar`, `.tar`, `.tar.gz`/`.tgz`, or a folder.

**Success:** the last line is
`404,294 files, 1,126,869,300 bytes: IDENTICAL to the project's corpora (anchor OK)`.
(The line before says where the corpora were found and which file-name decoding was used: any value
is fine.)

**Recovery:**
- `already exists and is not empty` → installed before: run `uv run python -m hebloc corpora verify`
  (same success line).
- `INSTALL FAILED … could not find a folder containing Mikra, Hazal, …` → wrong file, or a part of the
  download is missing. Ask for the right path; re-download if needed.
- `INSTALL FAILED … file names … are not the project's corpora`, `… sizes differ`, or `DIFFERENT` →
  nothing was installed. The download is different or damaged: download it again from the course,
  retry once. Still failing → STOP S3.
- `INSTALL FAILED … path is too long for Windows` → the clone is too deep. The person clones again into
  the home folder as in §0, opens that folder in VS Code, and starts over at §2.
- `not enough free disk space` → free space (setup needs ~10 GB), retry.
- Interrupted (sleep, crash) → run the same command again; it starts cleanly.

## 7. Download and verify the parser model (*~30 s on a fast connection, 0.7 GB*)

**Skip if** `uv run python -m hebloc models verify` prints `base: … OK`.
```
uv run python -m hebloc models fetch
```
**Success:** `base: dicta-il/dictabert-joint@7b1256fc0846 OK (all files match the pinned sha256)`.
**Recovery:**
- Network error → run it again (it resumes).
- sha256 problem → delete the folder `data/models/dictabert-joint` and run it again.
- Still failing → STOP S2.

## 8. Build the derived data (*inventory ~1.5–3 min, prepare ~3–5 min, fingerprint ~10 s*)

**Skip if** `uv run python -m hebloc fingerprint` already ends with `IDENTICAL to the reference`.
```
uv run python -m hebloc inventory
uv run python -m hebloc prepare
uv run python -m hebloc fingerprint
```
**Success:**
- `inventory` prints `Catalog: 404,294 documents -> …` with every verification flag `True`;
- `prepare` prints one line per corpus ending in `ok=True`;
- `fingerprint` ends with **`IDENTICAL to the reference`**: all 9,709,662 sentences are the same as on
  Ori's computer.

**Recovery:**
- `inventory` refuses (anchor) → go back to §6 (`corpora verify`).
- Fingerprint DIFFERENT → `uv sync`, repeat once. Still different → STOP S4.

## 9. Check the whole setup (*tests ~1–2 min*)

```
uv run python -m pytest -q
uv run python -m hebloc doctor
```
**Success:**
- `pytest` ends with `passed` and no `failed`. About 8 `skipped` are expected (tests that need Ori's
  pilot data).
- `doctor` ends with `ready_for_setup=True`. Its `TODO` lines are done in §10 or wait for Ori. Each
  `FAIL`/`TODO` prints its fix after `->`.
- A `WARN` about git ("modified files") → run `git status` and tell the person; do not commit.
- A `WARN` about the project folder or power → tell the person (it matters for the long run).

## 10. Agreement check, then the parsing run

### 10a. Cross-machine agreement (*~3–5 min*)

**Skip if** `data/team/agreement.json` exists with `"ok": true` and `doctor` shows
`[PASS] parsing  agreement check`.
```
uv run python -m hebloc agreement
```
It parses the 1,000-sentence pilot sample with the plan's exact settings, and compares every
piece's raw parser output with the reference made on Ori's computer.

**Success:** `AGREEMENT OK: this machine reproduces the reference output exactly` (1161 = 1161).
**AGREEMENT NOT OK** → STOP S4. It has already packaged its run into `data/outbox/NAME-agreement`:
the person sends that folder and `data/team/agreement.json` to Ori, who compares it word by word
(`hebloc agreement --compare`) and decides.

**Setup is complete.** Tell the person to send Ori the two small files `data/team/doctor.json` and
`data/team/agreement.json` (no corpus text). Then continue with 10b.

### 10b. Start or check the parsing run (only after Ori's approval)

1. Get Ori's latest plan:
   ```
   git pull
   uv sync
   uv run python -m hebloc work --status
   ```
2. Act on the first line of `work --status`:

   | First line says | Meaning | Do |
   |---|---|---|
   | `waiting for Ori's approval` | the plan is still a draft | Tell the person: **"Setup is complete. Ori has not started the parsing phase yet. When Ori says so, open this folder in VS Code and ask me again to follow PARTNER_START.md."** Stop (not an error). |
   | `running` | the run is already going in its own window | Show the progress lines and say how many hours are left. Done for now. |
   | `complete` | everything is parsed and packaged | Go to §11. |
   | `not started` or `stopped: run it again to resume` | ready to (re)start | Step 3. |

3. Tell the person how long it takes: the doctor's `your slices` line (`uv run python -m hebloc doctor --quick`)
   gives the estimate for this computer.
   Then tell them: keep the laptop **plugged in, lid open**; a new window will open and must stay
   open; VS Code may be closed; if Windows asks to restart for updates, choose a later time. Run:
   ```
   uv run python -m hebloc work --detach
   ```
   **Success:** `STARTED in its own window (pid …)`. The run:
   - re-checks the whole setup;
   - parses each of NAME's slices, validates it against this computer's data, and packages it as a
     verified `.zip` + `.zip.sha256` into `data/outbox/NAME/` (with `DELIVERY.json`);
   - keeps the computer from sleeping while it runs.

   A refusal `full runs are not enabled` → the plan is not approved yet (see the table). `not ready:` +
   a list → run each listed `->` fix, then step 3 again. Any other `REFUSED` → STOP S5.
4. Show `uv run python -m hebloc work --status` once a slice is under way. Tell the person they can
   ask Claude Code ("follow PARTNER_START.md") at any time to see progress.

**After any interruption** (window closed, crash, power cut, reboot): the person opens the folder in
VS Code and says "follow PARTNER_START.md". The status says `stopped`, and step 3 resumes. Finished
slices are skipped, and the current slice continues at its first unfinished shard (≤ 500 sentences
redone). Never delete anything in `data/annotations/` or `data/outbox/`.
**The window shows `FAILED`** → STOP S6 (send Ori the window's last lines and `data/team/work.log`).

## 11. Completion message and sending the results

When `work --status` says `complete`, the window shows `WORK COMPLETE`. Give the person this message,
filled in from `work --status` and `data/outbox/NAME/DELIVERY.json`:

> **Your part of the parsing is complete.** I parsed **N slices (S sentences)**. Each was checked
> against this computer's data and packaged as a checksum-verified bundle (**X MiB** in total).
> Everything is in the folder **`<full path>\data\outbox\NAME`**.
>
> **Send Ori that whole folder, unchanged.** Upload the folder itself to the team's private shared
> folder (Google Drive / OneDrive / Dropbox), or copy it to a USB drive. Never put it on GitHub. Wait
> until the upload has finished, then tell Ori. Keep your copy until Ori confirms the merge reported
> **MERGE OK**.

Expected sizes:
- Option A (all of Modern): ~4–5 GB per person;
- Option B (10% Haaretz sample): ~1.5–2 GB per person.

A partial folder may be sent early; send it again when complete. Ori's merge skips what it already
has.

---

## 12. Merging everything (Ori's computer only)

Copy every received folder somewhere outside the project (e.g. `C:\hebloc-incoming\efrat`), then:
```
uv run python -m hebloc merge "C:\hebloc-incoming"
```
For every bundle it checks:
- the zip against its `.sha256` and the `DELIVERY.json` that lists it (a missing or damaged upload
  fails), and every file inside it;
- the corpora anchor and the parse settings;
- the restored run's integrity;
- that the run holds **exactly** its slice's sentences on Ori's computer (same ids, same text, none
  missing, none repeated), and that the slice's owner made it.

Identical copies are merged once. Two DIFFERENT bundles of one slice are a CONFLICT, and neither is
merged. Merging again is safe.

**Success:** `MERGE OK` and
`full coverage A: 31/31 slices OK; units 9,709,662/9,709,662; units in more than one run: 0; COMPLETE`
(for option B: its own slice and unit totals).
`uv run python -m hebloc merge` with no paths prints only the completeness report.

When COMPLETE:
1. `uv run python -m hebloc plan register` (preview);
2. `… plan register --write` (refuses unless COMPLETE);
3. add a decision entry;
4. `uv run python -m hebloc check`;
5. commit `config/annotations.yaml`.

M6 statistics are then computed centrally from the registered runs (D-040).

If a partner's agreement failed: `uv run python -m hebloc agreement --compare <their agreement zip>`
gives the word-by-word agreement per column, so Ori can decide with evidence.

---

## 13. Quick recovery reference

| Symptom | Action |
|---|---|
| "An Application Control policy has blocked this file" on `hebloc` / `pytest` | Use `uv run python -m hebloc …` / `uv run python -m pytest` (§1) |
| The same message on `python` / `uv venv` | §3 (python.org 3.12), then §4 |
| `uv` / `py` / `git` "not recognized" | Reopen VS Code after installing (PATH refresh), then "follow PARTNER_START.md" |
| `REFUSED: who are you?` | §5 |
| `REFUSED: this computer is set up for X, not Y` | Wrong computer or wrong name: STOP S5 |
| `REFUSED: hebloc work is already running` | It is running in its window: `work --status` |
| The parsing window was closed / the computer restarted | §10b (status says `stopped`; `--detach` resumes) |
| `corpora install` / `agreement` interrupted | Run the same command again |
| Disk full | Setup ~10 GB; the full run adds up to ~10 GB (option A). Free space, then resume |
| Anything else | STOP S2: send Ori the output and `data/team/doctor.json` |
