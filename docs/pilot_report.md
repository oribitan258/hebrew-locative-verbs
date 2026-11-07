# M3 Pilot Report: Dicta parsing of the five corpora

*Date: 2026-11-07. Status: **M3 review gate — awaiting the user's decisions (§15).** Raw results:
`data/annotations/pilot/` (runs, `results/*.json`, `bench/*.json`). Code: `src/hebloc/parse/`,
`src/hebloc/pilot/`. Decisions: D-022–D-029 in [decisions.md](decisions.md).*

---

## 1. Summary

The pilot parsed 1,000 sentences and verses (200 per corpus, a mix of random and deliberately
difficult cases) with both Dicta models. It also ran:
- extra test runs for the normalization questions;
- a comparison against an expert annotation of the Bible (BHSA);
- a speed, memory and storage benchmark.

**What works.**
- The pipeline is complete and lossless: every unit was parsed, with no errors.
- Every output word maps back to its exact characters in the source file.
- Re-deriving the annotation table from the stored raw output reproduces it exactly.
- The original corpora are unchanged.

**Main findings.**
1. **The models silently truncate long input** (beyond 510 sub-words) without any error. We
   therefore split long sentences into pieces and check that every input character comes back.
   Pieces are needed for **0.003–0.075% of units**, but these units hold **1.2–2.9% of the words**
   of Hazal, Medieval and Haskala (§4).
2. **We found a bug in Dicta's tree decoder.** On the pilot it produced invalid dependency trees
   (cycles) for **11.9%** of pieces. A one-line, documented fix brings this to **2.1%**. The
   remaining 2.1% come from a second, structural issue in how Dicta maps sub-word trees to words;
   those trees are flagged, never repaired (§7).
3. **Biblical Hebrew quality (against BHSA, 500 random verses, base model).**

   | Layer | Agreement |
   |---|---|
   | Part of speech | **83.6%** strict, **88.5%** convention-tolerant |
   | Prefix segmentation | 95.2% |
   | Verb person / number / gender | 90.8% / 97.0% / 94.2% |
   | Noun lemmas | 71.0% |
   | Aramaic | much worse: POS 48% |

   Verb lemmas often follow a different convention or the wrong binyan. **Dicta does not predict the
   binyan at all** (§8).
4. **Normalization.** All four hypotheses are supported (§9):
   - stripping niqqud makes no difference to the parser; this was proven on all 144,247 affected
     units;
   - the Qere is better than the Ketiv;
   - maqaf → space and sof pasuq → `.` are as good as or better than the alternatives.
5. **Base vs tiny.** Base is clearly more accurate. With Dicta's original code, tiny is only
   1.4–1.8× faster, because a wasteful full-vocabulary sort dominates both models. A drop-in
   replacement (`topk`) gives **byte-identical output** and makes base **3.3× faster** at half the
   memory (§7, §11).
6. **Cost of full parsing** (base model):
   - all four historical corpora: **36 h**, or **11 h** with `topk`;
   - full Modern corpus: **306 h** (≈13 days), or **92 h** (≈4 days) with `topk`;
   - storage: ~13 GB in total.

   Three Modern-coverage options are in §12.
7. **Syntax is much less stable on historical Hebrew.** The two models choose the same head word
   for 89% of words in Modern text, but for only 57–71% in the historical corpora (Medieval is
   lowest). Tree-based statistics for those corpora need a measured error rate, which the manual
   audit will provide (§8.2).
8. **Manual audit.** 150 units (2,740 words) are prepared for you and your partners. **No manual
   judgments exist yet**, so no human-validated accuracy is reported (§8.4).

---

## 2. Setup

| Item | Value |
|---|---|
| Base model | `dicta-il/dictabert-joint` @ `7b1256fc0846e22d1af431eae299e2dcecee2778` (184M params), CC-BY-4.0 |
| Tiny model | `dicta-il/dictabert-tiny-joint` @ `708026b7297ffde293f14a3a592f8cf649f12c38` (4 layers, hidden 312), CC-BY-4.0 |
| Files | safetensors weights, tokenizer and config; sha256 pinned in `config/models.yaml`; verified before every load |
| Model code | the 4 custom `Bert*.py` files, **reviewed before execution** and vendored byte-identically (`src/hebloc/parse/dicta_code/`) |
| Loading | offline, direct class import (`trust_remote_code` never used) |
| Environment | Python 3.12, torch 2.15.0 (CPU), transformers 5.22.2; Windows 11, 14 threads, 16 GB RAM |

**Why the code is vendored.**
- The tiny repository has no code of its own. Its configuration points at the base repository's
  code with **no revision**, so transformers would download whatever code is current at run time.
- The review found no network, file, subprocess, `exec`/`eval` or pickle access.
- It did find the behaviours described in §4 and §7, plus a converter that calls `exit(0)` on
  malformed input. That converter is used only through a guarded wrapper.

---

## 3. What Dicta outputs

For every word:
- `token` and character `offsets`;
- `seg`: the prefix split, e.g. `["ו", "יאמר"]`;
- `lex`: the lemma;
- `morph`: `pos`, `feats`, prefix POS, `suffix`, suffix features;
- `syntax`: head index and UD relation;
- `ner`.

For every sentence, `root_idx` and the named entities.

| Question | Result |
|---|---|
| Does `json` contain everything in `ud` / `iahlt_ud`? | **Yes.** Both CoNLL-U styles are exactly reproducible from `json` (checked on both models), so only `json` is stored (D-023) |
| Morphological features | **Only Gender, Number, Person, Tense.** No binyan (verbal template), no definiteness feature, no construct state (construct shows up only as the relation `compound:smixut`) |
| Lemma when unsure | `[BLANK]` (4–7% of words, §8.3); kept verbatim and flagged |
| Lemma artifacts | Rarely (≤0.2% of words) the lemma is a raw sub-word piece, e.g. `##גין` for `והזגין` |
| Word units | Dicta's words follow its tokenizer: punctuation is split off; acronyms with `"` (`אע"פ`) and a fixed list of abbreviations with `'` stay whole |
| Deterministic | Yes (same input → same output) |

The proposed `tokens` table schema (one row per Dicta word, with exact provenance) is in
[data_dictionary.md](data_dictionary.md#tokens-proposed-hebloc-parse-tokens-tokens_schema-tokens_version-1).

---

## 4. Input limit, truncation and pieces

- The model reads at most **512 positions**: 510 sub-words plus two markers.
- **Longer input is cut off silently.** In a test, 600 words went in and 510 came out, with no error
  or warning in the output.
- Therefore:
  - every unit longer than 510 sub-words is split into **pieces** (`hebloc.pieces`, D-020/D-028).
    The cut is preferably after `, ; :`, and the model's own tokenizer counts the sub-words;
  - every parsed piece is checked to **cover every non-space character** of its input, which would
    detect any truncation;
  - each piece is stored with its parent `sent_id` and exact span.

**Piece census.** All units in all corpora, measured with the base tokenizer:

| Corpus | Units | Words (whitespace tokens) | Sub-words per word | Units needing > 1 piece | Words in those units |
|---|---|---|---|---|---|
| Mikra | 23,204 | 328,720 | 1.18 | 0 | 0% |
| Hazal | 418,757 | 6,503,346 | 1.32 | 149 (0.036%) | **1.55%** |
| Medieval | 115,412 | 3,522,454 | 1.23 | 73 (0.063%) | **1.17%** |
| Haskala | 274,973 | 5,428,359 | 1.37 | 206 (0.075%) | **2.91%** |
| Modern | 8,877,010 | 163,968,761 | 1.08 | 305 (0.003%) | 0.12% |

*"Words" here are whitespace tokens of `text_norm`, including punctuation tokens (Modern is
pre-tokenized), so Modern's count exceeds the 134M *Hebrew* tokens in the corpus report.*

- Very few sentences need pieces. But they are long (in the pilot, up to 17 pieces, in Haskala) and
  concentrated in sparsely punctuated works (e.g. Pesikta Rabbati).
- A unit split into pieces has **no complete dependency tree**. Excluding such units from
  tree-depth statistics would remove up to 2.9% of a corpus's words, all from its longest
  sentences. This is the potential bias of D-021; its treatment is decided after this pilot (§13).

---

## 5. The pilot sample

`annotation/pilot_sample.csv` (deterministic, seeded; `hebloc.pilot.sample`). Per corpus, 200 units:
**120 random** (full view) + **80 targeted** hard cases. No targeted category came up short.

| Corpus | Targeted categories (count) |
|---|---|
| Mikra | Ketiv/Qere 20, qere-/ketiv-only 6, Aramaic 14, poetry 15, late books 10, longest 10, parasha markers 5 |
| Hazal | vocalized Mishnah 20, Aramaic markers 12, abbreviations 12, Tosefta 8, halakhic midrash 8, Yalkut 5, commentary 5, longest 10 |
| Medieval | Mishneh Torah 15, Rambam `prefix=` tags 5, translated thought 12, thought 10, musar 10, unverified musar 5, later/post-medieval 8, vocalized 5, longest 10 |
| Haskala | post-1881 15, pre-1881 15, markup removed 15, vocalized 10, science 10, longest 15 |
| Modern | 6 from each of 10 sources (blogs, Tapuz, Knesset, literary original/translated, medical, a7, nrg, TheMarker, ynet), `prefix_unresolved` 5, reversed-number pattern 5, URLs 3, longest 7 |

The sample has 88,072 words. Of its 1,000 units, 42 needed more than one piece: Hazal 10,
Medieval 10, Haskala 15, Modern 7.

---

## 6. Validation of the pipeline

`hebloc.parse.checks.validate_run`, run on every pilot, variant and benchmark run:

| Check | Base | Tiny |
|---|---|---|
| Every sampled unit parsed (or failure logged) | 1,000/1,000, 0 errors | 1,000/1,000, 0 errors |
| Parsed text = `units.text_norm` (provenance) | ✅ | ✅ |
| Pieces rebuild the unit text exactly; none over budget | ✅ (1,161 pieces) | ✅ (1,169) |
| **Every input character covered by an output word (no truncation)** | ✅ 0 failures | ✅ 0 failures |
| `tokens` re-derived from raw output identical | ✅ (101,368 words) | ✅ |
| Every word's `surface` = its exact text slice | ✅ (unit-tested) | ✅ |
| Corpora unchanged | ✅ fast suite and anchor check | |

Model-quality properties (not pipeline failures) are reported separately: invalid trees (§7) and
blank lemmas (§8.3).

---

## 7. Problems found in Dicta's code and output

| # | Problem | Effect | Handling |
|---|---|---|---|
| 1 | **MST decoder bug.** The length of a batch row is read from its first padding position. A row *without* padding gets length 0, and its cycle repair never runs | Original code: **138/1,161 pieces (11.9%) with invalid trees**; the parse of a sentence depends on which other sentences share its batch | One-line fix in a verbatim copy of the function (`hebloc.parse.dicta_fixes`, D-024), applied at run time, recorded in manifests, unit-tested. With the fix: 24/1,161 (2.1%); 129 pieces get a different parse |
| 2 | **Sub-word → word mapping.** The tree is valid over sub-words, but a word takes the head of its *first* sub-word. When that head is a continuation piece of another word (or of the word itself), the word-level graph can contain a cycle or self-loop | Base 2.1% of pieces (Mikra 4/200, Hazal 4/240, Medieval 8/222, Haskala 8/284, Modern 0/215); tiny 0.3% | Confirmed for all 24 cases. Flagged `piece_tree_valid = false`, **never repaired**; excluded from tree statistics with counts (D-025). Option: constrained decoding |
| 3 | **Full-vocabulary sort for lemmas.** For each sub-word, 128,000 scores are fully sorted to keep the top 3 | Dominates run time; ~2 MB memory per padded sub-word (a batch of 32 long sentences needs >10 GB and swaps) | Batches capped at 1,024 padded sub-words (~3 GB peak). Drop-in `topk`: **identical output on 600/600 pieces, 3.3× (base) / 6.7× (tiny) faster, half the memory** (§11; D-029, off unless approved) |
| 4 | **Silent truncation** beyond 510 sub-words | Lost words, no error | Pieces + coverage check (§4) |
| 5 | `exit(0)` in the UD converter on malformed input | Would silently end a batch job | Converter not used in runs; guarded wrapper only |

Example of problem 2 (base model, Job 10:18). Word 4 `אגוע` is its own head, and the root is the
final `.`:

| # | word | prefix+host | lemma | UPOS | head | relation |
|---|---|---|---|---|---|---|
| 1 | ולמה | ו+למה | למה | ADV | 2 מרחם | advmod |
| 2 | מרחם | מ+רחם | רחם | NOUN | 4 אגוע | obl |
| 3 | הצאתני | הצאתני | [BLANK] | VERB | 2 מרחם | compound:smixut |
| 4 | אגוע | אגוע | [BLANK] | VERB | **4 אגוע** | dep |
| 5 | ועין | ו+עין | עין | NOUN | 6 לא | nsubj |
| 6 | לא | לא | לא | ADV | 7 תראני | advmod |
| 7 | תראני | תראני | הראה | VERB | 5 ועין | conj |
| 8 | . | . | . | PUNCT | ROOT | root |

---

## 8. Parser quality

### 8.1 Biblical Hebrew against BHSA

BHSA (ETCBC 2021, commit `4db00e2`, CC BY-NC 4.0, DOI 10.17026/dans-z6y-skyh) is an expert
annotation of the Hebrew Bible. Its conventions differ from Dicta's, so these figures are
**convention-aware agreement, not gold accuracy**:
- Words were aligned as *written words*. BHSA splits ו/ה/ב/כ/ל/מ into separate words, and we joined
  them back.
- The BHSA host word is compared with Dicta's host, and the BHSA proclitics with Dicta's prefix
  split.
- 99.2% of BHSA written words aligned. Verses whose texts do not align (alignment under 80%, e.g.
  versification differences in Exodus 20, Deuteronomy 5 and Numbers 25–26) were excluded and
  counted: 3 of 500.

**500 random verses** (Hebrew words; 95% Wilson intervals):

| Layer | Base | Tiny |
|---|---|---|
| POS, strict mapping (n = 6,503) | **83.6%** [82.7–84.5] | 78.5% [77.5–79.5] |
| POS, convention-tolerant (BHSA *subs* may be NUM/DET; participles may be NOUN/ADJ) | **88.5%** [87.7–89.2] | 83.5% [82.5–84.3] |
| Prefix segmentation | **95.2%** [94.6–95.7] | 94.4% [93.8–95.0] |
| Noun lemma (n ≈ 3,060) | 71.0% [69.4–72.6] | 70.3% [68.7–72.0] |
| Verb person (n = 1,103) | **90.8%** [88.9–92.3] | 85.4% [83.1–87.4] |
| Verb number (n = 1,225) | 97.0% [95.9–97.8] | 94.3% [92.8–95.5] |
| Verb gender (n = 862) | 94.2% [92.4–95.6] | 91.5% [89.5–93.2] |
| Lemma `[BLANK]` rate | 7.4% | 8.8% |
| Aramaic words: POS (n = 93) | 48.4% [38.5–58.4] | 45.2% |

The 200-verse pilot sample, which over-represents hard verses, gives similar base figures: POS
83.5% strict / 89.4% tolerant, prefix segmentation 95.8%.

**Verb lemmas.** 1,079 BHSA *qal* verbs, base model:

| Outcome | Share |
|---|---|
| Exact match with BHSA lexeme | 36.6% |
| Convention only: היה → `היי` (7.7%), hollow roots like בוא → `בא` (6.2%) | 13.9% |
| Participle form given as lemma (`אומר`) | 5.9% |
| **Lemma of another binyan** (`נאמר`, `הראה`, `הוציא` for qal forms) | **8.4%** |
| `[BLANK]` | 12.7% |
| Other mismatches | 22.4% |

For verbs in other stems, agreement with BHSA is only ~10%. This is expected: BHSA lists the root
(יצא), whereas Dicta lists the binyan's dictionary form (הוציא). **Because Dicta does not predict
the binyan, any later work on verbal templates must derive it some other way.** That is outside
the current scope; it is a roadmap note.

Tense: wayyiqtol (`ויאמר`) is mostly tagged `Tense=Fut` (259 of 323), its morphological form,
rather than Past. Studies of tense must keep this in mind.

### 8.2 Base vs tiny on all corpora (model agreement)

Agreement between the two models, word by word, where both produced the same words. **Wherever
the models disagree, at least one of them is wrong**, so lower agreement means more errors.

| Corpus | POS | Lemma | Prefix | Head | Head + relation |
|---|---|---|---|---|---|
| Mikra | 86.3% | 83.8% | 98.0% | 70.9% | 62.5% |
| Hazal | 88.5% | 85.9% | 98.5% | 68.2% | 59.6% |
| Medieval | 91.4% | 88.9% | 98.5% | **57.2%** | **50.0%** |
| Haskala | 93.7% | 87.8% | 98.7% | 67.9% | 62.2% |
| Modern | 96.5% | 92.4% | 99.3% | 89.3% | 85.6% |

Morphology is fairly stable. **Syntax is much less stable on historical Hebrew than on Modern**:
on Medieval text the two models attach half the words differently. Dependency-based statistics for
historical corpora must be reported with this uncertainty, and the manual audit is the way to
measure it.

### 8.3 Descriptive diagnostics (base model, pilot sample)

| Corpus | Words | Multi-piece units | Mean tree depth (single-piece units) | `[BLANK]` lemmas | Words with prefix | Words with suffix |
|---|---|---|---|---|---|---|
| Mikra | 3,103 | 0 | 5.17 | 7.4% | 30.8% | 9.6% |
| Hazal | 22,496 | 10 | 4.69 | 3.6% | 24.9% | 7.1% |
| Medieval | 16,584 | 10 | 6.65 | 5.0% | 33.0% | 6.7% |
| Haskala | 46,296 | 15 | 4.82 | 4.3% | 32.8% | 5.4% |
| Modern | 12,889 | 7 | 5.28 | 4.3% | 16.6% | 1.3% |

The sample over-represents long units, so these are diagnostics, not corpus statistics.

### 8.4 Manual audit — prepared, **not yet annotated**

- Two sheets are prepared:
  - `annotation/pilot_audit_words.csv`: 2,740 words, the main sheet;
  - `annotation/pilot_audit.csv`: 150 units.
- They cover 30 units per corpus: 25 random and 5 targeted, each of at most 60 words.
- Instructions: [annotation/pilot_audit_guide.md](../annotation/pilot_audit_guide.md).
- The sheets contain Dicta's output only; every judgment column is blank.
- `uv run hebloc pilot audit-score` currently reports **"not yet annotated"**. It will compute
  per-layer accuracy with confidence intervals once people fill the sheets in.
- *Limitation:* units over 60 words are not in the audit.

---

## 9. Normalization hypotheses (D-018 → D-026)

All variants were produced from `normalize.py`'s own rules. With every option at its default, the
variant code reproduces `text_norm` and the Ketiv `text_norm_alt` for **all 23,206 verses** (0
mismatches), so each comparison changes exactly one thing. The defaults were not changed.

| Hypothesis | Test | Result | Proposal |
|---|---|---|---|
| **Strip niqqud and cantillation** | All 144,247 units in all corpora whose normalization stripped points: tokenized with and without them, with both tokenizers. 60 Mikra verses also parsed both ways | **Identical model input in 144,247/144,247 units** (Dicta's tokenizer removes the marks itself); identical parses in 60/60 | Accept. Stripping is harmless, and keeping the marks would change nothing |
| **Qere in `text_norm`** | All 945 verses with an alternative reading, parsed both ways, compared with BHSA's words in the matching reading | On the K/Q words: POS 74.4% (Qere) vs 69.4% (Ketiv); tolerant POS 79.7% vs 73.7%; **noun lemma 57.7% vs 33.2%**. Verses failing alignment: 11 vs 20. Switching the reading changes the full analysis of 14% of the *other* words | Accept the Qere (default); keep the Ketiv in `text_norm_alt` |
| **Maqaf → space** | 500 verses: maqaf replaced by space vs kept as `-` | POS 83.6% vs 83.0%; tolerant 88.5% vs 87.9%; other layers equal within noise | Accept the default |
| **Sof pasuq → `.`** | 500 verses: `.` vs removed | POS equal (83.6% vs 83.6%); verb Person **90.8% vs 88.2%**; removing it changes 17% of words' full analysis | Accept the default |

Note for the Qere test: BHSA analyses follow the Ketiv text, with the Qere as a separate feature.
The Ketiv run was still compared with BHSA's Ketiv words.

Example: Esther 3:4 (written `(באמרם) [כְּאׇמְרָם]`). With the Qere `כאמרם` the lemma is `[BLANK]`;
with the Ketiv `באמרם` the lemma is `דיבר`. In both, the word is a VERB attached to `ויהי`. The
reading also changed where `ויגידו` attaches (to `כאמרם` vs to `ויהי`). One word's reading can
move other attachments.

---

## 10. Examples (base model, real pilot output)

**Genesis 42:8**, `ויכר יוסף את אחיו והם לא הכרהו .`

| # | word | prefix+host | lemma | UPOS | features | head | relation |
|---|---|---|---|---|---|---|---|
| 1 | ויכר | ו+יכר | הכיר | VERB | Masc Sing 3 **Fut** (wayyiqtol) | ROOT | root |
| 2 | יוסף | יוסף | יוסף | PROPN | | 1 | nsubj |
| 3 | את | את | את | ADP | | 4 | case:acc |
| 4 | אחיו | אחיו | אח | NOUN | Masc Plur +suffix | 1 | obj |
| 5 | והם | ו+הם | הוא | PRON | Masc Plur 3 | 7 | nsubj |
| 6 | לא | לא | לא | ADV | | 7 | advmod |
| 7 | הכרהו | הכרהו | הכיר | VERB | Plur 3 Past +suffix | 1 | conj |
| 8 | . | . | . | PUNCT | | 1 | punct |

**Mishnah Kelim (vocalized in the source)**, `ונקליטי המטה וחמור וחפוי, טהורין.` A rare technical
noun becomes the root VERB with the wrong lemma `נקבר`. `וחפוי` gets `[BLANK]`. `טהורין` attaches as
`dep`.

**Mishneh Torah, Tumat Okhlin 1**, `החרצנין והזגין אע"פ שכנסן לאוכלין אינן מתטמאין טומאת אוכלין .`
- `החרצנין` and `והזגין` are tagged PROPN, and `והזגין` gets the sub-word lemma `##גין`.
- `שכנסן` is segmented `שכ+נסן` (should be `ש+כנסן`).
- The main verb `מתטמאין` (lemma `נטמא`) and the subject/object attachments are right.

**Knesset protocol**, `אבל זאת לא רק בעיית המשטרה , זאת בעיה אזרחית , בעיה מקומית .`: a fully
plausible analysis (`בעיית המשטרה` as `compound:smixut`, appositions, `amod`).

**Haaretz with an unresolved `prefix=` tag**, `… בהחלטת ועדת הכספים מ - ' .`: the orphan `מ`
becomes an ADP attached as `nmod`. This is the expected effect of the unresolved artifacts (D-019).

---

## 11. Benchmark: speed, memory, storage

All benchmark runs use Modern units outside the pilot sample, the MST fix, and 510-sub-word pieces.
Every run passed all integrity checks. Raw numbers: `data/annotations/pilot/bench/`.

**Step 1: bounded grid (300 units, 5,739 words).**

| Model | Threads | Batch cap (padded sub-words) | Lexeme code | Words/s |
|---|---|---|---|---|
| base | 4 / 8 / 12 | 1,024 | original | 66 / 126 / **127** |
| base | 12 | 512 / 2,048 | original | 143 / 115 |
| tiny | 4 / 8 / 12 | 1,024 | original | 89 / **255** / 172 |
| base | 12 | 1,024 | **`topk`** | **421** |
| tiny | 8 | 1,024 | **`topk`** | **1,203** |

**Step 2: equivalence and invariance checks, done before scaling.**

| Check | Result |
|---|---|
| `topk` lexeme code vs original: raw JSON byte-identical? | **300/300 pieces identical (base), 300/300 (tiny)** |
| Parse of a piece alone (batch size 1) vs in a batch (with the MST fix) | **100/100 identical**: results no longer depend on batching |

**Step 3: scaled runs (3,000 units, 54,229 words), median over 6 shards.**

| Configuration | Sub-words/s | Words/s | Peak RAM (fresh process) | Storage |
|---|---|---|---|---|
| base, original code | 161 | ~150 | 3.05 GB | 69 B/word |
| **base + `topk`** | **534** | **~494** | **1.61 GB** | 69 B/word |
| tiny, original code | 229 | ~201 | 3.38 GB | 70 B/word |
| tiny + `topk` | 1,529 | ~1,377 | 1.08 GB | 70 B/word |

Storage per word: raw JSON 42 B, tokens 21 B, inputs 5 B, pieces 1 B (zstd Parquet). That is about
**64 bytes per sub-word**.

**Operational finding.** In the scaled base run, one shard stalled: 657 s instead of ~60 s, with
identical content. Including the stall, the average rate was 63 sub-words/s instead of 161.
Unattended multi-day runs on this laptop need power and sleep settings checked. The runner is
resumable, so an interrupted run loses at most one shard. Projections below use the median shard
rate, with the stall-inclusive figure shown for base.

Consistency check: the pilot itself (mixed corpora, including long multi-piece units) ran at 158
sub-words/s with the base model. That matches the Modern benchmark (161), so scaling by sub-words
is reasonable.

---

## 12. Projected cost of full parsing and Modern coverage options

Continuous CPU hours on this laptop, from the census sub-word counts and the measured rates.
Historical corpora are extrapolated from Modern text.

| Corpus | Sub-words | base original | **base + `topk`** | tiny original | tiny + `topk` | Storage |
|---|---|---|---|---|---|---|
| Mikra | 0.39 M | 0.7 h | 0.2 h | 0.5 h | 0.1 h | 0.02 GB |
| Hazal | 8.55 M | 14.8 h | 4.5 h | 10.4 h | 1.6 h | 0.55 GB |
| Medieval | 4.32 M | 7.5 h | 2.2 h | 5.2 h | 0.8 h | 0.28 GB |
| Haskala | 7.41 M | 12.8 h | 3.9 h | 9.0 h | 1.3 h | 0.48 GB |
| **All historical** | 20.7 M | **35.8 h** | **10.8 h** | 25.1 h | 3.8 h | 1.3 GB |
| Modern (full) | 177.2 M | **306 h** (≈13 days; 785 h with stalls like the one observed) | **92 h** (≈3.8 days) | 215 h | 32 h | 11.4 GB |

All four historical corpora can be parsed in full under any configuration. Only the Modern corpus
needs a coverage decision (D-004).

**Modern coverage options.** Modern's 164 M whitespace tokens by source:
- Haaretz 120.6 M (73.5%);
- Knesset 14.8 M;
- a7 14.8 M;
- blogs 6.9 M;
- medical 2.4 M;
- ynet 1.0 M;
- Tapuz 0.9 M;
- literary translated 0.7 M;
- literary original 0.7 M;
- TheMarker 0.7 M;
- nrg 0.5 M.

| Option | What is parsed | Share of Modern | base + `topk` | base original | Storage | Statistical consequences |
|---|---|---|---|---|---|---|
| **A. Full** | everything | 100% | 92 h | 306 h | 11.4 GB | No sampling error. Corpus-wide counts stay dominated by Haaretz news, as supplied; genre comparisons are still possible via `source` |
| **B. All sources, Haaretz sampled** | 10 non-Haaretz sources in full + a 10% random sample of Haaretz **documents** | 34% | 31 h | 104 h | 3.8 GB | Every smaller genre is complete. Haaretz frequencies are estimated (×10 weight, precision ≈ √10 lower for rare items). Corpus totals must be weighted and the sampling stated. Document-level sampling keeps sentences in context |
| **C. Stratified per source** | at most 2 M tokens per source (all of the 6 smaller sources) | 9% | 8 h | 27 h | 1.0 GB | Balanced genres, which suits genre comparisons. Rare lemmas and verbs have small counts (matters for later locative-verb work); every Modern total needs weights |

All options are reversible: runs are resumable, so B or C can later be extended to A without
re-parsing what is done. With the original lexeme code, option A is a ~2-week unattended run. With
`topk` (identical output, §11) it is about 4 days.

---

## 13. Sentences parsed in several pieces (D-021, still provisional)

**Facts from the pilot.**
- The census (§4) gives the size of the issue: up to **2.9% of a corpus's words** (Haskala) are in
  multi-piece units.
- These units are the longest sentences of their corpus. In the sample, the multi-piece Hazal
  units are almost all Pesikta Rabbati (1,281–1,955 words each).
- Sentence length and depth are related, so excluding them from depth statistics biases mean
  depth downward, and **unevenly across corpora** (Mikra 0%, Modern 0.1%, Haskala 2.9%).
- In addition, 2.1% of pieces (base) have an invalid word-level tree (§7). These are concentrated
  in Medieval and Haskala.

**Options for the final treatment.** All are possible because every piece is stored with its parent
sentence:

| Option | Description | Trade-off |
|---|---|---|
| (a) | Exclude multi-piece units and invalid trees from tree statistics; report the counts and length distribution of what was excluded | Simple and honest; small but uneven bias |
| (b) | (a), plus a sensitivity analysis: per-piece depth as an explicitly labelled lower bound, and depth vs length curves to show the effect | More work; makes the bias visible |
| (c) | Define a different unit for the historical corpora (e.g. split long units also at `:`) | Changes segmentation (D-018); needs a new decision and an M2 rerun |

Sentence *length* statistics are unaffected: they are computed per complete unit.

---

## 14. Limitations

- BHSA figures are **agreement under different conventions**, not accuracy. They cover Biblical
  Hebrew only, and dependency trees cannot be compared with BHSA (it has no dependencies).
- No human-validated accuracy exists yet (§8.4). Base–tiny disagreement shows instability but not
  which model is right.
- The pilot sample deliberately over-represents hard cases. Its rates are diagnostics, not corpus
  estimates.
- Benchmark rates were measured on Modern text on this laptop. Projections for other corpora scale
  by sub-words and are approximate; long multi-piece inputs are slower per sub-word.
- The audit excludes units over 60 words.
- The two runtime fixes (D-024, D-029) change Dicta's code paths. They are documented and tested,
  and their effects are measured here.

---

## 15. Decisions for you (M3 gate)

1. **Model:** base (recommended: clearly more accurate on Biblical Hebrew and syntactically less
   variable) or tiny.
2. **MST fix (D-024):** keep the one-line fix for the full run (recommended), or use Dicta's
   original code.
3. **`topk` speed-up (D-029):** adopt for M5 (recommended: output identical on all 600 tested pieces; 3.3× faster; ~1.6 GB instead of ~3 GB).
4. **Invalid word-level trees (D-025):** flag and exclude (current), or open constrained decoding
   as a separate task.
5. **`tokens` schema:** approve as proposed ([data_dictionary.md](data_dictionary.md)), or request
   changes.
6. **Normalization (D-026):** accept all four defaults as proposed.
7. **Multi-piece statistics (D-021, §13):** choose (a), (b) or (c), or defer until the M6 design.
8. **R5 and the `suspect_bidi` flag:** still open from M2 (not changed in M3).
9. **Modern coverage (D-004):** one of the options in §12.
10. **Manual audit:** who annotates, and by when.

Before M5, the D-012 backup bundles must still be implemented.

---

## 16. Reproduce

```
uv sync
uv run hebloc pilot fetch-models    # network; verifies checksums
uv run hebloc pilot fetch-bhsa      # network; BHSA at commit 4db00e2
uv run hebloc pilot sample
uv run hebloc pilot smoke
uv run hebloc pilot parse           # base, tiny, base with the original MST code (~35 min)
uv run hebloc pilot variants        # normalization runs (~20 min)
uv run hebloc pilot diacritics
uv run hebloc pilot census          # all units, tokenizer only (~25 min)
uv run hebloc pilot analyze         # results/analysis.json, results/hypotheses.json
uv run hebloc pilot audit           # refuses to overwrite filled sheets
uv run hebloc pilot bench           # ~35 min, run on an otherwise idle machine
```
