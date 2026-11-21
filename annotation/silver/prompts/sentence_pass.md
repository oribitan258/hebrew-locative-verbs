# SILVER pass: annotate verb instances (S56-v1-g1)

You are an independent AI annotator. Your labels are **SILVER** (`label_source = ai`). They are never human gold.

## Step 0: isolation preflight (mandatory, before anything else)

Try to read these two files with the Read tool. **Both reads must fail.** Never copy, quote or use their content.

1. `{{CANARY_1}}`
2. `{{CANARY_2}}`

Then write `out/preflight.json` as `{"read_1": "denied" | "read", "read_2": "denied" | "read"}`.
If either read succeeded, write only that file and stop: do not annotate.

## Step 1: read the standard

Read `S56_GUIDELINE.md` (the annotation guideline `S56-v1-g1`) completely, then `S56_SILVER_PROTOCOL.md`.
The guideline is the only standard. Apply it exactly.

## Step 2: annotate

`input.csv` has {{N}} rows, one verb instance each:
- `target` is the word in `[[double brackets]]` in `sentence`;
- `words` gives every word with its index;
- `verb_key` and `verb_entries` give the lexicon entries the token was matched to;
- context given: {{CONTEXT}}. If `context_before` and `context_after` exist, they are the previous and next units of
  the same text; use them only to understand the sentence.

For **each row, in the given order**, decide from the sentence itself, as the guideline says:

| Column | Value |
|---|---|
| `is_target_verb` | `Y` / `N` |
| `member` | one entry id from `verb_key` if the context decides it, else empty |
| `locative` | `Y` / `N` / `?` |
| `frame` | `A` / `B` / `NON_LOCATIVE` / `AMBIGUOUS` |
| `do`, `bare_np`, `locatum`, `location` | a word index, or `suffix`, `subject`, `elided`, `none` (guideline §2) |
| `pps` | `idx:prep; idx:prep` (the PP's noun head and the preposition as written) |
| `notes` | a few words at most; never quote more than a few words |
| `confidence` | `high` / `medium` / `low` |
| `evidence_rule` | the guideline step or case that decided it, e.g. `§3.5`, `§4.3`, `§4.11` |
| `abstain_reason` | required when `locative = ?` or `frame = AMBIGUOUS`; else empty |

**Rules:**
- **Abstain rather than guess.** When the sentence does not decide, use `locative = ?` or `frame = AMBIGUOUS` and
  give `abstain_reason`.
- **Never decide the frame by the preposition alone** (guideline §3.6).
- If `is_target_verb = N`, leave every other label column empty.
- **Consistency:** in Frame A the direct object is the `locatum`, and in Frame B it is the `location`. `locative = N`
  goes with `NON_LOCATIVE`. A partitive מן-noun is the `do`, not a PP.

## Step 3: write the output

Write `out/labels.csv` (UTF-8, with a header) with exactly these columns: `{{OUT_COLUMNS}}`.
- One row per input row, in any order.
- Write the file progressively: rewrite it after every 5 rows, so that nothing is lost.
- When all {{N}} rows are written, stop. Do not summarize the content in your final reply: reply only "done".

## Message from the checker (empty unless this is a rerun)

{{MESSAGE}}
