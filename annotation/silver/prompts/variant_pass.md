# SILVER pass: paper-verb lemma variants (D-059 P5; evidence for Phase C I-1)

You are an independent AI annotator. Your decisions are **SILVER** (`label_source = ai`). They are only
**evidence**: the lexicon (`lexicon-v2`) is changed only by Ori's decision in Phase C.

## Step 0: isolation preflight (mandatory, before anything else)

Try to read these two files with the Read tool. **Both reads must fail.** Never copy, quote or use their content.

1. `{{CANARY_1}}`
2. `{{CANARY_2}}`

Then write `out/preflight.json` as `{"read_1": "denied" | "read", "read_2": "denied" | "read"}`.
If either read succeeded, write only that file and stop.

## Step 1: the question

**Each row is a Dicta lemma** that looks like a variant (present tense, passive or middle) of a verb in the paper's
lexicon. The `candidates` column shows the lexicon entries it may belong to, as entry (kind, template, rule, n).

Decide one of:
- **`dicta_lemma`**: the lemma is a form of exactly one entry and is used for that verb. Write the entry in `entry`,
  and `voice` = `active`, `passive` or `middle`.
- **`shared_lemma`**: the lemma covers this entry **and** another verb or another meaning in real use. Write the
  entry in `entry`, and explain in `evidence`.
- **`exclude`**: the lemma is not this verb, or its uses are mostly another meaning.

**When unsure: `exclude`**, with `low` confidence.

## Step 2: decide every row

Per row, write `decision`, `entry` (empty for `exclude`), `voice`, `confidence` (`high` / `medium` / `low`) and
`evidence` (a few words).

## Step 3: write the output

Write `out/labels.csv` (UTF-8, with a header) with exactly these columns: `{{OUT_COLUMNS}}`.
- Rewrite the file after every 10 rows.
- When all {{N}} rows are written, reply only "done".

## Message from the checker (empty unless this is a rerun)

{{MESSAGE}}
