# EFRAT_SECTION_6.md — Efrat's §6 handoff and the shared §5–§6 methodology `S56-v1`

**Status:** approved by Ori on 2026-11-19 (CHECKPOINT 1; decisions D-053 to D-056 in `docs/decisions.md`).
**Release R1 (tag `s56-r1`) is out since 2026-11-20 (D-057). Release R1.1 (tag `s56-r1.1`, D-061) replaces every
manual annotation step with AI-only SILVER annotation: §9.2 as amended below is allowed once `git tag -l s56-r1.1`
lists the tag.** R2 (`s56-v1`) is not out yet: nothing of §9.3.

> **Amended by D-061 (2026-11-21): AI-only SILVER annotation.**
> - **Zero manual data work.** Efrat and Ori annotate nothing, type no noun and review no row. They manage the
>   project and approve project-level decisions.
> - **Every AI label is SILVER** (`label_source = ai`), never human gold, and is never reported as validated
>   accuracy.
> - **Efrat's Claude Code is the silver annotator** for both frozen samples (Modern and Mikra), the paper anchor, the
>   worked examples and the Modern noun types. It follows `annotation/S56_SILVER_PROTOCOL.md` exactly: isolated
>   workspaces outside the repo, two independent passes, deterministic adjudication, QC, and a freeze.
> - **Unchanged:** the methodology, the frozen samples and the roles.
> - **The passages marked "D-061" below replace the manual steps.**
>
> **Sessions (2026-11-21): [STAGES.md](STAGES.md) orders every remaining stage** (E1 … E12 for Efrat), with
> prerequisites, checks and handoffs. Begin each Claude Code session with `start` and finish it with `end-of-session`,
> which updates `data/outbox/efrat-s6/STATE.md` and prints CONTINUE, SEND TO PARTNER or WAIT.

**Who reads this:** Efrat and her Claude Code, on Efrat's computer, in her clone of the public repo.

**What it is:** the complete, self-contained handoff for assignment §6. It also contains **the one research
methodology that §5 and §6 share** (`S56-v1`). Ori, Adi and Efrat all follow it.

> **For Claude Code: read this first.**
> 1. This document is **normative**. Do not invent your own frame definitions, extraction rules, role rules, verb
>    classes or output formats. If something here seems wrong or missing, write it down as feedback for Ori
>    (§12) and continue only with what is allowed.
> 2. **What is allowed depends on the release present in the repo** (§9). Since 2026-11-20 the "after R1" steps
>    (§9.2) are allowed: `git tag -l s56-r1` must list the tag. Never write or run frame extraction or
>    classification code before release R2 (`s56-v1`) exists.
> 3. Work in **Plan Mode** for any non-trivial step. Present the plan to Efrat; she approves before you execute.
> 4. **No paid external API** (no LLM API) may be used, for any purpose.
> 5. Talk to Efrat in clear, simple English. Each step ends with a short summary: what was done, why, and how we
>    know it worked.

---

## Contents

1. The exact requirements of §5 and §6
2. The paper in brief (what you must know)
3. Division of work, dependencies and timeline
4. Assignment requirement vs. our methodological choice
5. The shared methodology `S56-v1`
6. AI tools: what is used and what is not
7. Shared code, interfaces and output formats
8. Data: what you need, how to get it, how to verify it
9. Start here: what Efrat can do now, and what must wait
10. Outputs and how they come back to Ori
11. Answers to every point raised by Efrat's Claude Code
12. STOP rules
13. Glossary and facts measured on our data

---

## 1. The exact requirements of §5 and §6

`project.pdf` (local course copy, not in git) is the source of truth. The original Hebrew follows, then an English
rendering.

### §5 — Testing the paper's central claim

> **.5 בדיקת הטענה המרכזית של המאמר**
> בשלב הראשון על מאגר לשון המקרא, בשלב השני על כל שאר המאגרים:
> - מצאו את כל פועלי הלוקייטיב
> - סווגו אותם, אוטומטית, על פי המבנה התחבירי לקטגוריות השונות במאמר.
> - מצאו את מילת היחס בכל מבנה, ובדקו האם היא זהה.
> - הפיקו סטטיסטיקות של הנתונים
> - השוו זאת לנאמר במאמר

The work runs first on the Biblical corpus, then on all the other corpora:
1. Find all the locative verbs.
2. Classify them **automatically, by syntactic structure**, into the paper's categories.
3. Find the preposition in each structure, and check whether it is identical.
4. Produce statistics of the data.
5. Compare with what the paper says.

### §6 — Extending the paper's scope

> **.6 הרחבת ההיקף של המאמר**
> עבור על אחד מהמאגרים:
> - סווגו את כל הפעלים על פי השתייכותם לכל אחת מהקטגוריות במאמר.
> - בדקו האם קיימים פעלים המופיעים, כמו פעלי לוקייטיב, בשני המבנים התחביריים. אם כן, נסו לאפיין אותם.

For **one** corpus:
1. Classify **all** the verbs by their membership in each of the paper's categories.
2. Check whether there are verbs that, like locative verbs, appear in **both** syntactic structures. If so, try to
   characterize them.

### Related requirements

- **§1.2** asks you to read about classification metrics: precision, recall, F-measure and accuracy. We use them in
  every validation.
- **§7** (out of scope for now) will later need "a dataset with each verb's category". Our §6 output is designed so
  §7 can use it.
- **§8** asks how AI tools can be used. See §6 of this document.
- **§9** is the report. It presents the results of §5–§8.

**Decided for §6 (Ori, 2026-11-19): the corpus is Modern Hebrew.**
- All 27 Modern slices, all genres.
- The **full view** is the primary result. The curated view is reported as a secondary, labelled view.
- Results are also given per genre.

---

## 2. The paper in brief (what you must know)

Doron & Dubnov (2017), *The locative alternation in Biblical (and Modern) Hebrew*.
Read chapters 1–3 (pp. 1–12); for §6, also read §5–§6 (the verb lists) and §8 (Modern Hebrew).

### Arguments and frames

- **Arguments.** A locative verb has an Agent/Cause, a **Locatum** (the thing that moves, or is put or removed) and
  a **Location** (the place, container or possessor). Arguments can be abstract (p. 4): "deprive myself of good"
  is locative.
- **Frame A.** Agent V **Locatum** (= direct object) P + Location. Example: מילא מים **ב**מיכל.
- **Frame B.** Agent V **Location** (= direct object) P + Locatum. Example: מילא את המיכל **ב**מים.
- **Passives count.** The passive subject plays the role of the direct object (p. 4, fn 10).
- **Partial frames count.** "In Frame A the direct object is the Locatum, whereas in Frame B the direct object is
  the Location" (§2.2). So an object alone shows the frame.

### Verb classes

| Class | Meaning | Stated count | Listed in the paper |
|---|---|---|---|
| **A** | Frame A only (motion of the Locatum) | 95 | §4.1: 38 Causative; §6.1: 12 Intensive; fn 33: Simple |
| **A/B** | Both frames (alternating) | 45 | §4.1: 7 Causative; §6.1: 7 Intensive; fn 33: 31 Simple |
| **B** | Frame B only (mereological: Location gains or loses a part) | 37 | §4.1: 3 Causative; §6.1: 15 Intensive; fn 33: 19 Simple |

**Known discrepancy.** fn 33's Simple-template A list names **46** verbs, but the text says 45. So the A lists add
up to 96, not the stated 95. The lexicon records this; it is not silently fixed.

**Other verb sets in the paper:**
- **Table 1:** path verbs used both for putting and for removal. All of them are A or A/B, never B.
- **Table 2:** change-of-state verbs used as A verbs.
- **Table 3:** causative A verbs derived from Simple motion verbs.
- **Table 4:** B verbs derived from verbs of mereological relations.

### The central claim

The **Locative Alternation Preposition Identity**: Hebrew verbs that alternate "allow **the same preposition** in the
two alternants".
- For verbs of **putting** the preposition is **ב-**.
- For verbs of **removal** it is **מן** (cliticized as **מ-**). Per fn 8, both allomorphs appear in both frames.

### Pitfalls the paper itself names (our extractor flags each one)

- **fn 13, 21.** The Locatum's ב- is often **elided** when the Locatum is indefinite (a bare second noun), e.g.
  Haggai 2:7.
- **fn 24, 27.** **Partitive** מן ("some of the blood") is not the locative מן. That noun is the direct object.
- **fn 7.** **Instrumental** ב- ("with a staff") is not the Locatum's ב-. It can co-occur with a Location ב-.
- **fn 15.** Path verbs also take other prepositions: אל, ל-, על, תחת, אחרי, בין, מעל, מעם, מאת.
- **fn 22.** Some verbs take **על** in Frame A instead of ב-. The paper suggests על ≈ ב+על, by analogy with
  מעל ≈ מן+על.

### Modern Hebrew (§8): testable claims

- **Alternations preserved in MH:** מילא, משח, זרע, שטף, רוקן/הריק, פרק, ניקה, ריפא, פינה, רחץ, בזז, מנע, הפשיט.
- **When an alternation is lost, Frame A is what survives:** שם, הסיר, היזה, ירה, אסף, חסך, גזל, מחה.
- **New MH alternators (manner verbs, mostly removal):** שטף, שפשף, ניער, ניגב, קרצף, צחצח, הבריש, טאטא, מירק,
  גירף, זיקק.
  - Some of these can also be read as putting: עיסה, שטף, שפשף.
- **fn 38:** חגר, מירק, זיקק, ריסס alternate in MH.
- **fn 39:** נישל alternates in MH.
- **Prediction:** A/(B) verbs never become B verbs.

---

## 3. Division of work, dependencies and timeline

| Who | Task | When |
|---|---|---|
| **Ori** | Leads §5. **Stage 1 = Mikra**: builds and validates the shared code. **D-061:** his Claude Code (in isolated silver workspaces) makes the Mikra and historical noun types, the verb-unit links and the 100-link AI audit; it never annotates sentences (it is the developer) | Now → CHECKPOINT 2 |
| **Ori + Adi** | **§5 stage 2**: the remaining corpora (Hazal, Medieval, Haskala, Modern), divided between them by corpus with a **balanced workload**, run **in parallel**. Adi uses her existing repo clone and an M5-style workflow (detached run, outbox, verified merge). **The split is decided at CHECKPOINT 2.** | After CHECKPOINT 2 |
| **Efrat** | **All of §6, on Modern**: classify all verbs; find and characterize verbs in both structures. Also, for the shared validation, **D-061:** her Claude Code produces the **SILVER labels of both frozen samples** (Modern and Mikra), the paper anchor and the **Modern noun types**; Efrat manages and delivers | Preparation now; runs after R2 |
| Ori | Merges stage 2, computes the official §5 statistics **once, centrally**, reviews Efrat's §6 delivery, writes the report | After stage 2 |
| — | §7 classifiers | Out of scope for now |

### Checkpoints and releases

- **CHECKPOINT 1 (reached 2026-11-19).** The methodology was approved, and this document was published in git.
- **R1 (early in stage 3).** Ori releases:
  - the verb lexicon;
  - the annotation guideline;
  - the gold sampler;
  - the frequent-argument-noun lists to be labelled.
- **R2 = git tag `s56-v1` (CHECKPOINT 2).** The shared code, validated on Mikra and frozen: extractor, role
  resolver, classification, statistics, and the noun-type file. Adi and Efrat run **only** this version.

### Dependency graph

```
CHECKPOINT 1 ──► Efrat: sync, data check, §6 planning (no extraction code)
     │
     ▼
Stage 3 (Ori, Mikra) ── R1 ──► Efrat: Modern gold annotation + Modern noun-type labels ──┐
     │                                                                                 │ (feeds validation
     ▼                                                                                 │  and the frozen
CHECKPOINT 2 = R2 = tag s56-v1 (Mikra validated; split of stage 2 decided) ◄──────────────┘  noun types)
     │
     ├──► Ori ∥ Adi: §5 stage 2 (lexicon mode, their corpora) ──► verified merge ──► central §5 statistics
     └──► Efrat: §6 on Modern (all-verbs mode) ──► data/outbox/efrat-s6 ──► Ori's review
```

**What blocks what:**
- Efrat's §6 runs need R2.
- **D-061:** "gold annotation" in the graph above is now **SILVER annotation by Efrat's Claude Code** (both samples).
- Phase C needs the dev silver of both corpora and the Modern noun types. Deliver them first, after R1.1.
- The validation and test silver can come later: each is frozen and its hash recorded before it is read once.

---

## 4. Assignment requirement vs. our methodological choice

| `project.pdf` requires | Our choice | Why |
|---|---|---|
| §5: Mikra first, then all other corpora | Stage 1 Mikra (Ori), validated; then stage 2: Ori ∥ Adi, balanced | The agreed workflow |
| §5: find **all** locative verbs | A **closed lexicon** = the paper's verbs + the §8 MH supplement. **Every occurrence** in every corpus is found (by lemma or by word form), never sampled | The paper defines the set; discovering new verbs is §6 |
| §5: classify **automatically by syntactic structure** | Automatic extraction from Dicta's dependency trees; automatic local role rules; classes A / B / A/B, plus explicit non-decisions | The frames differ in which argument is the object. That is a role, decided by local rules and validated |
| §5: find the preposition in each structure; is it identical? | Per alternating verb: is the same preposition **attested** in both frames? | This is the paper's exact claim ("allow the same preposition") |
| §5: statistics; compare with the paper | Per corpus; full view primary, curated view secondary; Mikra vs the paper's lists and examples; Modern vs §8 | Project rule D-015 |
| §6: one corpus | **Modern** | Ori's choice |
| §6: classify **all** verbs | **Every** verb lemma gets a label, with **no frequency cut-off**, including explicit "non-locative", "ambiguous" and "insufficient evidence" labels | "all" |
| §6: verbs in both structures; characterize them | A role-free swap detector, plus local roles, plus Efrat's manual review; characterized by the paper's own criteria | The paper's §3, §5, §6, §8 |
| §1.2 metrics; §8 AI tools | Precision, recall, F1 and accuracy in every validation; Claude Code only for human-reviewed steps; **no paid API** | Ori, 2026-11-19 |

---

## 5. The shared methodology `S56-v1`

Every output records the version string `S56-v1`. Changing the methodology needs a decision entry by Ori and a
version bump.

### 5.1 Lexicon (`config/locative_verbs.yaml`; only Ori edits it)

**Core entries** come from the paper's class lists (§4.1, §5, §6.1, fn 33).
- **One entry per (root, template).** The template matters for the class. For example, שלח in the Simple template
  is an A verb, but שִׁלַּח in the Intensive template is A/B; חיסר (Intensive) is B, but החסיר (Causative) is A.
- **Each entry has:**
  - `id`, `root`, `template` (Simple / Intensive / Causative), and the citation form;
  - `class` (A, A/B or B) and `putting_removal` (where the paper says);
  - `paper_refs`: the section or table, and its examples with their a/b frame, mapped to Hebrew verse numbering;
  - `dicta_lemmas`: the lemma variants Dicta uses, including passive forms;
  - `forms`: the form list used by the fallback;
  - `flags`: homograph, template-ambiguous (forms that cannot tell two entries apart without vowels), and so on;
  - `nonlocative_idioms`: object nouns that turn the verb into an idiom, e.g. שם + לב. These are listed only from
    clear dictionary knowledge, and reviewed by Ori.
- **Supplementary entries** are flagged and reported separately:
  - verbs that appear only in Tables 1, 2 and 4;
  - the **§8 MH supplement** (the lists in §2 above), with the paper's MH prediction for each verb.
- The 95/96 discrepancy is documented inside the file.

### 5.2 Identification: every occurrence, never sampled

- A token is an occurrence of entry *e* when **either**:
  - its Dicta lemma is in `e.dicta_lemmas`; **or**
  - its upos is VERB and its prefix-stripped form is in `e.forms`. This recovers blank and wrong lemmas.
- Every occurrence records `match_method` (`lemma`, `form` or `both`).
- **In Mikra** (Ori), identification is measured against BHSA lexeme + stem: precision and recall per verb. A
  sensitivity run with gold BHSA identification checks whether any conclusion changes. **BHSA is used only for
  Mikra.**
- **In Modern**, the loss of recall is estimated from a sample of blank-lemma verbs. This sample only measures; it
  decides nothing.

### 5.3 Extraction: automatic, from Dicta's tree, one row per occurrence

For each occurrence, look at its dependents in the parse tree, within its piece:

**Direct object (DO)**, any one of:
- an `obj` dependent, with or without את (`case:acc`);
- an object suffix on the verb (`suffix = PRON`);
- the separate object pronouns אותו, אותה, אותם… (`obj`);
- for a passive entry, the `nsubj`.

**Prepositional phrases (PP):** every `obl` or `nmod` dependent that carries a preposition. The preposition is
either a clitic prefix (ב, מ, ל, in `prefix` / `prefix_upos`) or a `case` word (מן, על, אל, עד, בתוך, מעל…).
Pronoun forms such as בו, ממנו, עליו count as PPs whose object is a pronoun. Each PP records:
- `p_exact`: the exact preposition, e.g. `ב`, `מן`, `מ`, `מעל`, `על`, `בתוך`;
- `p_family`: `B` (ב-, בתוך), `MIN` (מן, מ-, and every מ+X compound: מעל, מתוך, מאת, מעם, מיד, מקרב, by the
  paper's fn 22 analogy), `AL` (על), `EL` (אל), `LE` (ל-), or `OTHER`.

**Bare second noun (`BARE_NP`):** a second nominal dependent with no preposition (`obj`, `xcomp`, `dep`,
`parataxis`, `obl:npmod`). This is a candidate for the elided preposition of fn 13.

**Signature:** a string that summarizes the structure, e.g. `V+DO+PP[B]`, `V+DO`, `V+PP[MIN]`, `V+DO+BARE`,
`V+DO+PP[B]+PP[AL]`.

**Flags (never filters):**
- `partitive_candidate`: a מן-PP that is the only complement of a transitive use (fn 24, 27);
- `instrument_candidate`: two ב-PPs (fn 7);
- `al_for_b`: על where ב is expected (fn 22);
- `conj_shared`: the verb is a conjunct, so its object may sit on the first conjunct (no inheritance across
  conjuncts);
- `tree_invalid`: `piece_tree_valid = False`;
- `multi_piece`: `n_pieces > 1` (D-021).

**Design rule:** rows depend only on the token and its tree, never on which verbs were selected. So
`--mode lexicon` and `--mode all-verbs` give **byte-identical rows** for the same token.

### 5.4 Roles and frames: the local resolver (no API)

**Rule zero.** The role decision **never uses the preposition of the instance being decided**. Otherwise the
identity test would be circular.

**Roles.** The resolver decides which argument is the **Locatum** and which is the **Location**:
- **Frame A**: the DO is the Locatum.
- **Frame B**: the DO is the Location.

**Instance outcomes.** Exactly one per instance, always with a `reason` code. **Nothing is forced.**

| Outcome | Meaning |
|---|---|
| `A` / `B` | Resolved frame |
| `NON_LOCATIVE` | **Positive** evidence that this use is not locative: a listed idiom (`nonlocative_idioms`), or a clausal complement with no nominal object |
| `AMBIGUOUS` | Evidence exists but supports both readings, or is in conflict (e.g. both arguments are LOCATION-type) |
| `UNDETERMINED` | Not enough information (e.g. no object; an untyped noun; a pronoun with no antecedent) |

**Noun types** (`config/noun_types.yaml`, frozen at R2):

| Type | Meaning | Examples |
|---|---|---|
| `LOCATION` | Inherently a place, container, surface, body part, land, building | בית, ארץ, כלי, ראש, עיר |
| `LOCATUM` | Inherently movable content: a substance, material, object, or abstract content | מים, שמן, אבן, אש, שמחה, טומאה |
| `ANIMATE` | A person or animal; can take either role, so context decides | איש, עם, בהמה |
| `UNCLEAR` | None of the above, or unknown | |

**Components**, applied in a fixed order:
1. **Structural rules from the paper.**
   - A DO plus a `BARE_NP` (indefinite) → Frame B, with the bare noun as the Locatum (fn 13, 21).
   - A `partitive_candidate` → the מן-noun is a Locatum DO (fn 24, 27).
   - A listed idiom → `NON_LOCATIVE`.
2. **Noun types.** Each argument head gets its type from the noun-type file.
   - **Variant R1** adds a corpus-induced *location-likeness score* for nouns that are not in the file. It is
     computed locally from the Dicta parses, using only **intransitive** motion and position verbs and excluding
     every lexicon verb. For example, "ישב בבית" shows בית used as a location. So the score never uses the tested
     constructions.
3. **Complementary inference.** In an instance with a DO and a PP, if one argument is LOCATION-type and the other
   is LOCATUM, ANIMATE or UNCLEAR, the first is the Location and the other the Locatum (and the reverse for
   LOCATUM). Two arguments of the same inherent type give `AMBIGUOUS`. ANIMATE + ANIMATE, or UNCLEAR + UNCLEAR,
   gives `UNDETERMINED`.
4. **DO only** (a partial frame): a LOCATION DO → B; a LOCATUM DO → A; otherwise `UNDETERMINED`.
5. **Pronouns.**
   - **Variant R2** adds an antecedent heuristic: the nearest preceding noun, in the same or the previous unit,
     whose gender and number match the pronoun's `suffix_feats`. The pronoun then takes that noun's type.
   - Without it, a pronoun is resolved only by complementary inference.

**Fixed variants:**
- **R0** = rules + noun-type file + complementary inference;
- **R1** = R0 + induced scores;
- **R2** = R1 + antecedent heuristic.

**Choosing a variant (pre-registered):**
- The choice uses **only the validation part of the gold** (see 5.8): Mikra validation, plus Modern validation if
  delivered before CHECKPOINT 2.
- **Metric:** macro-F1 over Frame A and Frame B, where a gold A or B instance that the resolver labels
  `AMBIGUOUS`, `UNDETERMINED` or `NON_LOCATIVE` counts as a miss.
- **Tie-break:** if two variants are within 1 F1 point, or not significantly different by McNemar's test, the
  simpler variant wins (R0 < R1 < R2).
- `NON_LOCATIVE` detection (precision and recall) and the shares of `AMBIGUOUS` and `UNDETERMINED` are always
  reported.
- The **test** part of the gold is scored **once**, after the choice, per corpus. It never influences any choice.

**The resolver id** is written into every output, e.g. `rules-R1@s56-v1`.

### 5.5 Verb classes (§5 bullet 2; also used by §6)

Per verb, per corpus and view, with `k = 1` as the primary threshold (the paper's own criterion: attestation), and
sensitivity runs at `k = 2` and `k = 3`:

| Class | Rule (applied in this order) |
|---|---|
| `A/B` | ≥ k resolved Frame A instances **and** ≥ k resolved Frame B instances |
| `A` | ≥ k resolved Frame A instances, no Frame B |
| `B` | ≥ k resolved Frame B instances, no Frame A |
| `NON_LOCATIVE` | No resolved frame, **and** either ≥ 1 instance with positive `NON_LOCATIVE` evidence, or ≥ 20 instances with an object examined and none locative. The rule of three: the locative rate is then below 15% with 95% confidence. The basis used is reported in `class_basis` |
| `AMBIGUOUS` | No resolved frame, no non-locative evidence, ≥ 1 `AMBIGUOUS` instance |
| `INSUFFICIENT_EVIDENCE` | Everything else, e.g. too few occurrences, or only `UNDETERMINED` ones |

**Rules that apply to every class:**
- **Never forced.** There is no default class. Every class comes with its evidence counts (A, B, NON_LOCATIVE,
  AMBIGUOUS, UNDETERMINED) and the ids of its deciding instances.
- **Mixed verbs.** A verb with locative frames also has `nonlocative_share` reported. Locative verbs often have
  idiomatic uses too.
- **Disagreements with the paper.** For §5, a class that differs from the paper lists the deciding instances, and
  those are audited as error analysis by the silver protocol (D-061: isolated two-pass AI review, never manual; the
  task is built before R2, STAGES.md C0).
- **Thresholds are labels, not exclusions.** `k` and the "20 with an object" evidence threshold are fixed at R2 and
  recorded in the manifest. A verb that does not reach them is labelled; it is never dropped.

### 5.6 Preposition identity (§5 bullet 3)

**The claim, exactly as the paper states it:** alternating verbs **allow the same preposition** in both frames (ב-
for putting, מן/מ- for removal).

**The test.** For every verb whose class is `A/B` in a corpus:

| Verdict | Meaning |
|---|---|
| `IDENTITY_ATTESTED` | Some `p_family` occurs **both** marking the Location in a full Frame A instance **and** marking the Locatum in a full Frame B instance. We report which family, and whether it is ב for putting or מן for removal |
| `COUNTEREXAMPLE` | Both frames have full instances with PPs, but **no** family is shared |
| `NOT_TESTABLE` | One of the frames has no full instance with a PP |

**Not counted as counterexamples:**
- other prepositions occurring alongside (fn 15);
- על in Frame A (fn 22). Reported twice: strictly, and with על counted as ב+על;
- an elided preposition with an indefinite Locatum (fn 13, 21).

**Secondary check:** fn 8, that both מן and מ- occur in both frames.

**Audit:** every verdict lists its deciding instances. Verdicts that differ from the paper are audited by the silver
protocol (D-061: isolated two-pass AI review, never manual; the task is built before R2, STAGES.md C0).

**Descriptive only:** distributions of preposition by frame are statistics, not the test.

### 5.7 Statistics and comparison (§5 bullets 4–5)

**Reporting conventions:**
- per corpus, on the **full view** (primary) and the curated view (secondary);
- per stratum or genre where relevant;
- Wilson 95% confidence intervals;
- every number traces back to `sent_id` and `ref`.

**Tables:**
- coverage and how each match was found;
- signatures;
- outcome shares, including `UNDETERMINED`;
- class against the paper: a confusion matrix, accuracy, and precision, recall and F1 per class;
- identity verdicts;
- putting/removal ambiguity: Table 1 verbs should be A or A/B, never B (§3.2.1).

**Robustness check, the role-free swap test.** For a verb and a preposition family, count the noun lemmas that
occur both as its DO and as the object of that preposition. A positive count shows alternation with the same
preposition, without any role decision.

**Comparisons:**
- **Mikra** against the paper's lists, examples and template proportions;
- **Modern** against §8;
- **Hazal, Medieval and Haskala** as the diachronic path, which is our own contribution.

### 5.8 Validation: SILVER labels (D-061), three-way split

> **D-061.** The annotator is **Efrat's Claude Code**, under `annotation/S56_SILVER_PROTOCOL.md`. The labels are
> **SILVER**: two independent passes in isolated workspaces, deterministic adjudication, QC, a freeze.
> - **There is no human gold.** Every score against silver is "agreement with silver", never accuracy.
> - **The 60 agreement items per corpus** become the fixed subset on which κ between pass A and pass B is reported.
> - **The rest of this section stands as written** for the guideline, the sizes and the splits. Read "annotator" as
>   "the silver annotator".

**Annotation guideline** (released at R1). The annotator reads the sentence and marks:
- whether the verb use is locative;
- the direct object;
- the PP(s) and their preposition;
- the role of each argument;
- the frame: A, B, non-locative, or ambiguous.

The annotator marks all of this from the sentence itself, so the gold also measures extraction recall.

**The labels are SILVER (D-061)**, not human gold. No AI label is ever presented as gold.

| Corpus | Annotator (D-061) | Size | Split |
|---|---|---|---|
| Mikra | Efrat's Claude Code (silver; not Ori's, which is the developer) | a stratified random sample of 387 (frozen `mikra-r1b-1cd4ee9802`), plus the paper anchor (the single-token paper examples outside the frozen validation/test items) | 98 dev / 98 validation / 191 test |
| Modern | Efrat's Claude Code (silver) | 400 = 300 paper-verb instances (serve §5 and §6) + 100 non-paper verbs with a locative signature (serve §6) | 101 / 101 / 198, within each stratum |
| Agreement | pass A vs pass B | 60 Mikra + 60 Modern | Cohen's κ between the two independent passes (reliability, not validity) |
| Hazal, Medieval, Haskala | — | 150 each | test only; silver only if Ori decides it at CHECKPOINT 2 |

**Storage.** Sheets, workspaces, transcripts and silver label files stay **local** (`data/`, gitignored; D-042).
- **Delivery:** by outbox only (`data/outbox/efrat-s6/silver/`).
- **In git:** only `annotation/silver/FROZEN_SILVER.json` (ids and hashes).

### 5.9 §6 on Modern (Efrat)

**Run** the shared extractor in `--mode all-verbs` over all of Modern (full view primary, curated view secondary,
per-genre tables), then the frozen resolver variant.

**(1) Classify all verbs.**
- **Every** verb lemma gets one row in `verb_classes`: about 18,600 lemma types in Modern.
- Tokens with a blank lemma first go through the form fallback. Those still unmatched form an `UNLEMMATIZED`
  bucket that is described, not dropped.
- Classes are those of 5.5, always with evidence counts. A sensitivity view covers verbs with at least 20 tokens.
- **When a non-paper verb counts as locative at all:** at least one full locative frame (DO + PP, with roles
  Locatum/Location). This is the paper's own inclusion criterion (fn 5): both internal arguments are attested.
- **Evaluation** against the paper's verbs (their BH classes) and the §8 MH predictions:
  - A/B → A in MH is a change the paper expects;
  - A/(B) → B would violate §8.
- Precision, recall and F1 per class.

**(2) Verbs in both structures.**
- **Role-free definition:** V X P Y ~ V Y P X with the same preposition family.
- **Candidates:**
  - the swap test of 5.7, which needs no roles, with its supporting instance ids;
  - plus verbs whose resolved outcomes include both A and B;
  - plus verbs whose signature profiles show DO + PP[B] and DO + PP[MIN] patterns.
- **Confirmation (D-061).** Efrat's Claude Code reviews a sample of each candidate's instances by the silver
  protocol, recorded in a review file with `label_source = ai`:
  - isolated workspaces;
  - two independent passes;
  - abstention when unsure.

  Efrat approves the delivery, not the rows.

**(3) Characterize the confirmed verbs.** For each one:
- semantic field;
- preposition family;
- **template proxy** from the lemma's shape, checked by the silver protocol (D-061: a two-pass AI check of a sample
  of lemmas, `label_source = ai`; the task is built before R2) (e.g. ה_י_ → Causative; נ___ → Nifal;
  הת___ → Hitpael; a Modern plene spelling with י after the first radical → Intensive);
- putting / removal / both;
- path vs mereological, using the paper's two conditions for alternation (§3.1, §5): an agentive verb leading to a
  result state, and a symmetric stative preposition;
- whether it is a manner-of-motion verb (§8);
- frequency by genre;
- whether its arguments are spatial at all. Some verbs may alternate with non-spatial arguments; describe them,
  don't force them into locative roles.
- *These dimensions are a framework, not expected results.*

**(4) Feedback to §5.** A paper verb that looks misclassified, or an alternating verb that the paper does not list,
is reported to Ori. It may point to a lexicon or extraction issue.

---

## 6. AI tools: what is used and what is not

- **No paid external API is used** (Ori, 2026-11-19). That means no LLM API and no paid service. An external LLM
  could only be added later, as an extra resolver, after Ori's **separate** approval. Nothing in `S56-v1` depends on
  one.
- **Dicta's existing parses are the main resource.** They give the lemmas, POS, morphology, suffixes and dependency
  trees for every unit. **We never re-run Dicta.**
- **Each person's existing Claude Code (D-061, amending D-054):**
  - **SILVER annotation.** It makes every data label under `annotation/S56_SILVER_PROTOCOL.md`: sentence labels,
    noun types, unit links, audits and the §6 candidate review.
    - Each pass runs in an isolated workspace, and two independent passes are adjudicated deterministically.
    - Abstention is allowed, QC thresholds are pre-registered, and every result is frozen.
    - **Humans approve files and milestones, never rows.**
  - **Code and docs.** It writes the code (Ori's repo) and the documentation.
- **Never:**
  - an AI label is presented as **gold**, or a silver-based score as validated accuracy;
  - Claude Code labels instances **at run time** (the resolver is rules only);
  - a frozen silver file is changed;
  - the developer (Ori's Claude Code) annotates sentences, or reads validation or test silver outside the once-only
    `--choose` and `--final-test`.
- **Disclosure.** All of this is disclosed in the report as AI-generated annotation, approved at the project level by
  Ori, with no row-level human review. The limits are part of our §8 discussion: no independent human gold;
  annotator and developer are both Claude models; Modern has no external anchor.

---

## 7. Shared code, interfaces and output formats

**Everything below is implemented by Ori in stage 3 and released as R1 and R2.**
- The **column names and meanings are binding now**. Exact types and command spellings are confirmed in the
  release notes of R1 and R2 (in `docs/HANDOFF.md` and an update of this document).
- **Do not implement your own version.**

### I1 — Configuration (read-only for Efrat)

- `config/locative_verbs.yaml`: the lexicon (5.1).
- `config/noun_types.yaml`: the noun types. Each row has `lemma`, `type`, `corpus_source`, `proposed_by` (`human` or
  `claude_code`), `reviewed_by`, `note`.
  - **D-061:** silver rows add `review_mode = automated`, `label_source = ai` and `silver_status`, with
    `reviewed_by = auto-qc:<qc_id>`.
  - They are merged only with `loc nouns merge --automated <frozen job folder>`.

### I2 — Commands (provisional names; exact syntax in the R1 and R2 release notes)

```
uv run python -m hebloc loc lexicon check                           # R1: lexicon is valid; counts vs the paper
uv run python -m hebloc loc gold sample --corpus modern --source package --package <path>   # R1: local sheets
uv run python -m hebloc loc nouns list --corpus modern --source package --package <path>    # R1: nouns to type
uv run python -m hebloc loc extract  --corpus modern --mode all-verbs --source package --package <path>  # R2
uv run python -m hebloc loc resolve  --corpus modern                # R2: frozen resolver variant
uv run python -m hebloc loc classify --corpus modern                # R2: verb_profiles + verb_classes
uv run python -m hebloc loc swap     --corpus modern                # R2: swap-test candidates
uv run python -m hebloc loc verify   <output folder>                # R2: re-hash + schema + manifest check
```

**Requirements on the commands:**
- `--source repo` reads the registered runs of the repo; `--source package` reads the D-051 package. **Both must
  give identical output**; this is tested before R2.
- The commands refuse to run unless the code is at tag `s56-v1` (clean tree) for R2 steps, and the
  lexicon and noun-type hashes match.

### R1 release notes (tag `s56-r1`, 2026-11-20, D-057)

**What R1 contains:**
- the lexicon `config/locative_verbs.yaml` (210 entries) and its generated forms
  `config/locative_verb_forms.yaml`;
- the guideline `annotation/S56_GUIDELINE.md` (`S56-v1-g1`);
- the gold sampler and gold check;
- the noun lists.

The full explanation is in [S56_R1.md](S56_R1.md).

**R1 is a provisional infrastructure milestone.** Its verb identification has known limits (S56_R1.md §0.1). They
are improved and validated on the dev gold before R2. For Efrat this changes nothing: she annotates what the sampler
gives her, by hand, and judges each item from the sentence.
*(Amended by D-061, 2026-11-21: there is no manual annotation. "Gold" here is the dev SILVER, and every item is
labelled by Efrat's Claude Code under `annotation/S56_SILVER_PROTOCOL.md`, §9.2 steps 4–9. The released R1 text above
is kept as it was.)*

**The exact R1 commands** (on Efrat's computer, `<package>` = the extracted D-051 package, e.g.
`C:\hebloc\hebloc-analysis-pack`):
```
uv run python -m hebloc loc lexicon check
uv run python -m hebloc loc gold sample --corpus modern --source package --package <package>
uv run python -m hebloc loc gold sample --corpus mikra  --source package --package <package>
uv run python -m hebloc loc nouns list  --corpus modern --source package --package <package>
uv run python -m hebloc loc verify <output folder>
uv run python -m hebloc loc gold check <sheet.csv> --sample <sample folder> --annotator efrat --out data/outbox/efrat-s6/gold
```

**Expected results** (anything else is a STOP, S1):

| Command | Must give |
|---|---|
| `loc lexicon check` | OK |
| Modern sample | `modern-r1b-5fbb5e22e7`, 400 items (dev 101 / validation 101 / test 198), manifest `frozen_check.items_match = true`. It takes about 10 minutes and 3.5 GB of memory |
| Mikra sample | `mikra-r1b-1cd4ee9802`, 387 items, 60 of them agreement items, `items_match = true` |
| Modern nouns | `modern-nouns-r1-826929982d`, 1,763 nouns to type |
| `loc verify` | OK on each output folder |

**The samples are frozen.** The sampler refuses to produce any other sample, so Ori and Efrat get the same ids.
The outputs go to `data/loc/gold/<corpus>/<sample_id>/` and `data/loc/nouns/modern/<list_id>/`.

### I3 — Output tables (Parquet + CSV copies with a UTF-8 BOM)

These are written under `data/loc/<corpus>/<output_id>/`.

**`instances`: one row per verb token in scope.**

| Columns | Meaning |
|---|---|
| `instance_id` = `sent_id\|piece_idx\|word_idx` | Key |
| `corpus`, `subcorpus` (genre), `run_id`, `shard`, `doc_id`, `sent_id`, `piece_idx`, `word_idx`, `sent_word_idx`, `ref` | Provenance (`ref`: Mikra only) |
| `in_full_view`, `in_curated_view` | Views |
| `form`, `lemma`, `upos` | The verb token |
| `verb_key` | Lexicon entry id; else `lemma:<lemma>`; else `form:<form>` for unlemmatized tokens |
| `in_lexicon`, `paper_class`, `match_method` (`lemma`/`form`/`both`/`none`), `voice`, `template_proxy` | Lexicon link |
| `signature`, `has_do`, `do_kind` (`noun`/`pronoun`/`suffix`/`passive_subject`/`none`), `n_pp`, `has_bare_np` | Structure |
| `flags` (list) | Flags of 5.3 |

**`arguments`: one row per candidate internal argument.**
- `instance_id`, `arg_idx`, `slot` (`DO`/`PP`/`BARE_NP`/`PASSIVE_SUBJ`);
- `head_word_idx`, `head_form`, `head_lemma`, `head_upos`, `is_pronoun`, `pron_feats`, `deprel`;
- `p_exact`, `p_family`;
- `flags`.

**`roles`: one row per instance per resolver.**
- `instance_id`, `resolver_id`;
- `outcome` (`A`/`B`/`NON_LOCATIVE`/`AMBIGUOUS`/`UNDETERMINED`), `reason`;
- `locatum_arg_idx`, `location_arg_idx`;
- `decided_by` (list of rule codes).

**`verb_profiles`: one row per corpus × view × `verb_key` × resolver.**
- token counts, counts per signature, and counts per outcome;
- the long table `verb_preps` (`verb_key`, `frame`, `p_family`, `p_exact`, `count`, `example_ids`).

**`verb_classes`: one row per corpus × view × `verb_key` × resolver.**
- `class`, `class_basis`, `k`;
- evidence counts, `nonlocative_share`;
- `paper_class`, `agrees_with_paper`;
- `identity_verdict`, `identity_family`;
- `putting_removal` (`PUTTING`/`REMOVAL`/`BOTH`/`UNKNOWN`);
- `deciding_ids`.

**`swap_candidates` (§6):**
- `verb_key`, `p_family`;
- `n_swap_nouns`, `swap_nouns`;
- `n_as_do`, `n_as_pobj`;
- `example_ids`.

### I4 — Gold files (ids and labels only; no corpus text)

- One row per gold instance: `sample_id`, `instance_key` (`sent_id|piece_idx|word_idx`, or a word span for tokens
  the extractor may not see).
- The annotation columns of 5.8.
- `split` (`dev`/`validation`/`test`), `annotator`, `guideline_version`.
- **D-061: SILVER files** (`<corpus>_<split>_silver.csv`) add:
  - `label_source = ai`, `silver_version`, `protocol_version`;
  - `silver_status` (`agreed` / `agreed_ctx` / `adjudicated` / `abstained` / `single_pass`);
  - `confidence`, `evidence_rule`, `abstain_reason`.

  They stay out of git, and the scorer reads them only when their hash is in `annotation/silver/FROZEN_SILVER.json`.

### I5 — Manifest (`manifest.json` in every output folder)

- **Version and code:** `methodology` = `S56-v1`; `git_tag`, `git_commit`, `dirty` (must be false).
- **Hashes:** `lexicon_sha256`, `noun_types_sha256`.
- **Run:** `resolver_id`, `mode`, `scope`.
- **Data source:** `repo` (with the run fingerprints of `config/annotations.yaml`) or `package` (with its
  `VERIFICATION.json` sha256).
- **Contents:** row counts, the sha256 of every file, `created_utc`, and the Python and package versions.

**Synchronization guarantees (checked by Ori):**
1. Repo input and package input give identical outputs.
2. Efrat's Modern rows for paper verbs are **byte-identical** to the §5 stage-2 Modern rows, whoever runs them.
3. Every delivery's manifest matches the tag, the hashes and the schemas.
4. Ori recomputes at least one delivered unit and must get a byte-identical result.

---

## 8. Data: what you need, how to get it, how to verify it

**What §6 needs:**
- the tokens and sentences of **all 27 Modern slices**: a7, news-other, knesset, blogs, medical, tapuz, literary,
  and haaretz b00–b19;
- the document catalog.

**What Efrat has today:** her repo clone, holding her own M5 share: Medieval plus 8 Modern slices (a7 and haaretz
b01, b04, b05, b06, b09, b12, b18).
- That is **not enough** for §6.
- **Do not modify or delete it** (D-045).

**The source of data for §6: the D-051 analysis package** (`hebloc-analysis-pack.zip`).
- It holds the tokens, sentences, pieces and document catalog of all five corpora, proved lossless against the
  official runs.
- Inside the extracted folder:
  - `data/tokens/modern/base-topk-v1__modern-*.parquet` (27 files);
  - `data/sentences/`;
  - `data/documents.parquet`;
  - `VERIFICATION.json`.
- **Ori sends it privately** (Google Drive link), with `hebloc-analysis-pack.zip.sha256`. It is never in git and
  never public: it contains corpus text.
- **Extract it OUTSIDE the repo,** to a short path without Hebrew letters, e.g. `C:\hebloc\hebloc-analysis-pack`.
  - It is a **data source only**. Open the **repo**, not the package, in VS Code for §6 work.
  - The package has its own CLAUDE.md for the separate §4 extra-statistics work (D-051); that work is unrelated to
    §6.
- **Verify it** in a terminal opened in the extracted folder:
  ```
  uv sync
  uv run python -m hebpack.verify
  ```
  Expect OK for every file. Any failure → STOP (§12).
  - If Efrat already set up and verified the package for her §4 work, run `hebpack.verify` once more and continue.
  - `hebpack.selftest` (optional) reproduces the official statistics. Modern alone takes 1–2 hours.

**Not needed:**
- **BHSA.** It covers only the Hebrew Bible (§11, point 3).
- **The Mikra bundle.** §6 is on Modern. The package contains Mikra anyway, in case you want to look.
- **Re-parsing.** Never re-run Dicta.

---

## 9. Start here: what Efrat can do now, and what must wait

### 9.1 Now (after CHECKPOINT 1)

Claude Code does these steps in order and shows Efrat each result:

1. **Check for local changes:** `git status`.
   - If it lists modified tracked files, **STOP**. Never discard local changes; show the list to Efrat and report
     to Ori.
   - Untracked `data/` files are fine.
2. **Update:**
   ```
   git pull
   uv sync
   uv run python -m pytest
   uv run python -m hebloc whoami
   ```
   - The tests must pass.
   - `whoami` must say `efrat`. If it doesn't, follow `PARTNER_START.md` §2/§5, then rerun it.
   - On Smart App Control errors, use `uv run python -m …` exactly as written (D-038).
3. **Get and verify the package** (§8). If Efrat doesn't have it yet, tell her to ask Ori for the Drive link, then
   continue with step 4.
4. **Read.**
   - This document, and the paper: chapters 1–3, plus §4–§6 and §8 for the verb lists and Modern Hebrew.
   - `project.pdf` §5–§6, from her own course copy.
5. **Plan §6 in Plan Mode** with Efrat. Save the plan as `data/analyses_s6/PLAN.md` in her repo; `data/` is never
   in git. The plan covers:
   - the report outline;
   - how each characterization dimension of 5.9(3) will be measured;
   - which tables and figures, by genre;
   - how candidates will be reviewed.

   The plan uses **only** the definitions of this document.
6. **Optional, read-only exploration of the package data with DuckDB**, e.g. verb lemma frequencies per genre, or
   the size of each genre. This helps planning.
   - **No** frame extraction, role or class code.
   - No outputs that pretend to be §6 results.

**Not allowed yet:**
- writing or running extraction, role or classification code;
- downloading BHSA;
- editing `config/`;
- annotating gold, until the R1 sampler exists;
- any paid API.

### 9.2 After R1 (tag `s56-r1`; released 2026-11-20)

> **Your two Dicta findings are recorded as open issues for R2** (D-058):
> - OI-1: present-tense and passive forms with their own lemmas;
> - OI-2: VERB-tagged יש, אין, אפשר, היי.
>
> They do **not** block these steps. Do your R1 tasks now, and annotate every item from the sentence exactly as
> the guideline says. These issues change no label rule. The policy, if any, comes with R2.

The exact commands and expected results are in §7, "R1 release notes". Claude Code does the steps in order and
shows Efrat each result.

1. **Update and check** (as in §9.1 step 1–2):
   - `git status`: STOP if tracked files are modified (S9);
   - `git pull`, `uv sync`, `uv run python -m pytest` (all pass), `whoami` = efrat;
   - `git tag -l s56-r1` lists the tag;
   - `loc lexicon check` = OK.
2. **Verify the package** (`hebpack.verify` in the package folder, §8). If Efrat doesn't have it yet, STOP here and
   ask Ori for the Drive link.
3. **Draw the two samples from the package** (Modern, then Mikra), and run `loc verify` on both folders. The ids and
   `items_match` must be as in §7.
> **Steps 4–9 below are the D-061 version (R1.1, tag `s56-r1.1`).** Efrat does no manual data work: her Claude
> Code runs every step, and Efrat approves and sends the deliveries.
> - The coordinating session (Efrat's normal Claude Code, in the repo) builds and launches the isolated annotator
>   sessions. It never labels anything itself, and never opens a sheet's labels or a workspace's output.
> - Commands print counts and statuses only.
> - Full protocol: `annotation/S56_SILVER_PROTOCOL.md`.

4. **Check R1.1 and isolation (T1, T2):**
   - `git tag -l s56-r1.1` lists the tag, `git merge-base --is-ancestor s56-r1.1 HEAD` succeeds (your checkout
     contains R1.1; later documentation-only commits on main are fine), and `docs/decisions.md` contains D-061.
     Otherwise STOP.
   - Both frozen samples still give `items_match = true` (step 3).
   - Run `uv run python -m hebloc loc silver isolation-test`. It must print `"ok": true`: the canary reads were
     denied. Otherwise STOP and report to Ori.
   - **From now until the last delivery, the pinned files never change** (`annotation/`, `config/`, `src/`,
     `pyproject.toml`, `uv.lock`). The pull rule (STAGES.md §1 step 2): `git pull` only when
     `git diff --quiet HEAD origin/main -- annotation/ config/ src/ pyproject.toml uv.lock` succeeds (a
     documentation-only update, which Ori announces as allowed). A release you must take (`s56-r1.2` for a
     supplement, `s56-v1`) is announced in STAGES.md §6 and taken with `git merge --ff-only <tag>`. Never
     `git checkout` a tag.
5. **The worked-example compliance check (T3):**
   ```
   uv run python -m hebloc loc silver create --task worked
   uv run python -m hebloc loc silver step worked       # repeat until "finalized" or "STOP"
   ```
   15/15 is required. On a STOP, send Ori the `QC_STOP.md` folder name and wait.
6. **Modern noun types:**
   - The earlier proposals are reused as pass A (D-061 D-f). Pass B never sees them.
     ```
     uv run python -m hebloc loc silver create --task noun --corpus modern --list data/loc/nouns/modern/modern-nouns-r1-826929982d/nouns_to_label.csv
     uv run python -m hebloc loc silver import-pass noun-modern --pass A --from <the earlier proposals CSV> [--confidence-column <name>]
     uv run python -m hebloc loc silver step noun-modern  # repeat until "finalized"
     ```
   - **Deliver it early:** `loc silver deliver noun-modern --out data/outbox/efrat-s6 --who efrat`.
7. **Sentence silver, dev first.** For each job, create it, then repeat `step` until `finalized` or `STOP`:
   ```
   uv run python -m hebloc loc silver create --task sentence --corpus modern --split dev --sample data/loc/gold/modern/modern-r1b-5fbb5e22e7
   uv run python -m hebloc loc silver step sentence-modern-dev --source package --package <package folder>
   ```
   - **Order:**
     - Modern dev → Mikra dev → the paper anchor (`create --task anchor --source package --package <package folder>`;
       it reads `annotation/silver/anchor_ids.csv`, which holds no frames) → deliver;
     - then Modern validation → Mikra validation → deliver;
     - then Modern test → Mikra test → deliver.
   - Each split is finalized and **frozen** before the next one is opened.
   - Never revise a frozen job. On any STOP (T4: κ < 0.6; T5: > 5% format failures; abstention > 30%; a second
     isolation breach), send Ori the job name and wait for his project-level decision.
   - **ישב.I** (guideline §4.15) is judged like every other item: locative, non-locative, or `?` with a reason.
8. **Deliver** (§10), after each group of jobs:
   ```
   uv run python -m hebloc loc silver deliver <job> [<job> ...] --out data/outbox/efrat-s6 --who efrat
   ```
   - The outbox holds the frozen final files, pass files, QC, access logs and `DELIVERY.json`. It holds no input
     texts.
   - Send the folder to Ori by Google Drive, OneDrive or USB, with message M2 of STAGES.md §8 (the jobs and the
     `DELIVERY.json` sha256). `end-of-session` records it in `STATE.md`.
   - **Order of deliveries** (STAGES.md §4): E3 Modern nouns → E4 dev (Modern, Mikra) + anchor → E5 validation →
     E6 test.
9. **STOP** after each delivery, and wait for R2 after the last one. Nothing of §9.3 before Ori announces `s56-v1`.
   Phase C supplements, if Ori approves any, come as new jobs by the same protocol (STAGES.md stage ES: an
   announcement in STAGES.md §6, then `git merge --ff-only s56-r1.2`, whose pinned protocol files are identical to
   `s56-r1.1`).

### 9.3 After R2 = tag `s56-v1` (CHECKPOINT 2; Ori announces it)

1. Take and pin the release (STAGES.md E7): `git fetch origin --tags`, `git merge --ff-only s56-v1`,
   `git diff --quiet s56-v1 HEAD -- src/ config/` must succeed, then `uv sync`, `uv run python -m pytest`,
   `hebpack.verify`, `loc lexicon check` and `loc silver isolation-test`. Afterwards only documentation-only pulls
   (the pull rule of §9.2 step 4) until Ori announces a new release.
2. Run `loc extract --mode all-verbs`, then `loc resolve`, `loc classify` and `loc swap` on Modern from the
   package. These are long runs: run them detached if the release notes say so.
3. Run `loc verify` on the outputs. Any failure → STOP.
4. **Analysis (Plan Mode; Efrat approves each step):**
   - the §6 tables;
   - evaluation against the paper and §8;
   - candidate review and the template-proxy check, by the silver protocol (§5.9(2), (3); the silver tasks come in R2;
     STAGES.md E9);
   - characterization;
   - figures.

   Every analysis reads only the output tables of step 2.
5. **Write `REPORT.md`** in plain English:
   - research question;
   - method (by reference to this document);
   - results;
   - limitations: the `UNDETERMINED` share, parser errors, the resolver's **agreement with the Modern test silver**
     (D-061: never called accuracy);
   - feedback to §5.
6. **Package and deliver** (§10), with message M2 (STAGES.md §8). §6 is **complete** when Ori has verified the
   hashes, recomputed at least one output, checked the cross-checks of §7 and accepted `REPORT.md` (STAGES.md
   E-done).

---

## 10. Outputs and how they come back to Ori

Everything goes into `data/outbox/efrat-s6/` in her repo. It travels by Google Drive, OneDrive or USB, and **never
by git**.

```
data/outbox/efrat-s6/
  DELIVERY.json            # who, when, git tag/commit, list of files with sha256 (written by `loc silver deliver`)
  silver/<job>/            # D-061: frozen SILVER jobs (final file, pass files, qc.json, access logs, FROZEN.json):
                           #   sentence-modern-dev|validation|test, sentence-mikra-*, anchor-mikra, worked, noun-modern
  results/                 # copies of the R2 output folders (I3 tables + manifest.json), unchanged
  analyses/                # her §6 tables/figures, each with the script that made them
  code/                    # any §6-specific scripts (Ori reviews; only Ori commits them to git)
  REPORT.md
```

**Partial deliveries are welcome:**
- after R1.1: `silver/` jobs, in the order of §9.2;
- after R2: everything else.

Each delivery has its own `DELIVERY.json`.

**What Ori does on receipt:**
- verifies the hashes and manifests;
- recomputes at least one output from the package;
- checks the cross-checks of §7;
- reviews `REPORT.md`.

§6 results enter the project report only after Ori's review.

---

## 11. Answers to every point raised by Efrat's Claude Code

| # | Efrat's Claude Code said | Answer |
|---|---|---|
| 1 | Her local repository is outdated and must be synchronized with GitHub | **Yes.** §9.1 steps 1–2: `git status` (STOP if tracked files are modified; never discard), `git pull`, `uv sync`, tests, `whoami`. Only Ori pushes to git; Efrat never commits or pushes. |
| 2 | She has Medieval and eight Modern slices but lacks the Mikra parse bundle | **Mikra is not needed: §6 is on Modern.** But §6 needs **all 27** Modern slices, which she lacks. The data source is the **D-051 package** (§8): all corpora, lossless-verified, sent privately by Ori, checked with `hebpack.verify`. Her own slices stay as they are (D-045). |
| 3 | Use BHSA, because Dicta has no binyan and its Biblical lemmas may be unreliable | **The concern is right for Mikra, but BHSA is not used in §6.** BHSA annotates only the Hebrew Bible; it has nothing for Modern. In Modern, Dicta's verb lemma is blank in only 5.3% of verb tokens (14.7% in Mikra), and the lemma's spelling usually shows the binyan (מילא 15,121 vs מלא 121; פירק vs פרק). Where it doesn't (e.g. שלח/שילח), the lexicon flags the entry as template-ambiguous and the form fallback recovers blank lemmas. BHSA stays Ori's validation tool for Mikra; its result reaches Efrat through the lexicon. **Do not download BHSA.** |
| 4a | She needs the paper's verb lexicon (95 A, 45 A/B, 37 B) | **It comes in R1** as `config/locative_verbs.yaml` (§5.1, §7 I1). Note the paper's own discrepancy: fn 33 lists 46 Simple-A verbs, so the A lists total 96 against the stated 95. It is documented, not hidden. Read-only for Efrat; she proposes corrections via §10. |
| 4b | She needs the extraction and classification code (direct objects, PPs, frames) | **It comes in R2 = tag `s56-v1`**, validated on Mikra first (§5.3–5.5, §7 I2). The same code serves §5 and §6 (`--mode all-verbs`). Efrat must not write her own extractor or frame rules. |
| 5 | An agreed output format so §6 can directly reuse §5's work | **Fixed now** (§7 I3–I5): the `instances`, `arguments`, `roles`, `verb_profiles` and `verb_classes` tables, `swap_candidates`, gold files and manifests. Rows are identical across modes, so her Modern paper-verb rows are byte-identical to §5 stage 2's. |
| 6 | Her CLAUDE.md scope restriction must be updated to authorize §6 | **Done at CHECKPOINT 1.** The repo's CLAUDE.md (she gets it with `git pull`) now has an **Efrat branch**: §6 is authorized as staged in §9 of this document, and her `start` points here. It no longer means "planning only" for her. It never means re-running her M5 share. |

---

## 12. STOP rules

Claude Code stops, explains the problem to Efrat in plain language, and tells her what to send Ori, when **any** of
these happens:

| # | Situation |
|---|---|
| S1 | A failed check: tests, `hebpack.verify`, `loc lexicon check`, `loc verify`, a hash or tag mismatch, a schema error, or a gold sample whose id or `items_match` differs from §7. **Never work around a check.** |
| S2 | The code is not at the required release (R1 steps need R1; R2 steps need tag `s56-v1` with a clean tree) |
| S3 | A step would edit `config/`, the lexicon, the noun types, `config/annotations.yaml` or anything in `corpora/`. Propose changes in the outbox instead. |
| S4 | A step would create own frame definitions, extraction rules, role rules or classes. Write it down as feedback instead. |
| S5 | A step would use a paid or external API, or download BHSA. |
| S6 | A step would delete or modify parse data, bundles or package files, or re-run Dicta. |
| S7 | A step would put corpus text or data in git, or `git commit`/`git push`. Efrat never commits; only Ori pushes. |
| S8 | (D-061) A step would present AI labels as human gold, omit `label_source`, change a FROZEN silver job, or label anything outside an isolated silver workspace. |
| S9 | `git status` shows modified tracked files before `git pull`. |
| S10 | The data or results look surprising: e.g. a paper A/B verb never alternates, or most instances are `UNDETERMINED`. **Report it; don't "fix" it.** |
| T1 | (D-061) `s56-r1.1` or D-061 is missing after `git pull`. Nothing of §9.2 steps 4–9 runs before them. |
| T2 | A frozen sample no longer gives `items_match = true`. |
| T3 | The worked examples are below 15/15 after the one rerun. |
| T4 | Frame κ between the first-run passes is below 0.6, or abstention is above 30% after recovery, in any split. |
| T5 | More than 5% of a split's items fail the format or consistency check after their rerun. |
| T6 | The isolation test fails, a chunk is breached twice, or a step would open extractor or resolver code or outputs inside an annotator session. |
| T7 | A step would edit a tracked file, `config/` or a frozen dataset, or commit or push. |

To report to Ori, send him:
- what was run;
- the full message;
- `git describe --tags --always`;
- the relevant manifest or `DELIVERY.json`.

---

## 13. Glossary and facts measured on our data

### Glossary

| Term | Meaning |
|---|---|
| **Locatum / Location** | The thing moved, put or removed / the place, container or possessor |
| **Frame A / B** | Locatum / Location is the direct object |
| **Occurrence / instance** | One token of a verb, with its arguments |
| **Full frame** | DO + PP |
| **Partial frame** | DO only |
| **Full view / curated view** | All supplied text (primary) / in-period, non-blank, deduplicated (secondary); D-015 |
| **Release R1 / R2** | Lexicon, guideline, sampler, noun lists / the frozen validated code, tag `s56-v1` |
| **Unit** | A verse (Mikra) or a sentence. Units can be long in older corpora |
| **Piece** | A part of an over-long unit, parsed separately (D-020/D-021) |

### Facts measured on the parses (read-only, 2026-11-19)

Volumes use an approximate active-voice lemma list, so true counts are somewhat higher.

**Verb lemmas**

| Corpus | Verb tokens | `[BLANK]` lemma |
|---|---|---|
| Mikra | 65,871 | 14.7% |
| Hazal | 1,421,987 | 6.3% |
| Medieval | 709,747 | 5.7% |
| Haskala | 960,188 | 8.1% |
| Modern | 19,612,455 | 5.3% |

**Paper-verb occurrences**

| Corpus | Occurrences | With an object | Object + PP |
|---|---|---|---|
| Mikra | 8.5k | 4.9k | 2.9k |
| Hazal | 88k | 40k | 22k |
| Medieval | 42k | 17k | 10k |
| Haskala | 69k | 36k | 24k |
| Modern | 1.02M | 659k | 402k |

**Objects that are only a pronoun or suffix:** Mikra 21.9%, Hazal 17.4%, Modern 14.8%. Dicta also misses some
object suffixes.

**Modern, all verbs**

| Measure | Value |
|---|---|
| Verb lemma types | 18,626 |
| … of which hapax | 4,154 |
| … with ≥ 20 tokens | 7,201 |
| Share of verb tokens in types with < 20 tokens | 0.27% |
| Verb occurrences with an object | 5.51M |
| … with object + PP | 2.54M |
| … with object + PP headed by ב/מ/מן | 1.11M |

**Data representation**
- A clitic ב/מ is a `prefix` on an `obl` noun (`prefix_upos` contains ADP).
- A separate preposition is a `case` row under its noun.
- את is `case:acc` on the `obj`.
- There is no `iobj`, no passive label and no binyan feature.
