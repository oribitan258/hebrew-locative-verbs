# PARTNER_START: execution guide for Claude Code on a partner's computer

**This file is an instruction script for a Claude Code session.** It sets up this project on one
team member's computer (Ori, Efrat or Adi), verifies that the machine produces exactly the same data
and parser output as everyone else's, runs **only that person's** assigned parsing work, and
packages the results for merging.

Every command below was run end to end from a clean clone on Windows 11 (D-037). Timings in
*italics* are from that test on Ori's laptop. Steps marked **(untested)** were not run on that
platform.

---

## 0. For the human, before Claude Code (one time, ~10 min)

1. Accept the GitHub invitation to `oribitan258/hebrew-locative-verbs` (it arrives by email).
2. Download the corpora from: **`<ORI: fill in the course link>`**. Keep the downloaded `.zip`, or
   the folder you extracted, anywhere on your computer **outside** the project folder, and note its path.
3. Open a terminal (Windows: PowerShell) and run:
   ```
   git clone https://github.com/oribitan258/hebrew-locative-verbs.git
   cd hebrew-locative-verbs
   claude
   ```
4. In Claude Code, type: **`Read PARTNER_START.md and run it for me. I am <your name>.`**

---

## 1. Rules for Claude Code (read first; they override everything below)

**Hard rules.**
- Work only inside this repository folder. Never edit, move or delete anything in `corpora/`.
- Never `git commit` or `git push` `corpora/`, `data/`, bundles or any generated file. Never
  change `config/parse_plan.yaml`, `config/work_plan.json`, `config/annotations.yaml`,
  `config/corpora_anchor.json`, `config/reference/*`, `tests/` or `src/`. A partner session
  changes no tracked file. `git status` must stay clean.
- Never work around a failed check: no skipping verification, editing tests, `--force`,
  `--overwrite`, another person's `--as`, or deleting `data/annotations/` to "start over".
- Run commands one at a time and read their output before continuing. Every step states what
  success looks like.
- Talk to the user in plain, beginner-friendly English. Before long steps, say how long they take.

**STOP conditions.** Stop, show the user the exact output, and tell them to send it plus
`data/team/doctor.json` to Ori if any of these happens:
- S1: the person is not exactly one of the names in `config/parse_plan.yaml` → `people`.
- S2: a step's success check fails twice, after the recovery listed for it.
- S3: `corpora install`/`corpora verify` says DIFFERENT (the download is not the project's corpora).
- S4: `fingerprint` says DIFFERENT, or `agreement` says AGREEMENT NOT OK.
- S5: `hebloc parse` prints `REFUSED`. Do not retry with other arguments.
- S6: a parse ends with `validation_ok` or `integrity_ok` = false.
- S7: anything would require breaking a hard rule above.

**Shell.**
- Windows: run commands in **PowerShell**, and in every new PowerShell first run
  `$env:PYTHONUTF8 = "1"`.
- macOS/Linux **(untested)**: use bash, and run `export PYTHONUTF8=1` first.
- Run everything from the repository root (the folder containing this file).

---

## 2. Identify the partner

1. Read `people` in `config/parse_plan.yaml` (currently `ori`, `efrat`, `adi`).
2. Take the name from the user's request. If it is missing, ask "Which team member are you:
   Ori, Efrat or Adi?" Use it in lower case as `NAME` in every `--as NAME` below. If it matches
   none of them, apply STOP S1.
3. Confirm with the user: "I will set up this computer for NAME. OK?"

---

## 3. Prerequisites

Check each one. Install only what is missing.

| Tool | Check | Expected | Install if missing |
|---|---|---|---|
| Git | `git --version` | a version | Windows: `winget install --id Git.Git -e --scope user`; macOS: `xcode-select --install` |
| uv | `uv --version` | `uv 0.12` or newer | Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"`; macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh \| sh`. Then open a NEW terminal |
| Python 3.12 (python.org) | Windows: `py -3.12 --version` | `Python 3.12.x` | Windows: `winget install --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements` (*tested; ~1 min, no admin*). macOS **(untested)**: the 3.12 installer from python.org. Linux **(untested)**: the `python3.12` package |

Why python.org Python on Windows: Windows 11 **Smart App Control** blocks the unsigned Python that
uv downloads ("An Application Control policy has blocked this file"). The python.org build is
signed and allowed (D-035).

## 4. Create the environment

Windows (*tested; ~1 min with a warm cache, a few minutes on first download*):
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
**Recovery:**
- "Application Control policy has blocked this file": the venv was made with uv's own Python.
  Make sure §3's python.org 3.12 is installed (`py -3.12 --version`) and repeat this section:
  `--clear` replaces the environment, which holds only installed packages, no data.

## 5. Install and verify the corpora (*tested: ~20 min to copy + verify 404,294 files*)

Ask the user for the full path of the downloaded corpora (the `.zip` or the extracted folder from
§0). Then:
```
uv run hebloc corpora install --from "<PATH>"
```
**Success:** the last line says `404,294 files, 1,126,869,300 bytes: IDENTICAL to the project's corpora (anchor OK)`.
The command finds the folder that contains `Mikra Hazal Medieval Haskala Modern` (also inside a
zip), copies it to `corpora/`, hashes every file and compares with the git-tracked anchor. The
user's download is not modified.
**Recovery:**
- "already exists and is not empty": the corpora were installed before. Run
  `uv run hebloc corpora verify` instead (same success line).
- "could not find a folder containing ...": the path is wrong or the download is incomplete. Ask
  for the correct path.
- DIFFERENT → STOP S3.

## 6. Download and verify the parser model (*tested: 30 s on a fast connection, 0.7 GB*)

```
uv run hebloc models fetch
```
**Success:** `base: dicta-il/dictabert-joint@7b1256fc0846 OK (all files match the pinned sha256)`.
**Recovery:** a network error → run the same command again (it resumes). A sha256 problem →
delete `data/models/dictabert-joint` and run it again. If it still fails → STOP S2.

## 7. Build the derived data (*tested: inventory ~1.5 min, prepare ~3 min, fingerprint ~10 s*)

```
uv run hebloc inventory
uv run hebloc prepare
uv run hebloc fingerprint
```
**Success:**
- `inventory` prints `Catalog: 404,294 documents -> ... Verification: ...=True, ...` (every flag `True`);
- `prepare` prints one line per corpus ending in `ok=True`;
- `fingerprint` ends with **`IDENTICAL to the reference`**. The rebuilt catalog and all 9,709,662
  sentences are byte-for-byte the same content as on Ori's machine.

**Recovery:** `inventory` refuses (anchor) → go back to §5 (`corpora verify`). Fingerprint
DIFFERENT → run `uv sync` and repeat this section once. Still different → STOP S4.

## 8. Verify the whole setup (*tested: tests ~1 min*)

```
uv run pytest
uv run hebloc doctor --as NAME
```
**Success:**
- `pytest` ends with `passed` and no `failed` (on a fresh machine it also shows about 8 `skipped`: tests that
  need Ori's pilot data. That is expected);
- `doctor` ends with `ready_for_setup=True`. Its `ready_to_parse` stays False until §9 is done and
  Ori approves the plan.

Every line the doctor marks `TODO` or `FAIL` prints its fix command (`->`). Run it and re-run the
doctor. A `WARN` about git ("modified files") means a tracked file was changed: run `git status`
and tell the user. Do not commit.

## 9. Cross-machine parser agreement (*tested: ~3 min*)

```
uv run hebloc agreement --as NAME
```
This parses the 1,000-sentence pilot sample with the plan's exact settings and compares every
piece's raw parser output with the reference produced on Ori's computer.
**Success:** `AGREEMENT OK: this machine reproduces the reference output exactly`
(`pieces_identical` = `pieces_compared` = 1161). It also prints `subwords_per_second`, your
machine's real speed.
**Recovery:** if interrupted, run the same command again (it resumes). AGREEMENT NOT OK → STOP S4.
Ori may ask for `uv run hebloc bundle create agreement/<run>`.

**Setup is complete.** Tell the user to send Ori `data/team/doctor.json` and
`data/team/agreement.json`. These are small JSON files with no corpus text.

---

## 10. Parse the assigned slices (ONLY after Ori's go-ahead)

1. Get Ori's latest plan:
   ```
   git pull
   uv sync
   uv run hebloc doctor --as NAME
   ```
   Continue only if the doctor shows `plan approved` = PASS and `ready_to_parse=True`. If the plan
   is not approved: stop here and tell the user that Ori has not started the parsing phase. This is
   not an error.
2. List the work: the doctor's line `your slices` and `docs/WORK_PLAN.md` give NAME's slices and
   hours. Tell the user to keep the laptop **plugged in**, set **Settings → System → Power →
   Power mode: Best performance**, and set **Screen and sleep: Never** while it runs.
3. For each of NAME's slices, one at a time:
   ```
   uv run hebloc parse --slice <SLICE> --as NAME
   ```
   It parses only that slice, refusing anything not assigned to NAME (`REFUSED` → STOP S5). Long
   slices take hours.
   **Success:** the final JSON has `"validation_ok": true` and `"integrity_ok": true`, and a `next`
   command. Otherwise → STOP S6.
   **Recovery:** if it stops for any reason (sleep, crash, reboot, Ctrl+C), run the **same command**
   again. It resumes at the first unfinished shard and never re-parses finished work. Never delete
   its folder.
4. Package the slice by running the `next` command it printed:
   ```
   uv run hebloc bundle create <corpus>/<settings_id>__<SLICE>
   ```
   **Success:** `data/bundles/hebloc-annotations-<...>.zip` plus a `.zip.sha256` file.

## 11. Share the results

Upload **both** files of every bundle (`.zip` and `.zip.sha256`) from `data/bundles/` to
**`<ORI: fill in the private shared folder>`**. Never upload them to GitHub. Then tell Ori which
slices are done. Ori verifies and merges them (§12). Keep your bundles until Ori confirms the merge.

## 12. Merging (Ori's computer only)

```
uv run hebloc merge <path\to\bundle1.zip> <path\to\bundle2.zip> ...
uv run hebloc plan status
uv run hebloc check
```
Keep each `.zip.sha256` next to its `.zip`. Every `merge` line must start with `OK`. A merge
re-checks:
- the zip against its `.sha256` file (damage in transfer);
- the sha256 of every file inside it;
- the corpora anchor;
- the run's integrity against Ori's own units;
- that the run belongs to the current plan and settings.
- When all slices are present: `uv run hebloc plan register` (preview), then `--write`. Add a
  decision entry, re-run `uv run hebloc check`, and commit.
- Smoke runs merge as `OK` for testing but are never registered.

---

## 13. Quick recovery reference

| Symptom | Action |
|---|---|
| "An Application Control policy has blocked this file" | §3 (python.org 3.12) and §4 (recreate `.venv`) |
| `UnicodeEncodeError` / garbled Hebrew | `$env:PYTHONUTF8 = "1"` in this terminal, then repeat the command |
| `uv` / `py` "not recognized" | Open a NEW terminal after installing (PATH refresh) |
| A long command was interrupted | Run the same command again: corpora install refuses (then use `corpora verify`); models, agreement and parse resume |
| `hebloc parse` REFUSED | STOP S5: read the message. Usually the plan is not approved yet, or the slice is someone else's |
| Disk full | Setup needs ~6 GB; parsing adds ~1.2 GB per 10 h (~4 GB for a full option-A share), and bundles about as much again. Free space, then resume |
| Anything else | STOP S2 and send Ori the output and `data/team/doctor.json` |
