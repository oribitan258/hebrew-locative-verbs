# Project Roadmap — Hebrew Locative Verbs Across Periods

Status: **living document.** Part 1 (M0–M6) is done; M7 review is pending.

**§5–§6 CHECKPOINT 1 reached (2026-11-19).**
- **Approved:** the shared methodology **`S56-v1`** (D-053–D-056).
- **Where it is written:** in full in [EFRAT_SECTION_6.md](EFRAT_SECTION_6.md) §5, which is normative and is also
  Efrat's §6 handoff.
- **Stage 3 = §5 on Mikra.** Its plan is approved.
  - **Release R1 = tag `s56-r1`** (2026-11-20, D-057) is a provisional infrastructure milestone.
  - **OI-1/OI-2** were investigated, and the shared policy `vunit-v1` was approved (D-059).
  - **Phase B (the R2 code) is BUILT** (`docs/S56_R2.md`); STOP-B was decided on 2026-11-21 (D-060 accepted).
  - **AI-only SILVER annotation (D-061, 2026-11-21) is BUILT and RELEASED** as R1.1 = tag `s56-r1.1` (G1 done,
    pushed; zero manual data work; `annotation/S56_SILVER_PROTOCOL.md`).
  - **The ordered remaining stages, through §5 and §6 completion, are in [STAGES.md](STAGES.md)** (prerequisites,
    completion checks, handoffs, gates; `start` / `end-of-session`). In short:
    - Efrat's Claude Code makes the sentence silver and the Modern noun types (E1–E6);
    - Ori's Claude Code makes the Mikra and historical noun types, the unit links and the AI audit (O1–O3);
    - **Phase C** (identification and the resolver on dev silver; validation once; test once) needs Ori's approval
      (G2), and follows the pre-registered rules of D-059 (addendum).
- Efrat does no manual data work (D-061); her steps are EFRAT_SECTION_6 §9.2 as amended.
- **No paid external API** (D-054).
- **Still closed** until Ori opens them: §7, the rest of §8, and §4 R7.

Authoritative spec: `project.pdf` (Hebrew; local copy, not in git). Paper: Doron & Dubnov (2017), *The locative alternation
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

§2–§4 are closed (2026-11-16, D-050). Summary for the professor: [SECTIONS_2-4.md](SECTIONS_2-4.md).

| § | Stage | Status (reviewed 2026-11-16) |
|---|---|---|
| §1 | Background reading and summaries (paper ch. 1–3; morphology/syntax of each period, with sources; classifiers; Acc/P/R/F) | **Not started in the repo.** Only an internal paper summary (§0 above) exists |
| §2 | Corpora | **Done** (M1: 404,294 files cataloged; M2: 9,709,662 units) |
| §3 | Dicta parsing of every verse/sentence | **Done** (M5: all units of all five corpora, all of Modern, 31/31, D-049). Dicta has no construct state or binyan (§3.2 lists construct) |
| §4 | Statistics R1–R6 | **Done, final** (2026-11-16); analysis draft awaits Ori's approval |
| §4 | "Any additional statistic" (R7) | **In progress, exploratory (Efrat):** analysis package D-051; findings reviewed by Ori before the report. Part B of the main design stays deferred (D-046). Parser accuracy vs BHSA was done as an extra |
| §5 | Test the claim (Mikra first, then the other corpora) | **Methodology approved** (`S56-v1`, CHECKPOINT 1, 2026-11-19). Ori leads; stage 3 = Mikra (R1 → code → validation → CHECKPOINT 2 = tag `s56-v1`); stage 2 = Ori ∥ Adi, split by corpus with a balanced workload, decided at CHECKPOINT 2, M5-style workflow. **R1 released 2026-11-20 (`s56-r1`, provisional, D-057).** **Phase B built 2026-11-20 (D-059, D-060 accepted).** **SILVER workflow released 2026-11-21 (D-061, tag `s56-r1.1`).** **D-062 fix released 2026-11-21 (`s56-r1.2`); O1 done (Mikra noun silver frozen).** **O2 done 2026-11-22 (unit links, AI audit 95/100, P5 evidence frozen; D-063).** **P2 (D-064): D-063 to Efrat as `s56-r1.2.1`; `FROZEN_SILVER.json` excluded from the pinned-file checks.** **O3 done 2026-11-22 (unit map + `noun_types.yaml` v1, 2,777 lemmas, frozen).** **C0 done 2026-11-22 (Phase C build, D-065; local commit, not pushed).** **G2 done 2026-11-22.** **C1 done on dev 2026-11-23 (D-067): I-2 not adopted; I-1/I-4 → supplement, I-3 → sense screen.** **G3 done 2026-11-23 (D-068 … D-070): supplements mikra-s1 / modern-s1 registered, I-3 screens drawn; tag `s56-r1.3` → Efrat's ES.** **R done 2026-11-23: ES part 1 received (delivery 3).** Next: C1 part 2 (I-1 / I-3 / I-4 decisions) → ★ G4. Stages: [STAGES.md](STAGES.md) §3 |
| §6 | Extend to all verbs in one corpus | **Handoff ready:** [EFRAT_SECTION_6.md](EFRAT_SECTION_6.md). Owner: Efrat; corpus = **Modern** (D-055). Now: her silver deliveries (E1–E6: Modern noun types, then the sentence silver of both samples, D-061); her §6 runs after R2 (`s56-v1`). Stages: [STAGES.md](STAGES.md) §4 |
| §7 | Classifiers (lexical, morphological, syntactic and word2vec features; 10-fold CV; Acc/P/R/F1) | Not started (R5–R6). **Out of scope for now** (2026-11-19) |
| §8 | LLM integration | Not started (R7). Policy (D-054): no paid external API without Ori's separate approval. Claude Code assists only human-reviewed steps of §5–§6, disclosed in the report |
| §9 | Report | Partial: only the §4 part exists (`stats_report.md` + draft `stats_analysis.md`) |
| §10 | Submission (report, data, code) | Not started. Code is in the public repo; a data package is still to be chosen |
| §11 | Personal initiative | Ongoing. Examples: parser accuracy on all of Mikra vs BHSA; full provenance; exact-units merge |

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
| M6 Statistics | Exactly the §4 statistics (R1–R6) per corpus, full view (D-046; R7 extras deferred); parser accuracy on Mikra vs BHSA. Built 2026-11-12; accuracy final; **FINAL statistics for all five corpora 2026-11-16** (31/31 merged and registered, D-049; `final-20261116-565826e3c1`); analysis draft [stats_analysis.md](stats_analysis.md) | `data/stats`, `results/stats`, `docs/stats_report.md`, [stats_analysis.md](stats_analysis.md), [m6_design.md](m6_design.md) |
| M7 Review | Stop and review with the partners | — |

---

## Part 2 — Long-term roadmap

> **R1–R4 are SUPERSEDED by the approved methodology `S56-v1`** ([EFRAT_SECTION_6.md](EFRAT_SECTION_6.md) §5;
> D-053–D-056, 2026-11-19). The main differences from the draft below:
> - **Roles.** Locatum/Location roles come from a local resolver (R0, R1, R2) chosen on validation gold, with no
>   verb-class priors.
> - **Outcomes and classes.** Instance outcomes and verb classes include NON_LOCATIVE, AMBIGUOUS and
>   UNDETERMINED/INSUFFICIENT_EVIDENCE.
> - **Identity.** The test is the paper's existence claim.
> - **§6.** Modern, every verb lemma.
> - **Validation.** Gold sizes are 400 (Mikra) + 400 (Modern), with a dev / validation / test split.
>
> R1–R4 are kept below for history only. R5–R8 remain unapproved drafts.
>
> **Agreed workflow for §5–§6 (Ori, 2026-11-19).** `project.pdf` and the paper win over R1–R4 below. Details:
> `docs/HANDOFF.md` and EFRAT_SECTION_6.md §3.
> - **§5 (R1–R3): Ori leads.** Ori implements and validates Mikra first.
>   - Then Ori and **Adi** divide the remaining corpora **by corpus**, with a balanced workload, and work in
>     parallel. **The split is decided at CHECKPOINT 2.**
>   - Adi's workflow mirrors M5 (assignments, data, automated execution, validation, packaging, verified merge) in
>     her existing repo clone.
>   - Her handoff is `docs/ADI_SECTION_5.md`, started with `start`.
> - **Compatibility:** the same methodology, pinned code version and output formats for Ori, Adi and Efrat.
> - **§6 (R4): Efrat**, on her computer, on **Modern** (D-055), following
>   [EFRAT_SECTION_6.md](EFRAT_SECTION_6.md). She reuses the shared methodology and code.
> - **One shared methodology** for both sections, written in `docs/EFRAT_SECTION_6.md` (self-contained, for
>   Efrat's Claude Code).
> - **Mandatory checkpoint 1:** once Ori approves the methodology, STOP, complete `docs/EFRAT_SECTION_6.md` and
>   tell Ori it is ready to transfer. No implementation until Ori approves the next stage. **DONE 2026-11-19.**
> - **Mandatory checkpoint 2:** once §5 is validated on Mikra, STOP: split stage 2 between Ori and Adi, build and
>   test Adi's workflow, write `docs/ADI_SECTION_5.md` and her `start` rule, and tell Ori it is ready for Adi.
> - **Sessions:** one stage per session, each ending at an approval checkpoint, with docs and memory updated.
> - **§7 (R5–R6):** out of scope.

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
- **Policy (D-054):** no paid external API without Ori's separate approval. Locally run models are a possible
  option, to be decided if §8 is opened.
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
