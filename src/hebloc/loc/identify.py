"""Which tokens are occurrences of which lexicon entry (S56-v1 §5.2) — with the AMBIGUITY RULE (D-057).

A token is identified when ``upos == 'VERB'`` and its lemma is one of an entry's ``dicta_lemmas`` or
``shared_lemmas``, or its ``host`` is one of the entry's generated forms.

One token = one instance:
- if several entries match (a lemma or form shared by two templates or by homographs), the token gets ONE
  combined ``verb_key`` = the sorted entry ids joined by ``|`` (e.g. ``שלח.I|שלח.S``);
- if the lemma is a ``shared_lemma`` (also the lemma of a non-lexicon verb), a ``~<lemma>`` member is added
  (e.g. ``צפה.I|~ציפה``): the token may not be this verb at all;
- the token is never assigned to one member by default and never counted under each member.
- forms-v2: an entry matched by FORM ONLY (the token's lemma is not one of the entry's own or shared lemmas) on an
  AMBIGUOUS host adds that host's ``~partners`` (a competing verb's lemma, or ``~<root>.S`` for a Causative/Intensive
  form that is also a Simple form of the same root): the token stays in, as a combined key, never dropped.

``match_method``: ``lemma`` (lemma or shared lemma only), ``form`` (host only) or ``both``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import pyarrow as pa

from hebloc.loc.lexicon import Lexicon


@dataclass
class Index:
    lemma: dict[str, list[tuple[str, str]]]    # lemma -> [(entry id, voice)]
    shared: dict[str, list[str]]                # lemma -> [entry id]
    form: dict[str, list[str]]                  # host -> [entry id]
    form_tilde: dict[tuple[str, str], list[str]]  # (host, entry id) -> ~partners (ambiguous forms)


def build_index(lex: Lexicon) -> Index:
    lem, sh, fo = defaultdict(list), defaultdict(list), defaultdict(list)
    for e in lex.entries:
        for d in e.dicta_lemmas:
            lem[d["lemma"]].append((e.id, d["voice"]))
        for d in e.shared_lemmas:
            sh[d["lemma"]].append(e.id)
        for h in lex.forms.get(e.id, []):
            fo[h].append(e.id)
    ft = {(h, eid): list(p) for eid, hp in lex.ambiguous.items() for h, p in hp.items()}
    return Index(dict(lem), dict(sh), dict(fo), ft)


def combine(entries: set[str], tildes: set[str]) -> str:
    return "|".join(sorted(entries) + sorted(tildes))


def identify(idx: Index, lemma: str | None, host: str | None, upos: str | None) -> dict | None:
    """Python version of the rule (small inputs, tests). Same result as :func:`identify_sql`."""
    if upos != "VERB":
        return None
    ents, tildes, voices = set(), set(), set()
    by_lemma = by_form = False
    lemma_ents: set[str] = set()
    for eid, voice in idx.lemma.get(lemma, []):
        ents.add(eid)
        lemma_ents.add(eid)
        voices.add(voice)
        by_lemma = True
    for eid in idx.shared.get(lemma, []):
        ents.add(eid)
        lemma_ents.add(eid)
        tildes.add(f"~{lemma}")
        by_lemma = True
    for eid in idx.form.get(host, []):
        ents.add(eid)
        by_form = True
        if eid not in lemma_ents:                       # form-only for this entry: an ambiguous host adds its partners
            tildes.update(idx.form_tilde.get((host, eid), []))
    if not ents:
        return None
    return {"verb_key": combine(ents, tildes), "members": sorted(ents), "tilde": sorted(tildes),
            "match_method": "both" if by_lemma and by_form else ("lemma" if by_lemma else "form"),
            "voice": voices.pop() if len(voices) == 1 else ("mixed" if voices else "unknown")}


def register(con, lex: Lexicon) -> None:
    """Create the lookup tables ``lex_lemma``, ``lex_shared``, ``lex_form`` and ``lex_entry`` in ``con``."""
    rows_l = [(d["lemma"], e.id, d["voice"]) for e in lex.entries for d in e.dicta_lemmas]
    rows_s = [(d["lemma"], e.id) for e in lex.entries for d in e.shared_lemmas]
    rows_f = [(h, e.id, lex.ambiguous.get(e.id, {}).get(h, [])) for e in lex.entries for h in lex.forms.get(e.id, [])]
    con.register("_lex_lemma", pa.table({"lemma": [r[0] for r in rows_l], "entry_id": [r[1] for r in rows_l],
                                         "voice": [r[2] for r in rows_l]}, schema=pa.schema([("lemma", pa.string()), ("entry_id", pa.string()), ("voice", pa.string())])))
    con.register("_lex_shared", pa.table({"lemma": [r[0] for r in rows_s], "entry_id": [r[1] for r in rows_s]},
                                         schema=pa.schema([("lemma", pa.string()), ("entry_id", pa.string())])))
    con.register("_lex_form", pa.table({"host": [r[0] for r in rows_f], "entry_id": [r[1] for r in rows_f],
                                        "partners": [r[2] for r in rows_f]},
                                       schema=pa.schema([("host", pa.string()), ("entry_id", pa.string()),
                                                         ("partners", pa.list_(pa.string()))])))
    con.register("_lex_entry", pa.table({"entry_id": [e.id for e in lex.entries], "class": [e.klass for e in lex.entries],
                                         "status": [e.status for e in lex.entries]},
                                        schema=pa.schema([("entry_id", pa.string()), ("class", pa.string()), ("status", pa.string())])))
    for t in ("lex_lemma", "lex_shared", "lex_form", "lex_entry"):
        con.execute(f"CREATE OR REPLACE TEMP TABLE {t} AS SELECT * FROM _{t}")


def identify_sql(tokens_relation: str) -> str:
    """SQL: one row per identified token of ``tokens_relation`` (needs sent_id, piece_idx, word_idx, lemma,
    host, upos): ``sent_id, piece_idx, word_idx, verb_key, members, tilde, match_method, voice, classes,
    statuses``. Requires :func:`register`."""
    return f"""
    WITH t AS (SELECT sent_id, piece_idx, word_idx, lemma, host FROM {tokens_relation} WHERE upos = 'VERB'),
    m AS (
      SELECT t.sent_id, t.piece_idx, t.word_idx, l.entry_id, 'lemma' AS how, l.voice, NULL::VARCHAR AS tilde,
             NULL::VARCHAR[] AS partners FROM t JOIN lex_lemma l USING (lemma)
      UNION ALL
      SELECT t.sent_id, t.piece_idx, t.word_idx, s.entry_id, 'lemma', NULL, '~' || t.lemma, NULL FROM t JOIN lex_shared s USING (lemma)
      UNION ALL
      SELECT t.sent_id, t.piece_idx, t.word_idx, f.entry_id, 'form', NULL, NULL, f.partners FROM t JOIN lex_form f ON t.host = f.host
    ),
    me AS (
      SELECT sent_id, piece_idx, word_idx, entry_id, bool_or(how = 'lemma') AS el, bool_or(how = 'form') AS ef,
             list(voice) FILTER (WHERE voice IS NOT NULL) AS voices,
             list(tilde) FILTER (WHERE tilde IS NOT NULL) AS tl,
             flatten(list(partners) FILTER (WHERE partners IS NOT NULL)) AS fp
      FROM m GROUP BY ALL
    ),
    g AS (
      SELECT sent_id, piece_idx, word_idx,
             list_sort(list_distinct(list(entry_id))) AS members,
             list_sort(list_distinct(flatten(list(list_concat(coalesce(tl, []::VARCHAR[]),
                                                              CASE WHEN el THEN []::VARCHAR[] ELSE coalesce(fp, []::VARCHAR[]) END))))) AS tilde,
             bool_or(el) AS by_lemma, bool_or(ef) AS by_form,
             list_distinct(flatten(list(coalesce(voices, []::VARCHAR[])))) AS voices
      FROM me GROUP BY ALL
    )
    SELECT g.sent_id, g.piece_idx, g.word_idx,
           array_to_string(list_concat(g.members, g.tilde), '|') AS verb_key, g.members, g.tilde,
           CASE WHEN by_lemma AND by_form THEN 'both' WHEN by_lemma THEN 'lemma' ELSE 'form' END AS match_method,
           CASE WHEN len(voices) = 1 THEN voices[1] WHEN len(voices) > 1 THEN 'mixed' ELSE 'unknown' END AS voice,
           (SELECT list_sort(list_distinct(list(coalesce(e.class, 'none')))) FROM lex_entry e WHERE list_contains(g.members, e.entry_id)) AS classes,
           (SELECT list_sort(list_distinct(list(e.status))) FROM lex_entry e WHERE list_contains(g.members, e.entry_id)) AS statuses
    FROM g"""
