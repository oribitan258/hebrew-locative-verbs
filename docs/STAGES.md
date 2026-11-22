# STAGES.md: the ordered workflow for §5 (Ori) and §6 (Efrat) through completion

**This file is the single ordered tracker.** Every Claude Code session on Ori's or Efrat's computer:
- starts with `start` (§1);
- does **one** stage;
- ends with `end-of-session` (§2).

The methodology is `S56-v1` (`docs/EFRAT_SECTION_6.md` §5) with D-053 … D-061. Nothing here changes it. This file
only orders the approved work, names who hands what to whom, and says when the next stage may start.

> **Plan files (`~/.claude/plans/…`) are not durable:** each planning session overwrites them. Everything approved is
> recorded in the repo (this file, `docs/decisions.md`, `docs/HANDOFF.md`, the protocol). Never rely on a plan file.

**Current position (updated by Ori's `end-of-session`):**
- §5: **P0** done and pushed (2026-11-21). **P1** = the D-062 fix, released as tag `s56-r1.2` (0396a2b, pushed
  2026-11-21).
  - **O1 done (2026-11-21):** job `noun-mikra-r2` frozen (979 lemmas; final sha256 `47dc464e…c064`; κ 0.907;
    0 breaches; no STOP). The pre-fix job `noun-mikra` is kept unchanged and never used.
  - **R done (2026-11-21):** Efrat's delivery 1 (`noun-modern-r2`) was received and its hashes recorded in
    `annotation/silver/FROZEN_SILVER.json`, without reading any label. The commit of that record (★) is in the R row.
  - **O2 done (2026-11-22):** jobs `audit` (95 / 100 `Y`, exactly the threshold: the automatic links come into
    force at O3; an AI audit), `variant` (136 / 160 agree; P5 evidence only) and `unit` (κ 0.873; 1,440 links
    accepted, 625 no link) frozen; 0 breaches.
    - On the way, the usage limit refused 16 `unit` launches. **D-063** (Ori): such a refusal is an outage, not an
      attempt (`step` WAITs; `loc silver reclassify-outages`). Local commit `83aade8`.
    - **Both open items are resolved by P2 (D-064, 2026-11-22):** D-063 goes to Efrat as tag `s56-r1.2.1` (stage ED);
      `FROZEN_SILVER.json` is excluded from the pinned-file checks (the pull rule, G3, ES). Commit, tag and push await
      Ori's ★.
  - **R done again (2026-11-22): Efrat's delivery 2 (E4: Modern dev, Mikra dev, the anchor) received**, its hashes
    recorded in `FROZEN_SILVER.json` before any read (§5 row 2). No label was read; nothing was scored.
  - Next: **O3** (all inputs present: O1, O2, Efrat's E3 received). O3's onward DEP (Efrat's dev silver, E4) is now
    met too, as is the dev-silver part of G2.
- §6: Efrat has done EF, E3 and **E4** (delivery 2 received). Her next stage is **E5** (validation silver); after P2's
  push and message M8, she first takes **ED** (`s56-r1.2.1`) at the start of a session. Her
  progress is in her `STATE.md`.

---

## 0. Words used here

| Word | Meaning |
|---|---|
| **AUTO** | The next stage may start in the next session, with no approval. |
| **★ APPROVAL** | Ori must approve (in the session) before the next stage starts. |
| **DEP** | Wait for the named input (usually a delivery from the other person, or a release). |
| **CONTINUE** | `end-of-session` result: the next stage is eligible now. |
| **SEND TO PARTNER** | `end-of-session` result: this session produced a handoff. Send it exactly as printed. |
| **WAIT** | `end-of-session` result: nothing is eligible until the named input or approval arrives. |
| **Delivery** | A folder made by `loc silver deliver` (or `hebloc work` / the §6 outbox), with `DELIVERY.json`. It travels by Google Drive, OneDrive or USB, **never by git**. |
| **Pinned files** | `annotation/` (the protocol, the prompts, the guideline, the worked examples, the anchor ids), `config/`, `src/`, `pyproject.toml`, `uv.lock`, **except `annotation/silver/FROZEN_SILVER.json`** (Ori's SG2 record of received hashes: not an input of any job; D-064). As a git pathspec, **PINNED** = `annotation/ config/ src/ pyproject.toml uv.lock ':(exclude)annotation/silver/FROZEN_SILVER.json'`. |

---

## 1. `start` (whole message "start", "go", "continue" or "status")

Claude Code does these steps in order and shows each result.

1. **`git status`.** If tracked files are modified: STOP, show the list, never discard it.
2. **Synchronize with GitHub** (`git fetch origin --tags`):
   - **Ori:** `git pull` if origin is ahead (only Ori pushes, so this is a fast-forward).
   - **Efrat (the pull rule):**
     - If `git diff --quiet HEAD origin/main -- annotation/ config/ src/ pyproject.toml uv.lock ':(exclude)annotation/silver/FROZEN_SILVER.json'`
       succeeds, the update is documentation only: `git pull`. (Since D-064 the exclusion is part of the rule: Ori's
       `FROZEN_SILVER.json` record is not a pinned file.)
     - Otherwise do **not** pull. Read the announcements with `git show origin/main:docs/STAGES.md` (§6 below). If an
       announcement names a tag for Efrat (`s56-r1.2` = the D-062 fix, `s56-r1.2.1` = D-063 + D-064,
       `s56-r1.3` = a supplement, `s56-v1`):
       `git merge --ff-only <tag>`, then run the checks
       that announcement lists.
     - Never `git checkout` a tag (a detached checkout breaks later pulls), and never pull pinned files in any other
       way.
3. **Environment:** `uv sync`, then `uv run python -m pytest -q` (all pass), then `uv run python -m hebloc whoami`.
4. **Read the state:**
   - **Ori:** this file and `docs/HANDOFF.md` "Current position"; list deliveries waiting in `data/incoming/`
     (any folder with a `DELIVERY.json` not yet in `annotation/silver/FROZEN_SILVER.json` or merged).
   - **Efrat:** this file and her `data/outbox/efrat-s6/STATE.md` (created at her first `end-of-session` if
     missing).
5. **Report** the stage that is next for this person and whether it is eligible (its prerequisites in §3 / §4 are
   met and any ★ approval is recorded).
   - **Eligible:** propose that one stage in Plan Mode. Execute only after approval (Ori approves his stages; Efrat
     approves hers).
   - **Not eligible:** print **WAIT**, what is missing and from whom, and stop.

## 2. `end-of-session` (whole message "end-of-session", or `/end-of-session`)

1. **Checks:** run the completion checks of the stage just done (§3 / §4). If one fails, the stage is not done.
2. **Persistent record.**
   - **Ori** updates:
     - the "Current position" line at the top of this file, and the `Status` cells in §3 / §5;
     - `docs/HANDOFF.md` "Current position";
     - the CLAUDE.md scope line, and the `docs/roadmap.md` §5 / §6 rows when a stage changes them;
     - `docs/decisions.md` (only if a decision was taken);
     - the memory.

     Show the diff. **Commit and push only on Ori's approval** in that session. A push is needed whenever Efrat must
     see an announcement.
   - **Efrat** updates `data/outbox/efrat-s6/STATE.md` (local, never git; format in §7). She never commits.
3. **Print exactly one result:**
   - **CONTINUE:** "Next session: `start` → stage `<id>`."
   - **SEND TO PARTNER:** the folder to send, the channel, the message (§8 templates), then what this person does
     next (usually WAIT).
   - **WAIT:** for what, from whom, and what `start` will check.

---

## 3. §5: Ori (Ori's computer)

| Id | Prerequisites | Tasks | Completion checks | Outputs / handoff | Next | Status |
|---|---|---|---|---|---|---|
| **P0** | Ori's approval of the workflow plan | Docs only: this file, the restored Phase C rules (D-059 addendum), stale-doc fixes, `start` / `end-of-session` | Full tests; `hebloc check`; pinned files unchanged since `s56-r1.1` | Commit + push (★) → **SEND TO PARTNER** (§8 M1) | AUTO → O1 | done, pushed 2026-11-21 |
| **P1** | O1 stopped (the duplicate-noun-ID defect); Ori's plan approval | D-062: `nouns-r2` lists (one row per lemma); unique item ids in every silver job; versioned noun job ids; pre-fix jobs kept but inactive; the import rule. Tests. The Mikra and Modern r2 lists (verified). Docs | Full tests; `hebloc check`; `git diff --quiet s56-r1.1 -- annotation/ config/`; old `noun-mikra` byte-identical | Commit + tag **`s56-r1.2`** + push (★) → **SEND TO PARTNER** (§8 M7) | ★ APPROVAL → O1 | done; `s56-r1.2` pushed 2026-11-21 |
| **O1** | P1 | Mikra noun types: `loc nouns list --corpus mikra` (→ `mikra-nouns-r2-826929982d`, 979 lemmas; from the clean `s56-r1.2` tree, `nouns_to_label.csv` sha256 `f26714a0…cbd7`), then `loc silver create --task noun --corpus mikra --list data/loc/nouns/mikra/mikra-nouns-r2-826929982d/nouns_to_label.csv` → job `noun-mikra-r2`, then `loc silver step noun-mikra-r2` until `finalized` (protocol §9). The stopped pre-fix job `noun-mikra` is never used (D-062) | QC thresholds met; access logs clean; job frozen | Job `noun-mikra-r2` (local) | AUTO → O2 | done 2026-11-21: `noun-mikra-r2` frozen (final sha256 `47dc464e…c064`; κ 0.907; 0 breaches) |
| **O2** | P0 | Units (D-061): `create --task unit --sheet data/loc/review/units/unit_review.csv --examples-csv …/unit_review_examples.csv`, `--task audit --sheet …/audit.csv`, `--task variant --sheet …/paper_variants.csv`; `step` each until `finalized` | Each job frozen; audit result ≥ 95 / 100 or the pre-registered withdrawal (D-059 P2) | Jobs `unit`, `audit`, `variant` (local); the P5 evidence | DEP: Efrat's Modern nouns (E3) → O3 | done 2026-11-22: all frozen; audit 95/100; variant 136/160 agree; unit κ 0.873, 1,440 / 625; 0 breaches (16 usage-limit outages, D-063) |
| **P2** | O2; Ori's plan approval (2026-11-22) | D-064 (docs only): release D-063 to Efrat as tag **`s56-r1.2.1`**; `FROZEN_SILVER.json` excluded from the pinned-file checks (the pull rule, G3, ES); stage ED + its announcement in §6; template M8 | Full tests; `hebloc check`; `git diff --quiet s56-r1.1 HEAD -- annotation/ config/ ':(exclude)annotation/silver/FROZEN_SILVER.json'`; `git diff --quiet s56-r1.2 HEAD -- config/ pyproject.toml uv.lock`; a rehearsal of Efrat's path in a scratch clone | Commit + tag `s56-r1.2.1` + push (★) → **SEND TO PARTNER** (§8 M8) | AUTO → O3 | docs written 2026-11-22; commit / tag / push await ★ |
| **R** | A delivery from Efrat in `data/incoming/efrat-s6/<n>/` (any time) | `loc silver receive <folder>` only: hashes into `annotation/silver/FROZEN_SILVER.json`. **Never read the labels.** Update §5 "Partner status" | Hashes match `DELIVERY.json` | Commit of `FROZEN_SILVER.json` (★, before any read) | Back to the stage that waited | delivery 1 (`noun-modern-r2`) received 2026-11-21; delivery 2 (dev × 2 + anchor) received 2026-11-22; see §5 |
| **O3** | O1, O2, Efrat's E3 received (R) | `loc nouns merge --automated` (Modern, Mikra) → historical nouns (`loc nouns list --exclude-typed`, a noun job, merge) → `loc units merge` / `audit --automated` → freeze `config/noun_types.yaml` v1 and the unit map | Merge checks; cross-corpus conflicts listed (D-061 G1 rule); `loc verify`; tests | Config commit (★ Ori approves each merged **file**, never rows) | DEP: Efrat's dev silver (E4) | |
| **C0** | O3 (reads no silver) | **Phase C build**, in Plan Mode (★ plan approval first): supplement silver jobs that do not collide (`job_id` is `sentence-<corpus>-<split>` today); I-2, I-3, I-4 code; the I-3 sense-screen draw; the §6 silver tasks (EFRAT §5.9(2) candidate review, §5.9(3) template proxy); the class/identity audit task (EFRAT §5.5, §5.6) and who runs it under D-061 | Full tests; pinned protocol files unchanged | Local code commit (pushed only at G3 or G7) | ★ APPROVAL; then DEP: dev silver | |
| **G2** | O3, C0, dev silver of **both** corpora + the anchor received (R) and QC-passed | — | — | — | ★ APPROVAL → C1 | |
| **C1** | G2 | Identification candidates I-0 … I-5 on dev silver + the paper examples, by the **pre-registered rules** (D-059 addendum) | Each rule applied exactly as written | A decision record per candidate | ★ G3 if a supplement or sense screen is needed, else ★ G4 | |
| **G3** | C1 needs a supplement / screen | Ori approves each draw (decision id). Push the code + tag **`s56-r1.3`** (pinned protocol files byte-identical to `s56-r1.1`; `s56-r1.2` is the D-062 fix) + an announcement in §6 | `git diff --quiet s56-r1.1 s56-r1.3 -- annotation/ ':(exclude)annotation/silver/FROZEN_SILVER.json'` (D-064) | **SEND TO PARTNER** (§8 M3) | DEP: Efrat's ES delivery → R → C1 | |
| **G4** | C1 complete | Freeze `lexicon-v2` / `forms-v3` (P5 decided here, file level) | Tests; `loc lexicon check`; `loc verify` | Commit (★) | ★ APPROVAL → C2 | |
| **C2** | G4 | Resolver development on dev silver + the paper examples | Determinism | Commit | DEP: validation silver (E5) received → G5 | |
| **G5** | C2, validation silver of both corpora received | `loc score --choose` (once; ledger) | Ledger `annotation/gold/VALIDATION_CHOICE.json` written | Commit (★) | DEP: test silver (E6) received → G6 | |
| **G6** | G5, test silver of both corpora received | `loc score --final-test` once per corpus; the BHSA identification sensitivity run; the paper replication; determinism; repo = package | Ledgers; all checks | Results in `docs/S56_R2.md` (★) | ★ APPROVAL → G7 | |
| **G7** | G6 | **CHECKPOINT 2.** R2 release notes; EFRAT_SECTION_6 §7 I2 / I3 and §9.3 exact commands; tag **`s56-v1`**, push. Decide the stage-2 split and the historical test silver. Build and test Adi's M5-style workflow, write `docs/ADI_SECTION_5.md` and her `start` | Tag on origin; Adi's workflow tested | **SEND TO PARTNER** (§8 M4 to Efrat, M5 to Adi) | DEP: Adi's stage-2 delivery → O4 | |
| **O4** | G7 | Ori's stage-2 corpora; `hebloc merge` of Adi's delivery | Merge OK; all five corpora present | Merged §5 outputs | AUTO → O5 | |
| **O5** | O4 | Central §5 statistics (identity, classes, §8 predictions, per corpus), the class/identity audits, `loc verify` → `docs/SECTION_5.md` | `loc verify` OK; reconciliation | **§5 COMPLETE** (★ Ori approves) | — | |

**§5 depends on Efrat** (approved, D-061) for: the Modern noun types (O3), and the dev (G2), validation (G5) and test
(G6) silver of both corpora, plus any supplement (G3). **§5 depends on Adi** for stage 2 (O4), as decided at
CHECKPOINT 2.

## 4. §6: Efrat (Efrat's computer; steps of `docs/EFRAT_SECTION_6.md` §9)

| Id | Prerequisites | Tasks | Completion checks | Outputs / handoff | Next |
|---|---|---|---|---|---|
| **E1** | `s56-r1.1` in her checkout | §9.2 step 4: T1, T2, `loc silver isolation-test` | `"ok": true`; both samples `items_match = true` | — | AUTO |
| **E2** | E1 | §9.2 step 5: worked examples | 15 / 15 (T3) | — | AUTO |
| **EF** | The P1 announcement in §6 (`s56-r1.2`, D-062) | Take the fix: `git merge --ff-only s56-r1.2`; checks as announced. A pre-fix `noun-modern` job (any state) is kept untouched and never stepped, finalized or delivered | All announced checks OK | — | AUTO → E3 (redone), and the current E4–E6 stage continues |
| **ED** | The P2 announcement in §6 (`s56-r1.2.1`, D-063 + D-064) | Take the release at the start of a session, never while a `step` is running: `git merge --ff-only s56-r1.2.1`; checks as announced; `reclassify-outages` only for a STOP caused by refused launches | All announced checks OK | — | AUTO → the current E5 / E6 stage continues |
| **E3** | E2, EF | §9.2 step 6: the Modern r2 list (`loc nouns list --corpus modern --source package`; row count and sha256 as announced in §6) → `create` → job `noun-modern-r2` → pass A imported (`dropped_duplicate` lemmas relabelled in an isolated pass A), pass B → `deliver noun-modern-r2` | List = announced; QC; frozen | **SEND TO PARTNER** (§8 M2) | AUTO → E4 |
| **E4** | E2 | §9.2 step 7: Modern dev → Mikra dev → anchor → `deliver` | QC per job; frozen | **SEND TO PARTNER** (M2) | AUTO → E5 |
| **E5** | E4 | Modern validation → Mikra validation → `deliver` | Same | **SEND TO PARTNER** (M2) | AUTO → E6 |
| **E6** | E5 | Modern test → Mikra test → `deliver` | Same | **SEND TO PARTNER** (M2) | WAIT: a G3 announcement (→ ES) or `s56-v1` (→ E7) |
| **ES** | A G3 announcement in §6 | `git merge --ff-only s56-r1.3`; check `git diff --quiet s56-r1.1 HEAD -- annotation/ ':(exclude)annotation/silver/FROZEN_SILVER.json'` (D-064); draw the announced supplement / screen from the package; its jobs (dev first) → `deliver` | `items_match`; QC; frozen | **SEND TO PARTNER** (M2) | WAIT |
| **E7** | `s56-v1` announced (§8 M4) | §9.3 step 1: `git merge --ff-only s56-v1`, `uv sync`, tests, `hebpack.verify`, `loc lexicon check`, `loc silver isolation-test` | All OK; `git diff --quiet s56-v1 HEAD -- src/ config/` | — | AUTO |
| **E8** | E7 | §9.3 steps 2–3: `loc extract --mode all-verbs` → `resolve` → `classify` → `swap` on Modern → `loc verify` | Verify OK | `results/` | AUTO |
| **E9** | E8 | §5.9(2) candidate review and §5.9(3) template-proxy check, by the silver protocol (tasks in R2) | QC; frozen | `silver/` | AUTO |
| **E10** | E9 | §9.3 step 4: analyses (Plan Mode; Efrat approves each) | Each table re-runs from its script | `analyses/` | AUTO |
| **E11** | E10 | §9.3 step 5: `REPORT.md` (limitations include R2's agreement with the Modern test silver; feedback to §5) | Complete | `REPORT.md` | AUTO |
| **E12** | E11 | §9.3 step 6: deliver (§10) | `DELIVERY.json` | **SEND TO PARTNER** (M2) | WAIT: Ori's review |
| **E-done** | E12 received | Ori verifies the hashes, recomputes at least one output, checks the cross-checks, reviews `REPORT.md` | Ori's acceptance (★) | **§6 COMPLETE** | — |

**§6 depends on §5 only through releases:** `s56-r1.1` (now), `s56-r1.2` (the D-062 noun-ID fix), `s56-r1.2.1` (D-063 outages + D-064 checks), `s56-r1.3` (only
if Ori requests a supplement), and
`s56-v1` (R2). Any STOP of a T1–T7 or S1–S10 rule ends Efrat's session with **SEND TO PARTNER** (§8 M6).

## 5. Partner status (Ori updates it on each receipt)

| Delivery | From | Jobs | Received | `DELIVERY.json` sha256 | Recorded in `FROZEN_SILVER.json` |
|---|---|---|---|---|---|
| 1 (`data/incoming/efrat-s6/1/`; copy of `data/efrat-s6/efrat-s6/`) | Efrat (E3) | `noun-modern-r2` (1,668 items; made at `s56-r1.2`, clean; no QC STOP) | 2026-11-21 (`loc silver receive`; 81/81 hashes OK) | `51e3c7d9100052160cbad04d0a100dfb81601c195613b5cb94fbfbbfbcad44e8` | yes: final `noun_types_modern.csv` sha256 `88382c7d…1454` (labels NOT read) |
| 2 (`data/incoming/efrat-s6/2/`; verified copy of the Drive download `data/efrat-s6/efrat-s6 (1)-20261122T095313Z-1-001/efrat-s6 (1)/`: `silver (1)` → `silver`, `DELIVERY (1).json` → `DELIVERY.json`, bytes unchanged) | Efrat (E4) | `sentence-modern-dev` (101), `sentence-mikra-dev` (98), `anchor-mikra` (48); made at `a820d3e` (`s56-r1.2` + docs), clean; protocol, guideline and prompts = Ori's; no QC STOP, none accepted; 0 breaches; 0 qc_format; abstention 4.95 / 2.04 / 4.17%; first-run frame κ 1.0 / 0.916 / 0.922 | 2026-11-22 (`loc silver receive`; 176/176 hashes OK) | `acc3200bffc6b05a6acd540c4782a11b86ef85fa3439ed488a2d7c36dce81e95` | yes: `modern_dev_silver.csv` `b120c2b6…eaab`, `mikra_dev_silver.csv` `a62809f4…eb5c`, `anchor-mikra_silver.csv` `0bea5c56…e460` (labels NOT read) |

## 6. Announcements for Efrat (read by her `start` from origin)

- 2026-11-21: P0 (this file) is documentation only. Your pin holds: the pull rule (§1 step 2) allows it. Continue
  E1–E6 and use `start` / `end-of-session` from now on.
- **2026-11-21: `s56-r1.2` = the D-062 noun-ID fix (P1). Take it (stage EF), then redo E3.**
  - **What it is.**
    - Noun lists now have one row per lemma (`nouns-r2`). The r1 lists repeated a lemma tagged both NOUN and PROPN:
      Modern 1,763 rows for 1,734 lemmas.
    - Every silver job must have unique item ids.
    - Noun jobs are named after the list version (`noun-modern-r2`).
    - `annotation/` and `config/` are byte-identical to `s56-r1.1`.
    - The sentence, anchor and worked-example jobs behave exactly as before.
  - **EF (at the start of a session, never while a `step` is running).**
    1. `git status`: if tracked files are modified, STOP (M6).
    2. `git fetch origin --tags`, then `git merge --ff-only s56-r1.2`.
    3. These must all succeed, otherwise STOP (M6):
       - `git diff --quiet s56-r1.1 HEAD -- annotation/ config/`;
       - `git merge-base --is-ancestor s56-r1.1 HEAD`;
       - `uv sync`;
       - `uv run python -m pytest -q` (all pass).
    4. **A `noun-modern` job made before the fix, in any state** (created, in progress, frozen or delivered): keep it,
       and never step, finalize, import into or deliver it. The code refuses it anyway; `loc silver status noun-modern`
       still reads it. If it was already delivered, say so in your next M2 message: Ori records it, and it is never
       merged.
    5. Record EF in `STATE.md`. Your frozen sentence jobs and deliveries are untouched; continue your current
       E4–E6 stage as before.
  - **E3 again, with the corrected list:**
    1. `uv run python -m hebloc loc nouns list --corpus modern --source package --package <your package folder>`
       → `data/loc/nouns/modern/modern-nouns-r2-826929982d/`.
    2. **Check the list.** Its `nouns_to_label.csv` must have **1,668 data rows** (one per lemma) and sha256
       **`155e9b55639d4c4b6eb86e4709fff0db5299deecef4f9e8859da78afb7d0bd4f`**.
       - These are the values of Ori's repo-built list, so a match proves repo = package.
       - Any difference is a STOP (M6); never work around it.
       - The list is shorter than r1 (1,763 rows) because each lemma's NOUN and PROPN evidence is now summed, so the
         85% coverage cut is reached with fewer lemmas.
    3. `uv run python -m hebloc loc silver create --task noun --corpus modern --list data/loc/nouns/modern/modern-nouns-r2-826929982d/nouns_to_label.csv`
       → job `noun-modern-r2`.
    4. `uv run python -m hebloc loc silver import-pass noun-modern-r2 --pass A --from <your earlier proposals CSV> [--confidence-column <name>]`.
       - The result lists `dropped_duplicate`: lemmas that had two proposal rows. They, and lemmas new in r2, are
         labelled by an isolated pass A in the next step.
    5. `uv run python -m hebloc loc silver step noun-modern-r2`, repeated until `finalized` (or `STOP` → M6).
    6. `uv run python -m hebloc loc silver deliver noun-modern-r2 --out data/outbox/efrat-s6 --who efrat` → M2.
- **2026-11-22: `s56-r1.2.1` = D-063 (a launch refused by the usage limit is an outage, not an attempt) + D-064 (the
  corrected pull rule). Take it at the start of your next session (stage ED), never while a `step` is running.**
  - **What it is.**
    - D-063 (code: `src/hebloc/loc/silver.py`, `src/hebloc/cli.py`, tests). A launch that the Claude Code client
      refuses before doing anything (the usage / session limit) used to be filed as a breach, so two refusals raised a
      false SG3 STOP. Now it is kept on file as an outage, it is not an attempt, and `step` prints `WAIT` (exit code 3).
    - D-064 (docs). `annotation/silver/FROZEN_SILVER.json` is Ori's record of the hashes he received. It is not a
      pinned file, so the pull rule (§1 step 2) and the ES check exclude it.
    - The protocol, prompts, guideline, worked examples, anchor ids and `config/` are byte-identical to `s56-r1.1`;
      `pyproject.toml` and `uv.lock` to `s56-r1.2`. Every label rule and QC threshold is unchanged.
  - **ED (at the start of a session, never while a `step` is running).**
    1. `git status`: if tracked files are modified, STOP (M6).
    2. `git fetch origin --tags`, then `git merge --ff-only s56-r1.2.1`.
    3. These must all succeed, otherwise STOP (M6):
       - `git merge-base --is-ancestor s56-r1.2 HEAD`;
       - `git diff --quiet s56-r1.1 HEAD -- annotation/ config/ ':(exclude)annotation/silver/FROZEN_SILVER.json'`;
       - `git diff --quiet s56-r1.2 HEAD -- pyproject.toml uv.lock`;
       - `uv sync`;
       - `uv run python -m pytest -q` (all pass).
    4. **New behaviour.** A `step` that prints `"action": "WAIT"` (exit code 3) was refused by the usage limit. Stop
       stepping and run `step` again after the reset time it prints. It is not a STOP; send no M6.
    5. **An open (not frozen) job whose `QC_STOP.md` was caused by refused launches** (sessions with 0 tool calls):
       run `uv run python -m hebloc loc silver reclassify-outages <job>` once.
       - If it reports a `stop_superseded` file, continue with `step`.
       - Otherwise the STOP stands: M6.
       - Frozen jobs and earlier deliveries are never touched.
    6. Record ED in `STATE.md`, then continue your current stage (E5 or E6) as before.
    7. `annotation/silver/FROZEN_SILVER.json` is now in your checkout. Never edit or use it. When Ori later updates
       only that record, your pull rule treats it as documentation.

## 7. Efrat's `STATE.md` (local: `data/outbox/efrat-s6/STATE.md`, never git)

```
# §6 state — Efrat (local; never in git; travels with each delivery)
Current stage: E<n> — <done | in progress | waiting>
Last session: <date> — <what was done, checks passed>
Deliveries sent: <n>. <date> <jobs> DELIVERY.json sha256 <hash> via <Drive/OneDrive/USB>
Waiting for: <nothing | Ori's decision on QC_STOP <job> | announcement s56-r1.3 | s56-v1 | Ori's review>
Next: start → E<n+1>
```

## 8. Message templates (printed by `end-of-session`)

- **M1 (Ori → Efrat, after P0's push):** "I pushed a documentation-only update (STAGES.md). Type `start`: your Claude
  Code will pull it (your pin still holds). From now on, begin each session with `start` and finish it with
  `end-of-session`."
- **M2 (Efrat → Ori, each delivery):** "Delivery `<n>` (`<jobs>`) is at `<link>`. `DELIVERY.json` sha256 `<hash>`."
  Ori downloads it into `data/incoming/efrat-s6/<n>/` → stage R.
- **M3 (Ori → Efrat, a supplement):** "Supplement `<id>` approved (`<decision>`). Type `start`: it fast-forwards to
  `s56-r1.3` and runs ES."
- **M7 (Ori → Efrat, after P1's push):** "I released `s56-r1.2` (D-062: a fix for duplicate noun IDs in the noun
  lists; the protocol, prompts and guideline are unchanged). Type `start`: it fast-forwards to `s56-r1.2` (stage EF)
  and then redoes E3 with the corrected Modern noun list. Do not use your earlier `noun-modern` job; keep it. Your
  sentence work (E4 on) is not affected."
- **M8 (Ori → Efrat, after P2's push):** "I released `s56-r1.2.1` (D-063: a launch refused by the usage limit is now a
  WAIT, not a breach; D-064: the pull rule ignores my `FROZEN_SILVER.json` record). The protocol, prompts, guideline
  and config are unchanged. At the start of your next session type `start`: it fast-forwards to `s56-r1.2.1` (stage
  ED), then continues your current stage. Never take it while a `step` is running."
- **M4 (Ori → Efrat, R2):** "`s56-v1` is released. Type `start`: it fast-forwards to `s56-v1` and runs E7."
- **M5 (Ori → Adi, R2):** "Type `start` (`docs/ADI_SECTION_5.md`)."
- **M6 (Efrat → Ori, a STOP):** "STOP `<rule>` at `<stage>`: `<message>`; `git describe --tags --always`; `<job>`
  `QC_STOP.md` / `DELIVERY.json`." Efrat then WAITs for Ori's project-level decision.

## 9. Open items that do not block the next stage

- B1: the code gaps of C0 (supplement jobs, I-2/I-3/I-4, the sense screen, the §6 silver tasks, the class/identity
  audit task and who runs it under D-061). Built at C0, after ★ approval.
- B2: Efrat's Claude Code must support `--restricted` (E1 isolation test; a STOP goes to Ori).
- B3: the confidence-column name of her Modern pass A file (`import-pass --confidence-column`, E3).
- B4: the CHECKPOINT 2 decisions (stage-2 split, the historical test silver), by design at G7.
- B5 (D-064): once O3's `config/` commit is pushed, `config/` differs from Efrat's tag, so her documentation-only pulls
  stop until the next announced tag. Announcements still reach her (`git show origin/main:docs/STAGES.md`). This is
  by design; no action.
