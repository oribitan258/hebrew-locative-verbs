# Annotation guideline for the S56-v1 gold standard (`S56-v1-g1`)

**For:** every human annotator of the §5–§6 gold samples. That is Ori for Mikra, Efrat for Modern, both for the
agreement items, and whoever runs Hazal, Medieval or Haskala in stage 2.

**Methodology:** `docs/EFRAT_SECTION_6.md` §5.8 (normative). The paper is Doron & Dubnov (2017), chapters 1–3.

**Release:** R1.

> **Human only.** You decide every label yourself, from the sentence. No AI tool may pre-fill, suggest or check
> labels: not Claude Code, not an LLM, not Dicta's analysis. The gold is the independent yardstick for the
> automatic method; if a machine shaped it, it would no longer measure anything (D-054).
>
> **Work in order: dev, then validation, then test.** Finish and check one split before you open the next. Never
> change a test label after you have seen any automatic result.

---

## 1. What you receive

`hebloc loc gold sample` writes the sheets to `data/loc/gold/<corpus>/<sample_id>/sheets/`:
- `dev.csv`, `validation.csv` and `test.csv`;
- `agreement.csv`: the items that a second annotator also labels.

The files open in Excel, and Hebrew displays correctly. **They contain corpus text, so they stay on your computer:
never in git, never in an email body (D-042).**

Each row is one verb **instance**. The read-only columns are:

| Column | Meaning |
|---|---|
| `item_id` | the item's id, e.g. `MI0007` |
| `split` | `dev`, `validation` or `test` |
| `agreement` | `Y` if a second annotator labels this item too |
| `stratum` | how the item was sampled: `A`, `A/B`, `B`, `MIXED`, `MH` or `NONPAPER` |
| `where` | the verse (Mikra), or the source and sub-corpus |
| `verb_key` | the lexicon entry, or entries, the token was matched to. `שלח.I\|שלח.S` means "Simple or Intensive שלח": the letters cannot tell them apart. A `~` member such as `~ציפה` means the token may be a different verb altogether |
| `target` | the word being annotated |
| `sentence` | the verse or sentence, with the target in `[[double brackets]]` |
| `words` | every word of the parsed piece with its index, e.g. `0:ויקח 1:עבדיהו 2:מאה …`. You refer to words by these indices |

**Do not use the `stratum` or `verb_key` to guess the answer.** They only say how the item was drawn.

## 2. The columns you fill

| Column | Values | Notes |
|---|---|---|
| `is_target_verb` | `Y` / `N` | Is `target` really this verb, i.e. one of the entries in `verb_key`? `N` if it is another word or another verb (a misidentification). If `N`, leave the rest empty |
| `member` | an entry id from `verb_key`, or empty | Only for combined keys: which entry it is, **if the context decides it**, e.g. Intensive שִׁלַּח "send away" vs Simple שָׁלַח "send". Leave empty when you cannot tell |
| `locative` | `Y` / `N` / `?` | Is this use locative: does a Locatum change or keep its relation to a Location? Abstract arguments count (paper p. 4) |
| `frame` | `A` / `B` / `NON_LOCATIVE` / `AMBIGUOUS` | §3 below. `locative = N` → `NON_LOCATIVE` |
| `do` | word index, or `suffix`, `elided`, `none` | The head of the direct object. For a passive or middle verb, the subject (§4.1) |
| `pps` | `idx:prep; idx:prep` | Every prepositional phrase that is an argument or modifier of this verb: the index of the PP's **noun head**, and the preposition as written (`ב`, `מן`, `מ`, `על`, `מעל`, `אל`, `ל`, `בתוך` …). For a pronoun PP (בו, ממנו, עליו), the index of that word |
| `bare_np` | word index or empty | A second noun with no preposition, e.g. Judges 9:45 ויזרעה **מלח** (§4.3) |
| `locatum` | word index, or `suffix`, `subject`, `elided` | Which argument is the Locatum (the thing moved, put or removed) |
| `location` | word index, or `suffix`, `subject`, `elided` | Which argument is the Location (the place, container, surface, body or possessor) |
| `notes` | free text | Anything unusual. **Do not quote more than a few words** of the text |

**Use the noun's head word for every index:**
- the noun itself, not את, not the preposition, not an adjective;
- in a construct chain (סמיכות), the first noun.

## 3. The decision procedure

1. **Is the target this verb?** If not, `is_target_verb = N`. Stop.
2. **Find the internal arguments in the sentence itself.** Don't rely on the parse.
   - **The direct object:** with or without את, a pronoun (אותו), or an object suffix on the verb (→ `suffix`).
   - **For a passive or middle form:** the grammatical subject (→ index, or `subject`).
   - **Every PP.**
   - **A bare second noun.**
3. **Is the use locative?** That is, is there a Locatum–Location relation brought about, kept or prevented? If not
   (an idiom, a clausal complement, a pure change of state), then `locative = N`, `frame = NON_LOCATIVE`.
4. **Assign the roles:**
   - **Locatum:** what moves, or is put, added or removed.
   - **Location:** where it goes or where it comes from: a place, container, surface, body part, or the possessor
     (for a recipient, see §4.6).
5. **The frame follows from the role of the direct object:**
   - **Frame A:** the direct object (or the passive subject) is the **Locatum**. מילא **מים** במיכל.
   - **Frame B:** the direct object (or the passive subject) is the **Location**. מילא **את המיכל** במים.
   - A **partial frame** (a direct object only, no PP) still has a frame: decide by what the object is (paper §2.2).
   - **`AMBIGUOUS`:** a careful reader cannot decide which argument is which, even from the wider context.
     Write why in `notes`. Example: paper fn 25 on Psalms 81:7.
6. **Never use the preposition alone to decide the frame.** In this construction the same preposition marks the
   Location in Frame A and the Locatum in Frame B; that is the paper's claim. Decide by meaning.

## 4. Special cases (with the paper's own examples)

1. **Passives and middles** (nif'al, pu'al, hof'al, hitpa'el):
   - the subject plays the direct object's role (paper p. 4, fn 10);
   - `do` = the subject's index, or `subject`;
   - example: Esther 2:6 הָגְלָה מירושלים → Frame A.
2. **Elided object.** The object is missing but has an antecedent, e.g. Psalms 12:6 אשית Ø בישע (fn 9). Then:
   - `do = elided`;
   - roles by the antecedent;
   - frame accordingly.
3. **Elided Locatum preposition** (fn 13, 21). An indefinite Locatum often appears without ב/מן, e.g. Haggai 2:7
   ומלאתי את הבית הזה **כבוד**; Judges 9:45 ויזרעה **מלח**. Then:
   - `bare_np` = that noun;
   - `locatum` = that noun;
   - the frame is **B**.
4. **Partitive מן** (fn 24, 27). "Some of the blood", as in Leviticus 16:14 ולקח **מדם** הפר; Ezra 9:3 ואמרטה
   **משער** ראשי.
   - The מן-noun is the **direct object**, the Locatum.
   - Put it in `do`, not in `pps`, and write `partitive` in `notes`.
5. **Instrument ב** (fn 7). For example Jeremiah 15:7 ואזרם **במזרה** בשערי הארץ; Numbers 22:27 ויך … **במקל**.
   - An instrument is not a Locatum: list it in `pps` but never as `locatum` or `location`.
   - Write `instrument` in `notes`.
6. **A recipient or possessor is a Location.**
   - Example: שלח מכתב **לחברו** → Frame A (letter = Locatum, friend = Location).
   - So with "deprive / rob / spare **X of** Y": X is the Location, Y the Locatum.
7. **על instead of ב** (fn 22): e.g. Genesis 27:16 הלבישה **על** ידיו. Roles as usual; write the preposition exactly.
8. **Other prepositions of path verbs** (fn 15): אל, ל, על, תחת, אחרי, בין, מעל, מעם, מאת and the directional ה-.
   Annotate them normally.
9. **Locatum as subject.** "The cloud **covered** the mercy seat" (Leviticus 16:13); MH המים מילאו את הבור.
   - `locatum = subject`.
   - The frame follows the direct object: here the object is the Location, so **B**.
   - Write `locatum_subject` in `notes`.
10. **Change of state without a Location**: "and it **tore**" (1 Samuel 15:27). `locative = N`, `NON_LOCATIVE`.
11. **Idioms and figurative uses that are not locative**: שם לב, נשא עין, כרת ברית, נתן קול, MH מילא תפקיד.
    `NON_LOCATIVE`, with the idiom in `notes`.
    - Metaphorical **motion** is still locative: "the rebuke He will take away from all the earth" (Isaiah 25:8).
12. **Clausal complement** (מנע מלהצביע, שלח לומר): `NON_LOCATIVE` unless a nominal Locatum and Location are also
    present.
13. **Two direct objects** (BH double accusative): mark the one that is the Locatum or Location in `do`, the other in
    `bare_np`, and explain in `notes`.
14. **The target is part of a conjunction** (ויקח … ויתן) and its object belongs to the other verb: annotate only
    what this verb takes. If the object is shared, use the shared object.
15. **A verb with frequent non-locative senses** (sense review, R1 release, D-057). Example: Modern **ישב.I
    יישב**.
    - It is the same verb in every sense, so `is_target_verb = Y`.
    - "Populate / settle (people in a place)", e.g. יישב את הגליל ביהודים, is **locative**: frame by the direct
      object as usual.
    - "Resolve / settle (a dispute, a contradiction)", e.g. יישב את הסכסוך, is **not locative**: `locative = N`,
      `frame = NON_LOCATIVE`, and the sense in `notes`.
    - **When you cannot decide, use `locative = ?`.** Give the frame the use would have if it were locative (`A` or
      `B`), or `AMBIGUOUS` if that cannot be decided either. Explain in `notes`. Never skip the item: these items
      are kept so that people measure the sense split; it is never decided automatically.

## 5. Worked examples

**Biblical examples, from the paper:**

| Sentence (target in bold) | do | pps | bare_np | locatum | location | frame |
|---|---|---|---|---|---|---|
| ומלאת בו מלאת אבן (Exodus 28:17) | מלאת | בו: ב | | מלאת | בו | **A** |
| … אשר **מלאוה** … בטמאתם (Ezra 9:11) | suffix | טמאתם: ב | | טמאתם | suffix | **B** |
| **ויזרעה** מלח (Judges 9:45) | suffix | | מלח | מלח | suffix | **B** |
| **ופרקת** עלו מעל צוארך (Genesis 27:40) | עלו | צוארך: מעל | | עלו | צוארך | **A** |
| **ויפרקנו** מצרינו (Psalms 136:24) | suffix | צרינו: מ | | צרינו | suffix | **B** |
| ולקח מדם הפר **והזה** באצבעו על פני הכפרת (Leviticus 16:14) | elided (the blood) | אצבעו: ב (instrument); פני: על | | elided (the blood) | פני | **A** |

**Modern Hebrew (constructed):**

| Sentence | frame | Why |
|---|---|---|
| דני **מילא** את המיכל במים | B | object = container (Location) |
| דני **מילא** מים במיכל | A | object = water (Locatum) |
| הוא **הפיץ** את הידיעה בערוצים | A | object = the news (Locatum) |
| הוא **ציפה** את הקירות בטפטים | B | object = walls (Location) |
| הצוות **פינה** את הפצועים מהשטח | A | object = the wounded (Locatum) |
| הצוות **פינה** את השטח מפצועים | B | object = area (Location) |
| היא **שמה** לב לבעיה | NON_LOCATIVE | idiom |
| הוא **שלח** לה מכתב | A | letter = Locatum, she = Location (recipient) |
| **ניקינו** את הדירה | B (partial) | object = flat (Location) |

## 6. When you are done with a split

1. Save the sheet. Keep the same file name and the CSV format.
2. Run the check. It validates every row and writes a **text-free** file of ids and labels (I4):
   ```
   uv run python -m hebloc loc gold check <sheet.csv> --sample <sample folder> --annotator <your name> --out <folder>
   ```
   - Ori: `--out annotation/gold`.
   - Efrat: `--out data/outbox/efrat-s6/gold`.
3. Fix every `PROBLEM` it reports and run it again. Rows you have not filled are reported as pending.
4. Deliver only the text-free file. The sheet stays local.

## 7. Time

- Expect about 1–3 minutes per item. Long verses and full frames take longer.
- Time your first 20 items and tell Ori. The workload estimate is then corrected from your real pace.
