# M2: Unit Extraction, Normalization and Provenance (Methodology)

*Date: 2026-11-06. Code: `src/hebloc/{units,segment,normalize,artifacts,versification,data}.py`.
Rule versions: `norm_version = 1`, `segment_version = 2` (M2.1, 2026-11-07; see §8). Real before/after examples:
[`m2_sample_review.md`](m2_sample_review.md).*

## 1. What M2 does (plain English)

The parser needs **one sentence (or one Biblical verse) at a time**, as clean text. The corpus
files contain whole paragraphs, Biblical accents, editorial markup and tokenizer leftovers. M2 cuts
every file into units and produces a cleaned copy of each unit for the parser. It also keeps:

- **the exact original text** of the unit (`text_raw`), never modified;
- **its exact location**: file, line number, and character offsets within that line;
- **a list of every change made** (`norm_flags`), so any cleaning step can be audited, reversed,
  or used to split the statistics.

Nothing is deleted. A unit exists for every non-empty line of every file that contains text,
including out-of-period and duplicate files, which remain distinguishable through the view
columns (D-015).

## 2. Units and identifiers

| Field | Meaning |
|---|---|
| `sent_id` | `<corpus>:<doc_id>:<line_no>:<k>`. Stable, because it is derived from the file path, the line number and the position within the line |
| `line_no` | 1-based line in the decoded source file. Lines are split on `\n` only, the same definition the catalog uses |
| `char_start`, `char_end` | Offsets in that line. `source_line[char_start:char_end] == text_raw`, checked for every unit |
| `ref` | Human-readable reference: `Genesis 2:7`, `Mishnah Beitzah ¶11`, `Mishneh Torah/NASHIM/aishowt/prk_a ¶1`, `Ytext1044001 ¶12.1`, `news/haaretz/0/14178.txt ¶1` |
| `unit_type` | `verse` (Mikra) or `sentence`. Units are always complete; segment v1 also had `chunk` (§8) |

**Mapping a unit back to its source.** `hebloc.data.trace(sent_id)` re-opens the original file
(read-only), takes the line and the character span, and verifies that they equal `text_raw`. Example:

```
mikra:7ed0fd1ad789:113:0  →  Mikra/Tanakh - Torah - Genesis.txt, line 113, chars 0–148  (verified)
RAW : וַיִּ֩יצֶר֩ יְהֹוָ֨ה אֱלֹהִ'ים אֶת-הָֽאָדָ֗ם עָפָר֙ מִן-הָ֣אֲדָמָ֔ה … לְנֶ֥פֶשׁ חַיָּֽה׃
NORM: וייצר יהוה אלהים את האדם עפר מן האדמה ויפח באפיו נשמת חיים ויהי האדם לנפש חיה .
```

## 3. Segmentation: what counts as a unit

| Corpus | Rule | Evidence |
|---|---|---|
| Mikra | One verse per line, never split. References `Book chapter:verse` come from Sefaria's chapter lengths | The per-book sum of chapter lengths equals the file's line count **for all 39 books** (23,206 verses) |
| Hazal, Medieval, Haskala, Modern | Split after `.` `?` `!` (or a run of them, including spaced `! !` and `. . .`), when followed by more text | In a sample, 85% of Hazal lines, 25% of Medieval, 67% of Haskala and 11.5% of Modern lines contain more than one sentence |
| | Not inside matched `() [] {} <>` | Citations such as `(שמות כח, יז.)` must not be cut |
| | Not after a single letter (initials `י. ל.`) or after a leading number (`1 .`) | Real cases from Modern |
| | The colon is **not** a terminator | Mid-line it introduces quotations (`שנאמר: …`, `אמר :`) |
| | Units are **never** cut for the parser's input limit (segment v2). A unit too long for the parser is split at parse time into *pieces* that keep their parent `sent_id` (`hebloc.pieces`, §8) | Some texts have hardly any punctuation (e.g. Pesikta Rabbati, 47 lines and 101k tokens), so very long units exist; Dicta's actual sub-word limit is measured in M3 |

**Aramaic.** Mikra units carry `aramaic` = `aramaic` (Dan 2:5–7:28, Ezra 4:8–6:18 and 7:12–26,
Jer 10:11; 269 verses) or `aramaic_partial` (Dan 2:4, Gen 31:47), so statistics can exclude them.

## 4. Normalization (`text_raw` → `text_norm`)

**Common to all corpora:**
- Remove invisible bidi and format characters (LRM, RLM, embeddings, BOM, CGJ).
- Strip niqqud and cantillation.
- Collapse whitespace.

The diacritic stripping is a **hypothesis** (D-009): Dicta is trained on unvocalized Modern
Hebrew, and vocalization is inconsistent even within one corpus (Mishnah is vocalized, Tosefta is
not). It will be tested in M3 by parsing vocalized and stripped versions of the same units.

**Mikra:**

| Rule | Status | Count |
|---|---|---|
| **Qere** used in `text_norm`; **Ketiv** reading stored in `text_norm_alt` | **Hypothesis**, M3 test | 1,053 pairs (910 written `(K) [Q]`, **143 written `[Q] (K)`**), plus 12 Qere-only and 10 Ketiv-only verses |
| Maqaf (`-` in this edition) → space | **Hypothesis**, M3 test | 18,092 verses |
| Sof pasuq `׃` → `.` | **Hypothesis**, M3 test | 23,204 verses |
| ASCII `'` `"` inside words removed. In this edition they are converted accents (`אֱלֹהִ'ים`, `וֵֽאלֹהִ"ים`); Mikra has no other quotation marks | Accepted | 8,039 verses |
| `{פ}` `{ס}` paragraph markers removed and recorded as flags | Accepted | 3,628 verses |
| Joshua 21:36–37 contain only `-` (verses absent from the Masoretic text). They are kept, with empty `text_norm` | Accepted | 2 |

**Hazal and Medieval:**
- HTML entities are decoded (`&lt;ושל&gt;` → `<ושל>`; 256 units).
- Line-initial editorial paragraph numbers `(א)…` are removed (346 units). Only valid Hebrew numerals are matched, so `(השב)` is kept.
- Biblical citations, editorial `[…]` and textual variants `(…) […]` are **kept as supplied**.
- **Rambam**: citations marked `+ דברים כ"ב +` become `( דברים כ"ב )` (234 units).

**Haskala** (Ben-Yehuda markup; contents of 30,779 `<…>` spans were classified):

| Markup | Meaning | Handling | Units |
|---|---|---|---|
| `<span style=…>` | HTML | tag removed | 576 |
| `<במהד' 1836: …>` | **editor's note on a variant edition** | **whole note removed**: apparatus, not the author's text | 203 |
| `<!>` | editor's *sic* | removed | 4,989 |
| `<>` | separator | removed | 5,035 |
| `<…>` (other) | quotation or chapter heading | brackets removed, text kept | 11,984 |
| `{…}` | editorial emphasis | braces removed, text kept | 23,374 |
| `#…#` | quotation marker | `#` removed | 1,820 |

**Modern:**
- The Haaretz timestamp header `עדכון אחרון - HH:MM DD/MM/YY` is removed from the first line of each Haaretz file (276,814 units). It is metadata, not language.
- `[ IMG ]` markers are removed (114).
- URLs are kept and flagged (12,719).
- The text stays **pre-tokenized as supplied** (spaces around punctuation). It is not re-joined.

## 5. The `prefix=` / `token=` artifacts (D-016)

An earlier tokenizer split a Hebrew prefix off a following non-word token and wrote it as
`prefix=X`. All **1,159,353** occurrences were classified by what follows them.

| Rule | Pattern → reconstruction | Applied |
|---|---|---|
| R2 | `prefix=ה - 13` → `ה-13` (hyphen + number or Latin token) | 668,935 |
| R3 | `prefix=ל " ב` → `ל"ב` (gershayim numeral or acronym, or a prefix before a quoted word; identical spelling in Hebrew) | 176,515 |
| R1 | `prefix=ל token=פרופ'` → `לפרופ'` | 8,912 |
| R4 | `token=` tag text removed (incl. literary `ו-token=פרופ'` → `ו-פרופ'`) | 10 |
| pre-pass | `prefix= ו` (space after the tag, nrg) → `prefix=ו` | 2 |
| **Not reconstructed** | everything else: **304,991 (26.3%)** in 250,149 units, flagged `prefix_unresolved:<class>`. Only the literal text `prefix=` is removed; nothing is joined, added or reordered | — |

Why the remaining 26% are not reconstructed. Each pattern, with what the original probably was:

| Pattern | Share of unresolved | Probable original | Problem |
|---|---|---|---|
| `prefix=ב - , 2001` | ~27% | `ב-2001,` | punctuation was moved in front of the number |
| `prefix=ב - % 20.3` | ~20% | `ב-20.3%` | `%` was moved in front of the number |
| `prefix=ב - דולר` | — (107,547 tags) | `ב-<N> דולר` | **the number is missing from the source** |
| `prefix=ב - .` | — | — | the number is missing from the source |

Reconstructing the first two would mean **reordering** tokens, which is an inference about how the
source was corrupted. That is not allowed without approval (§7).

**Wider reordering issue.** In Haaretz, ynet and nrg, numbers, `%` and Latin text adjacent to
punctuation sometimes appear in reversed visual order (`% 2`, `כבשנת , 2005`, `MC2 = E`). The
rate of "`%` before a number" is 14 per 10k tokens in Haaretz and 8.9 in ynet, against ≈0.1 in
the Knesset, a7 and blogs. This is a **source** limitation; M2 does not alter it.

## 6. Verification

| Check | Result |
|---|---|
| Every unit's `text_raw` equals the source line slice (asserted during extraction) | ✅ all 9,714,378 v1 units; all 9,709,662 v2 units (§8) |
| Independent re-read of 3,000 random units from the **original files** | ✅ exact match |
| Coverage: the units of each line contain all its non-whitespace characters | ✅ 0 failures |
| Every non-empty line of every full-view document yields units; line counts equal the catalog | ✅ |
| Mikra: 23,206 verses; known verses at the right references (Gen 1:1, Exod 20:13, Ps 23:1, Joel 4:1, Mal 3:24) | ✅ |
| `sent_id` unique; views and strata consistent with the catalog | ✅ |
| `text_norm` contains no tool tags, diacritics or invisible characters | ✅ |
| Deterministic: two runs give identical content (checksum) | ✅ |
| Original corpora unchanged (fast and full SHA-256 checks) | ✅ |

## 7. Open issues and decisions for the user

1. **Candidate rule R5 (not applied).** For `prefix=X - P N`, where P is `, ; % .` and N is a number, rebuild `X-N` with P placed after it (e.g. `ב-20.3%`, `ב-2001 ,`). It would resolve about a third (~100k) of the unresolved cases, but it reorders tokens. *Options:* (a) keep as is, flagged (current); (b) approve R5 after a manual check of ~100 random cases.
2. **Reversed-order numbers and Latin in Haaretz, ynet and nrg** (§5). *Options:* (a) document as a limitation and flag nothing more (current); (b) add a unit-level `suspect_bidi` flag so statistics can exclude affected units. A fix would be guesswork.
3. **The M3 pilot will test the hypotheses:** diacritic stripping, Qere vs Ketiv, maqaf, and sof pasuq.
4. **Over-long units:** resolved structurally by M2.1 (§8). The piece budget (Dicta sub-words) is set in M3; the statistical treatment of multi-piece units is provisional (D-021).
5. **Empty after normalization:** 306 units (mostly Haskala separator lines, plus Joshua 21:36–37). They are kept and flagged `is_empty_norm`; M3 will skip them.

## 8. M2.1 correction: complete-sentence units (segment v2, D-020)

**What was wrong in v1.**
- Sentences over 200 whitespace tokens were cut into `chunk` units: 7,716 chunks from 3,000
  sentences (Hazal 708, Medieval 475, Haskala 850, Modern 967).
- The original sentence was not stored. On 101 lines, two chunked sentences were adjacent
  (135 pairs), and nothing in the stored columns showed where one sentence ended.
- Chunks were cut **before** normalization, so a rule whose pattern crossed a cut could fail.
- The 200-token cap had no relation to Dicta's real input limit.

**What changed.**
- `segment_line` no longer cuts sentences, so each unit is a complete sentence or verse and is
  normalized as a whole.
- Cutting for the parser is now a parse-time step (`hebloc.pieces.plan_pieces`), measured in the
  parser's own cost unit. Each piece records its parent `sent_id` and its exact span in `text_norm`
  (`PIECES_SCHEMA`; see `data_dictionary.md`).
- With cost = 1 token and budget = 200, `plan_pieces` reproduces every v1 chunk boundary exactly.
- No normalization rule changed (`norm_version` 1).

**How it was verified.** `hebloc verify-units-v2` compared the regenerated units with a preserved
copy of v1 (`data/units_v1`). No result was assumed in advance.

| Check | Result |
|---|---|
| Rows on lines that had no chunk (9,699,645 rows), every column except `segment_version` | 0 differences |
| Unit counts per corpus: v2 = v1 − chunks + chunked sentences | reconciles (total 9,714,378 → 9,709,662) |
| Source line sets, v1 vs v2 | identical |
| v2 units on affected lines (2,710 lines) = `sentence_spans(line)`, `text_raw == line[s:e]` | ✅ (source re-read from `corpora/`) |
| Non-whitespace characters per affected line | identical (nothing lost or added) |
| v1 chunk offsets = `plan_pieces(text_raw, 200)` | ✅ for all 3,000 sentences |
| Merged sentences: `text_norm` vs v1 chunk norms joined | **2 differences** |
| Merged sentences: flag sets, token counts, other columns | **3 sentences** in total differ (below); 400 flag-count differences are once-per-unit flags (e.g. `diacritics_stripped`, `braces_removed`) that v1 repeated per chunk |
| Validation sample (`data/units_sample`) | regenerated with v2 at clean commit `924efd5`. The old sample recorded the pre-M2 commit `be72e1d+dirty`, so it was stale; it was moved to `data/units_sample_v1` |

**All 3 sentences with derived-value differences.** Each is a v1 chunk-boundary defect that is
now fixed:

| Unit | v1 (chunked) | v2 (whole sentence) |
|---|---|---|
| Haskala Ytext1005003, line 499 | The editor's note `<במהד' 1851: איתרמי>` was cut in half, so the note's words entered `text_norm` and a spurious `quote_brackets_removed` flag was added (227 tokens) | The note is removed as rule D-018 intends (224 tokens) |
| Haaretz 812673.txt, line 1 | `prefix=ב - 38` was cut, so it was left as `ב - 38`, flagged `prefix_unresolved:hyphen_eol` | R2 applies: `ב-38` |
| nrg 174.txt, line 7 | A chunk ended right after `prefix=כ`, so the tag was classified `prefix_unresolved:eol` | Classified `prefix_unresolved:number` (the next token is `130`). The text is identical, and the tag is still not reconstructed (D-019) |

**Identifiers.**
- Ids and refs changed only on the 2,710 affected lines: 7,716 chunks merged and 3,682 units
  renumbered; 3,335 kept their id.
- A v1 id on those lines can name a different unit in v2, so v1 ids must not be used against v2
  data. None were used downstream.
- The full mapping is in `data/migrations/segment_v1_to_v2/map.parquet`.

**Statistics.**
- Length is computed per complete unit.
- Dependency-tree statistics for units parsed in several pieces are **provisional** (D-021).
  Those units have no complete tree and must be reported explicitly.
- Excluding them may cause substantial selection bias: they are the longest sentences, and they
  are concentrated in particular corpora.

