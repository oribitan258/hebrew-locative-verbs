# Analysis of the Descriptive Statistics (project.pdf §4, §9)

*DRAFT for Ori's wording, 2026-11-16. This is hand-written. The tables and figures it discusses are generated:
[stats_report.md](stats_report.md) (from `data/stats/final-20261116-565826e3c1`; CSV in `results/stats/`, figures in
`results/stats/figures/`). Re-rendering the generated report never touches this file.*

## 1. What was measured

- **Data.** All five corpora, full view (every supplied text, D-015), parsed by Dicta (`dictabert-joint`,
  settings base-topk-v1), 9,709,662 units, 0 parse errors.
- **Units.** Mikra counts verses; the other corpora count sentences, as segmented in M2.
- **Words and lemmas.** A word is a Dicta word that is not punctuation. Lemma = Dicta's lemma.
- **Depth.** The number of levels from the root to the deepest word (root = 1). It is measured only on
  units with one valid tree: over 99% of the measured units in every corpus (see "Coverage").

| | Mikra | Hazal | Medieval | Haskala | Modern |
|---|---:|---:|---:|---:|---:|
| units | 23,206 | 418,758 | 115,415 | 275,166 | 8,877,117 |
| words | 305,514 | 6,499,956 | 3,469,269 | 5,357,059 | 139,462,367 |

**Size.** Modern is 456 times the size of Mikra, and 21–40 times each of the other three corpora. Every
count that grows with size cannot be compared directly across the corpora: word types, lemma types,
maxima. Vocabulary at equal sample size was deferred (Part B).

## 2. Words and lemmas (R1)

| | Mikra | Hazal | Medieval | Haskala | Modern |
|---|---:|---:|---:|---:|---:|
| word types | 39,556 | 198,047 | 164,711 | 276,657 | 1,020,105 |
| lemma types | 8,295 | 22,712 | 18,065 | 27,230 | 60,693 |
| word types per lemma | 4.8 | 8.7 | 9.1 | 10.2 | 16.8 |
| word types seen once | 52% | 39% | 43% | 46% | 36% |
| words with blank lemma | 7.1% | 4.7% | 3.6% | 5.0% | 3.3% |

- **Surface forms per lemma.** The word type is the form as written, with its prefixes (ו, ה, ב, ל, מ, ש,
  כ) and suffixes attached. Each lemma therefore appears in many surface forms. The ratio grows with corpus
  size: more text shows more of each lemma's forms.
- **Frequency curves.** All five corpora follow the usual Zipf shape (figure `zipf_words.png`), with
  parallel slopes. Mikra's curve is the shortest only because the corpus is small.
- **Blank lemmas.** Dicta leaves the lemma blank for 3–7% of words. The highest rate is in Mikra (7.1%):
  biblical names and rare forms fall outside its modern lexicon.

## 3. Sentence length and distinct words (R2, R3)

| | Mikra (verse) | Hazal | Medieval | Haskala | Modern |
|---|---:|---:|---:|---:|---:|
| median length (words) | 12 | 9 | 21 | 13 | 14 |
| mean | 13.2 | 15.5 | 30.1 | 19.8 | 16.2 |
| 95th / 99th percentile | 24 / 30 | 48 / 99 | 82 / 144 | 58 / 120 | 36 / 54 |
| maximum | 43 | 1,955 | 1,257 | 6,433 | 1,272 |

- **Mikra.** The verse is a bounded unit, so lengths cluster tightly (maximum 43).
- **Medieval.** It has the longest sentences by every measure: medieval prose builds long periods.
- **Hazal, Medieval and Haskala.** Their long tails come from paragraph-length "sentences". These texts
  often have sparse or no sentence punctuation, so M2 segmentation (which never cuts a unit) leaves whole
  paragraphs as one unit. Haskala's maximum (6,433 words) is one paragraph of Horowitz, *Sefer HaBrit*
  (1797). It was traced to its source line and verified.
- **Modern.** It has the most regular lengths (99th percentile 54).
- **Distinct words (R3).** The number of distinct words per sentence is close to the length in every
  corpus (e.g. medians 12 vs 12 in Mikra, 20 vs 21 in Medieval). Words rarely repeat within a sentence; the
  gap widens only in very long units.

## 4. Depth (R4): what it means

| | Mikra | Hazal | Medieval | Haskala | Modern |
|---|---:|---:|---:|---:|---:|
| median depth | 5 | 4 | 6 | 5 | 5 |
| mean | 4.84 | 4.41 | 5.71 | 4.68 | 5.36 |
| 99th percentile / max | 9 / 18 | 10 / 187 | 12 / 102 | 10 / 86 | 11 / 112 |

**What depth measures.** In a dependency tree every word hangs from a head. Depth counts how many levels
of embedding lie between the main predicate and the most deeply embedded word. Examples of embedding:
- a noun inside a prepositional phrase inside a relative clause;
- a construct chain (סמיכות);
- a subordinate clause.

So depth measures **hierarchical** complexity, as opposed to length, which counts words.

**Depth and the annotation scheme.** In UD the content word is the head, and prepositions and the article
are leaves. Coordination is also nested: each conjunct hangs from the first. Two consequences:
- long chains of "and … and …" add levels;
- depth is a property of the text *as analysed under this scheme*, not a theory-free fact.

**Depth grows with length, more slowly than linearly** (figure `depth_by_length.png`): from about 2.5 levels
at 1–5 words to about 9 at more than 100 words. So the corpus means above partly restate the length
differences: Medieval is deepest because its sentences are longest.

**At equal length, Modern is deeper than all four older corpora, from 16 words on.** Mean depth by length
band:

| Length band | Older corpora | Modern |
|---|---:|---:|
| 21–30 words | 6.2–6.4 | 7.0 |
| 31–40 words | 6.7–7.0 | 8.0 |
| 41–60 words | 6.8–7.0 | 8.6 |

The relation profile (§6) points the same way:
- Modern has more stacked noun-phrase structure: `nmod` 6.3%, `amod` 6.4%;
- the older corpora have more flat linking: `conj` (Mikra 13.7%) and `parataxis` (Hazal 4.6%).

A careful reading follows below: part of the difference may come from the parser.

**Extremes are mostly artifacts of the unit or the text, not of syntax:**
- The Hazal and Medieval maxima (187, 102) are very long passages (362 and 388 words).
- Haskala's (86) is a 281-word chain of comma-separated clauses.
- Modern's (112) is a blog line made of HTML character codes (`&#1492;…`) that the parser chained into one
  path.

All of these were traced to their source lines, and their depths were recomputed independently from the
stored heads. Decision D-049: very long units stay in the statistics as defined, and the 99th percentiles
(9–12) describe the corpora better than the maxima.

## 5. Word categories and inflection (R5)

| % of words | Mikra | Hazal | Medieval | Haskala | Modern |
|---|---:|---:|---:|---:|---:|
| NOUN | 35.1 | 29.8 | 33.1 | 36.1 | 35.7 |
| VERB | 21.6 | 21.9 | 20.5 | 17.9 | 14.1 |
| ADJ | 2.4 | 3.5 | 4.8 | 6.4 | 7.9 |
| PROPN | 11.4 | 9.7 | 3.4 | 3.9 | 11.3 |
| SCONJ | 3.7 | 1.6 | 3.1 | 3.2 | 1.3 |

- **Verbs and adjectives.** The share of verbs falls from about 21–22% (Mikra, Hazal) to 14% in Modern, and
  adjectives rise from 2.4% to 7.9%. This is a steady drift towards a more nominal style. Haskala is in
  between on both.
- **Proper nouns** reflect content rather than period: Mikra's genealogies and narratives, and Modern
  news. Medieval and Haskala, mostly discursive prose, have few.
- **Tense of verbs** (share of verbs):
  - Mikra has the most "future" forms (39.1%). Dicta labels the *form*, and the biblical narrative tense
    (ויאמר, wayyiqtol) has the shape of a future.
  - Modern has far more "present" forms (19.2%, vs ≤ 4.8% elsewhere): the participle became the regular
    present tense in later Hebrew.
  - In Hazal, Medieval and Haskala, Dicta gives no tense for about 46–49% of verbs (e.g. infinitives).
    This is not analysed further here.
- **Features Dicta does not provide:** construct state, binyan and verbal form. Construct state is visible
  only as the relation `compound:smixut` (R6).

## 6. Syntactic relations (R6)

- **Oblique dependents.** `obl` (prepositional phrases and other obliques) is the most frequent relation in
  every corpus (11.5–15.1% of words).
- **Mikra** stands out with `conj` (13.7%: the vav-chain of narrative) and `compound:smixut` (9.7%).
- **Hazal** has the most `parataxis` (4.6%), likely from dialogue and quotations placed side by side.
- **Modern** has the most `amod` and `nmod` (noun-phrase modification), and the fewest `conj`.
- **The relation `dep`** means "unspecified dependency". It covers 4.8–4.9% of words in Hazal and Medieval,
  3.7% in Haskala, 1.8% in Mikra and 0.7% in Modern. The parser uses it when unsure, so this is a direct
  sign of lower confidence on older Hebrew.

## 7. Reading these numbers carefully

1. **Dicta's output is not ground truth.**
   - It is trained on Modern Hebrew. On Mikra, against BHSA (297,324 aligned words): POS 83.5% strict /
     88.8% tolerant; prefix segmentation 95.8%; noun lemma 73.4%; verb person/number/gender
     90.9/96.4/94.1%.
   - Syntax has no gold standard here: BHSA has no dependency trees. In the pilot, Dicta's two model sizes
     (base and tiny) attached the same head on 89% of Modern words but only 57–71% of words in the
     historical corpora (lowest: Medieval). Where they disagree, at least one of them is wrong (pilot
     report §8.2).
   - Differences between the corpora therefore mix real linguistic differences with parser error, and the
     error grows with distance from Modern Hebrew (e.g. the `dep` share above). Differences in depth and
     relations between Modern and the older corpora are the most exposed.
2. **Units differ.** A verse (Mikra) is not a sentence. The older corpora's punctuation-poor texts yield
   paragraph-length units.
3. **Text conventions differ.**
   - Rambam and Modern are pre-tokenized.
   - Modern has 288,102 punctuation-only lines (mostly blogs: 30% of blog units are lone "." or "!"
     lines). They are counted and not measured.
   - Several Medieval works are translations from Arabic.
4. **The full view mixes periods inside a corpus.**
   - About 60% of Hazal's tokens are later commentary and Yalkut Shimoni.
   - 37% of Haskala's tokens are post-1881.
   - Modern is about 74% Haaretz.
   - Breakdowns by sub-corpus (Part B) were deferred.
5. **Coverage.** No unit was lost. Excluded from depth only:
   - multi-piece units: under 0.1% of units;
   - invalid trees: 0.04% (Modern) to 0.81% (Medieval) of units.
