# SILVER protocol addendum R2: the Phase C jobs (`S56-silver-p1` + D-065)

**What this is.** It pre-registers the SILVER jobs that Phase C needs and that the pinned protocol
(`annotation/S56_SILVER_PROTOCOL.md`, `S56-silver-p1`, pinned at `s56-r1.1`) does not list:
- the sentence jobs of a supplement;
- the I-3 sense screen;
- the §6 candidate review;
- the §6 template-proxy check;
- the class / identity audit.

It was written at stage C0 (2026-11-22, Ori's plan approval; decision D-065), **before any dev silver was read**.

**Precedence.** The pinned protocol stays in force and unchanged: SG1 isolation, SG2 freeze and hashes, SG3
recovery, the QC thresholds and the STOP options. This addendum only adds job types. Where the two differ, the
pinned protocol wins.

**Where the files are.** New files live in `annotation/silver/r2/` only. Nothing is added to or changed in
`annotation/silver/prompts/`. So the prompt record of every earlier job (`FROZEN.json` `prompts_sha256`) stays
identical, and the G3 / ES checks compare the pinned files exactly (D-065).

## 1. The jobs

| Job | Made by | Items from | Prompt | Passes and decision | Owner (D-061, D-065) | When |
|---|---|---|---|---|---|---|
| `sentence-<supplement id>-<split>` | `loc silver create --task sentence --sample <supplement folder> --split …` | A **registered** supplement (`gold.FROZEN_SUPPLEMENTS`, Ori at G3); drawn again from the package, the items must match (`items_sha256`) | `prompts/sentence_pass.md` (pinned) | As the protocol's `sentence` task (§3), dev first | Efrat's Claude Code | ES (after G3) |
| `screen-<corpus>-<hash>` | `loc draw screen` (Ori, G3, `--approval`), then `create --task instances --purpose screen --ids <draw>` | The I-3 sense screen: per affected key, 15 instances from outside every sample (no sentence holding a frozen or supplement item, an anchor item, a paper-example verse or an R1 screen reading) | `prompts/sentence_pass.md` (pinned) | As `sentence`; the screen reads `is_target_verb` | Efrat's Claude Code | ES (after G3) |
| `review-<corpus>-<hash>` | `loc draw review --input <all-verbs extract> --variant <R…>`, then `create --task instances --purpose review` | §6 candidate review (EFRAT §5.9(2)) | `prompts/sentence_pass.md` (pinned) | As `sentence` | Efrat's Claude Code | E9 |
| `template-<corpus>-<hash>` | `loc draw template --input <all-verbs extract>`, then `create --task template --ids <draw>` | §6 template proxy (EFRAT §5.9(3)): lemma items (the lemma and its 5 most frequent forms; the proxy is never shown) | `r2/template_pass.md` | A ∥ B. The same label in both passes, neither `low` → that label; otherwise `unclear` (`abstained`). κ is reported; no STOP (as for the noun types) | Efrat's Claude Code | E9 |
| `audit-<corpus>-<hash>` | `loc draw audit --input <extract> --variant <chosen>` (Ori), then `create --task instances --purpose audit` | Class / identity audit (EFRAT §5.5, §5.6): the deciding instances of every PRIMARY verb whose class differs from the paper, and the identity instances of every COUNTEREXAMPLE | `prompts/sentence_pass.md` (pinned) | As `sentence` | **Efrat's Claude Code** (D-065). Ori sends the draw folder (ids only); the pipeline outcomes stay in Ori's local `audit_key.csv` | EA: Mikra after G6, all corpora at O5 |

**The sentence-type jobs** (supplement, screen, review, audit) use the pinned sentence prompt, guideline, decision
fields, κ, QC thresholds (T4, T5, abstention 30%), recovery and STOP rules **unchanged**. For these jobs, a "split"
in those rules is the job.
- A verb outside the lexicon is shown as `lemma:<lemma>`, with the entry text "the verb whose dictionary form
  (Dicta's lemma) is …".
- `is_target_verb` asks whether the token is that verb.
- `member` stays empty.

## 2. Pre-registered sizes (Ori, 2026-11-22)

- **Supplement:** one per corpus for I-1 + I-4, stratified by candidate × gold stratum, with the gold-r1b caps (8 per
  key; HOMOGRAPH 4 per key and at most 10% of the size). The size is fixed per supplement when Ori approves its draw
  (G3; proposed 120 = 30 / 30 / 60).
- **I-3 screen:** 15 instances per affected key. Decision at C1: the key's I-3 change applies when **≤ 3** of the 15
  are the verb (`is_target_verb = Y`).
- **§6 candidate review:**
  - candidates are the non-lexicon units that are swap-test candidates, have both A and B outcomes, or have both
    DO+PP[B] and DO+PP[MIN] signatures;
  - the **100** most frequent are reviewed;
  - per unit, **≤ 5** instances of each pool (outcome A / outcome B; for a unit with no A/B outcome, the two
    signatures).
- **Template proxy:** **200** lemmas with ≥ 20 tokens, by proxy value: proportional, with at least **20** per value
  when available.
- **Class / identity audit:** every differing verb's existing `deciding_ids` (≤ 5 per outcome) and `identity_ids`
  (≤ 3 + 3). There is no further sampling.

Every draw is deterministic (salted sha256), independent of the data source, and records `items_sha256`. A draw
repeated on Efrat's computer must give the same items.

## 3. Use and wording

- Supplement silver enters scoring as a second stratum of the design (S56_R1 §3; `score.load_gold`). Ori's code reads
  it only after its hashes are recorded in `FROZEN_SILVER.json`.
- Screen silver decides I-3 per key at C1, read by Ori's code after it is received.
- Review and template silver are §6 analysis inputs (Efrat).
- Audit silver is **error analysis** of §5 and §6 results.
- None of these is ever validation, accuracy or human gold. The report wording is "agreement with SILVER".
