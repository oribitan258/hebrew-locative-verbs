# Pilot audit: instructions for annotators

The sheets contain **Dicta's automatic analysis only**. Every judgment column is empty and must
be filled in by a person. Please do not copy Dicta's answer into a judgment column without
checking it.

## What to audit

150 units: 30 per corpus. For each corpus, 25 come from the random part of the pilot sample and
5 from its targeted hard cases. Only units of up to 60 Dicta words were eligible, so that a
person can check them. Longer sentences are therefore not represented in this audit, and the
report states this.

Two sheets, both UTF-8 with BOM, so Excel shows Hebrew correctly:

| File | Rows | Use |
|---|---|---|
| `pilot_audit_words.csv` | one per Dicta word (~3,000) | **Main sheet.** Mark each layer of each word |
| `pilot_audit.csv` | one per unit (150) | Unit-level checks, counts and notes. The `dicta_analysis` column shows the whole analysis in one cell |

## Word sheet: `pilot_audit_words.csv`

Each row shows:
- `surface`: the word as it appears in the text;
- `segmentation`: the prefix and host, e.g. `ו+ב+בית` is shown as `וב+בית`;
- `lemma`, `upos` and `feats` (only Gender, Number, Person and Tense exist);
- `suffix`;
- `head_no` and `head_word` (`0`/`ROOT` = the root);
- `deprel`.

Fill in each column with `y` (correct), `n` (wrong) or leave it empty (not judged / unsure):

| Column | Correct when |
|---|---|
| `seg_ok` | The prefix letters (ו ה ב כ ל מ ש…) are split off correctly, and nothing else is |
| `lemma_ok` | The lemma is the right dictionary entry *for this context* (dictionary form; for verbs, the 3rd person masculine singular past of the word's binyan, as in Modern Hebrew dictionaries) |
| `pos_ok` | The part of speech is right for this context (UD categories: NOUN, VERB, ADJ, ADV, ADP, PRON, PROPN, DET, CCONJ, SCONJ, NUM, AUX, INTJ, PUNCT, X) |
| `feats_ok` | The listed features are right, and no required one is missing (e.g. Person on a finite verb) |
| `head_ok` | The word attaches to the right head word (or is rightly the root) |
| `deprel_ok` | The relation label is right (nsubj, obj, obl, nmod, amod, case, …), judged **only if `head_ok` = y** |
| `comment` | Free text: e.g. "Aramaic", "Biblical sense", "source typo" |

**Historical Hebrew.** Judge by the language of the text, not by Modern Hebrew. If an analysis is
reasonable under Biblical or Rabbinic grammar, mark it correct and, if useful, add a comment.

**Ambiguity.** If several analyses are defensible, mark it correct. If you cannot decide, leave
the cell empty: empty cells are excluded, never counted as correct.

## Unit sheet: `pilot_audit.csv`

| Column | Value |
|---|---|
| `segmentation_ok` | `y`/`n`: is the unit one sensible sentence or verse, not cut in the middle or joined with the next one? |
| `normalization_ok` | `y`/`n`: compared with `text_raw`, did `text_norm` lose or change anything that matters? |
| `main_predicate_ok` | `y`/`n`: is the root of the tree the main predicate of the sentence? |
| `n_*_errors` | Optional counts, if you did not use the word sheet |
| `annotator`, `notes` | Your initials, and anything noteworthy |

## Scoring

```
uv run hebloc pilot audit-score
```
This reports, per corpus and layer, accuracy with 95% Wilson confidence intervals over the cells
humans filled in. Until somebody fills the sheets in, it reports `not yet annotated`. The pilot
report does **not** present any manual accuracy until then.

Please keep a backup of the filled sheets. `hebloc pilot audit` refuses to overwrite sheets that
already contain judgments.
