# M6 Design: Descriptive Statistics (project.pdf §4) and Parser Accuracy

*Approved by Ori on 2026-11-12 (D-046). This file is the reference for what M6 computes and why.
Implementation: `src/hebloc/stats/`; command: `hebloc stats`.*

## 1. What the assignment requires

`project.pdf` §4: "Produce statistical data on the different corpora (Mikra, Hazal, Haskala,
Medieval, Modern)":

| # | §4 item | Meaning |
|---|---|---|
| R1 | המילים / הלמות ושכיחותן | Words and lemmas, and their frequencies |
| R2 | אורכי המשפטים | Sentence lengths |
| R3 | מספר המילים השונות במשפט | Number of distinct words per sentence |
| R4 | עומקי המשפטים, על פי העץ התחבירי (נסו לחשוב מה משמעותו) | Sentence depth from the dependency tree, and what it means |
| R5 | המאפיינים הצורניים: קטגוריות המילים; מאפייני ההטיה | Word categories (POS) and inflection features |
| R6 | מבנים תחביריים: סוג הקשרים התחביריים | Types of dependency relations |
| R7 | כל סטטיסטיקה נוספת שעולה בדעתכם | Any additional statistic (optional) |

§9 asks for these statistics to be presented and analysed in the final report.

## 2. Part A: the explicit requirements (implemented)

Everything in Part A is computed **per corpus** on the **full view**, which is the primary reference
(D-015). Every unit of the full view is included.

| Req | Output per corpus |
|---|---|
| R1 words | Word tokens, distinct word types, types occurring once, and the frequency of every word (complete table in Parquet; top 1,000 in CSV; top 20 in the report) |
| R1 lemmas | The same for lemmas. Words whose lemma Dicta left `[BLANK]` are counted and reported, never given a lemma |
| R2 | Sentence length in words: mean, standard deviation, min, percentiles (5, 25, 50, 75, 95, 99), max; full distribution |
| R3 | Distinct words per sentence: same summary and distribution |
| R4 | Sentence depth: same summary and distribution, plus mean depth by sentence-length band (for the "what does it mean" discussion) |
| R5 POS | Count and share of each of Dicta's 16 POS categories |
| R5 inflection | **Every inflection feature Dicta predicts** (verified in the model code, `dicta_code/BertForMorphTagging.py`), each value counted per POS: see §2.1 |
| R6 | Count and share of every dependency-relation type |

### 2.1 Inflection features: what Dicta actually provides

Checked against the model's label set (`ALL_FEATURES`, `ALL_SUFFIX_POS`) and against all 7.9M words of
Mikra and Hazal:

| Feature | Values Dicta can output | Source |
|---|---|---|
| Gender | Masc, Fem, Fem,Masc | word feature |
| Number | Sing, Plur, Dual, Plur,Sing, Dual,Plur | word feature |
| Person | 1, 2, 3, 1,2,3 | word feature |
| Tense | Past, Fut, Pres, Imp | word feature |
| Pronominal suffix | PRON (possessive, e.g. ספרו), ADP_PRON (on a preposition, e.g. לו) | suffix head |
| Suffix gender, number, person | as above | suffix feature head |
| Definiteness | Def, if the prefix POS includes DET (ה, also the implicit ה after ב/כ/ל) | derived: Dicta's own UD converter derives it this way |

**Not provided by Dicta:**
- construct vs absolute state (נפרד/נסמך, listed in §3.2). Construct shows up only as the relation
  `compound:smixut` (R6);
- binyan;
- verbal form (participle, infinitive).

The report states this. Multi-values such as `Fem,Masc` or `1,2,3` are kept exactly as Dicta gives them.

### 2.2 Definitions (D-046)

1. **Word** = a Dicta word that is not punctuation (`upos ≠ PUNCT`). It is the unit that carries the
   lemma, POS, features and relation. Punctuation tokens are counted once per corpus (7% of Mikra's
   tokens, 14% of Hazal's).
2. **Word type** = the word as written (`surface`, a slice of the normalized unit text, prefixes
   attached, niqqud removed). **Lemma** = Dicta's lemma (its dictionary form, which for verbs includes
   the binyan; it is not the root).
3. **Sentence** = the unit: a verse in Mikra (labelled "verse"), a sentence elsewhere.
   - *Empty* units (no text after normalization, e.g. two placeholder verses in Joshua) and units that
     contain only punctuation are counted, not measured.
   - Units with a parse `error` piece would be counted and excluded from R2–R4. There are none so far.
4. **Depth** = the number of levels on the longest path from the root word down to a word: the root =
   1, a word attached to the root = 2, and so on.
   - Punctuation leaves are ignored: the maximum is taken over words.
   - Depth measures how deeply phrases and clauses are embedded. It grows with sentence length, so it
     is also shown per length band.
5. **Units without one valid tree are excluded from depth only.** This covers units parsed in several
   pieces (D-021) and pieces whose word-level tree is not a tree (D-025).
   - Every depth table reports how many units and words were excluded, and their length.
   - All other statistics (R1–R3, R5, R6) use all words.

### 2.3 Required by project rules (not by §4)

- **Coverage** of every corpus: units, empty and punctuation-only units, words, punctuation, blank
  lemmas, `mst_fallback` pieces, and depth exclusions.
- **Parser accuracy, Mikra vs BHSA:** the pilot comparison (`hebloc.pilot.experiments.bhsa_eval`) rerun
  on all of Mikra. It is final now (Mikra is complete) and is checked by reproducing the pilot's
  500-verse figures exactly.
- The manual audit stays deferred.

## 3. Part B: optional additions for R7 (deferred, not implemented)

Ori deferred all of these on 2026-11-12:

| Option | Content |
|---|---|
| O1 | Part A per sub-corpus (Hazal strata, Haskala before/after 1881, Modern by source, Medieval strata) |
| O2 | The curated view next to the full view |
| O3 | Prefix and suffix rates |
| O4 | Vocabulary at equal sample size |
| O5 | Diachronic indicators: subject–verb order, של vs construct, אשר vs ש- |

Note for O1/O2: about 60% of Hazal's full view (by Hebrew tokens) is later commentary and Yalkut
Shimoni. Part A's "Hazal" numbers therefore largely describe that text.

## 4. Workflow (D-040, D-045)

- **One code path.**
  - Now: `hebloc stats run --runs <run,…>`, an explicit run list.
  - After the merge: `hebloc stats run --registered`, the canonical runs in `config/annotations.yaml`.
- **The run set is checked before anything is computed.**
  - Per corpus, the runs must cover every unit of the corpus exactly once.
  - Every run's `checks.json` must be `ok` and current (fingerprint).
  - A partial corpus is **refused**. `--scale-test` lifts the refusal for a timing test and writes only
    to an explicit folder outside `data/stats` and `results`.
- **Status.** `final` only with `--registered` and all five corpora complete; otherwise `provisional`.
- **Outputs.**
  - `data/stats/<status>-<date>-<hash>/`: Parquet tables + `manifest.json` (runs and their
    fingerprints, code commit, stats version, row counts, sha256 per file). Never overwritten.
  - A provisional run writes its CSV, PNG and `stats_report.md` inside that folder only.
  - The final run writes them to `results/stats/` and `docs/stats_report.md` (git).
  - Parser accuracy (final now) goes to `results/stats/accuracy/`.
- **Reconciliation inside every run.** A failure stops the run before anything is published:
  - words + punctuation per unit = token rows;
  - frequency totals = word totals;
  - POS and relation totals = token rows;
  - each feature's totals per POS = that POS's count;
  - unit statuses sum to the corpus's units.

## 5. Order and review points

1. This design, D-046/D-047, matplotlib tested against Smart App Control.
2. Code + tests.
3. Accuracy on full Mikra (final). **Review.**
4. Provisional Mikra + Hazal statistics. **Review (STOP).**
5. Speed test on Ori's Modern slices (timing only).
6. After the merge (31/31) and registration: the final run → `results/stats/`, `docs/stats_report.md`.
   **M7 STOP.**
