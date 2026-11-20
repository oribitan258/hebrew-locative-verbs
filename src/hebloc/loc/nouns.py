"""Frequent-argument-noun lists (to be typed by a human) and the merge of reviewed types (S56-v1 §5.4; I1).

``list_nouns`` ranks the NOUN/PROPN lemmas that head a direct object, a passive subject or a PP of the corpus's
lexicon-verb occurrences (full view). For Modern it also counts the arguments of ALL verbs that have a full frame
(DO + PP of family B or MIN), because §6 classifies all verbs. The list is cut by coverage (D-057):
- Mikra (small, the validation corpus): every lemma with >= 2 argument tokens (93% of argument tokens);
- Hazal, Medieval, Haskala, Modern: the most frequent lemmas until 85% of argument-head tokens are covered, at most
  2,000; with ``--exclude-typed`` only lemmas not yet in ``config/noun_types.yaml`` (incremental typing).
(With min_n = 2 everywhere Ori would type ~5,400 historical nouns; this cut gives ~1,900. Resolver variant R1
induces location-likeness for untyped nouns.)
Both the cut and the coverage reached are written to the manifest and shown at review.

The typing itself is human: Claude Code may PROPOSE a type (``proposed_type``, ``proposed_by: claude_code``);
the human accepts or corrects EVERY row (``type``, ``reviewed_by``). ``merge`` refuses rows without a human
reviewer and writes ``config/noun_types.yaml`` (only Ori runs it).
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import yaml

from hebloc.loc import identify as ID
from hebloc.loc import tree as TR
from hebloc.loc.gold import TREE_COLUMNS
from hebloc.loc.lexicon import Lexicon
from hebloc.loc.manifest import write_csv, write_manifest
from hebloc.loc.source import Source, connect
from hebloc.paths import CONFIG_DIR, DATA_DIR
from hebloc.store.io import atomic_write_parquet, atomic_write_text

NOUN_TYPES_PATH = CONFIG_DIR / "noun_types.yaml"
NOUNS_DIR = DATA_DIR / "loc" / "nouns"
NOUN_TYPES = ("LOCATION", "LOCATUM", "ANIMATE", "UNCLEAR")
LIST_VERSION = "nouns-r1"
CUT = {"mikra": {"min_n": 2},
       "hazal": {"coverage": 0.85, "max_rows": 2000}, "medieval": {"coverage": 0.85, "max_rows": 2000},
       "haskala": {"coverage": 0.85, "max_rows": 2000}, "modern": {"coverage": 0.85, "max_rows": 2000}}
LABEL_COLUMNS = ("proposed_type", "proposed_by", "type", "reviewed_by", "note")


class NounsError(Exception):
    pass


def load_types(path: Path = NOUN_TYPES_PATH) -> dict[str, dict]:
    if not Path(path).exists():
        return {}
    d = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {r["lemma"]: r for r in d.get("nouns") or []}


def list_nouns(corpus: str, source: Source, lex: Lexicon, *, out_root: Path = NOUNS_DIR, git: dict,
               exclude_typed: bool = False, progress: bool = True) -> dict:
    con = connect()
    ID.register(con, lex)
    con.execute(f"CREATE OR REPLACE TEMP TABLE units AS SELECT sent_id, in_full_view FROM {source.units_sql(corpus, ('sent_id', 'in_full_view'))}")
    all_verbs = corpus == "modern"
    parts = []
    for run in source.runs(corpus):
        if progress:
            print(f"  nouns {corpus}: {run.run_id}", flush=True)
        con.execute(f"CREATE OR REPLACE TEMP TABLE tok AS SELECT t.* FROM {source.tokens_sql(run, TREE_COLUMNS)} t JOIN units u USING (sent_id) WHERE u.in_full_view")
        con.execute(f"CREATE OR REPLACE TEMP TABLE idn AS {ID.identify_sql('tok')}")
        if all_verbs:
            # lexicon verbs, plus every other verb that can have a full frame (an obj child or an object suffix)
            con.execute("""CREATE OR REPLACE TEMP TABLE v AS SELECT t.sent_id, t.piece_idx, t.word_idx, t.suffix,
                             coalesce(i.voice, 'unknown') AS voice, i.verb_key FROM tok t LEFT JOIN idn i USING (sent_id, piece_idx, word_idx)
                           WHERE t.upos = 'VERB' AND (i.verb_key IS NOT NULL OR t.suffix = 'PRON' OR EXISTS (
                             SELECT 1 FROM tok o WHERE o.sent_id = t.sent_id AND o.piece_idx = t.piece_idx AND o.head = t.word_idx AND o.deprel = 'obj'))""")
        else:
            con.execute("""CREATE OR REPLACE TEMP TABLE v AS SELECT i.sent_id, i.piece_idx, i.word_idx, t.suffix, i.voice, i.verb_key
                           FROM idn i JOIN tok t USING (sent_id, piece_idx, word_idx)""")
        con.execute(f"CREATE OR REPLACE TEMP TABLE args AS {TR.arguments_sql('v', 'tok')}")
        parts.append(con.sql("""
            WITH a AS (SELECT a.*, v.verb_key FROM args a JOIN v ON v.sent_id = a.sent_id AND v.piece_idx = a.piece_idx AND v.word_idx = a.verb_word_idx),
                 ff AS (SELECT sent_id, piece_idx, verb_word_idx FROM a GROUP BY ALL
                          HAVING bool_or(slot IN ('DO', 'PASSIVE_SUBJ')) AND bool_or(p_family IN ('B', 'MIN'))),
                 a2 AS (SELECT a.*, (f.sent_id IS NOT NULL) AS in_full_frame FROM a LEFT JOIN ff f USING (sent_id, piece_idx, verb_word_idx))
            SELECT head_lemma AS lemma, head_upos AS upos,
                   count(*) FILTER (WHERE verb_key IS NOT NULL)::BIGINT AS n_lexicon,
                   count(*) FILTER (WHERE verb_key IS NULL AND in_full_frame)::BIGINT AS n_allverbs_full_frame,
                   count(*) FILTER (WHERE slot IN ('DO', 'PASSIVE_SUBJ'))::BIGINT AS n_as_do,
                   count(*) FILTER (WHERE p_family = 'B')::BIGINT AS n_pp_B,
                   count(*) FILTER (WHERE p_family = 'MIN')::BIGINT AS n_pp_MIN,
                   count(*) FILTER (WHERE slot = 'PP' AND p_family NOT IN ('B', 'MIN'))::BIGINT AS n_other_pp,
                   list(DISTINCT verb_key) FILTER (WHERE verb_key IS NOT NULL) AS verbs
            FROM a2
            WHERE head_upos IN ('NOUN', 'PROPN') AND head_lemma IS NOT NULL AND head_lemma <> '[BLANK]'
              AND slot IN ('DO', 'PASSIVE_SUBJ', 'PP') AND (verb_key IS NOT NULL OR in_full_frame)
            GROUP BY ALL""").to_arrow_table())
    con.register("p", pa.concat_tables(parts))
    t = con.sql("""SELECT lemma, upos, sum(n_lexicon)::BIGINT AS n_lexicon, sum(n_allverbs_full_frame)::BIGINT AS n_allverbs_full_frame,
                          sum(n_as_do)::BIGINT AS n_as_do, sum(n_pp_B)::BIGINT AS n_pp_B, sum(n_pp_MIN)::BIGINT AS n_pp_MIN,
                          sum(n_other_pp)::BIGINT AS n_other_pp, list_sort(list_distinct(flatten(list(verbs)))) AS verbs
                   FROM p GROUP BY ALL""").to_arrow_table().to_pylist()
    for r in t:
        r["n"] = r["n_lexicon"] + r["n_allverbs_full_frame"]
        r["n_verbs"] = len(r["verbs"])
        r["verbs"] = r["verbs"][:10]
    t.sort(key=lambda r: (-r["n"], r["lemma"], r["upos"]))
    total = sum(r["n"] for r in t)
    cut = CUT[corpus]
    cum = 0
    for i, r in enumerate(t, 1):
        cum += r["n"]
        r["rank"] = i
        r["cum_coverage"] = cum / total if total else 0.0
        if "min_n" in cut:
            r["included"] = r["n"] >= cut["min_n"]
        else:
            r["included"] = i <= cut["max_rows"] and (cum - r["n"]) / total < cut["coverage"]
    typed = load_types()
    for r in t:
        r["already_typed"] = r["lemma"] in typed
    lid = f"{corpus}-{LIST_VERSION}-{lex.sha256[:10]}"
    out = Path(out_root) / corpus / lid
    out.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(t)
    atomic_write_parquet(table, out / "nouns.parquet")
    label = [{"lemma": r["lemma"], "upos": r["upos"], "n": r["n"], "n_as_do": r["n_as_do"], "n_pp_B": r["n_pp_B"],
              "n_pp_MIN": r["n_pp_MIN"], "n_other_pp": r["n_other_pp"], "n_verbs": r["n_verbs"],
              "example_verbs": "; ".join(r["verbs"][:5]), "corpus_source": corpus, **{c: "" for c in LABEL_COLUMNS}}
             for r in t if r["included"] and not (exclude_typed and r["already_typed"])]
    write_csv(pa.Table.from_pylist(label) if label else pa.table({"lemma": pa.array([], pa.string())}), out / "nouns_to_label.csv")
    inc = [r for r in t if r["included"]]
    covered = sum(r["n"] for r in inc) / total if total else 0.0
    return write_manifest(out, what="frequent-argument-noun list", git=git, source=source.describe(corpus),
                          extra={"corpus": corpus, "list_id": lid, "list_version": LIST_VERSION, "lexicon_sha256": lex.sha256,
                                 "cut": cut, "all_verbs_full_frames": all_verbs, "n_lemmas": len(t), "n_included": len(inc),
                                 "n_to_label": len(label), "argument_tokens": total, "coverage_of_included": round(covered, 4),
                                 "exclude_typed": exclude_typed})


def merge(reviewed: Path, path: Path = NOUN_TYPES_PATH, *, replace: bool = False) -> dict:
    """Merge a reviewed list (CSV with lemma, type, proposed_by, reviewed_by, note, corpus_source) into
    ``config/noun_types.yaml``. Every row must have a type and a HUMAN reviewer. Ori only."""
    import csv

    with open(reviewed, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("type") or "").strip()]
    probs = []
    for i, r in enumerate(rows, 2):
        if r["type"].strip() not in NOUN_TYPES:
            probs.append(f"line {i} {r.get('lemma')}: type {r['type']!r} not in {NOUN_TYPES}")
        if not (r.get("reviewed_by") or "").strip() or r["reviewed_by"].strip().lower() in ("claude_code", "claude"):
            probs.append(f"line {i} {r.get('lemma')}: reviewed_by must name the human reviewer")
        if (r.get("proposed_by") or "human").strip() not in ("human", "claude_code"):
            probs.append(f"line {i} {r.get('lemma')}: proposed_by must be human or claude_code")
    current = load_types(path)
    conflicts = [f"{r['lemma']}: {current[r['lemma']]['type']} -> {r['type']}" for r in rows
                 if r["lemma"] in current and current[r["lemma"]]["type"] != r["type"].strip()]
    if conflicts and not replace:
        probs += [f"conflict (use --replace deliberately): {c}" for c in conflicts]
    if probs:
        return {"ok": False, "problems": probs}
    for r in rows:
        current[r["lemma"]] = {"lemma": r["lemma"], "type": r["type"].strip(), "corpus_source": (r.get("corpus_source") or "").strip(),
                               "proposed_by": (r.get("proposed_by") or "human").strip(), "reviewed_by": r["reviewed_by"].strip(),
                               "note": (r.get("note") or "").strip()}
    doc = {"meta": {"methodology": "S56-v1", "types": list(NOUN_TYPES),
                    "rule": "every row reviewed by a human; Claude Code may only propose (D-054)"},
           "nouns": [current[k] for k in sorted(current)]}
    atomic_write_text("# Noun types of S56-v1 (I1). Written by `hebloc loc nouns merge` (Ori only).\n"
                      + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=200), path)
    return {"ok": True, "merged": len(rows), "total": len(current), "replaced": len(conflicts)}
