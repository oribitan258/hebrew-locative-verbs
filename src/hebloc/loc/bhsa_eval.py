"""Identification measured against BHSA on Mikra, ONCE, with a pre-registered decision rule (R1 correction, D-057).

BHSA (ETCBC, CC BY-NC; ``data/external/bhsa``) is independent of Dicta and of the lexicon: it is never used to choose
Dicta lemmas, forms or flags. It only measures. Truth for an entry = a BHSA *verb* word (Hebrew) whose lexeme is in
the entry's mapping (``config/reference/locative_bhsa.yaml``) and whose stem belongs to the entry's template.

Dicta and BHSA are aligned verse by verse on orthographic words (``hebloc.pilot.bhsa``: Qere reading). For every
aligned word the Dicta host token is identified with the rule under test and compared with the truth:

- precision = identified words whose members include a true entry / identified words with a mapped member;
- recall    = true words whose identification includes that entry / true words (aligned);
- breakdowns by ``match_method``, by form origin (Dicta-attested host vs generated-only), by key kind (single,
  combined, ``~``), per entry, and the cause of every miss.

Configurations: ``V1`` (the archived forms-v1 lexicon and forms), ``V2-L`` (forms-v2 without generated forms) and
``V2`` (forms-v2, full). PRE-REGISTERED RULE (fixed before measuring): generated forms stay in R1 only if in V2
(a) generated-only matches in clean keys (no ``~`` member) have precision >= 0.80 and (b) F1(V2) >= F1(V2-L).
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

import yaml

from hebloc.loc import identify as ID
from hebloc.loc import lexicon as L
from hebloc.paths import CONFIG_DIR, DATA_DIR

MAP_PATH = CONFIG_DIR / "reference" / "locative_bhsa.yaml"
WORDS_PATH = DATA_DIR / "external" / "bhsa" / "words.parquet"
OUT_DIR = DATA_DIR / "loc" / "review" / "quality" / "bhsa"
ARCHIVE_V1 = DATA_DIR / "loc" / "archive" / "r1-v1"
STEMS = {"Simple": {"qal", "nif", "pasq"},
         "Intensive": {"piel", "pual", "hit", "hotp", "poel", "poal", "htpo", "nit", "etpa"},
         "Causative": {"hif", "hof", "hsht", "tif"}}
RULE = {"generated_clean_precision_min": 0.80, "f1_v2_ge_f1_v2l": True}
MIN_ALIGN = 0.8


def _norm(s: str | None) -> str:
    from hebloc.pilot.bhsa import norm_lex
    return norm_lex(s)


# ---------------------------------------------------------------------------------------------- mapping
def propose_mapping(lex: L.Lexicon) -> dict:
    """Entry → BHSA verb lexemes whose consonants equal the root (a proposal for Ori's review; no Dicta data used)."""
    import duckdb

    rows = duckdb.sql(f"SELECT lex_utf8, vs, count(*) AS n FROM '{WORDS_PATH.as_posix()}' "
                      "WHERE sp = 'verb' AND language = 'Hebrew' GROUP BY ALL").fetchall()
    by_cons: dict[str, Counter] = defaultdict(Counter)
    for lx, vs, n in rows:
        by_cons[_norm(lx)][(lx, vs)] += n
    out = {}
    for e in lex.entries:
        c = by_cons.get(_norm(e.root), Counter())
        lexes = sorted({lx for (lx, _vs) in c})
        in_t = sum(n for (lx, vs), n in c.items() if vs in STEMS[e.template])
        note = "" if lexes else "no BHSA verb lexeme with these consonants"
        if lexes and not in_t:
            note = f"lexeme exists but has no {e.template} stem tokens"
        out[e.id] = {"lex": lexes, "template": e.template, "stems": sorted(STEMS[e.template]),
                     "tokens_in_template": in_t, "tokens_all_stems": sum(c.values()), "note": note}
    return out


def write_mapping(mapping: dict, path: Path = MAP_PATH) -> None:
    from hebloc.store.io import atomic_write_text

    head = ("# Entry -> BHSA verb lexeme(s), for MEASURING identification on Mikra only (R1 correction, D-057).\n"
            "# Proposed by consonant match of the root (hebloc loc lexicon bhsa-eval --propose); reviewed by Ori.\n"
            "# Never used to choose Dicta lemmas, forms or flags. Truth = BHSA verb, lexeme in `lex`, stem in `stems`.\n")
    atomic_write_text(head + yaml.safe_dump({"entries": mapping}, allow_unicode=True, sort_keys=False, width=200), path)


def load_mapping(path: Path = MAP_PATH) -> dict[str, set[str]]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {k: {_norm(x) for x in (v or {}).get("lex") or []} for k, v in (raw.get("entries") or {}).items()}


# ---------------------------------------------------------------------------------------------- configurations
def configuration(name: str) -> tuple[L.Lexicon, set[tuple[str, str]]]:
    """The lexicon under test and the set of (entry, host) forms that are Dicta-attested (for the origin breakdown).

    V1 = archived forms-v1; V2-L / V2 = forms-v2 built in memory without / with generated forms for every entry;
    R1 = the shipped files (forms-v2 with the pre-registered fallback policy)."""
    from hebloc.loc import inventory as INV

    inv = INV.load()
    cur = L.load()
    attested = {(e, h) for e, hs in L.build_forms(cur, inv, generated="none")["forms"].items() for h in hs}
    if name == "V1":
        return L.load(ARCHIVE_V1 / "locative_verbs.v1.yaml", ARCHIVE_V1 / "locative_verb_forms.v1.yaml", validate=False), attested
    if name in ("V2-L", "V2"):
        r = L.build_forms(cur, inv, generated="none" if name == "V2-L" else "all")
        return replace(cur, forms=r["forms"], ambiguous=r["ambiguous"]), attested
    if name == "R1":
        return cur, attested
    raise ValueError(f"unknown configuration {name!r} (V1, V2-L, V2, R1)")


# ---------------------------------------------------------------------------------------------- evaluation
def evaluate(lex: L.Lexicon, mapping: dict[str, set[str]], attested: set[tuple[str, str]], *, progress: bool = True) -> dict:
    from hebloc.loc.source import Source, connect
    from hebloc.pilot import bhsa as B
    from hebloc.pilot.experiments import _bhsa_index

    by_id = lex.by_id()
    truth_ix: dict[tuple[str, str], set[str]] = defaultdict(set)
    for eid, lexes in mapping.items():
        e = by_id.get(eid)
        if not e:
            continue
        for lx in lexes:
            for vs in STEMS[e.template]:
                truth_ix[(lx, vs)].add(eid)
    mapped = {eid for eid, lx in mapping.items() if lx and eid in by_id}
    idx = ID.build_index(lex)
    bidx = _bhsa_index()
    src = Source.repo()
    con = connect()
    refs = dict(con.sql(f"SELECT sent_id, ref FROM {src.units_sql('mikra', ('sent_id', 'ref'))}").fetchall())
    cols = ("sent_id", "piece_idx", "word_idx", "sent_word_idx", "ws_idx", "surface", "upos", "lemma", "lemma_blank",
            "host", "prefix")
    toks: dict[str, list[dict]] = defaultdict(list)
    for run in src.runs("mikra"):
        if progress:
            print(f"  bhsa-eval: reading {run.run_id}", flush=True)
        for r in con.sql(f"SELECT {', '.join(cols)} FROM {src.tokens_sql(run, cols)}").fetchall():
            toks[r[0]].append(dict(zip(cols, r)))
    # every lexicon host form any entry COULD generate (for the miss causes)
    from hebloc.loc import morph
    gen_any: dict[str, set[str]] = defaultdict(set)
    for e in lex.entries:
        try:
            for h in morph.forms(e.root, e.template):
                gen_any[e.id].add(h)
        except ValueError:
            pass
    c = Counter()
    by_key = defaultdict(Counter)
    per_entry = defaultdict(Counter)
    miss = Counter()
    for sid, ts in toks.items():
        words = bidx.get(refs.get(sid, ""), [])
        bg = B.ortho_groups(words, "qere")
        if not words:
            continue
        truth_words = [g for g in bg if g["host"].get("sp") == "verb" and g["host"].get("language") == "Hebrew"
                       and truth_ix.get((_norm(g["host"].get("lex_utf8")), g["host"].get("vs")))]
        dg = B.dicta_groups(ts)
        pairs = B.align(dg, bg)
        if len(pairs) / max(len(bg), 1) < MIN_ALIGN:
            c["verses_excluded"] += 1
            c["truth_in_excluded_verses"] += len(truth_words)
            continue
        c["verses"] += 1
        aligned_b = set()
        for d, b in pairs:
            h = b["host"]
            aligned_b.add(h["w"])
            if h.get("language") != "Hebrew":
                continue
            t = d["host"]
            truth = set()
            if h.get("sp") == "verb":
                truth = truth_ix.get((_norm(h.get("lex_utf8")), h.get("vs")), set())
            m = ID.identify(idx, t.get("lemma"), t.get("host"), t.get("upos"))
            members = set(m["members"]) if m else set()
            if m and members & mapped:
                kind = "tilde" if m["tilde"] else ("combined" if len(members) > 1 else "single")
                if m["match_method"] == "form":
                    origin = "attested" if any((x, t.get("host")) in attested for x in members) else "generated"
                else:
                    origin = "lemma"
                ok = bool(members & truth)
                for k in ("all", f"method:{m['match_method']}", f"origin:{origin}", f"kind:{kind}",
                          f"origin:{origin}|kind:{'clean' if kind != 'tilde' else 'tilde'}"):
                    by_key[k]["identified"] += 1
                    by_key[k]["correct"] += int(ok)
                for x in members & mapped:
                    per_entry[x]["identified_as_member"] += 1
                    per_entry[x]["correct_as_member"] += int(x in truth)
            for x in truth:
                c["truth"] += 1
                per_entry[x]["truth"] += 1
                if x in members:
                    c["recalled"] += 1
                    per_entry[x]["recalled"] += 1
                    if not m["tilde"]:
                        c["recalled_clean"] += 1          # lands in a class stratum (no ~ member)
                    continue
                if m:
                    cause = "identified_as_other_entry"
                elif t.get("upos") != "VERB":
                    cause = "dicta_pos_not_verb"
                elif t.get("lemma_blank"):
                    cause = "blank_lemma_form_filtered" if (t.get("host") in gen_any[x]) else "blank_lemma_form_not_generated"
                else:
                    cause = "other_lemma_form_filtered" if (t.get("host") in gen_any[x]) else "other_lemma_not_generated"
                miss[cause] += 1
                per_entry[x][f"miss:{cause}"] += 1
        for g in truth_words:
            if g["host"]["w"] not in aligned_b:
                n = len(truth_ix.get((_norm(g["host"].get("lex_utf8")), g["host"].get("vs")), ()))
                c["truth_not_aligned"] += n
    def prf(k):
        x = by_key[k]
        return round(x["correct"] / x["identified"], 4) if x["identified"] else None
    P = by_key["all"]["correct"] / by_key["all"]["identified"] if by_key["all"]["identified"] else 0.0
    R = c["recalled"] / c["truth"] if c["truth"] else 0.0
    F = 2 * P * R / (P + R) if P + R else 0.0
    ident_clean = by_key["all"]["identified"] - by_key["kind:tilde"]["identified"]
    corr_clean = by_key["all"]["correct"] - by_key["kind:tilde"]["correct"]
    Pc = corr_clean / ident_clean if ident_clean else 0.0
    Rc = c["recalled_clean"] / c["truth"] if c["truth"] else 0.0
    Fc = 2 * Pc * Rc / (Pc + Rc) if Pc + Rc else 0.0
    return {"counts": dict(c), "precision": round(P, 4), "recall": round(R, 4), "f1": round(F, 4),
            "clean": {"identified": ident_clean, "precision": round(Pc, 4), "recall": round(Rc, 4), "f1": round(Fc, 4),
                      "note": "tokens WITHOUT a ~ member only (what feeds the class strata and the class analysis)"},
            "breakdown": {k: {**dict(v), "precision": prf(k)} for k, v in sorted(by_key.items())},
            "miss_causes": dict(miss.most_common()),
            "per_entry": {k: dict(v) for k, v in sorted(per_entry.items())},
            "entries_mapped": len(mapped), "entries_unmapped": sorted(set(by_id) - mapped)}


def decide(v2: dict, v2l: dict) -> dict:
    gen = v2["breakdown"].get("origin:generated|kind:clean", {})
    p = gen.get("precision")
    a = p is not None and p >= RULE["generated_clean_precision_min"]
    b = v2["f1"] >= v2l["f1"]
    return {"rule": RULE, "generated_clean_precision": p, "generated_clean_identified": gen.get("identified", 0),
            "a_precision_ok": a, "b_f1_ok": b, "f1_v2": v2["f1"], "f1_v2l": v2l["f1"],
            "keep_generated_forms": bool(a and b),
            "fallback_if_not": "generated forms only for entries with no Dicta lemma of their own, always marked ambiguous"}


def run(configs: list[str], *, out_dir: Path = OUT_DIR, progress: bool = True) -> dict:
    mapping = load_mapping()
    res = {}
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in configs:
        lex, attested = configuration(name)
        r = evaluate(lex, mapping, attested, progress=progress)
        r["configuration"] = name
        r["forms_rule"] = lex.forms_meta.get("rule_version")
        (out_dir / f"{name}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        res[name] = r
    if "V2" in res and "V2-L" in res:
        d = decide(res["V2"], res["V2-L"])
        (out_dir / "decision.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        res["decision"] = d
    return res
