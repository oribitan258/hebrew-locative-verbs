# The Assignment in Brief, and Where Additional Statistics Fit

*Summary of the course's `project.pdf` (Hebrew; use your own course copy for the exact wording). The paper is
Doron & Dubnov (2017) on locative verbs in Biblical and Modern Hebrew.*

## The research question
**Locative verbs** describe putting something somewhere, or removing it. Some of them alternate between two
frames:
- **Frame A:** the moved thing (Locatum) is the direct object: מילא מים **ב**מיכל;
- **Frame B:** the place (Location) is the direct object: מילא את המיכל **ב**מים.

**Doron & Dubnov's claim:** in Hebrew an alternating verb keeps the **same preposition** in both frames (ב- for
putting, מ-/מן for removal), unlike English (*fill water into* vs *fill … with*). The project tests this on five
corpora with Dicta's parser.

## Sections and status

| § | Requirement | Status |
|---|---|---|
| 1 | Background reading with written summaries: the paper (ch. 1–3); morphology and syntax of each period, with sources; classifiers; Accuracy/Precision/Recall/F | open |
| 2 | Corpora: Mikra; Hazal (Mishnah, Tosefta, tannaitic midrashim, midrashim); Medieval (Mishneh Torah, Thought, Musar); Haskala; Modern (news, literature original/translated, Tapuz forum, blogs, medical, Knesset) | **done** |
| 3 | Run Dicta on every verse/sentence: lemma, POS, inflection, prefixes/suffixes, dependency tree | **done**: everything in `data/` |
| 4 | Statistics per corpus (see below) | **done** (R1–R6, `official/`); **R7 open: this package** |
| 5 | Test the claim: find all locative verbs (Mikra first, then the others), classify each use by syntactic frame, find the preposition, check identity, compare with the paper | next team stage |
| 6 | In one corpus, classify all verbs by the paper's categories; find other verbs that alternate | later |
| 7 | Classifiers: verb feature vectors (lexical, morphological, syntactic, word2vec), 10-fold cross-validation, Accuracy/P/R/F | later |
| 8 | Use Dicta's LLMs or another AI tool in the research | later |
| 9 | Final report: research question, literature review, **presentation and analysis of the §4 statistics**, results of §5–8, conclusions | partly |
| 10 | Submission: report, relevant data, relevant code | later |
| 11 | **Personal initiative beyond what is described is given weight in the grading** | ongoing |

## §4 in detail ("produce statistical data on the corpora")

| Item | Official result (`official/`) |
|---|---|
| R1 words and lemmas, with frequencies | `lexicon`, `word_freq`, `lemma_freq` |
| R2 sentence lengths | `sentence_stats`, `distributions` |
| R3 distinct words per sentence | `sentence_stats`, `distributions` |
| R4 sentence depth by the dependency tree ("think about what it means") | `sentence_stats`, `depth_by_length`, `tree_status` |
| R5 morphological features: word categories; inflection features | `pos`, `features` |
| R6 syntactic structures: types of relations | `deprel` |
| **R7 "any additional statistic you can think of"** | **open: the purpose of this package** |

## Where your work can count
- **§4 R7:** every well-founded additional statistic.
- **§9:** the report must *present and analyse* the statistics. Comparisons by sub-corpus and period, and
  explanations of differences, make that analysis much stronger. The current written analysis is
  `docs/stats_analysis.md` (a draft).
- **§11:** initiative is graded. Original, careful comparisons are exactly that.
- **§5 background:** exploratory statistics about verbs, their objects and their prepositions per corpus help the
  next stage (see `RESEARCH_IDEAS.md` §6), without starting it.

Findings go to Ori (`analyses/REPORT.md`, see `CLAUDE.md`). Accepted findings enter the final report, crediting you.
