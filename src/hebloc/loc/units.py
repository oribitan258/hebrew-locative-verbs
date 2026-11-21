"""Verb units (policy ``vunit-v1``, D-059): which Dicta lemmas are one verb, the function-predicate list, and the
tense-aware verb inventory (S56-v1 §5.1 / §5.9; open issues OI-1 and OI-2, D-058).

THE UNIT (P1). A verb is its root + template (Simple = qal + nif'al; Intensive = pi'el + pu'al + hitpa'el;
Causative = hif'il + hof'al), as the lexicon already defines it for the paper's verbs. A unit never crosses roots or
templates. Paper verbs: the unit is the lexicon entry (authoritative; never overridden here). Every other lemma is
its OWN unit unless a link below is in force. The raw-lemma level is always kept next to the unit level.

AUTOMATIC LINKS (P2) — only a same-binyan present participle that is unambiguous. ``v -> f`` is automatic only if
1. ``v`` is the masculine-singular present participle of ``f`` in ``f``'s own binyan (the paradigm table in
   :func:`analyses`: qal CוCC/CוCה; pi'el מCCC/מCCה; hif'il מCCיC/מCיC/מוCיC; hitpa'el מתCCC);
2. no other reading of ``v`` (another binyan of the same root, e.g. a pu'al past of an existing pi'el; a po'el /
   polel; another root) leads to another established lemma, and ``v`` is not itself a finite lemma;
3. >= 50% of ``v``'s tokens are present/participle and <= 20% finite;
4. ``v`` and ``f`` are VERB lemmas with >= 20 tokens (pooled over the five corpora); ``f`` has >= 20% finite tokens;
5. ``v`` is not a lexicon lemma, and ``f`` is not one (a variant of a paper verb is listed for Ori instead: P5).
Automatic links take effect only after the pre-registered audit has passed (100 links by a fixed hash, >= 95
correct); until then they are inactive unless a development run asks for them explicitly (recorded).

REVIEWED LINKS (P3) — passive (nif'al, pu'al, hof'al) -> its active verb; middle (hitpa'el) -> pi'el; every
participle link that fails P2; inflected strings (עשית, קראתי). A link is accepted only when ``v`` is the same
lexeme as ``f`` (its passive, middle or inflection); otherwise ``v`` stays separate (נכנס ≠ כנס). Claude Code may
propose; a human accepts or corrects every row (D-059, A3); ``merge`` refuses rows without a human reviewer.

FUNCTION PREDICATES (P6) — a closed list (``config/function_predicates.yaml``) approved by Ori. It only TAGS
(``function_class``); nothing is excluded from the main analysis.
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import yaml

from hebloc.loc import METHODOLOGY
from hebloc.loc import morph
from hebloc.loc import tree as TR
from hebloc.loc.lexicon import INFLECTED_ENDINGS, Lexicon
from hebloc.loc.source import Source, connect
from hebloc.paths import CONFIG_DIR, DATA_DIR
from hebloc.store.io import atomic_write_parquet, atomic_write_text, file_sha256

UNITS_VERSION = "vunit-v1"
UNITS_PATH = CONFIG_DIR / "verb_units.yaml"
FUNCTION_PATH = CONFIG_DIR / "function_predicates.yaml"
INVENTORY_T_DIR = DATA_DIR / "loc" / "inventory_t"
REVIEW_DIR = DATA_DIR / "loc" / "review" / "units"

#: pre-registered thresholds (D-059, P2)
LINK_MIN_TOKENS = 20
BASE_MIN_FIN_SHARE = 0.20
VARIANT_MIN_PRES_SHARE = 0.50
VARIANT_MAX_FIN_SHARE = 0.20
INFLECTED_MIN_HOST_SHARE = 0.80
AUDIT_N = 100
AUDIT_MIN_CORRECT = 95
AUDIT_SALT = f"{METHODOLOGY}:units:audit:"
#: above this many review rows Ori sets a frequency cut at STOP-B (rows below it stay separate units)
REVIEW_CUT_WARN = 1000

TEMPLATE_OF_BINYAN = {"qal": "Simple", "nifal": "Simple", "piel": "Intensive", "pual": "Intensive",
                      "hitpael": "Intensive", "polel": "Intensive", "hifil": "Causative", "hofal": "Causative"}
LINK_KINDS = ("participle", "passive", "middle", "inflected")
STATUSES = ("auto", "proposed", "paper_variant")
DECISIONS = ("accept", "reject")
FUNCTION_CLASSES = ("EXISTENTIAL", "COPULA", "MODAL_IMPERSONAL")

#: tense category of a VERB token (Dicta predicts Tense, Person, Gender, Number only)
TCAT_SQL = ("CASE WHEN tense IN ('Past', 'Fut', 'Imp') THEN 'FIN' "
            "WHEN tense = 'Pres' OR (person IS NULL AND (gender IS NOT NULL OR number IS NOT NULL)) THEN 'PRES' "
            "WHEN gender IS NULL AND number IS NULL AND person IS NULL THEN 'NOFEAT' ELSE 'OTHER' END")
TCATS = ("FIN", "PRES", "NOFEAT", "OTHER")
INVENTORY_T_SCHEMA = pa.schema([("lemma", pa.string()), ("host", pa.string()), ("tcat", pa.string()), ("n", pa.int64())])
AUX_SCHEMA = pa.schema([("lemma", pa.string()), ("has_do", pa.bool_()), ("has_bm_pp", pa.bool_()), ("n", pa.int64())])


class UnitsError(Exception):
    """The unit map or a review file is invalid (a STOP condition)."""


# ============================================================================================ lemma shapes
@dataclass(frozen=True)
class Analysis:
    """One reading of a lemma string: it would belong to the verb ``base`` (a citation lemma)."""
    kind: str          # participle | passive | middle | polel
    binyan: str        # binyan of the variant string
    base: str          # citation lemma of the verb it would belong to
    base_binyan: str
    template: str      # template of the unit (never crosses templates)
    rule: str


def hitpael_root(s: str) -> str | None:
    """Root letters of a hitpa'el citation (התלבש, הסתכל, הצטרף, הזדקן), non-final letters; None if not one."""
    s = morph.nonfinal(s)
    if len(s) < 5:
        return None
    if s.startswith("הת"):
        r = s[2:]
    elif s[:3] in ("הסת", "השת"):
        r = s[1] + s[3:]
    elif s[:3] == "הצט":
        r = "צ" + s[3:]
    elif s[:3] == "הזד":
        r = "ז" + s[3:]
    else:
        return None
    if len(r) == 3 and r[1] == "י":       # a hif'il הCCיC whose first radical is ת (התחיל), not a hitpa'el
        return None
    return r


def binyan_of_h(s: str) -> str:
    """Binyan of an ה-initial citation: hitpa'el, hof'al (הו + no י) or hif'il (incl. I-yod הוציא)."""
    s = morph.nonfinal(s)
    if hitpael_root(s):
        return "hitpael"
    if s.startswith("הו") and "י" not in s[2:]:
        return "hofal"
    return "hifil"


def _piel_from_root(r: str) -> str:
    """Pi'el citation of root letters (plene MH spelling): גלח -> גילח; גייס (already plene) and quadriliterals stay."""
    if len(r) >= 4 or (len(r) >= 2 and "י" in r[1:3]):
        return r
    return r[0] + "י" + r[1:]


def analyses(v: str) -> list[Analysis]:
    """Every reading of the lemma string ``v`` as a form of another citation lemma (the paradigm table of P2/P3).

    Same-binyan participles (``participle``) are candidates for automatic links; ``passive`` / ``middle`` readings and
    ``polel`` (always reviewed) are never automatic. Bases are returned with final letters; unattested bases are
    filtered by the caller."""
    s = morph.nonfinal(v or "")
    n = len(s)
    out: list[Analysis] = []

    def add(kind: str, binyan: str, base: str, base_binyan: str, rule: str) -> None:
        if len(base) < 2:
            return
        b = morph.finalize(base)
        if b != v:
            out.append(Analysis(kind, binyan, b, base_binyan, TEMPLATE_OF_BINYAN[base_binyan], rule))

    if n == 4 and s[1] == "ו":
        add("participle", "qal", s[0] + s[2:], "qal", "qal_participle:CוCC")      # שולח <- שלח; רואה <- ראה; מוכר <- מכר
        add("passive", "pual", s[0] + "י" + s[2:], "piel", "pual:CוCC")           # שולח <- שילח (a pu'al past)
        if s[2] == s[3]:                                                         # סובב, כונן, רומם: po'el / polel
            out.append(Analysis("polel", "polel", v, "polel", "Intensive", "polel:CוCC"))
    if n >= 4 and s[0] == "מ":
        x = s[1:]
        hx = "ה" + x
        add("participle", binyan_of_h(hx), hx, binyan_of_h(hx), "participle:מX<-הX")   # מכניס, מקים, מוציא, מתלבש
        if x[0] != "ו":
            if len(x) >= 4 and x[1:3] == "יי":
                add("participle", "piel", x, "piel", "piel_participle:מCייC<-CייC")     # מקיים <- קיים; מגייס <- גייס
            elif not (len(x) == 3 and x[1] == "י"):     # MH spells a hollow pi'el with יי (מקיים): מקים/מגיע are hif'il only
                add("participle", "piel", x[0] + "י" + x[1:], "piel", "piel_participle:מCX<-CיX")  # מקבל, מנסה, מצווה
            if len(x) == 4 and "י" not in x[:2] and x[1] != "ו":
                add("participle", "piel", x, "piel", "quadriliteral_participle:מCCCC")   # מתרגם <- תרגם
        if len(x) == 4 and x[1] == "ו":
            add("passive", "pual", x[0] + "י" + x[2:], "piel", "pual_participle:מCוCC")   # מסודר <- סידר
        if x[0] == "ו" and len(x) >= 3:
            y = x[1:]
            add("passive", "hofal", "ה" + y[:-1] + "י" + y[-1], "hifil", "hofal_participle:מוX")      # מושלך <- השליך
            add("passive", "hofal", "הו" + y[:-1] + "י" + y[-1], "hifil", "hofal_participle:מוX(I-y)")  # מוצא <- הוציא
    if n == 4 and s[0] == "נ" and s[1] != "י":
        add("passive", "nifal", s[1:], "qal", "nifal:נCCC")                         # נשלח <- שלח
        if s[1] == "ו":
            add("passive", "nifal", "י" + s[2:], "qal", "nifal:נוCC(I-y)")         # נולד <- ילד
    if n >= 4 and s.startswith("הו"):
        y = s[2:]
        add("passive", "hofal", "ה" + y[:-1] + "י" + y[-1], "hifil", "hofal:הוX")             # הושלך <- השליך; הובא <- הביא
        add("passive", "hofal", "הו" + y[:-1] + "י" + y[-1], "hifil", "hofal:הוX(I-y)")       # הוצא <- הוציא
    r = hitpael_root(s)
    if r and len(r) in (3, 4):
        add("middle", "hitpael", _piel_from_root(r), "piel", "hitpael:התR")         # התפזר <- פיזר
    # one analysis per (kind, base): the same base can be reached by two spellings of one rule
    seen, uniq = set(), []
    for a in out:
        if (a.kind, a.base) not in seen:
            seen.add((a.kind, a.base))
            uniq.append(a)
    return uniq


def template_by_shape(v: str) -> str:
    """Template proxy of a lemma from its shape alone; 'unknown' when two templates are possible (S56-v1 §5.9)."""
    s = morph.nonfinal(v or "")
    if not s or "#" in s or s == "[BLANK]":
        return "unknown"
    if len(s) == 4 and s[1] == "ו":                 # CוCC: a qal participle or a pu'al past (הולך, שולח)
        return "unknown"
    if s[0] == "ה" and len(s) >= 4:
        return TEMPLATE_OF_BINYAN[binyan_of_h(s)]
    if len(s) == 3 or (len(s) == 2):
        return "Simple"
    if len(s) == 4 and s[0] == "נ" and s[1] != "י":
        return "Simple"
    if len(s) >= 4 and s[1] == "י":
        return "Intensive"
    return "unknown"


def voice_by_shape(v: str) -> str:
    """Voice from the shape alone, only where morphology is unambiguous: a hof'al citation (הושלך) or a hof'al
    participle (מושלך) is passive. The other passive-looking shapes (nif'al, pu'al, hitpa'el; CוCC, which is also a
    qal participle) are often active or middle verbs, so they stay 'unknown'; everything else is 'active'."""
    s = morph.nonfinal(v or "")
    if not s or "#" in s or s == "[BLANK]":
        return "unknown"
    if len(s) == 4 and s[1] == "ו":
        return "unknown"
    if s[0] == "ה" and len(s) >= 4:
        b = binyan_of_h(s)
        return {"hofal": "passive", "hitpael": "unknown"}.get(b, "active")
    if s[0] == "מ" and len(s) >= 4:
        b = binyan_of_h("ה" + s[1:])
        if b == "hofal" and len(s) >= 5:
            return "passive"
        if b == "hitpael" or (len(s) == 5 and s[2] == "ו"):
            return "unknown"
        return "active"
    if len(s) == 4 and s[0] == "נ" and s[1] != "י":
        return "unknown"
    return "active"


# ============================================================================================ inventory
def _aux_sql(tokens: str) -> str:
    """AUX tokens of ``tokens`` with whether they have a DO and a ב/מ-family PP (the §6 frame), by lemma."""
    return f"""
    WITH v AS (SELECT sent_id, piece_idx, word_idx, lemma, suffix, 'unknown' AS voice FROM {tokens} WHERE upos = 'AUX'),
    a AS ({TR.arguments_sql('v', tokens)}),
    f AS (SELECT sent_id, piece_idx, verb_word_idx AS word_idx, bool_or(slot = 'DO') AS has_do,
                 bool_or(p_family IN ('B', 'MIN')) AS has_bm_pp FROM a GROUP BY ALL)
    SELECT v.lemma, coalesce(f.has_do, false) AS has_do, coalesce(f.has_bm_pp, false) AS has_bm_pp, count(*)::BIGINT AS n
    FROM v LEFT JOIN f USING (sent_id, piece_idx, word_idx) GROUP BY ALL"""


def build_inventory_t(corpus: str, source: Source, out_dir: Path = INVENTORY_T_DIR, *, progress: bool = True) -> dict:
    """Tense-aware verb inventory ``<corpus>.parquet`` (lemma, host, tcat, n) of every VERB token (same scope as R1's
    ``data/loc/inventory``, which is never touched) and the AUX coverage ``<corpus>_aux.parquet``."""
    cols = ("sent_id", "piece_idx", "word_idx", "form", "host", "lemma", "upos", "tense", "gender", "number", "person",
            "prefix", "prefix_upos", "suffix", "head", "deprel")
    con = connect()
    inv_parts, aux_parts = [], []
    for run in source.runs(corpus):
        if progress:
            print(f"  inventory_t {corpus}: {run.run_id}", flush=True)
        con.execute(f"CREATE OR REPLACE TEMP TABLE t AS SELECT * FROM {source.tokens_sql(run, cols)}")
        inv_parts.append(con.sql(f"SELECT lemma, host, {TCAT_SQL} AS tcat, count(*)::BIGINT AS n FROM t "
                                 "WHERE upos = 'VERB' GROUP BY ALL").to_arrow_table())
        aux_parts.append(con.sql(_aux_sql("t")).to_arrow_table())
    con.register("inv_in", pa.concat_tables(inv_parts))
    con.register("aux_in", pa.concat_tables(aux_parts))
    inv = con.sql("SELECT lemma, host, tcat, sum(n)::BIGINT AS n FROM inv_in GROUP BY ALL").to_arrow_table().cast(INVENTORY_T_SCHEMA)
    aux = con.sql("SELECT lemma, has_do, has_bm_pp, sum(n)::BIGINT AS n FROM aux_in GROUP BY ALL").to_arrow_table().cast(AUX_SCHEMA)
    inv = inv.sort_by([("lemma", "ascending"), ("host", "ascending"), ("tcat", "ascending")])
    aux = aux.sort_by([("lemma", "ascending"), ("has_do", "ascending"), ("has_bm_pp", "ascending")])
    out_dir = Path(out_dir)
    atomic_write_parquet(inv, out_dir / f"{corpus}.parquet")
    atomic_write_parquet(aux, out_dir / f"{corpus}_aux.parquet")
    return {"corpus": corpus, "rows": inv.num_rows, "verb_tokens": int(pc.sum(inv["n"]).as_py() or 0),
            "aux_tokens": int(pc.sum(aux["n"]).as_py() or 0)}


def load_inventory_t(corpora: list[str] | None = None, root: Path = INVENTORY_T_DIR) -> pa.Table:
    """The tense-aware inventories present (or of ``corpora``), with a ``corpus`` column."""
    import pyarrow.parquet as pq

    tabs = []
    for f in sorted(Path(root).glob("*.parquet")):
        if f.stem.endswith("_aux") or (corpora and f.stem not in corpora):
            continue
        t = pq.read_table(f)
        tabs.append(t.append_column("corpus", pa.array([f.stem] * len(t), pa.string())))
    if not tabs:
        raise UnitsError(f"no tense-aware inventory under {root} (run: hebloc loc units inventory)")
    return pa.concat_tables(tabs)


def inventory_matches_r1(corpus: str, root_t: Path = INVENTORY_T_DIR, root_r1: Path | None = None) -> bool:
    """The tense-aware inventory, summed over tcat, equals R1's inventory row for row (same scope, nothing lost)."""
    from hebloc.loc.inventory import INVENTORY_DIR

    con = connect()
    a = Path(root_t) / f"{corpus}.parquet"
    b = Path(root_r1 or INVENTORY_DIR) / f"{corpus}.parquet"
    diff = con.sql(f"""
        WITH x AS (SELECT lemma, host, sum(n)::BIGINT AS n FROM read_parquet('{a.as_posix()}') GROUP BY ALL),
             y AS (SELECT lemma, host, n FROM read_parquet('{b.as_posix()}'))
        SELECT count(*) FROM (SELECT * FROM x EXCEPT ALL SELECT * FROM y UNION ALL SELECT * FROM (SELECT * FROM y EXCEPT ALL SELECT * FROM x))""")
    return diff.fetchall()[0][0] == 0


# ============================================================================================ links
@dataclass
class LemmaStats:
    n: int = 0
    fin: int = 0
    pres: int = 0
    by_corpus: dict = field(default_factory=dict)

    @property
    def fin_share(self) -> float:
        return self.fin / self.n if self.n else 0.0

    @property
    def pres_share(self) -> float:
        return self.pres / self.n if self.n else 0.0


def lemma_stats(inv: pa.Table) -> dict[str, LemmaStats]:
    st: dict[str, LemmaStats] = defaultdict(LemmaStats)
    for lem, tcat, n, corpus in zip(inv["lemma"].to_pylist(), inv["tcat"].to_pylist(), inv["n"].to_pylist(),
                                    inv["corpus"].to_pylist()):
        if not lem or lem == "[BLANK]":
            continue
        s = st[lem]
        s.n += n
        s.fin += n if tcat == "FIN" else 0
        s.pres += n if tcat == "PRES" else 0
        s.by_corpus[corpus] = s.by_corpus.get(corpus, 0) + n
    return dict(st)


def lexicon_lemmas(lex: Lexicon) -> dict[str, list[str]]:
    """Lemma -> the lexicon entries that own it (own or shared lemmas); these are never in the unit map."""
    out: dict[str, list[str]] = defaultdict(list)
    for e in lex.entries:
        for lem in sorted(e.own_lemmas | set(e.shared)):
            out[lem].append(e.id)
    return dict(out)


def _inflected_candidate(v: str, hosts_of: dict, host_lemmas: dict, finite: set[str]) -> tuple[str, float] | None:
    """Host evidence for an inflected lemma string: the finite lemma that shares the most of ``v``'s host tokens."""
    total = sum(hosts_of[v].values())
    if not total:
        return None
    share: dict[str, int] = defaultdict(int)
    for h, n in hosts_of[v].items():
        for f in host_lemmas.get(h, ()):
            if f != v and f in finite:
                share[f] += n
    if not share:
        return None
    best = sorted(share.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(best) > 1 and best[0][1] == best[1][1]:
        return None
    return best[0][0], best[0][1] / total


HEBREW_WORD = re.compile(r"^[א-ת]+$")


def build_links(lex: Lexicon, inv: pa.Table, function_lemmas: set[str] | frozenset = frozenset()) -> dict:
    """Classify every lemma (>= LINK_MIN_TOKENS pooled) by P2/P3/P5: ``auto``, ``proposed`` (review),
    ``paper_variant`` (Ori, lexicon-v2), or nothing (its own unit). Returns ``{links, stats, counts}``.

    Safeguards: only Hebrew-letter lemmas are linked (Dicta's ``##`` sub-word strings stay their own units); a link
    needs at least one attested candidate base; a FUNCTION-PREDICATE lemma (listed or pending, P6) is never an
    automatic base, because its string is shared by a function use and a lexical verb (אפשר 'possible' / 'enable')."""
    st = lemma_stats(inv)
    lexl = lexicon_lemmas(lex)
    established = {lem for lem, s in st.items() if s.n >= LINK_MIN_TOKENS and HEBREW_WORD.match(lem)}
    finite = {lem for lem in established if st[lem].fin_share >= BASE_MIN_FIN_SHARE}
    hosts_of: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    host_lemmas: dict[str, set[str]] = defaultdict(set)
    for lem, host, n in zip(inv["lemma"].to_pylist(), inv["host"].to_pylist(), inv["n"].to_pylist()):
        if lem and host and lem != "[BLANK]":
            hosts_of[lem][host] += n
            host_lemmas[host].add(lem)
    links: dict[str, dict] = {}
    for v in sorted(established):
        if v in lexl:
            continue
        s = st[v]
        all_a = analyses(v)
        polel = any(a.kind == "polel" for a in all_a)
        cands = [a for a in all_a if a.kind != "polel" and a.base in established and a.base != v
                 and (a.kind != "participle" or a.base in finite)]
        ev = {"n": s.n, "pres": round(s.pres_share, 3), "fin": round(s.fin_share, 3),
              "by_corpus": {k: s.by_corpus[k] for k in sorted(s.by_corpus)}}
        cand_rows = [{"base": a.base, "kind": a.kind, "binyan": a.binyan, "template": a.template, "rule": a.rule,
                      "base_n": st[a.base].n, "base_fin": round(st[a.base].fin_share, 3),
                      **({"paper_entries": lexl[a.base]} if a.base in lexl else {})} for a in cands]
        if not cands:
            if polel:
                continue                                  # a po'el / polel with no attested base: its own unit
            if v.endswith(INFLECTED_ENDINGS) or (v[:1] in ("ו", "ש") and v[1:] in established):
                ic = _inflected_candidate(v, hosts_of, host_lemmas, finite)
                if ic and ic[1] >= INFLECTED_MIN_HOST_SHARE:
                    f, sh = ic
                    row = {"base": f, "kind": "inflected", "binyan": "?", "template": template_by_shape(f),
                           "rule": f"host_share:{sh:.2f}", "base_n": st[f].n, "base_fin": round(st[f].fin_share, 3),
                           **({"paper_entries": lexl[f]} if f in lexl else {})}
                    links[v] = {"status": "paper_variant" if f in lexl else "proposed", "candidates": [row], **ev}
            continue
        if any(a.base in lexl for a in cands):
            links[v] = {"status": "paper_variant", "candidates": cand_rows, **ev, **({"polel": True} if polel else {})}
            continue
        if (len(cands) == 1 and cands[0].kind == "participle" and not polel and cands[0].base not in function_lemmas
                and s.pres_share >= VARIANT_MIN_PRES_SHARE and s.fin_share <= VARIANT_MAX_FIN_SHARE):
            a = cands[0]
            links[v] = {"status": "auto", "base": a.base, "kind": "participle", "rule": a.rule, "template": a.template,
                        "base_n": st[a.base].n, "base_fin": round(st[a.base].fin_share, 3), **ev}
            continue
        links[v] = {"status": "proposed", "candidates": cand_rows, **ev, **({"polel": True} if polel else {})}
    counts = defaultdict(int)
    for x in links.values():
        counts[x["status"]] += 1
    return {"links": links, "stats": st, "counts": dict(counts), "n_established": len(established), "n_finite": len(finite)}


# ============================================================================================ the map file
def _flow(d) -> str:
    """One-line YAML: a quoted scalar, or a flow mapping / sequence."""
    if isinstance(d, str):
        import json

        return json.dumps(d, ensure_ascii=False)
    return yaml.safe_dump(d, allow_unicode=True, default_flow_style=True, width=10_000, sort_keys=False).strip()


def write_map(built: dict, lex: Lexicon, inventory_info: dict, path: Path = UNITS_PATH) -> dict:
    """Write ``config/verb_units.yaml`` (Ori only): the generated links + the reviewed decisions and audit kept."""
    old = load_raw(path)
    reviewed = old.get("reviewed") or {}
    audit = old.get("audit") or {"status": "pending", "n": AUDIT_N, "min_correct": AUDIT_MIN_CORRECT}
    stale = sorted(k for k in reviewed if k not in built["links"])
    meta = {"methodology": METHODOLOGY, "version": UNITS_VERSION, "decision": "D-059",
            "lexicon_sha256": lex.sha256, "inventory": inventory_info,
            "thresholds": {"link_min_tokens": LINK_MIN_TOKENS, "base_min_fin_share": BASE_MIN_FIN_SHARE,
                           "variant_min_pres_share": VARIANT_MIN_PRES_SHARE, "variant_max_fin_share": VARIANT_MAX_FIN_SHARE,
                           "inflected_min_host_share": INFLECTED_MIN_HOST_SHARE, "audit_n": AUDIT_N,
                           "audit_min_correct": AUDIT_MIN_CORRECT},
            "counts": built["counts"], "n_established_lemmas": built["n_established"],
            "stale_reviewed": stale}
    lines = ["# Verb units of S56-v1 (policy vunit-v1, D-059). GENERATED by `hebloc loc units build` (Ori only);",
             "# `reviewed` holds the human decisions (`hebloc loc units merge`) and `audit` the pre-registered audit.",
             "# A lemma that is not listed here is its own unit. Paper verbs are never listed: the lexicon decides them.",
             "meta: " + _flow(meta), "audit: " + _flow(audit), "links:"]
    for v in sorted(built["links"]):
        lines.append(f"  {_flow(v)}: {_flow(built['links'][v])}")
    lines.append("reviewed:" + ("" if reviewed else " {}"))
    for v in sorted(reviewed):
        lines.append(f"  {_flow(v)}: {_flow(reviewed[v])}")
    atomic_write_text("\n".join(lines) + "\n", path)
    return meta


def load_raw(path: Path = UNITS_PATH) -> dict:
    if not Path(path).exists():
        return {}
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


@dataclass
class UnitMap:
    """The links in force. ``unit_of(lemma)`` -> the unit's citation lemma (itself when unlinked)."""
    links: dict[str, dict]
    reviewed: dict[str, dict]
    audit: dict
    sha256: str | None
    allow_unaudited: bool = False
    _cache: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path = UNITS_PATH, *, allow_unaudited: bool = False) -> "UnitMap":
        raw = load_raw(path)
        sha = file_sha256(Path(path)) if Path(path).exists() else None
        return cls(raw.get("links") or {}, raw.get("reviewed") or {}, raw.get("audit") or {"status": "absent"}, sha,
                   allow_unaudited)

    @property
    def auto_in_force(self) -> bool:
        return self.audit.get("status") == "passed" or (self.allow_unaudited and self.audit.get("status") == "pending")

    def link(self, lemma: str) -> dict | None:
        """The link in force for ``lemma``: ``{base, kind, how}`` (how = auto | reviewed), or None."""
        r = self.reviewed.get(lemma)
        if r is not None:
            return {"base": r["base"], "kind": r.get("kind", "reviewed"), "how": "reviewed"} if r.get("decision") == "accept" else None
        x = self.links.get(lemma)
        if x and x.get("status") == "auto" and self.auto_in_force:
            return {"base": x["base"], "kind": "participle", "how": "auto"}
        return None

    def unit_of(self, lemma: str) -> str:
        if lemma in self._cache:
            return self._cache[lemma]
        seen, cur = [lemma], lemma
        while True:
            lk = self.link(cur)
            if lk is None or lk["base"] in seen or len(seen) > 8:
                break
            cur = lk["base"]
            seen.append(cur)
        self._cache[lemma] = cur
        return cur

    def status(self, lemma: str) -> str:
        """own | auto | reviewed | auto_inactive (an automatic link not in force: audit pending / failed)."""
        lk = self.link(lemma)
        if lk is not None:
            return lk["how"]
        x = self.links.get(lemma)
        if x and x.get("status") == "auto":
            return "auto_inactive"
        return "own"

    def voice(self, lemma: str) -> str:
        """Voice of a non-lexicon lemma: an accepted passive / middle link, else the shape of its unit's base."""
        lk = self.link(lemma)
        if lk is not None and lk["kind"] in ("passive", "middle"):
            return lk["kind"]
        return voice_by_shape(self.unit_of(lemma))

    def template(self, lemma: str) -> str:
        lk = self.link(lemma)
        if lk is not None:
            r = self.reviewed.get(lemma) or self.links.get(lemma) or {}
            t = r.get("template")
            if t:
                return t
        return template_by_shape(self.unit_of(lemma))

    def table(self) -> pa.Table:
        """The links in force as a table (lemma, unit_lemma, link_status, voice, template) for SQL joins."""
        lem = sorted(set(self.links) | set(self.reviewed))
        rows = [(v, self.unit_of(v), self.status(v), self.voice(v), self.template(v)) for v in lem]
        return pa.table({"lemma": [r[0] for r in rows], "unit_lemma": [r[1] for r in rows], "link_status": [r[2] for r in rows],
                         "map_voice": [r[3] for r in rows], "map_template": [r[4] for r in rows]},
                        schema=pa.schema([("lemma", pa.string()), ("unit_lemma", pa.string()), ("link_status", pa.string()),
                                          ("map_voice", pa.string()), ("map_template", pa.string())]))

    def describe(self) -> dict:
        return {"version": UNITS_VERSION, "units_sha256": self.sha256, "audit": self.audit.get("status"),
                "auto_links_in_force": self.auto_in_force, "allow_unaudited": self.allow_unaudited,
                "n_reviewed_accept": sum(1 for r in self.reviewed.values() if r.get("decision") == "accept")}


# ============================================================================================ review sheets
REVIEW_COLUMNS = ("lemma", "candidates", "n", "pres_share", "fin_share", "n_by_corpus", "planned_reviewer",
                  "proposed_decision", "proposed_base", "proposed_by", "decision", "base", "reviewed_by", "note", "example_ids")
AUDIT_COLUMNS = ("lemma", "base", "rule", "n", "pres_share", "fin_share", "example_ids", "correct", "reviewed_by", "note")


def _cand_text(c: list[dict]) -> str:
    return " ; ".join(f"{x['base']} ({x['kind']}, {x['template']}, {x['rule']}, n={x['base_n']})" for x in c)


def planned_reviewer(by_corpus: dict) -> str:
    """Efrat reviews the Modern rows, Ori the historical-only rows (D-059, A7)."""
    return "efrat" if by_corpus.get("modern", 0) >= LINK_MIN_TOKENS else "ori"


def audit_sample(links: dict) -> list[str]:
    """The pre-registered audit: AUDIT_N automatic links, the first by sha256(AUDIT_SALT + lemma)."""
    auto = [v for v, x in links.items() if x.get("status") == "auto"]
    return sorted(auto, key=lambda v: hashlib.sha256((AUDIT_SALT + v).encode()).hexdigest())[:AUDIT_N]


def _write_rows(path: Path, header: tuple[str, ...], rows: list[dict]) -> None:
    import io

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(header), lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    atomic_write_text("﻿" + buf.getvalue(), path)


def write_review(path_map: Path = UNITS_PATH, out_dir: Path = REVIEW_DIR, examples: dict | None = None,
                 min_tokens: int = LINK_MIN_TOKENS) -> dict:
    """Review sheets (local; ids only except the optional examples sheet):
    ``unit_review.csv`` (proposed links, P3), ``paper_variants.csv`` (P5, Ori), ``audit.csv`` (the 100-link audit)."""
    raw = load_raw(path_map)
    links = raw.get("links") or {}
    ex = examples or {}
    rows, pv = [], []
    for v in sorted(links, key=lambda k: (-links[k]["n"], k)):
        x = links[v]
        if x["status"] == "auto" or x["n"] < min_tokens:
            continue
        r = {"lemma": v, "candidates": _cand_text(x["candidates"]), "n": x["n"], "pres_share": x["pres"],
             "fin_share": x["fin"], "n_by_corpus": "; ".join(f"{k}={n}" for k, n in x["by_corpus"].items()),
             "planned_reviewer": "ori" if x["status"] == "paper_variant" else planned_reviewer(x["by_corpus"]),
             "example_ids": "; ".join(ex.get(v, [])[:3])}
        (pv if x["status"] == "paper_variant" else rows).append(r)
    au = []
    for v in audit_sample(links):
        x = links[v]
        au.append({"lemma": v, "base": x["base"], "rule": x["rule"], "n": x["n"], "pres_share": x["pres"],
                   "fin_share": x["fin"], "example_ids": "; ".join(ex.get(v, [])[:3])})
    out_dir = Path(out_dir)
    _write_rows(out_dir / "unit_review.csv", REVIEW_COLUMNS, rows)
    _write_rows(out_dir / "paper_variants.csv", REVIEW_COLUMNS, pv)
    _write_rows(out_dir / "audit.csv", AUDIT_COLUMNS, au)
    by_rev = defaultdict(int)
    for r in rows:
        by_rev[r["planned_reviewer"]] += 1
    return {"unit_review": len(rows), "by_reviewer": dict(by_rev), "paper_variants": len(pv), "audit": len(au),
            "cut_needed": len(rows) > REVIEW_CUT_WARN, "min_tokens": min_tokens, "out_dir": str(out_dir)}


def review_examples(lemmas: set[str], source: Source, corpora: list[str], *, per_lemma: int = 3, progress: bool = True) -> tuple[dict, list[dict]]:
    """Up to ``per_lemma`` example instances per lemma (first by hash), with their sentences for the LOCAL sheet."""
    con = connect()
    con.register("want", pa.table({"lemma": sorted(lemmas)}))
    picks = []
    for corpus in corpora:
        for run in source.runs(corpus):
            if progress:
                print(f"  examples {corpus}: {run.run_id}", flush=True)
            picks.append(con.sql(f"""SELECT * FROM (SELECT t.lemma, t.sent_id, t.piece_idx, t.word_idx, t.surface, '{corpus}' AS corpus,
                     row_number() OVER (PARTITION BY t.lemma ORDER BY sha256('{AUDIT_SALT}ex:' || t.sent_id || '|' || t.piece_idx || '|' || t.word_idx)) AS r
                     FROM {source.tokens_sql(run, ('sent_id', 'piece_idx', 'word_idx', 'surface', 'lemma', 'upos'))} t
                     SEMI JOIN want w ON w.lemma = t.lemma WHERE t.upos = 'VERB') WHERE r <= {per_lemma}""").to_arrow_table())
    if not picks:
        return {}, []
    con.register("p", pa.concat_tables(picks))
    best = con.sql(f"""SELECT * FROM (SELECT *, row_number() OVER (PARTITION BY lemma ORDER BY sha256('{AUDIT_SALT}ex2:' || sent_id || '|' || piece_idx || '|' || word_idx)) AS q FROM p)
                      WHERE q <= {per_lemma} ORDER BY lemma, q""").to_arrow_table().to_pylist()
    ids: dict[str, list[str]] = defaultdict(list)
    for b in best:
        ids[b["lemma"]].append(f"{b['sent_id']}|{b['piece_idx']}|{b['word_idx']}")
    sentences = []
    by_corpus = defaultdict(list)
    for b in best:
        by_corpus[b["corpus"]].append(b)
    for corpus, bs in by_corpus.items():
        con.register("s", pa.table({"sent_id": sorted({b["sent_id"] for b in bs})}))
        text = dict(con.sql(f"SELECT sent_id, text_norm FROM {source.units_sql(corpus, ('sent_id', 'text_norm'))} SEMI JOIN s USING (sent_id)").fetchall())
        for b in bs:
            sentences.append({"lemma": b["lemma"], "instance_key": f"{b['sent_id']}|{b['piece_idx']}|{b['word_idx']}",
                              "corpus": corpus, "target": b["surface"], "sentence": text.get(b["sent_id"], "")})
    return dict(ids), sorted(sentences, key=lambda r: (r["lemma"], r["instance_key"]))


def merge_review(reviewed: Path, path: Path = UNITS_PATH, *, automated: Path | None = None) -> dict:
    """Merge a reviewed ``unit_review.csv`` into the ``reviewed`` section of the unit map (Ori only).

    Every row with a decision must name a HUMAN reviewer, or (D-061, ``automated`` = the frozen SILVER unit job
    folder) be that job's frozen final file with ``reviewed_by = auto-qc:<qc_id>``. ``accept`` must name one of the
    row's candidate bases (its kind and template come from that candidate, so an accepted link never crosses
    templates)."""
    raw = load_raw(path)
    links = raw.get("links") or {}
    with open(reviewed, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("decision") or "").strip()]
    probs, new = [], {}
    if automated is not None:
        from hebloc.loc.silver import check_automated

        _, probs = check_automated(Path(reviewed), Path(automated))
    for i, r in enumerate(rows, 2):
        v = (r.get("lemma") or "").strip()
        d = r["decision"].strip()
        w = f"line {i} ({v}):"
        if v not in links or links[v].get("status") not in ("proposed",):
            probs.append(f"{w} not a proposed link of the current map")
            continue
        if d not in DECISIONS:
            probs.append(f"{w} decision must be accept or reject")
        rb = (r.get("reviewed_by") or "").strip()
        if automated is None and (not rb or rb.lower() in ("claude_code", "claude") or rb.startswith("auto-qc:")):
            probs.append(f"{w} reviewed_by must name the human reviewer (automated SILVER links need --automated <job folder>)")
        pb = (r.get("proposed_by") or "human").strip() or "human"
        if pb not in ("human", "claude_code"):
            probs.append(f"{w} proposed_by must be human or claude_code")
        base = (r.get("base") or "").strip()
        cand = {c["base"]: c for c in links[v].get("candidates") or []}
        if d == "accept" and base not in cand:
            probs.append(f"{w} accept must name one of the candidate bases {sorted(cand)}")
            continue
        new[v] = {"decision": d, **({"base": base, "kind": cand[base]["kind"], "template": cand[base]["template"]} if d == "accept" else {}),
                  "proposed_by": pb, "reviewed_by": rb, **({"review_mode": "automated"} if automated is not None else {}),
                  "note": (r.get("note") or "").strip()}
    if probs:
        return {"ok": False, "problems": probs}
    reviewed_all = {**(raw.get("reviewed") or {}), **new}
    text = Path(path).read_text(encoding="utf-8")
    head = text.split("\nreviewed:", 1)[0]
    lines = [head, "reviewed:" + ("" if reviewed_all else " {}")]
    for v in sorted(reviewed_all):
        lines.append(f"  {_flow(v)}: {_flow(reviewed_all[v])}")
    atomic_write_text("\n".join(lines) + "\n", path)
    return {"ok": True, "merged": len(new), "total_reviewed": len(reviewed_all),
            "accepted": sum(1 for r in reviewed_all.values() if r["decision"] == "accept")}


def record_audit(audit_csv: Path, path: Path = UNITS_PATH, *, automated: Path | None = None) -> dict:
    """Score the filled audit sheet (pre-registered: >= AUDIT_MIN_CORRECT of AUDIT_N correct) and record it (Ori only).
    With ``automated`` (D-061: the frozen SILVER audit job folder) it is recorded as an AI AUDIT, not validation."""
    raw = load_raw(path)
    expected = set(audit_sample(raw.get("links") or {}))
    with open(audit_csv, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    got = {r["lemma"]: r for r in rows}
    probs = []
    if automated is not None:
        from hebloc.loc.silver import check_automated

        _, probs = check_automated(Path(audit_csv), Path(automated))
    if set(got) != expected:
        probs.append(f"the audit sheet must hold exactly the {len(expected)} pre-registered links (missing "
                     f"{len(expected - set(got))}, extra {len(set(got) - expected)})")
    for v, r in got.items():
        if (r.get("correct") or "").strip() not in ("Y", "N"):
            probs.append(f"{v}: correct must be Y or N")
        rb = (r.get("reviewed_by") or "").strip()
        if automated is None and (not rb or rb.lower() in ("claude_code", "claude") or rb.startswith("auto-qc:")):
            probs.append(f"{v}: reviewed_by must name the human reviewer (an AI audit needs --automated <job folder>)")
    if probs:
        return {"ok": False, "problems": probs}
    correct = sum(1 for r in got.values() if r["correct"].strip() == "Y")
    audit = {"status": "passed" if correct >= AUDIT_MIN_CORRECT else "failed", "n": len(got), "correct": correct,
             "min_correct": AUDIT_MIN_CORRECT, "reviewed_by": sorted({r["reviewed_by"].strip() for r in got.values()}),
             "sheet_sha256": file_sha256(Path(audit_csv)),
             "mode": "automated (AI audit, SILVER; D-061)" if automated is not None else "human"}
    text = Path(path).read_text(encoding="utf-8")
    out = []
    for line in text.splitlines():
        out.append("audit: " + _flow(audit) if line.startswith("audit:") else line)
    atomic_write_text("\n".join(out) + "\n", path)
    return {"ok": True, **audit}


# ============================================================================================ function predicates
@dataclass
class FunctionList:
    classes: dict[str, str]          # lemma -> class (only the listed, decided lemmas)
    pending: list[dict]
    status: str
    sha256: str | None

    @classmethod
    def load(cls, path: Path = FUNCTION_PATH) -> "FunctionList":
        if not Path(path).exists():
            return cls({}, [], "absent", None)
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        classes = {}
        for k, lemmas in (raw.get("classes") or {}).items():
            if k not in FUNCTION_CLASSES:
                raise UnitsError(f"{path}: unknown function class {k!r} (allowed: {FUNCTION_CLASSES})")
            for lem in lemmas or []:
                if lem in classes:
                    raise UnitsError(f"{path}: {lem} is listed twice")
                classes[lem] = k
        # lemmas decided NOT to tag (STOP-B) are kept with the pending ones for the unit-link safeguard only
        held = (raw.get("pending") or []) + [{**x, "not_listed": True} for x in raw.get("not_listed") or []]
        return cls(classes, held, (raw.get("meta") or {}).get("status", "unknown"), file_sha256(Path(path)))

    def table(self) -> pa.Table:
        lem = sorted(self.classes)
        return pa.table({"lemma": lem, "function_class": [self.classes[x] for x in lem]},
                        schema=pa.schema([("lemma", pa.string()), ("function_class", pa.string())]))

    def describe(self) -> dict:
        return {"function_sha256": self.sha256, "status": self.status, "n_listed": len(self.classes),
                "pending": [p.get("lemma") for p in self.pending if not p.get("not_listed")],
                "not_listed": [p.get("lemma") for p in self.pending if p.get("not_listed")]}

    def all_lemmas(self) -> set[str]:
        """Listed, pending and not-listed lemmas (for the unit-link safeguard: never an automatic base)."""
        return set(self.classes) | {p.get("lemma") for p in self.pending if p.get("lemma")}
