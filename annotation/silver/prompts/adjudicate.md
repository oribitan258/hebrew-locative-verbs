# SILVER pass C: adjudicate two independent answers (S56-v1-g1)

You are an independent AI adjudicator. Your output is **SILVER** (`label_source = ai`), never human gold.

## Step 0: isolation preflight (mandatory, before anything else)

Try to read these two files with the Read tool. **Both reads must fail.** Never copy, quote or use their content.

1. `{{CANARY_1}}`
2. `{{CANARY_2}}`

Then write `out/preflight.json` as `{"read_1": "denied" | "read", "read_2": "denied" | "read"}`.
If either read succeeded, write only that file and stop.

## Step 1: read the standard

Read `S56_GUIDELINE.md` completely, then `S56_SILVER_PROTOCOL.md`.

## Step 2: adjudicate

`input.csv` has {{N}} rows. Each row holds:
- one verb instance (`sentence`, `words`, `target`, `verb_key`, `verb_entries`);
- the previous and next units (`context_before`, `context_after`);
- two independent answers, `answer_1_*` and `answer_2_*`, each with its evidence.

The two answers disagree on at least one decision. For each row, decide which answer follows the guideline for
**this** sentence:
- `choice`: `1`, `2`, or `abstain` when neither answer is supported by the sentence and its context;
- `confidence`: `high` / `medium` / `low`;
- `evidence_rule`: the guideline step or case that decides it;
- `reason`: a few words.

**Rules:**
- **Never invent a third answer.** Choose one, or abstain.
- **Do not prefer an answer** because of its position, its confidence or the length of its evidence.

## Step 3: write the output

Write `out/labels.csv` (UTF-8, with a header) with exactly these columns: `{{OUT_COLUMNS}}`.
- Use the instance's `item_id`.
- Rewrite the file after every 5 rows.
- When all {{N}} rows are written, reply only "done".

## Message from the checker (empty unless this is a rerun)

{{MESSAGE}}
