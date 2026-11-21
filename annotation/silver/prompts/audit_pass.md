# SILVER audit pass: lemma → verb links (D-059 P2 audit, AI audit per D-061)

You are an independent AI auditor. Your verdicts are **SILVER** (`label_source = ai`): an AI audit, not human
validation.

## Step 0: isolation preflight (mandatory, before anything else)

Try to read these two files with the Read tool. **Both reads must fail.** Never copy, quote or use their content.

1. `{{CANARY_1}}`
2. `{{CANARY_2}}`

Then write `out/preflight.json` as `{"read_1": "denied" | "read", "read_2": "denied" | "read"}`.
If either read succeeded, write only that file and stop.

## Step 1: the question

**Each row links a Dicta lemma (`item_id`) to a verb (`base`).** You also get its counts, its tense shares and
`examples` (up to 3 sentences, with the token first).

Write **`correct = Y`** only when the lemma is the **present tense (participle) of the same verb in the same
binyan**, used as that verb. Examples:
- רואה → ראה: `Y`;
- מגיע → הגיע: `Y`.

Otherwise write **`N`**: a different binyan, a different meaning, a noun or adjective, or a wrong base. For example,
מאפשר → אפשר: `N`.

## Step 2: decide every row

Per row, write:
- `correct`: `Y` / `N`;
- `confidence`: `high` / `medium` / `low`;
- `evidence`: a few words.

## Step 3: write the output

Write `out/labels.csv` (UTF-8, with a header) with exactly these columns: `{{OUT_COLUMNS}}`.
- Rewrite the file after every 10 rows.
- When all {{N}} rows are written, reply only "done".

## Message from the checker (empty unless this is a rerun)

{{MESSAGE}}
