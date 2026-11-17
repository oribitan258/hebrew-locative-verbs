# Research Directions for Additional Statistics

Each idea names the data it needs. All are exploratory: label results so, state definitions, and give caveats
(`CLAUDE.md`). Start with what interests you; quality beats quantity.

## 1. Inside each corpus: sub-corpora and periods
The official numbers are per corpus. The corpora are internally diverse, so breaking them down is the single most
informative extension.
- **Hazal:** Mishnah vs Tosefta vs halakhic and aggadic midrash vs later commentary
  (`stratum = 'hazal.commentary'`) vs Yalkut Shimoni (`hazal.late_anthology`). How much of the official "Hazal"
  profile is really the commentaries?
- **Medieval:** Mishneh Torah vs Thought vs Musar; original vs translated from Arabic (`*_translated` strata).
- **Haskala:** before vs after 1881 (`documents.subperiod`), by decade (`year`), by genre (belles-lettres,
  essays/press, science). Does sentence length or verb share change over time?
- **Modern:** news (Haaretz, A7, ynet, nrg, TheMarker) vs blogs vs Tapuz forum vs Knesset vs medical vs
  literature, and **original vs translated literature** (`modern.literary.original/translated`).
- **Data:** `words` / `unit_metrics` joined with `documents` on `doc_id` (example: `hebpack.examples.pos_by_stratum`).

## 2. Fair vocabulary comparisons
Raw type counts grow with corpus size (Modern is 456 times Mikra).
- **Vocabulary at equal sample size:** sample N words (e.g. 300,000) from each corpus or stratum, then count types
  and lemma types; repeat over samples.
- **Vocabulary growth curves:** types against tokens, and the Heaps' law exponent per corpus.
- **Zipf's law fits** per corpus (slope of the rank–frequency curve).
- **Lexical diversity:** moving-average type–token ratio on equal-length windows.
- **Data:** `words.surface`, `words.lemma`; `official_word_freq` and `official_lemma_freq` (complete lists).

## 3. Morphology over time
- **Prefixes:** the rate of ו- (`prefix_upos` contains `CCONJ`), of the article (`DET`), and of ש- (`SCONJ`)
  vs the separate word אשר. Does ש- replace אשר over time?
- **Pronominal suffixes:** possessive suffix (`suffix = 'PRON'` on nouns) vs the analytic של + pronoun; object
  suffixes on verbs vs את + pronoun.
- **Tense profile by genre:** Modern present (participle) vs Mikra "future" forms (the narrative ויאמר).
- **Definiteness rates** by corpus and genre.
- **Data:** `words.prefix`, `prefix_upos`, `suffix`, `suffix_feats`, `tense`, `lemma`.

## 4. Syntax
- **Word order:** subject before or after the verb (`deprel = 'nsubj'`, compare `sent_word_idx` with the head's).
  VS order is expected to be common in Mikra.
- **Construct state vs של:** `compound:smixut` vs `nmod:poss` and של per 1,000 nouns.
- **Dependency distance:** the mean |word − head| per corpus, a standard complexity measure (complements depth).
- **Depth controlled for length:** regression of depth on length per corpus. Is Modern deeper at equal length?
- **Relation profiles per sub-corpus,** e.g. `parataxis` in Hazal dialogue.
- **Data:** `tokens.head_sent`, `sent_word_idx`, `deprel`; `unit_metrics.depth`, `n_words`.

## 5. Lexicon and content
- **Keyness:** lemmas characteristic of each corpus or stratum (log-likelihood; `hebpack.examples.keyness`).
- **Named entities:** rates of persons, places and organisations per corpus and genre (`ner` BIO tags).
- **Collocations:** strongest verb–object or noun–adjective pairs per corpus, by pointwise mutual information.
- **Aramaic in Mikra** (`sentences.aramaic`): how the parser's profile differs on Aramaic verses.

## 6. Background for the next stage (§5, locative verbs), without starting it
- For frequent verbs, the distribution of their dependents per corpus: direct object (`obj`), prepositional
  phrases (`obl`), and which prepositions (`case` children of `obl`, or the `prefix` ב/מ/ל on the `obl` word).
- How often do verbs such as מילא, נתן, שם, הסיר, טען, זרע, ריסס take obj + ב- in each corpus? (A descriptive
  table only: the frame classification itself is the team's §5 work.)

## 7. Parser behaviour by period (useful for every caveat)
- Share of `[BLANK]` lemmas, `X` POS, `dep` relations and invalid trees per stratum: where is the parser least
  sure?
- Compare with the official parser accuracy on Mikra (`official/results/accuracy/`).

## Presenting results
- One question per finding, then the number, a figure, and one paragraph of interpretation with caveats.
- Prefer medians and percentiles for skewed measures, and shares per 1,000 words for counts.
- Keep Hebrew in tables. In charts use corpus names, strata or transliteration (matplotlib cannot draw
  right-to-left text).
