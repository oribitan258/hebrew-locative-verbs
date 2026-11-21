# Proposal v2: an AI-only annotation workflow for S56-v1 (for Ori's approval)

**From:** Efrat's Claude Code, on Efrat's computer, 2026-11-20. Repo at `s56-r1-1-g64f62aa`, clean tree.
**Supersedes:** proposal v1 of the same day, which Ori did not approve because it kept manual audits and human
labels.
**Status: PROPOSAL ONLY. Nothing in it has been executed.**
- No gold or silver sentence label exists.
- No test sheet has been opened.
- No tracked file, config, shared document or frozen dataset has been changed.
- Nothing was committed or pushed.

**Ori's requirements this version follows:**
1. Zero manual data work for Ori and Efrat. Humans approve plans, methodology, checkpoints and deliverables.
2. Keep the approved S56-v1 plan, and propose only the smallest changes needed.
3. Ori's repo is authoritative: proposal only.
4. A complete automated workflow.
5. AI labels are always **SILVER**, never gold.
6. No paid API.

---

## 1. What stays exactly as approved

- **Kept as approved:**
  - the objectives and the §5–§6 methodology of S56-v1: frames, roles, resolver variants R0/R1/R2, classes, the
    identity test, the swap test and the statistics (EFRAT_SECTION_6 §5);
  - the output tables and manifests (I3, I5);
  - the stage order: R1 (Phase A, done), then Phase B (R2 code, **not started**), then CHECKPOINT 2 (`s56-v1`),
    then stage 2 and §6;
  - the STOP checkpoints.
- **Role division kept:** Ori leads §5, Efrat does §6 on Modern, Adi joins in stage 2. Only the *annotation* task
  changes hands, from humans to Claude Code (§6 below).
- **R1 outputs reused unchanged:**
  - lexicon, guideline, sampler;
  - the frozen samples `modern-r1b-5fbb5e22e7` (400) and `mikra-r1b-1cd4ee9802` (387, including 60 agreement
    items), both verified with `items_match = true`;
  - the noun list `modern-nouns-r1-826929982d`.
- **Earlier work reused:**
  - Efrat's 1,763 Modern noun proposals (`noun_types_modern_PROPOSED.csv`, sha256 `43e9badb…45cd`);
  - the open issues OI-1/OI-2 (D-058).
- **Unchanged rules:** the splits (dev / validation / test), "validation once, test once", the supplemental sampling
  procedure, no BHSA in §6, no retuning against BHSA, only Ori edits `config/`, and partners never commit.

## 2. The one principle that replaces "human gold"

**Every label made by Claude Code is SILVER.** It is marked as such in the data, the file names and the report.

- **No accuracy claims.** Since no human labels will exist, **no figure may be called accuracy against independent
  gold.** The report describes the silver only by:
  1. its **reliability**: agreement between two independent AI passes;
  2. its **agreement with the only independent references that exist**: the paper's own labelled examples
     (Mikra), and BHSA for verb identity (Mikra, description only);
  3. its **abstention rate**.
- **How resolver scores are reported.** Every §5/§6 resolver score is "agreement with silver", next to those three
  numbers.

## 3. The AI-only workflow

### W0. The silver protocol (one file, used by every silver task)

Ori's Claude Code adds `annotation/S56_SILVER_PROTOCOL.md`. It fixes:

- **Input** the annotator may see:
  - `sentence` and `words`;
  - `verb_key`, only to answer `is_target_verb`;
  - the guideline `S56-v1-g1`.

  **Not** `stratum`, `where`, Dicta's lemmas, POS, trees, or any extractor or resolver output.
- **Output:** the guideline's columns, plus:
  - `confidence` (high / medium / low);
  - `evidence`: which words and which guideline rule decided it (§3 step or §4 case number);
  - `abstain_reason`.
- **Abstention.** When the sentence does not decide, the annotator writes `locative = ?` or `frame = AMBIGUOUS`,
  with a reason. Never a guess.
- **Two independent passes, then deterministic adjudication.**
  - **Pass A** and **pass B** run in separate fresh sessions. Each sees the items in a different hash order, and
    pass B never sees pass A.
  - A script compares the passes field by field:
    - **Agree** → `silver_status = agreed`.
    - **Disagree** → **pass C**, a third fresh session, sees both answers with their evidence and either picks one
      (`adjudicated`) or abstains (`abstained`: `locative = ?`, `frame = AMBIGUOUS`).
  - Every pass is kept, so nothing is overwritten.
- **Freeze.** After a split is finished, its three pass files and the final file are hashed into `DELIVERY.json`.
  They are never changed again.

### W1. Modern sentences: 400 items (`modern-r1b-5fbb5e22e7`)

| Step | Who | What |
|---|---|---|
| 1 | Efrat's Claude | Passes A and B on **dev**, then validation, then test. Each split is completed and frozen before the next is opened |
| 2 | Script | Adjudication list → pass C → final file per split |
| 3 | Script | `loc gold check … --annotator claude_code --label-source ai` writes the text-free files `modern_<split>_silver.csv` |
| 4 | Script | QC report (W5) |

The ישב.I items (guideline §4.15) are judged like any other: locative, non-locative, or `?` with a reason.

### W2. Mikra: the frozen 387 items, including the 60 agreement items (`mikra-r1b-1cd4ee9802`)

- **The same W0 protocol.** Ori would otherwise have to annotate them, and requirement 1 rules that out.
- **The annotator is Efrat's Claude, not Ori's.** Ori's Claude writes the resolver (Phase B), so it must not also
  make the labels the resolver is measured against (§5).
- **The 60 agreement items keep their purpose, measured automatically.** They were meant to measure human–human
  agreement (κ). Without humans that cannot be measured, and the report says so. They become the fixed subset on
  which the pass A / pass B κ is reported for both corpora, so the agreement design stays comparable.
  - The same applies to the 60 Modern agreement items.

### W3. Noun typing

| List | Pass A | Pass B | Merge |
|---|---|---|---|
| Modern, 1,763 rows | **Reused:** the existing proposals | Efrat's Claude, fresh session, blind to pass A, same category scheme (`code/build_noun_proposals.py`) | Deterministic (below) |
| Mikra, 991 rows | Efrat's Claude | Efrat's Claude, separate session | Same |
| Hazal / Medieval / Haskala (≈ 113 new, `--exclude-typed`, after the Modern merge, as in option A) | Efrat's Claude | Efrat's Claude | Same |

**The deterministic merge rule:**
- A and B agree, and neither has low confidence → that type.
- Otherwise → **UNCLEAR** (abstention), with both proposals in `note`.

**Never hand-edited.** The merged file carries `proposed_by = claude_code`, `reviewed_by = auto-qc:<qc_id>` and
`review_mode = automated`. Ori runs `loc nouns merge` as a project-management approval of the whole file, not of
rows.

**Cross-corpus check.** A lemma typed differently in two corpora is listed. It is allowed, since senses differ
across periods, but it is reported.

**Pass A (Modern) result, for reference:**
- 1,763 rows: LOCATION 274, LOCATUM 386, ANIMATE 241, UNCLEAR 862 (50.5% of argument tokens).
- Confidence: 980 high, 734 medium, 49 low.
- 36 rows are probable Dicta lemma artifacts.

**Typing conventions Ori should confirm before pass B** (they are applied, not decided):
1. Collectives and organisations are ANIMATE.
2. Institutions with a physical seat are LOCATION.
3. Time, event and quantity nouns, and partitive heads, are UNCLEAR.
4. Transferable abstract content is LOCATUM.

Any change to these is a methodology decision for Ori. Pass B then follows it.

### W4. Verb-unit linking and paper-verb variants (Phase B planning inputs; Ori's Claude owns them)

1. **OI-1, linking participle and passive lemmas to their verb** (e.g. אומר → אמר, דובר → דיבר, נעשה → עשה).
   - A deterministic read-only script uses Dicta's `tense` and `feats`, plus the R1 form generator (`loc/morph.py`),
     to test whether a lemma string is a generated form of another verb lemma.
   - Output: a mapping table with `method`, evidence counts and `confidence`. **Ambiguous cases get no link**
     (abstention).
   - The policy (link or keep separate) is decided by Ori. It enters R2 with its own decision (D-058).
2. **OI-2, VERB-tagged existential and modal items** (יש, אין, אפשר, היי…).
   - A script lists them with frequencies and feature profiles.
   - Proposal: a flag such as `non_lexical_verb`. They stay in the tables and are labelled, never dropped.
3. **Paper-verb variants (`dicta_lemmas`, forms) and the lexicon review** (`lexicon_review.csv`, which was 2–4 h of
   Ori's manual time).
   - Ori's Claude reviews every entry, supported by the automated checks that already exist: `lexicon check
     --data`, near misses, paper references found, and blocking lemmas.
   - It writes one finding per entry with its evidence.
   - Lexicon changes stay Ori-approved decisions.
4. **Phase C identification improvements**, as already required by D-057 #18:
   - decided on the **dev silver** (`is_target_verb`, `member`) plus the paper's examples;
   - the variant choice read once on validation silver; test silver read once, with `--final-test`;
   - no retuning against BHSA.

### W5. Automated quality controls (all scripted and reproducible; a failure is a STOP)

| Check | What it tests | Threshold |
|---|---|---|
| Format | `loc gold check`: every row valid, every index exists, values in range | 0 problems |
| Internal consistency | e.g. frame A ⇔ `do` is the `locatum`; frame B ⇔ `do` is the `location`; `locative = N` ⇔ `NON_LOCATIVE`; instruments never Locatum/Location | 0 violations |
| Worked examples as unit tests | The guideline's 6 Biblical and 9 Modern worked examples, annotated blind by the same protocol | **15/15**, else STOP: the annotator does not follow the guideline |
| Reliability | κ between pass A and pass B for `is_target_verb`, `locative` and `frame`, per corpus and split, with a 95% interval; also on the 60 agreement items | Reported. If frame κ < 0.6, STOP and report (pre-registered) |
| External anchor 1: the paper's labelled examples (Mikra, about 110 instances with the paper's a/b frame, mapped in the lexicon) | Frame agreement of the silver protocol with the paper's own analysis. The 6 guideline examples are excluded | Reported with Wilson 95% interval. Never used to tune the protocol after it is frozen |
| External anchor 2: BHSA (Mikra, verb identity only) | `is_target_verb` against BHSA lexeme and stem, as a **description** (allowed by D-057: "reported as a description, never used to choose") | Reported only |
| Calibration | Agreement rate by `confidence` level, on anchor 1 | Reported |
| Abstention | Shares of `?`, `AMBIGUOUS` and `abstained`, per split | Reported. Above 30% is a STOP for Ori's decision |
| Leakage | Each split hashed and frozen before the next opens; access log of which session read which file | Every hash matches at delivery |

## 4. Research integrity: the limitations that go into the report (§9) and §8

1. **No independent human gold exists.** Precision, recall and F1 in §5/§6 measure **agreement with silver**.
2. **Shared blind spots.** The silver annotator and the resolver's author are both Claude models. Shared blind spots
   are likely, and they cannot be measured from the silver itself.
3. **Anchor 1 is Mikra-only and prototypical.** The paper's examples are clean textbook cases. The annotator has also
   read the paper, so agreement there is an upper bound. **Modern has no external anchor**: Modern silver quality is
   shown only by reliability, internal consistency and abstention.
4. **Pass agreement is reliability, not validity.** Two passes of one model can agree on the same error.
5. **What is disclosed.** All AI use is disclosed as AI-generated annotation, approved at the project level by Ori,
   with no row-level human review.

## 5. Separation of annotation and evaluation (leakage control)

- **The annotator is Efrat's Claude Code**, in dedicated sessions. Before the test silver is frozen, it never opens
  extractor or resolver code, outputs or scores.
  - Because Phase B has not started, **all silver (both corpora, all splits) is produced and frozen before any
    resolver exists.** This is the strongest guarantee available.
- **The developer is Ori's Claude Code.** It reads only dev silver and the paper's examples. Validation silver is
  read once, for the pre-registered R0/R1/R2 choice. Test silver is read once, by the `--final-test` scorer.
- **Test silver files are stored apart.** `annotation/silver/test/` is read by no loader except `--final-test`, a
  code guard tested in `test_loc.py`.
- **Order constraint:** CHECKPOINT 2 can only be passed after the test silver is frozen and delivered.

## 6. Minimal changes to existing decisions, code and documentation

**A new decision D-059 ("AI-only silver annotation")** amends the following, and nothing else:

| Existing rule | Conflict | Smallest change |
|---|---|---|
| D-054 AI tools: Claude Code "never for gold labels"; noun types "a human accepts or corrects every row" | AI labels; no human review | Allow Claude Code to make **silver** labels and noun types under W0/W3. Keep the bans on run-time labelling, paid APIs, and calling AI labels gold |
| D-055: §6 candidates reviewed manually by Efrat | Manual review | Candidate review by Efrat's Claude Code, with evidence, `label_source = ai` |
| D-056 / EFRAT_SECTION_6 §5.8 table: annotators Ori (Mikra), Efrat (Modern), both (agreement) | Manual annotators | Annotator = Efrat's Claude Code (W0), for both corpora. The agreement items become the fixed κ subset |
| D-057 #7 (60 agreement items for Cohen's κ, human–human) | No second human | κ between pass A and pass B on the same items |
| D-057 #8: "Claude Code does not open test sheets or labels during development" | The annotator must read the test sheets | Applies to **the developer's** Claude Code. The annotator reads test sheets only to label them, before Phase B |
| D-057 #10: "every row must have a human reviewer" | No row review | `review_mode = automated` with a QC record |
| D-057 #18 / S56_R1 §0.1(3): identification "validated on the dev split of the human gold" | No human gold | "… of the silver" |
| D-057 #20 / S56_R1 §0.1(2): ישב.I "labelled by the human annotator" | AI annotator | "… by the silver annotator" |

**Passages to update (by Ori's Claude Code):**

| File | Place |
|---|---|
| `docs/decisions.md` | Add D-059; mark the amended items of D-054, D-055, D-057 |
| `docs/EFRAT_SECTION_6.md` | §3 table (Ori/Efrat annotation tasks); §5.4 (noun types reviewed); §5.8 (title, "Gold is human only", annotator table); §5.9(2) (manual review); §6 (AI tools, "Never: Claude Code labels gold"); §7 I1 (`reviewed_by`, `review_mode`) and I4 (`label_source`, `pass`, `silver_status`, `confidence`, `evidence`); §9.2 steps 4–8; §10 (outbox: `silver/` instead of `gold/`); §12 S8 → "presents AI labels as human gold, changes frozen silver, or lets the developer read test silver" |
| `annotation/S56_GUIDELINE.md` | Header l. 3, 10–14: the guideline is the annotation standard for the silver annotator; human-only clause replaced by a pointer to the silver protocol |
| `annotation/S56_SILVER_PROTOCOL.md` | **New** (W0) |
| `docs/S56_R1.md` | §0.1 items 2–3; §2 l. 279; §3 agreement row; §4 l. 365–366; §6 workload table and option (e); §8 items 7, 8, 10, 18, 20 (mirror D-059) |
| `docs/HANDOFF.md` | l. 180 ("Ori annotates the human gold") and the stage-3 next steps |
| `CLAUDE.md` | Team, Efrat branch: "no AI pre-labelling of gold" → "no AI label presented as human gold; silver per D-059" |
| `src/hebloc/loc/gold.py` | `check_sheet`: `--label-source ai\|human`, the pass/adjudication columns, silver output names, the test-split guard |
| `src/hebloc/loc/silver.py` | **New:** pass-order hashing, field-wise comparison, adjudication list, final file, QC checks of W5 |
| `src/hebloc/loc/nouns.py` | `merge`: accept `review_mode = automated` with `reviewed_by = auto-qc:<id>` and a QC record; W3 merge rule |
| `src/hebloc/cli.py` | `loc silver order\|compare\|finalize\|qc` |
| `tests/test_loc.py` | Keep the test that refuses `reviewed_by = claude_code` as a *human*; add tests for automated review, silver labelling, the consistency checks and the test-split guard |

## 7. Responsibilities

| Ori (manager) | Ori's Claude Code (developer, authoritative repo) | Efrat (manager) | Efrat's Claude Code (silver annotator) |
|---|---|---|---|
| Approves this proposal, D-059, each checkpoint and the deliverables. Moves the outbox folder | Writes D-059, the docs and code of §6, and the silver protocol; tests; pushes. Owns W4 (OI-1, OI-2, lexicon review, Phase C). Develops Phase B on dev silver only. Runs `--final-test` once | Approves her session's steps, sends the outbox folder | Runs W1, W2 and W3 strictly from the pushed protocol. Runs the W5 QC. Produces delivery folders. Never reads R2 code or outputs before the test silver is frozen. Never edits tracked files |

## 8. Synchronization and handoff sequence

1. **Efrat → Ori:** sends this file (Drive, OneDrive or USB).
2. **Ori** approves it, or asks for changes.
3. **Ori's Claude Code:**
   - writes D-059;
   - updates the passages of §6 and adds the silver protocol;
   - implements `silver.py` plus the changes to `gold.py`, `nouns.py` and `cli.py`, with tests;
   - releases a tag (suggested `s56-r1.1`) and pushes.
   - The frozen samples and R1 outputs are untouched: `FROZEN_SAMPLES` must still match.
4. **Efrat's Claude Code:**
   - `git status` (STOP if tracked files are modified), `git pull`;
   - checks that the tag `s56-r1.1` and D-059 are present;
   - `uv sync`, tests, `loc lexicon check`;
   - re-verifies both frozen samples (`items_match = true`).
5. **Efrat's Claude Code:** the W5 unit test on the 15 worked examples. Failure → STOP.
6. **W3 Modern nouns** (pass B, then merge), then **W1 Modern dev → validation → test**, then **W2 Mikra dev →
   validation → test**. Each split is frozen, QC'd and hashed before the next is opened.
7. **Delivery:** `data/outbox/efrat-s6/` with `silver/`, `noun_types_modern.csv`, `noun_types_mikra.csv`, the QC
   reports, the pass files and `DELIVERY.json`. Efrat sends it.
8. **Ori's Claude Code:**
   - verifies the hashes;
   - merges the noun types (`loc nouns merge`, automated review mode);
   - stores the silver;
   - makes the historical noun lists;
   - Efrat's Claude Code then types them (W3), as in steps 6–7.
9. **Ori's Claude Code** plans Phase B (Plan Mode, Ori approves), with OI-1/OI-2 policies from W4, develops on dev
   silver, reaches CHECKPOINT 2 (`s56-v1`).
10. **Efrat's Claude Code** runs §6 (EFRAT_SECTION_6 §9.3) unchanged, except that its candidate review is automated
    (D-059).

## 9. STOP conditions (in addition to EFRAT_SECTION_6 §12)

| # | Stop when |
|---|---|
| T1 | D-059 or the tag `s56-r1.1` is missing after `git pull`. Nothing of W1–W3 runs before them |
| T2 | A frozen sample no longer gives `items_match = true` |
| T3 | The annotator fails any of the 15 worked examples |
| T4 | Frame κ between passes is below 0.6, or abstention is above 30%, in any split |
| T5 | A format or consistency check fails |
| T6 | A step would read extractor or resolver code or outputs before the test silver is frozen; or the developer's session would read test silver outside `--final-test` |
| T7 | A file would present silver as gold, or omit `label_source` |
| T8 | A step would edit a tracked file, `config/` or a frozen dataset on Efrat's computer, or commit or push |
| T9 | A paid or external API would be used |

**Blocked until Ori approves and pushes D-059:**
- all sentence silver (Modern 400, Mikra 387);
- noun pass B and the merges;
- any change to `loc nouns merge`;
- W4 results being used as policy;
- automated §6 candidate review.

**Allowed now and already done:** the R1 checks, the frozen samples, the Modern noun list and the Modern noun pass A
(proposals).

## 10. Changes from v1

- **Removed:**
  - every manual task: the noun audit (A), Ori's 60 human Modern labels as an anchor, Efrat's manual Mikra 60, and
    option B2;
  - row-level human sign-off.
- **Added:**
  - the second pass and deterministic adjudication;
  - the paper-example and BHSA anchors (description only);
  - the worked-example unit test;
  - internal consistency checks, pre-registered STOP thresholds and the leakage order;
  - Mikra silver (387) and noun typing for all corpora;
  - the W4 automation of OI-1, OI-2 and the lexicon review.
