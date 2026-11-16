# Sections 2–4 of the Assignment: What We Did, How, What We Found, Where It Is

*Closeout of `project.pdf` §2 (corpora), §3 (Dicta analysis) and §4 (statistics), 2026-11-16. Written to be
explained to the professor. Details live in the linked documents; when they disagree, the linked documents win.*

## 1. Status

| Section | Requirement | Status |
|---|---|---|
| §2 | The five corpora with their listed sub-corpora | **Complete** |
| §3 | Dicta's morphological and syntactic analysis of every verse and sentence | **Complete**: 9,709,662 of 9,709,662 units |
| §4 | Statistics R1–R6 (words and lemmas, lengths, distinct words, depth, POS and inflection, relations) | **Complete, final** |
| §4 | "Any additional statistic you can think of" | Optional item, **deferred** by Ori (decision D-046). Extra already done: parser agreement with BHSA on all of Mikra |

## 2. §2: The corpora

- **Contents.** 404,294 files (1,074.7 MiB), exactly as supplied. Every category the assignment lists is
  present and analysed:

  | Corpus | Sub-corpora |
  |---|---|
  | Mikra | 39 books |
  | Hazal | Mishnah, Tosefta, Midrash (incl. the halakhic/tannaitic midrashim) |
  | Medieval | Mishneh Torah, Thought, Musar |
  | Haskala | 320 files |
  | Modern | news (Haaretz, A7, ynet, nrg, TheMarker); literature, original and translated; Tapuz forum; blogs; medical texts; Knesset protocols |

- **Never modified.** The original files are never changed. A test checks them against a checksum
  manifest that is pinned in git.
- **Catalogued.** Every file has an entry in `data/catalog/documents.parquet`: encoding (Modern is
  Windows-1255), size, Hebrew-token counts, duplicates and period tags.
- **Not analysed, but catalogued.** 201 files hold no text: 91 empty Rambam files, 100 7-Zip logs,
  3 one-byte Haskala placeholders and 7 empty Modern files.
- **Two views.** The statistics use the **full view**: every supplied text, nothing removed (decision
  D-015). Period and duplicate tags define a curated view for later use. Data is tagged, never deleted.
- Facts per corpus: [corpus_report.md](corpus_report.md).

## 3. §3: Analysis with Dicta

### 3.1 Method

1. **Units** ([m2_preprocessing.md](m2_preprocessing.md)).
   - Mikra: one verse per line. Verse references come from an external versification table, checked
     against every book's line count.
   - Other corpora: lines are split into sentences after `.` `?` `!`, but not inside brackets, after
     initials or at a colon.
   - A unit is never cut.
   - Every unit keeps its exact original text and position (file, line, characters). Any number can be
     traced back to the source line (`hebloc.data.trace`).
2. **Normalization.** Niqqud and cantillation are stripped; this was tested and gives identical model input.
   - Mikra: the Qere is used and the Ketiv is kept. The Qere agrees better with BHSA (decision D-026).
   - Editorial markup is removed only where it is clearly not the author's text (e.g. Haskala
     variant-edition notes).
   - Every change is recorded per unit.
3. **Parser.** `dicta-il/dictabert-joint` (base model).
   - Pinned to an exact version with checksums; its code was reviewed and stored unchanged.
   - Base was chosen over tiny on BHSA agreement (D-027).
   - Two fixes were added at run time, both tested:
     - a bug fix in Dicta's tree decoder: invalid trees fell from 11.9% to 2.1% of the pilot pieces
       (D-024);
     - a speed-up with byte-identical output (D-029).
4. **Long units.** Dicta silently drops input beyond 510 sub-words. Such units (733 in all, 0.008%) are
   parsed in pieces that keep their parent sentence id (D-028).
   - Every output is checked to cover every input character.
5. **Output.** For every word: lemma, POS, gender, number, person, tense, prefixes (מ ש ה ו כ ל ב),
   pronominal suffix with its features, and head with relation type (the dependency tree).
   - Dicta's raw output is stored, so nothing needs to be re-parsed to recompute statistics.
   - **Dicta does not output** construct state (נפרד/נסמך, which §3 lists) or binyan. Construct
     appears only as the relation `compound:smixut`.
6. **Scale.**
   - Work split: 31 slices over three computers (Ori, Efrat, Adi). Before running, each computer
     reproduced a reference parse exactly (1,161 pieces).
   - Merge: each result folder was checked by checksum, restored, re-validated and checked to hold
     exactly its assigned sentences.
   - Result: **31/31 slices, 9,709,662 units, none in two runs, 0 parse errors.**
   - The 31 runs are registered as the canonical dataset (D-049).

### 3.2 Parser accuracy (Mikra vs BHSA, all of Mikra)

BHSA's annotation follows different conventions from Dicta's, so these figures are agreement between
the two annotations, not gold accuracy.

| Layer | Agreement |
|---|---:|
| POS, strict | 83.5% |
| POS, convention-tolerant | 88.8% |
| Prefix segmentation | 95.8% |
| Noun lemma | 73.4% |
| Verb person / number / gender | 90.9% / 96.4% / 94.1% |

- **Verb lemmas.** Agreement is low by convention (41.6% qal; 7.9% other stems): BHSA gives the root,
  Dicta gives the dictionary form of the binyan.
- **Syntax** has no gold standard, because BHSA has no dependency trees. In the pilot, Dicta's two model
  sizes agreed on the head of 89% of Modern words but only 57–71% in the historical corpora.
- Files: `results/stats/accuracy/`; report §7.

## 4. §4: Statistics

**Definitions** (D-046, [m6_design.md](m6_design.md)):
- **Word:** a non-punctuation Dicta word.
- **Word type:** the written form. **Lemma:** Dicta's lemma.
- **Sentence:** a verse in Mikra, a sentence elsewhere.
- **Depth:** levels from the root to the deepest word, root = 1. It is measured on units with one valid
  tree, which is over 99% of measured units in every corpus.
- **Excluded from depth only, and counted in every table:**
  - multi-piece units;
  - units with an invalid word-level tree (7,217 units, 0.07%).

| § 4 item | Where |
|---|---|
| R1 words and lemmas, with frequencies | report §3; `word_freq_top1000.csv`, `lemma_freq_top1000.csv`, `lexicon.csv`; complete lists in Parquet; `zipf_words.png` |
| R2 sentence length | report §4; `sentence_stats.csv`, `distributions.csv`; `length_distribution.png` |
| R3 distinct words per sentence | report §4; same files; `distinct_words_distribution.png` |
| R4 depth (and what it means) | report §4; `depth_by_length.csv`, `tree_status.csv`; `depth_distribution.png`, `depth_by_length.png`; meaning: analysis §4 |
| R5 POS and every inflection feature Dicta outputs | report §5; `pos.csv`, `features.csv`; `pos_shares.png` |
| R6 relation types | report §6; `deprel.csv`; `deprel_shares.png` |

**Main findings** (full discussion: [stats_analysis.md](stats_analysis.md), *draft awaiting Ori's wording*):

| | Mikra | Hazal | Medieval | Haskala | Modern |
|---|---:|---:|---:|---:|---:|
| words | 305,514 | 6.50 M | 3.47 M | 5.36 M | 139.5 M |
| median sentence length | 12 (verse) | 9 | 21 | 13 | 14 |
| median depth | 5 | 4 | 6 | 5 | 5 |
| verbs, % of words | 21.6 | 21.9 | 20.5 | 17.9 | 14.1 |
| adjectives, % of words | 2.4 | 3.5 | 4.8 | 6.4 | 7.9 |

1. **Medieval** has the longest sentences.
2. **Depth grows with length.** At equal length, Modern is deeper than all four older corpora (from 16
   words on). Depth measures hierarchical embedding, not word count.
3. **Towards a more nominal style:** the share of verbs falls from Mikra/Hazal to Modern, and adjectives
   rise.
4. **Tense forms:** Mikra's narrative tense (ויאמר) is tagged "future" by form (39% of verbs); Modern has
   far more present-tense participles (19%).
5. **Relations:** coordination (`conj`) is highest in Mikra, and noun-phrase modification
   (`amod`, `nmod`) highest in Modern.

## 5. Limitations (to state openly)

1. **Dicta is trained on Modern Hebrew** and its output is not ground truth.
   - Accuracy is measured only for Mikra, and only for morphology.
   - Syntax on the historical corpora is the least reliable layer. The unspecified relation `dep` is
     about 7 times more frequent in Hazal and Medieval than in Modern.
   - The planned manual audit of other corpora is deferred.
2. **Units are not uniform.**
   - A verse is not a sentence.
   - Punctuation-poor texts give paragraph-length "sentences" (up to 6,433 words, Haskala).
   - These stay in the statistics as defined (D-049): the percentiles describe the corpora better than
     the maxima.
3. **Extremes can be text artifacts.** Modern's maximum depth (112) is a blog line of HTML character codes.
4. **Corpus sizes differ a lot** (Modern is 456 times Mikra), so type counts and maxima are not directly
   comparable.
5. **Corpora mix periods and genres.**
   - About 60% of Hazal is later commentary and Yalkut Shimoni.
   - 37% of Haskala is post-1881.
   - Modern is 74% Haaretz.
   - Statistics per sub-corpus were deferred.
6. **Text conventions differ.**
   - Rambam and Modern are pre-tokenized.
   - Modern has 288,102 punctuation-only lines, mostly in blogs. They are counted, not measured.

## 6. How we know it is correct

| Check | Result |
|---|---|
| Originals unchanged | checksum test against the pinned manifest |
| Every unit = its exact source span | verified for all units (M2) |
| Parse coverage | every input character is covered by the output, for every piece |
| Merge | each slice holds exactly its assigned sentences; 0 duplicated across runs |
| Data layer | `hebloc check --deep`: OK (every run re-validated; registry ok) |
| Statistics reconcile | words + punctuation = tokens per unit; frequency, POS, relation and feature totals = word counts; 0 problems |
| Reproducible | a full independent recompute gave byte-identical tables (42/43 files; the manifest differs only in time stamps) |
| Stable | Mikra, Hazal and Medieval are identical to the provisional run of 2026-11-15 |
| Extremes | the longest and deepest unit of every corpus traced to its source line; depths recomputed independently |
| Code | test suite passes |

## 7. Where everything is

| What | Where | In git? |
|---|---|---|
| Statistics report (tables, figures, definitions, accuracy) | [docs/stats_report.md](stats_report.md) | yes |
| Written analysis (draft) | [docs/stats_analysis.md](stats_analysis.md) | yes |
| Tables, CSV (UTF-8; Hebrew shows correctly in Excel) | `results/stats/*.csv` | yes |
| Figures | `results/stats/figures/*.png` | yes |
| Parser accuracy vs BHSA | `results/stats/accuracy/` | yes |
| Complete statistics tables (incl. full frequency lists, one row per unit) | `data/stats/final-20261116-565826e3c1/` (Parquet + `manifest.json`) | no (local; zip in `data/backups/stats/`) |
| Parsed data (raw Dicta output, tokens) | `data/annotations/<corpus>/runs/` | no (local; verified bundles in `data/outbox/ori`, `data/efrat-data1/2`, `data/adi-data1/2`) |
| Units with provenance | `data/units/<corpus>/` | no (rebuilt by `hebloc prepare`) |
| Column meanings | [data_dictionary.md](data_dictionary.md) | yes |
| Design, decisions | [m6_design.md](m6_design.md), [decisions.md](decisions.md) | yes |

**Opening the data.**
- CSV files open in Excel or pandas.
- Parquet opens with pandas, DuckDB, or the project API, e.g. `hebloc.data.tokens('mikra')` for the
  parsed words of a corpus and `hebloc.data.trace(sent_id)` for the source of a sentence.

**Reproducing.**
- `uv run python -m hebloc stats run --registered` recomputes everything from the registered runs
  (about 35 min).
- `hebloc stats report <folder>` re-renders the CSV, figures and report identically.
- `hebloc stats verify <folder>` re-checks every file's checksum.
