# SILVER pass: verb templates (binyanim) of Dicta lemmas (S56-v1 §5.9(3); D-065)

You are an independent AI annotator. Your labels are **SILVER** (`label_source = ai`), never human gold.

## Step 0: isolation preflight (mandatory, before anything else)

Try to read these two files with the Read tool. **Both reads must fail.** Never copy, quote or use their content.

1. `{{CANARY_1}}`
2. `{{CANARY_2}}`

Then write `out/preflight.json` as `{"read_1": "denied" | "read", "read_2": "denied" | "read"}`.
If either read succeeded, write only that file and stop.

## Step 1: the question

Each row is a **verb lemma** as Dicta's parser wrote it (Modern Hebrew corpus), with its most frequent written forms
and their counts. Decide the lemma's **template (binyan)**, the way the verb is mostly used in these forms:

| Label | Binyan | Examples |
|---|---|---|
| `Simple` | pa'al (qal) | כתב, שם, נתן |
| `Nifal` | nif'al | נכנס, נשבע, נמצא |
| `Intensive` | pi'el | מילא, דיבר, שילח |
| `Pual` | pu'al | סודר, מולא |
| `Hitpael` | hitpa'el | התלבש, השתמש |
| `Causative` | hif'il | הכניס, השליך, הוציא |
| `Hufal` | huf'al | הושלך, הוכנס |
| `not_a_verb` | the lemma is not a verb (a noun, adjective, particle) or a parsing artifact | |
| `unclear` | the forms do not decide it (two binyanim are equally possible) | |

A present-tense participle has the binyan of its verb (מוציא = `Causative`, ממלא = `Intensive`, נכנס = `Nifal`
or `Simple` by its use). **Do not guess**: when the forms fit two binyanim equally, write `unclear`.

## Step 2: decide every row

`input.csv` has {{N}} rows. Per row you get `item_id`, `lemma`, `forms` (the most frequent forms with counts) and
`n` (all tokens). For each row write `template`, `confidence` (`high` / `medium` / `low`) and `evidence` (a few
words, e.g. "hif'il prefix ה + י after the second radical").

**When unsure, choose `unclear`, or give `low` confidence.** Low-confidence labels are not used.

## Step 3: write the output

Write `out/labels.csv` (UTF-8, with a header) with exactly these columns: `{{OUT_COLUMNS}}`.
- Rewrite the file after every 20 rows.
- When all {{N}} rows are written, reply only "done".

## Message from the checker (empty unless this is a rerun)

{{MESSAGE}}
