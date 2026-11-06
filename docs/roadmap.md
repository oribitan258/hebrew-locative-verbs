# Project Roadmap — Hebrew Locative Verbs Across Periods

Status: **living document.** The *active scope* is Part 1. Part 2 is the long-term plan. It will not
be implemented until it has been discussed with the project partners and explicitly opened.

Authoritative spec: `project.pdf` (Hebrew). Paper: Doron & Dubnov (2017), *The locative alternation
in Biblical (and Modern) Hebrew*, `DoronDubnov_revised.pdf`.

---

## 0. Research objective (summary)

Doron & Dubnov describe two alignment frames for ditransitive locative verbs:

- **Frame A:** Agent V **Locatum**(direct object) P+Location. Example: מילא מים **ב**מיכל.
- **Frame B:** Agent V **Location**(direct object) P+Locatum. Example: מילא את המיכל **ב**מים.

They sort the verbs into three classes:

| Class | Count in BH | Frames | Semantics | Template tendency |
|---|---|---|---|---|
| **A/B** (alternating) | 45 | Both | Agent brings about a symmetric result state | Mostly Simple (paʕal) |
| **A** | 95 | Frame A only | Motion of the Locatum (directed motion) | 40% Causative (hifʕil) |
| **B** | 37 | Frame B only | Onset or loss of a mereological (part–whole) relation | 40% Intensive (piʕel) |

**Central claim (Locative Alternation Preposition Identity):** an A/B verb takes the *same*
preposition in both frames, ב- for verbs of putting and מן/מ- for verbs of removal. The paper
explains this by Biblical Hebrew being verb-framed (Talmy), which makes the result preposition
stative and symmetric. MH inherits the property. When MH loses an alternation, Frame A is what survives.

Assignment stages (`project.pdf`):

| § | Stage |
|---|---|
| §1 | Background reading |
| §2 | Corpora |
| §3 | Dicta parsing |
| §4 | Statistics |
| §5 | Test the claim (Mikra first, then the other corpora) |
| §6 | Extend to all verbs in one corpus |
| §7 | Classifiers (lexical, morphological, syntactic and word2vec features; 10-fold CV; Acc/P/R/F1) |
| §8 | LLM integration |
| §9–10 | Report and submission |
| §11 | Personal initiative |

---

## Part 1 — Active scope: data foundation (M0–M7)

Detailed milestone definitions are kept in the approved plan and summarized here.

| Milestone | Goal | Key output |
|---|---|---|
| M0 Foundation | Reproducible environment, persistent context, immutability guard | CLAUDE.md, this file, `decisions.md`, uv env, git, guard test |
| M1 Inventory | Every file cataloged: encoding, counts, metadata, strata (nothing dropped) | `data/catalog/documents.parquet`, `docs/corpus_report.md`, `config/curation.yaml` |
| M2 Units | Verses and sentences with provenance (raw and normalized text, char offsets, refs) | `data/units/<corpus>/*.parquet` |
| M3 Pilot (gate) | ~1,000 units end to end; schema; storage and throughput benchmark; quality audit; BHSA check; **Modern coverage options for a user decision** | `docs/pilot_report.md` |
| M4 Data layer | Parquet schemas, atomic shard writer, DuckDB catalog, Python API, CoNLL-U export, integrity tests | `src/hebloc/store`, `hebloc.data`, `docs/data_dictionary.md` |
| M5 Full parse | All units in scope, resumable and sharded | `data/annotations/...` |
| M6 Statistics | All §4 statistics plus extras; full-coverage vs default-filter; parser accuracy on Mikra vs BHSA | `data/stats`, `results/stats`, `docs/stats_report.md` |
| M7 Review | Stop and review with the partners | — |

---

## Part 2 — Long-term roadmap (NOT in active scope)

### R1 — Locative-verb lexicon (§5 prerequisite)
- Transcribe the paper's verb classes into `config/locative_verbs.yaml`. For each verb: root/lemma, binyan, class (A, A/B, B), putting/removal, paper section and page, and example references with the expected frame.
- Sources in the paper:
  - §4.1 (causative A verbs) and §5 (causative A/B verbs).
  - §6.1 (intensive B verbs, plus the intensive A and A/B lists).
  - Footnote 33 (Simple-template A/B, A and B lists).
  - Tables 1–4.
- Check the totals: **95 A, 45 A/B, 37 B**.
- Map the paper's citation forms (roots, 3ms forms) to Dicta's lemma conventions.
- Build a gold set from the paper's ~100 numbered examples (verse, verb, frame, preposition). Correct versification to Hebrew numbering, because the paper sometimes cites English/KJV numbering (e.g. "Ezra 9:10" = Hebrew 9:11, "Psalms 52:5" = Hebrew 52:7).

### R2 — Frame extraction and the preposition-identity test on Mikra (§5, stage 1)
- For each occurrence of a lexicon verb:
  - Find the direct object: an את-marked or unmarked obj, a clitic (suffix) object, or the passive subject (the paper counts passive and middle forms).
  - Find the PP dependents and their preposition: ב, מ/מן, על, אל, ל, מעל, מתוך…
- Compute a deterministic **syntactic signature**, e.g. `V + obj + PP[ב]`.
- **Assign Locatum vs Location roles.** This is the methodological crux: מילא את המיכל במים and מילא מים במיכל have the *same* syntactic shape, so Frame A vs B is a semantic decision. Use transparent, logged heuristics: verb-class priors, noun semantic lists (place, container, body part vs substance), definiteness, and the paper's elided-preposition rule (footnote 13).
- Known pitfalls from the paper:
  - Elided Locatum ב- with indefinite nouns (fn 13, 21).
  - Partitive מן (fn 24, 27).
  - Instrumental ב- (fn 7).
  - על in place of ב- (fn 22).
- Aggregate per verb: observed class, preposition per frame, and the identity rate for A/B verbs. Compare with the paper using a confusion matrix.
- Validate on the paper's gold examples and a hand-annotated random sample (~150 occurrences). Separate parser errors from rule errors.

### R3 — All corpora (§5, stage 2)
- Run the same pipeline per corpus and stratum.
- Test the paper's §8 predictions:
  - alternations are preserved in MH;
  - when an alternation is lost, Frame A is preserved (שם, הסיר, היזה, ירה, אסף, חסך, גזל, מחה);
  - MH has new alternating manner verbs (שטף, שפשף, ניער, ניגב, קרצף…).
- Run a manual audit per corpus, because parser accuracy differs by period.

### R4 — Extend the scope (§6)
- In one corpus, classify *all* verbs: compute frame-signature distributions for every verb with obj+PP patterns and score its class.
- Find verbs that occur in both frames and characterize them.
- Corpus choice will be made on evidence: Mikra (paper ground truth) or a Modern genre (more data, better parser accuracy).

### R5 — Verb feature vectors (§7)
Labelled verbs come from the R1 lexicon plus validated R4 additions. Vectors are aggregated per verb, and each family is a separate vector set:

| Family | Contents |
|---|---|
| **Lexical** | Neighbouring lemmas in a context window |
| **Morphological** | The verb's own features and its neighbours' features, including binyan |
| **Syntactic** | Dependency paths rooted at the verb; deprel and preposition profiles |
| **word2vec** | Dicta's vectors (link still needed, ask the professor); fallbacks are gensim trained on our lemmatized corpora, or mean DictaBERT embeddings |
| **Combinations** | Concatenations of the above |

Apply a minimum-frequency threshold and report which verbs it excludes.

### R6 — Classifiers (§7)
- Models: scikit-learn LogisticRegression, LinearSVC, RandomForest, NaiveBayes, kNN, each crossed with each feature family.
- Evaluation: stratified, repeated 10-fold CV, split at the verb level (no lemma leakage).
- Metrics: Accuracy, macro and per-class P/R/F1, against a majority baseline.
- Analysis: ablations, and whether the results depend on verb class or corpus. The dataset is small (~180 verbs), so report variance.

### R7 — LLM integration (§8)
- Use DictaLM (or another LLM) as an *evaluated annotator*: Locatum/Location role labelling, frame judgments, and noun semantic classes.
- Measure agreement with the R2 gold set and compare with the rule-based method. Never use LLM output as ground truth.

### R8 — Report and submission (§9–10)
- Report: research question; literature review (§1 reading, the students' own work); §4 statistics and analysis; results of §5–8; conclusions.
- Submission: report, relevant data, relevant code, with a README and reproduction instructions.

### Personal-initiative opportunities (§11)
- Measure Dicta's accuracy on Biblical Hebrew against ETCBC/BHSA gold.
- Compare binyan profiles per period against the paper's template claims.
- Contrast original vs translated Modern literature (`literary/O` vs `literary/T`).
- Contrast Arabic-translated vs original medieval works.
