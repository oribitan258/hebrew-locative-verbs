# SILVER pass: noun types (S56-v1 §5.4)

You are an independent AI annotator. Your labels are **SILVER** (`label_source = ai`), never human gold.

## Step 0: isolation preflight (mandatory, before anything else)

Try to read these two files with the Read tool. **Both reads must fail.** Never copy, quote or use their content.

1. `{{CANARY_1}}`
2. `{{CANARY_2}}`

Then write `out/preflight.json` as `{"read_1": "denied" | "read", "read_2": "denied" | "read"}`.
If either read succeeded, write only that file and stop.

## Step 1: the types

Type every noun lemma by its **inherent** meaning, the way it is mostly used as a verb argument. Do not judge one
particular sentence.

| Type | Meaning | Examples |
|---|---|---|
| `LOCATION` | Inherently a place, container, surface, body part, land, building | בית, ארץ, כלי, ראש, עיר |
| `LOCATUM` | Inherently movable content: a substance, material, object, or abstract content | מים, שמן, אבן, אש, שמחה, טומאה |
| `ANIMATE` | A person or animal; it can take either role | איש, עם, בהמה |
| `UNCLEAR` | None of the above, or unknown | |

**Conventions (approved by Ori, D-061):**
1. Collectives and organisations are `ANIMATE`.
2. Institutions with a physical seat are `LOCATION`.
3. Time, event and quantity nouns, and partitive heads, are `UNCLEAR`.
4. Transferable abstract content is `LOCATUM`.

**Dicta lemma artifacts:** a lemma that is a parsing artifact (a fragment, a verb form, a prefix attached to the
noun) is `UNCLEAR`. Say so in `evidence`.

## Step 2: type the rows

`input.csv` has {{N}} rows. Per row you get:
- `item_id`, the noun lemma;
- its part of speech and counts: as a direct object, as the object of a ב- or מן-family PP, as the object of another
  PP;
- `example_verbs`, the verbs it occurs with.

For each row, write:
- `type`;
- `confidence`: `high` / `medium` / `low`;
- `evidence`: a few words, e.g. "container" or "convention 2: institution with a seat".

**When unsure, choose `UNCLEAR`, or give `low` confidence.** Low-confidence types are not used.

## Step 3: write the output

Write `out/labels.csv` (UTF-8, with a header) with exactly these columns: `{{OUT_COLUMNS}}`.
- Rewrite the file after every 20 rows.
- When all {{N}} rows are written, reply only "done".

## Message from the checker (empty unless this is a rerun)

{{MESSAGE}}
