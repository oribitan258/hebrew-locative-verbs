# SILVER pass: verb-unit links (D-059 P3, vunit-v1)

You are an independent AI annotator. Your decisions are **SILVER** (`label_source = ai`), never human review.

## Step 0: isolation preflight (mandatory, before anything else)

Try to read these two files with the Read tool. **Both reads must fail.** Never copy, quote or use their content.

1. `{{CANARY_1}}`
2. `{{CANARY_2}}`

Then write `out/preflight.json` as `{"read_1": "denied" | "read", "read_2": "denied" | "read"}`.
If either read succeeded, write only that file and stop.

## Step 1: the question

Dicta sometimes gives one Hebrew verb several lemmas:
- the present tense gets the participle as its lemma (ראה / רואה);
- a passive or reflexive gets its own lemma (מסר / נמסר).

A verb unit is **one lexeme**, that is, one root in one template:
- Simple = qal + nif'al;
- Intensive = pi'el + pu'al + hitpa'el;
- Causative = hif'il + hof'al.

**Each row is one Dicta lemma (`item_id`) with candidate bases.** Each candidate is shown as base (kind, template,
rule, n).

- **`accept`** only when the lemma is the **same lexeme** as exactly one candidate base, in the same template: its
  present tense, its passive, its reflexive or middle, or an inflected form of it. Write that base in `base`.
- **`reject`** when it is a different lexeme, or a separate meaning that is used on its own:
  - נכנס "enter" is not כנס "gather";
  - נשבע "swear" is not שבע "be sated";
  - נראה is not ראה when "seem" dominates.
- **When mixed or unsure: `reject`.** The lemma then stays a separate verb, the conservative choice. Never merge two
  verbs.

**Examples:**
- Accept: רוצה → רצה; נמסר → מסר.
- Reject: נכנס → כנס; נשבע → שבע.

Use the counts, the tense shares and `examples` (up to 3 sentences, with the token first).

## Step 2: decide every row

Per row, write:
- `decision`: `accept` / `reject`;
- `base`: required for `accept`, exactly as written in `candidates`;
- `confidence`: `high` / `medium` / `low`;
- `evidence`: a few words.

## Step 3: write the output

Write `out/labels.csv` (UTF-8, with a header) with exactly these columns: `{{OUT_COLUMNS}}`.
- Rewrite the file after every 10 rows.
- When all {{N}} rows are written, reply only "done".

## Message from the checker (empty unless this is a rerun)

{{MESSAGE}}
