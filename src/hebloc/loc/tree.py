"""Direct objects and prepositional phrases read from Dicta's dependency trees (S56-v1 §5.3).

Shared by R1 (frequent-argument-noun lists, the §6 sampling frame) and, unchanged, by the R2 extractor.
Facts about the token data this relies on (verified on Mikra, 2026-11-20):

- heads are piece-local (``head`` = ``word_idx`` of the parent in the same ``(sent_id, piece_idx)``; -1 = root);
- a clitic preposition is part of the noun's ``prefix`` and ``prefix_upos`` contains ``ADP``; ``prefix_upos``
  is NOT aligned letter by letter, so the preposition is the last of ב/ל/מ/כ in ``prefix``;
- a separate preposition is a ``case`` child of its noun (``case:acc`` = את is the object marker, not a PP);
- pronominal PPs (בו, ממנו, עליו, לו) are one ADP/PRON token with ``suffix == 'PRON'`` attached as obl/nmod;
- object pronouns (אותו, אתו) are ``obj`` ADP/PRON tokens with a PRON suffix; an object suffix on the verb is
  ``suffix == 'PRON'`` on the verb itself (``ADP_PRON`` is a possessive, never an object).

Preposition families (§5.3): ``B`` (ב, בתוך), ``MIN`` (מן, מ-, and every מ+X compound: מעל, מתוך, מאת, מעם,
מיד, מקרב, … by the paper's fn 22 analogy), ``AL`` (על), ``EL`` (אל), ``LE`` (ל), ``OTHER``.
"""

from __future__ import annotations

PREP_BASES = ("על", "תוך", "את", "עם", "יד", "קרב", "פני", "אחרי", "אחר", "תחת", "בין", "אצל", "סביב", "נגד",
              "לפני", "עד", "חוץ")
B_WORDS = ("ב", "בתוך")
MIN_WORDS = ("מ", "מן")
PP_DEPRELS_SQL = "(c.deprel LIKE 'obl%' OR c.deprel = 'nmod')"
BARE_DEPRELS = ("obj", "xcomp", "dep", "parataxis", "obl:npmod")
NOMINAL = ("NOUN", "PROPN", "PRON", "NUM", "ADJ")

FINAL = {"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"}


def _nf(s: str) -> str:
    return "".join(FINAL.get(ch, ch) for ch in s)


def pron_prep(form: str, lemma: str | None = None) -> str:
    """Preposition of a pronominal PP token (בו → ב, ממנו → מן, עליו → על, אליו → אל, לו → ל)."""
    f = form or ""
    for pre, p in (("בתוכ", "בתוך"), ("ממ", "מן"), ("מה", "מן"), ("מן", "מן"), ("מע", "מעל" if f.startswith("מעל") else "מעם"),
                   ("מאת", "מאת"), ("אל", "אל"), ("על", "על"), ("עמ", "עם"), ("אות", "את"), ("את", "את"),
                   ("ב", "ב"), ("ל", "ל"), ("כ", "כ")):
        if f.startswith(pre):
            return p
    return lemma or f


def p_family(p: str | None) -> str | None:
    if not p:
        return None
    if p in B_WORDS:
        return "B"
    if p in MIN_WORDS or (p.startswith("מ") and _nf(p[1:]) in {_nf(b) for b in PREP_BASES}):
        return "MIN"
    return {"על": "AL", "אל": "EL", "ל": "LE"}.get(p, "OTHER")


def p_family_sql(col: str) -> str:
    bases = ", ".join(f"'{b}'" for b in PREP_BASES)
    return (f"CASE WHEN {col} IS NULL THEN NULL "
            f"WHEN {col} IN ('ב', 'בתוך') THEN 'B' "
            f"WHEN {col} IN ('מ', 'מן') OR (left({col}, 1) = 'מ' AND substr({col}, 2) IN ({bases})) THEN 'MIN' "
            f"WHEN {col} = 'על' THEN 'AL' WHEN {col} = 'אל' THEN 'EL' WHEN {col} = 'ל' THEN 'LE' ELSE 'OTHER' END")


def pron_prep_sql(form: str, lemma: str) -> str:
    return (f"CASE WHEN {form} LIKE 'בתוכ%' THEN 'בתוך' WHEN {form} LIKE 'ממ%' OR {form} LIKE 'מה%' OR {form} LIKE 'מן%' THEN 'מן' "
            f"WHEN {form} LIKE 'מעל%' THEN 'מעל' WHEN {form} LIKE 'מע%' THEN 'מעם' WHEN {form} LIKE 'מאת%' THEN 'מאת' "
            f"WHEN {form} LIKE 'אל%' THEN 'אל' WHEN {form} LIKE 'על%' THEN 'על' WHEN {form} LIKE 'עמ%' THEN 'עם' "
            f"WHEN {form} LIKE 'אות%' OR {form} LIKE 'את%' THEN 'את' WHEN {form} LIKE 'ב%' THEN 'ב' WHEN {form} LIKE 'ל%' THEN 'ל' "
            f"WHEN {form} LIKE 'כ%' THEN 'כ' ELSE {lemma} END")


def arguments_sql(verbs: str, tokens: str) -> str:
    """One row per candidate internal argument of each verb in ``verbs`` (columns sent_id, piece_idx, word_idx,
    suffix, voice), using the tokens of the same run in ``tokens``.

    Output: sent_id, piece_idx, verb_word_idx, slot (DO | PP | BARE_NP | PASSIVE_SUBJ), do_kind, head_word_idx,
    head_form, head_lemma, head_upos, is_pronoun, deprel, p_exact, p_family. Rows depend only on the tree (the
    same token gives the same rows in lexicon and all-verbs modes)."""
    bare = ", ".join(f"'{d}'" for d in BARE_DEPRELS)
    nominal = ", ".join(f"'{u}'" for u in NOMINAL)
    return f"""
    WITH v AS (SELECT sent_id, piece_idx, word_idx, suffix, voice FROM {verbs}),
    tk AS (SELECT sent_id, piece_idx, word_idx, head, deprel, form, host, lemma, upos, prefix, prefix_upos, suffix FROM {tokens}),
    c AS (SELECT v.sent_id, v.piece_idx, v.word_idx AS verb_word_idx, v.voice, t.* EXCLUDE (sent_id, piece_idx)
          FROM v JOIN tk t ON t.sent_id = v.sent_id AND t.piece_idx = v.piece_idx AND t.head = v.word_idx),
    cw AS (SELECT c.sent_id, c.piece_idx, c.word_idx, string_agg(k.host, ' ' ORDER BY k.word_idx) AS case_word
           FROM c JOIN tk k ON k.sent_id = c.sent_id AND k.piece_idx = c.piece_idx AND k.head = c.word_idx AND k.deprel = 'case'
           GROUP BY ALL),
    a AS (
      SELECT c.*, cw.case_word,
        CASE WHEN c.upos IN ('ADP', 'PRON') AND c.suffix = 'PRON' AND {PP_DEPRELS_SQL} THEN {pron_prep_sql('c.form', 'c.lemma')}
             WHEN list_contains(c.prefix_upos, 'ADP') THEN regexp_extract(c.prefix, '([בלמכ])[^בלמכ]*$', 1)
             WHEN cw.case_word IS NOT NULL THEN cw.case_word END AS p_exact
      FROM c LEFT JOIN cw USING (sent_id, piece_idx, word_idx))
    SELECT sent_id, piece_idx, verb_word_idx, 'DO' AS slot,
           CASE WHEN upos IN ('ADP', 'PRON') THEN 'pronoun' ELSE 'noun' END AS do_kind,
           word_idx AS head_word_idx, form AS head_form, lemma AS head_lemma, upos AS head_upos,
           upos IN ('ADP', 'PRON') AS is_pronoun, deprel, NULL AS p_exact, NULL AS p_family
      FROM a WHERE deprel = 'obj' AND p_exact IS NULL
    UNION ALL
    SELECT sent_id, piece_idx, verb_word_idx, 'PASSIVE_SUBJ', 'passive_subject', word_idx, form, lemma, upos,
           upos IN ('ADP', 'PRON'), deprel, NULL, NULL
      FROM a WHERE voice IN ('passive', 'middle') AND deprel LIKE 'nsubj%'
    UNION ALL
    SELECT sent_id, piece_idx, verb_word_idx, 'PP', NULL, word_idx, form, lemma, upos,
           upos IN ('ADP', 'PRON'), deprel, p_exact, {p_family_sql('p_exact')}
      FROM a WHERE p_exact IS NOT NULL AND ({PP_DEPRELS_SQL.replace('c.', '')} OR deprel = 'obj')
    UNION ALL
    SELECT sent_id, piece_idx, verb_word_idx, 'BARE_NP', NULL, word_idx, form, lemma, upos,
           upos IN ('ADP', 'PRON'), deprel, NULL, NULL
      FROM a WHERE p_exact IS NULL AND deprel IN ({bare}) AND deprel <> 'obj' AND upos IN ({nominal})
    UNION ALL
    SELECT sent_id, piece_idx, word_idx, 'DO', 'suffix', word_idx, NULL, NULL, NULL, TRUE, NULL, NULL, NULL
      FROM v WHERE suffix = 'PRON'"""
