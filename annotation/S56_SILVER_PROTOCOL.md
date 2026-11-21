# The SILVER annotation protocol of S56-v1 (`S56-silver-p1`, D-061)

**What it is.** The one protocol for every AI-made label of §5–§6:
- the sentence labels of the frozen samples (Mikra and Modern, every split);
- the paper-example anchor and the guideline's worked examples;
- the noun types;
- the verb-unit links, the paper-verb variant evidence and the 100-link audit.

It was approved by Ori on 2026-11-21 (D-061), with the safeguards SG1–SG3. Ori's repository is the only source: both
computers run the identical, pinned text (tag `s56-r1.1`).

## 1. The principle: every AI label is SILVER

- **What a silver label is.** Every label made by Claude Code carries `label_source = ai`, and every file name and
  report says *silver*.
  - **It is never human gold.** `loc gold check` refuses an AI annotator name.
- **What is reported.** No figure computed against silver is called accuracy, or said to be validated. Silver is
  described only by:
  1. its **reliability**: κ between two independent first-run passes, with a bootstrap 95% interval;
  2. its **agreement with the independent references that exist**: the paper's own frames (Mikra, an upper bound,
     because the model has read the paper), and BHSA for verb identity (Mikra, description only);
  3. its **abstention rate**.
- **How a resolver score is reported.** As "agreement with SILVER labels (AI, two independent passes, adjudicated)
  — not validated accuracy".
- **Humans make no row-level decision.** Ori and Efrat manage the project and approve project-level decisions only.
  There is no human row labelling, no human row review and no human audit.

## 2. Isolation (SG1): every pass runs in an isolated workspace

**What a workspace is.** A pass is labelled in chunks. Each chunk is one Claude Code session in its own folder
**outside the repository**, by default `~/hebloc-silver-ws/<job>-<pass>-a<attempt>-c<chunk>-<random>/`. The folder
is built by `hebloc loc silver step|workspace` and holds only:

| File | Content |
|---|---|
| `input.csv` | The blind input of this chunk only (see below) |
| `S56_GUIDELINE.md` | The annotation guideline (sentence tasks and adjudication) |
| `S56_SILVER_PROTOCOL.md` | This protocol |
| `PROMPT.md` | The fixed prompt of the task (`annotation/silver/prompts/`) |
| `CLAUDE.md` | A minimal pointer to `PROMPT.md` (never the repository's CLAUDE.md) |
| `.claude/settings.json` | Deny rules: no shell, no web, no subagents; no Read or Edit of the repository, `~/.claude` or the session transcripts |
| `out/` | Where the session writes `labels.csv` and `preflight.json` |

**What never enters a workspace:**
- the R2 code, configs, extractor outputs or predictions;
- answer keys (the paper's frames, BHSA);
- the frozen sample files (they hold the stratum);
- any other split;
- any earlier AI label: the other pass, Efrat's earlier noun proposals, earlier silver.

**The only exception** is pass C, the adjudicator: it receives the two context-expanded answers, and only for the
items they disagree on.

**The blind sentence input** has `item_id`, `verb_key`, `verb_entries` (the entries in words), `target`,
`sentence` and `words`. It never has the stratum, the place or reference, the split or the agreement flag. With
context expansion, it adds `context_before` and `context_after`: the previous and next unit of the same document.

**The launch** (`hebloc loc silver step` does it) runs `claude -p` in the workspace folder with:
- `--restricted`: file tools confined to the folder; no shell or web; user, project and local settings ignored;
- `--strict-mcp-config`: no MCP servers;
- `--settings <workspace>/.claude/settings.json`;
- `--permission-prompts none`: anything that would prompt is denied;
- `--disallowedTools Bash PowerShell WebFetch WebSearch Agent Task NotebookEdit`.

It uses the same model for every pass (`opus`, D-061 D-i) and the person's own Claude Code login: no API key, so no
paid API.

**The canary preflight.** Before labelling, the session must try to read two canary files: one inside the
repository's `data/`, and one in a sibling folder of the workspace root.
- Both reads must be **denied**.
- The canary token must not appear in any tool result or output.

**The access log.** After the session, `collect` reduces its transcript (`~/.claude/projects/*/<session>.jsonl`) to
the paths of its tool calls, with no text, and checks that nothing was read or written outside the workspace and
that no forbidden tool succeeded.

**A breach** (a canary read, an access outside the workspace, a forbidden tool, or a missing transcript or
preflight) **discards the chunk.** The chunk is kept on file and flagged, and its items are rerun once in a new
workspace. A second failure is a STOP.

**Before first use on each computer:** `hebloc loc silver isolation-test` must report `ok` (a dummy workspace with
synthetic text).

## 3. The passes and the deterministic decisions

| Task | Passes | Final decision |
|---|---|---|
| `sentence` (corpus × split), `anchor` | A ∥ B (first run, different hash orders) → if the decisions differ: A2 ∥ B2 with context → if they still differ: C (adjudication) | Agree → `agreed` (pass A's row; PPs = those both passes list; confidence = the lower). Agree with context → `agreed_ctx`. Otherwise C chooses (`adjudicated`) or abstains (`abstained`: `locative = ?`, `frame = AMBIGUOUS`) |
| `worked` (the 15 guideline examples) | A | Compliance only: every frame must match (15/15) |
| `noun` (corpus) | A ∥ B | The same type in both passes, with neither confidence `low` → that type; otherwise `UNCLEAR` (`abstained`, merged as UNCLEAR so the uncertainty stays explicit). At merge, a lemma typed differently in two corpora → `UNCLEAR` (`cross_corpus_conflict`, both types in `note`) |
| `unit` (vunit-v1 P3 rows) | A ∥ B | A link only when both passes `accept` the **same** base and neither confidence is `low`; otherwise no link (the lemma stays its own unit) |
| `variant` (P5) | A ∥ B | Evidence only (both answers and whether they agree); `lexicon-v2` is Ori's Phase C decision |
| `audit` (the 100 P2 links) | A, which never sees the P2 rule | ≥ 95 `Y` → the automatic links come into force; otherwise they are withdrawn (D-059). Reported as an AI audit |

**The decision fields** of a sentence item are `is_target_verb`, `member`, `locative`, `frame`, `do`, `bare_np`,
`locatum` and `location`. Two answers agree when all of them are equal.

**Abstention is a valid outcome.** An annotator writes `locative = ?` or `frame = AMBIGUOUS` with an
`abstain_reason` when the sentence does not decide. Never a guess.

**Efrat's earlier Modern noun proposals** (pass A, made before this protocol) may be imported as pass A
(`loc silver import-pass`, D-061 D-f). Their provenance is recorded, and pass B never sees them.

## 4. QC and pre-registered STOP thresholds

**Checked for every job:**
- **format:** `loc gold check`'s row rules;
- **consistency:**
  - `is_target_verb = N` leaves the rest empty;
  - `NON_LOCATIVE` ⇔ `locative = N`;
  - Frame A: the direct object is the `locatum`; Frame B: it is the `location`;
  - `locatum` ≠ `location`;
  - a partitive object is not also a PP;
  - an abstention has a reason;
- **κ** between the first-run passes A and B (`is_target_verb`, `locative`, `frame`), on all items and on the 60
  agreement items, with bootstrap 95% intervals;
- the statuses, the abstention share, the share of rows that failed the format check, and the breaches.

**STOP thresholds:**

| # | STOP when |
|---|---|
| T3 | Worked examples below 15/15 after one fresh rerun |
| T4 | Frame κ (first-run A vs B) below 0.6 in a split |
| T5 | More than 5% of a split's items failed the format/consistency check after their rerun |
| — | Abstention above 30% in a split after the abstention recovery |
| — | Technical failure or breach twice for the same items |

## 5. Recovery (SG3): pre-registered; every attempt kept and reported, none selected

| Failure | Automatic recovery | Still failing |
|---|---|---|
| A session crash, or a missing chunk or row | Rerun those items once in a new workspace | STOP |
| An isolation breach | The chunk is discarded (kept, flagged); one rerun in a new workspace | STOP |
| Format or consistency errors in some rows | One rerun of those rows, with the checker's message. Still invalid → `abstained` (`qc_format`) | > 5% of the split → STOP |
| Worked examples < 15/15 | One fresh rerun of all of them | STOP |
| A and B disagree (the normal path) | A2 ∥ B2 with context → C | Abstention is a valid outcome |
| Abstention > 30% in a split | A3 ∥ B3 with context on the items both passes abstained on. They agree on a non-abstaining answer → `agreed_ctx`; otherwise the items stay abstained | STOP |
| Frame κ < 0.6 | None changes κ: **there is no rerunning to raise agreement**. The silver is still completed (context, C) | STOP |

**A STOP writes `QC_STOP.md`** with the numbers, an automatic diagnostic, and the only options, which are
project-level:
1. accept the split with its reliability stated (`finalize --accept-stop <decision id>`);
2. restrict the primary analysis to `agreed` items;
3. a protocol revision, only for splits not yet annotated, and for dev only if no dev silver has been read;
4. drop the split from the primary result.

**Nothing proceeds until Ori decides, and no option is human row labelling.**

## 6. Freeze, hash, never revise (SG2)

- **`finalize` freezes a job.** It writes the final file and `qc.json`, then `FROZEN.json` with the hashes of the
  final file, the protocol, the guideline, the prompts and the git state.
  - A frozen job is never rebuilt, rerun or re-finalized, and no command edits silver rows.
- **Only frozen jobs are delivered** (`loc silver deliver`, with `DELIVERY.json` holding the sha256 of every file).
- **On Ori's computer, `loc silver receive` verifies the hashes without printing any content.** It stores the files
  and records them in `annotation/silver/FROZEN_SILVER.json` (ids and hashes, committed) **before** any read:
  - dev: before Phase C;
  - validation: before the variant choice;
  - test: before the final test.
- **The scorer refuses** a silver file that is not frozen or whose hash differs from that record.
- **A defect found after a freeze is reported, never fixed in the rows.** A fatal defect is a STOP, and Ori may drop
  the split from the primary result.

**The pinned protocol.** The protocol, the prompts and the guideline are pinned at `s56-r1.1`. After the developer
has read any dev silver, they cannot change for validation or test. Efrat does not pull between `s56-r1.1` and the
end of her deliveries.

## 7. Separation of annotation and development

**The annotator is Efrat's Claude Code** for all sentence silver (both corpora), the anchor and the worked examples.
Its sessions are the isolated workspaces of §2. Her coordinating session builds and launches them, and never labels.

**The developer is Ori's Claude Code.** It never annotates sentences, and:
- it reads **only dev silver** (and the paper examples);
- validation is read once, by `loc score --choose`;
- test is read once per corpus, by `loc score --final-test`, from its own folder.

Ori's computer makes the noun types for Mikra and the historical corpora, the unit links, the variant evidence and
the audit. Each is in isolated workspaces too, and the noun types and unit map are frozen before any dev silver is
read.

## 8. Privacy and git

- **What stays in `data/` (gitignored):** every file that quotes corpus text. That is job inputs (`items.json`),
  workspaces, transcripts, pass files and final silver label files. They travel only by Drive, OneDrive or USB
  (`data/outbox/<name>/silver/`).
- **What is in git:**
  - this protocol;
  - the prompts;
  - `annotation/silver/worked_examples.csv` (its texts are already in the guideline);
  - `annotation/silver/anchor_ids.csv` (instance keys and entry ids, no frames);
  - `annotation/silver/FROZEN_SILVER.json` (ids and hashes).

## 9. Commands

```
uv run python -m hebloc loc silver isolation-test                     # SG1 check on this computer (once)
uv run python -m hebloc loc silver create --task sentence --corpus modern --split dev --sample <sample folder>
uv run python -m hebloc loc silver create --task worked
uv run python -m hebloc loc silver create --task anchor               # Mikra; needs annotation/silver/anchor_ids.csv
uv run python -m hebloc loc silver create --task noun --corpus modern --list <nouns_to_label.csv>
uv run python -m hebloc loc silver import-pass noun-modern --pass A --from <proposals.csv>   # D-061 D-f
uv run python -m hebloc loc silver step <job>       # the next automatic step; repeat until "finalized" or "STOP"
uv run python -m hebloc loc silver status <job>
uv run python -m hebloc loc silver deliver <job> [<job> ...] --out data/outbox/efrat-s6
uv run python -m hebloc loc silver receive <delivery folder>          # Ori: verify + record hashes (no content)
```
