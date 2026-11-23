"""Deterministic gold sampler, local annotation sheets, and the text-free gold check (S56-v1 §5.8; D-057).

DESIGN (Ori, 2026-11-19/20):
- Population: every lexicon-identified VERB token in the FULL view (identification only — never the extractor, so
  the gold also measures extraction recall). Each token belongs to exactly one stratum:
  ``A`` / ``A/B`` / ``B`` (all its lexicon members are core entries of that one class), ``MIXED`` (core members
  of different classes, or core + other paper verbs), ``MH`` (only §8 MH-supplement members; Modern only).
  Tokens whose members are only ``paper_other`` entries are reported but not sampled.
- Modern adds ``NONPAPER`` (§6): a VERB token not identified by the lexicon, with a non-blank lemma, a direct
  object (``obj`` or object suffix) AND a PP of family B or MIN (hebloc.loc.tree) — the sampling frame for §6.
- Allocation: Mikra 400; Modern 300 paper-verb (MH 30) + 100 NONPAPER; Hazal, Medieval, Haskala 150 (test only).
  ``MIXED`` gets its population share; the rest is split EQUALLY between A, A/B and B.
- gold-r1b (correction of 2026-11-20, D-057): a token whose key has a ``~`` member (a homograph with a non-lexicon
  verb: a shared lemma, an ambiguous form, or a same-root Simple partner) goes to the ``HOMOGRAPH`` stratum, ahead of
  the class strata, so homographs never fill A / A/B / B. ``HOMOGRAPH`` gets its population share of the core,
  capped at ``HOMOGRAPH_MAX_SHARE``, with at most ``HOMOGRAPH_CAP_PER_KEY`` items per key.
- Cap: at most 8 instances per ``verb_key`` (2 per lemma in NONPAPER, 4 in HOMOGRAPH), so frequent verbs do not dominate.
- Weights: within a stratum the capped pool has P = sum_k min(n_k, cap) items and the first m by hash are a uniform
  sample of it, so the inclusion probability is pi = (m / P) * (min(n_k, cap) / n_k) (``pi``, ``weight_ht`` = 1 / pi,
  unbiased but noisy when a few keys are huge). ``weight`` is the calibrated (post-stratified) weight: each sampled key
  stands for its own population, n_k / s_k per item, scaled by pop_stratum / (population of the sampled keys) for the
  keys that were not drawn — so the weights of a stratum sum EXACTLY to its population.
- Order: sha256(``S56-v1:<corpus>:gold:`` + instance_key). Shortfalls are recorded, never filled.
- Split, by rank within each stratum: rank % 4 == 0 → dev, 1 → validation, 2, 3 → test (1:1:2).
- Agreement subset (Mikra, Modern): 15 dev + 15 validation + 30 test items, by a second hash.
- ``sample_id`` depends on corpus, lexicon hash, sampler version and salt — not on the data source — so Ori and a
  partner draw exactly the same items from the repo or from the package.

TEST INDEPENDENCE: the split is fixed here; ``check_sheet`` writes each split to its own text-free file; nothing in
rule development reads test labels (the R2 scorer will need an explicit ``--final-test``).
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import pyarrow as pa

from hebloc.loc import METHODOLOGY
from hebloc.loc import identify as ID
from hebloc.loc import tree as TR
from hebloc.loc.lexicon import Lexicon
from hebloc.loc.manifest import write_csv, write_manifest
from hebloc.loc.source import Source, connect
from hebloc.paths import DATA_DIR
from hebloc.store.io import atomic_write_parquet, atomic_write_text, read_json

SAMPLER_VERSION = "gold-r1b"
#: the one-time redraw authorized by Ori on 2026-11-20 (before any annotation): the r1 rehearsal samples were drawn with
#: forms-v1, whose false matches and homographs filled the B strata (docs/S56_R1.md, D-057). Never annotated.
SUPERSEDES = {"mikra": "mikra-r1-6bf0bae6b4", "modern": "modern-r1-d5ae20ec4e"}
REDRAW_REASON = ("one-time redraw authorized by Ori 2026-11-20 before any annotation: forms-v2 / morph-v2 correct false "
                 "form matches; homographs (~ keys) moved to the HOMOGRAPH stratum; design-based weights")
#: frozen at the R1 release (tag s56-r1, D-057): a frozen corpus can never be redrawn to a different sample (the
#: dev / validation / test split stays fixed). `items_sha256` = items_fingerprint() of the sample (item, instance,
#: stratum, split, agreement): a draw whose items differ is refused, whatever the id. `sample_sha256` is the file
#: hash on Ori's computer (repo == package); a different file hash with identical items is recorded, not refused.
FROZEN_SAMPLES: dict[str, dict[str, str]] = {
    "mikra": {"sample_id": "mikra-r1b-1cd4ee9802",
              "items_sha256": "d6f2c5bfe0f3c8f9618c575cd76137beea7a602204bef11a6a4b4e65896db591",
              "sample_sha256": "0162267cca4d94d5f6aa20d632eaa436d13cd699b086e419759d482ecbed1881"},
    "modern": {"sample_id": "modern-r1b-5fbb5e22e7",
               "items_sha256": "37c26d60a40a08f67f578334ee4b5f8026ec68e14d18f514022078bda4197d87",
               "sample_sha256": "f0903a45102493c1d5783809ba4c1dac9989ade8bb2c868edef6934903c6851f"},
}
#: supplemental samples (S56_R1.md §3; D-059 addendum; D-065), registered by Ori at G3 with the decision that approved
#: the draw: corpus -> {sample_id: {"items_sha256", "approval"}}. Registered at G3 (2026-11-23). A SILVER sentence job
#: is made only from a frozen sample or a registered supplement; a supplement drawn again (Efrat, from the package) must
#: give the same items (``items_match``), exactly like FROZEN_SAMPLES. Both s1 were drawn from the candidate
#: I-1+I-4-fc200448c2 (D-067), size 120.
FROZEN_SUPPLEMENTS: dict[str, dict[str, dict[str, str]]] = {
    "mikra": {"mikra-s1-e134ad4c7e": {"items_sha256": "c79826c30e751a20e3a19903aee9ec53ce0aea67889d31adbc005f707e9a3b0c",
                                      "approval": "D-068"}},
    "modern": {"modern-s1-62013e6a05": {"items_sha256": "348bcb94123f958641eddb7e2c5ca19f4853c7126522baa2144be918e8027154",
                                        "approval": "D-069"}},
}
GUIDELINE_VERSION = "S56-v1-g1"
GOLD_DIR = DATA_DIR / "loc" / "gold"
CAP_PER_KEY = 8
NONPAPER_CAP_PER_LEMMA = 2
HOMOGRAPH_CAP_PER_KEY = 4
HOMOGRAPH_MAX_SHARE = 0.10
DESIGN = {
    "mikra": {"core": 400, "mh": 0, "nonpaper": 0, "test_only": False},
    "modern": {"core": 270, "mh": 30, "nonpaper": 100, "test_only": False},
    "hazal": {"core": 150, "mh": 0, "nonpaper": 0, "test_only": True},
    "medieval": {"core": 150, "mh": 0, "nonpaper": 0, "test_only": True},
    "haskala": {"core": 150, "mh": 0, "nonpaper": 0, "test_only": True},
}
AGREEMENT = {"dev": 15, "validation": 15, "test": 30}
AGREEMENT_CORPORA = ("mikra", "modern")
SPLITS = ("dev", "validation", "test")
CORE_STRATA = ("A", "A/B", "B")
STRATA_ORDER = CORE_STRATA + ("HOMOGRAPH", "MIXED", "MH", "NONPAPER")
#: token columns the sampler needs (identification + tree reading)
TREE_COLUMNS = ("sent_id", "piece_idx", "word_idx", "lemma", "lemma_blank", "host", "form", "upos", "prefix", "prefix_upos",
                "suffix", "head", "deprel")

ANNOTATION_COLUMNS = ("is_target_verb", "member", "locative", "frame", "do", "pps", "bare_np", "locatum", "location", "notes")
FRAMES = ("A", "B", "NON_LOCATIVE", "AMBIGUOUS")


class GoldError(Exception):
    pass


def salt(corpus: str) -> str:
    return f"{METHODOLOGY}:{corpus}:gold:"


def items_fingerprint(rows: list[dict]) -> str:
    """sha256 of the sorted item_id|instance_key|stratum|split|agreement lines: what freezing a sample protects."""
    lines = sorted(f"{x['item_id']}|{x['instance_key']}|{x['stratum']}|{x['split']}|{int(bool(x['agreement']))}" for x in rows)
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def sample_id(corpus: str, lex: Lexicon) -> str:
    h = hashlib.sha256(f"{corpus}|{lex.sha256}|{SAMPLER_VERSION}|{salt(corpus)}".encode()).hexdigest()[:10]
    return f"{corpus}-r1b-{h}"


def _stratum_sql() -> str:
    return """CASE
      WHEN len(tilde) > 0 AND list_contains(statuses, 'core') THEN 'HOMOGRAPH'
      WHEN list_has_all(['core'], statuses) AND len(statuses) = 1 AND len(classes) = 1 THEN classes[1]
      WHEN list_contains(statuses, 'core') THEN 'MIXED'
      WHEN statuses = ['mh_supplement'] THEN 'MH'
      ELSE 'OTHER' END"""


def _candidates(con, source: Source, corpus: str, lex: Lexicon, *, progress: bool) -> tuple[pa.Table, pa.Table]:
    """Per run: the population counts and the top candidates (by hash, cap per key) of every stratum."""
    design = DESIGN[corpus]
    ID.register(con, lex)
    con.execute(f"CREATE OR REPLACE TEMP TABLE units AS SELECT sent_id, ref, in_full_view FROM {source.units_sql(corpus, ('sent_id', 'ref', 'in_full_view'))}")
    cand_parts, pop_parts = [], []
    s = salt(corpus).replace("'", "''")
    for run in source.runs(corpus):
        if progress:
            print(f"  gold sample {corpus}: {run.run_id}", flush=True)
        con.execute(f"CREATE OR REPLACE TEMP TABLE tok AS SELECT t.* FROM {source.tokens_sql(run, TREE_COLUMNS)} t "
                    "JOIN units u USING (sent_id) WHERE u.in_full_view")
        con.execute(f"CREATE OR REPLACE TEMP TABLE idn AS {ID.identify_sql('tok')}")
        pop = f"""SELECT i.sent_id, i.piece_idx, i.word_idx, i.verb_key, i.members, i.match_method, {_stratum_sql()} AS stratum,
                         i.verb_key AS cap_key, t.lemma, t.run_id, t.shard, t.doc_id
                  FROM idn i JOIN tok t USING (sent_id, piece_idx, word_idx)"""
        if design["nonpaper"]:
            # only verbs that can have a direct object (an obj child or an object suffix): exact prefilter
            con.execute("""CREATE OR REPLACE TEMP TABLE v AS SELECT t.sent_id, t.piece_idx, t.word_idx, t.suffix, 'unknown' AS voice
                           FROM tok t ANTI JOIN idn i USING (sent_id, piece_idx, word_idx)
                           WHERE t.upos = 'VERB' AND NOT t.lemma_blank
                             AND (t.suffix = 'PRON' OR EXISTS (SELECT 1 FROM tok o WHERE o.sent_id = t.sent_id AND o.piece_idx = t.piece_idx
                                                                AND o.head = t.word_idx AND o.deprel = 'obj'))""")
            con.execute(f"CREATE OR REPLACE TEMP TABLE args AS {TR.arguments_sql('v', 'tok')}")
            pop += f""" UNION ALL
                  SELECT t.sent_id, t.piece_idx, t.word_idx, 'lemma:' || t.lemma, [], NULL, 'NONPAPER', 'lemma:' || t.lemma,
                         t.lemma, t.run_id, t.shard, t.doc_id
                  FROM tok t JOIN (SELECT sent_id, piece_idx, verb_word_idx AS word_idx FROM args GROUP BY ALL
                                   HAVING bool_or(slot = 'DO') AND bool_or(p_family IN ('B', 'MIN'))) f USING (sent_id, piece_idx, word_idx)"""
        con.execute(f"CREATE OR REPLACE TEMP TABLE pop AS SELECT *, sent_id || '|' || piece_idx || '|' || word_idx AS instance_key, "
                    f"sha256('{s}' || sent_id || '|' || piece_idx || '|' || word_idx) AS h FROM ({pop})")
        pop_parts.append(con.sql("SELECT stratum, cap_key, count(*)::BIGINT AS n FROM pop GROUP BY ALL").to_arrow_table())
        cand_parts.append(con.sql(f"""SELECT * FROM (SELECT *, row_number() OVER (PARTITION BY stratum, cap_key ORDER BY h) AS r FROM pop
                                     WHERE stratum <> 'OTHER') WHERE r <= CASE WHEN stratum = 'NONPAPER' THEN {NONPAPER_CAP_PER_LEMMA} WHEN stratum = 'HOMOGRAPH' THEN {HOMOGRAPH_CAP_PER_KEY} ELSE {CAP_PER_KEY} END
                                  """).to_arrow_table().drop(["r"]))
    return pa.concat_tables(cand_parts), pa.concat_tables(pop_parts)


def cap_of(stratum: str) -> int:
    return {"NONPAPER": NONPAPER_CAP_PER_LEMMA, "HOMOGRAPH": HOMOGRAPH_CAP_PER_KEY}.get(stratum, CAP_PER_KEY)


def allocate(corpus: str, pop_by_stratum: dict[str, int]) -> dict[str, int]:
    d = DESIGN[corpus]
    core_total = sum(pop_by_stratum.get(k, 0) for k in CORE_STRATA + ("MIXED", "HOMOGRAPH"))
    n_mixed = round(d["core"] * pop_by_stratum.get("MIXED", 0) / core_total) if core_total else 0
    n_homo = min(round(d["core"] * pop_by_stratum.get("HOMOGRAPH", 0) / core_total) if core_total else 0,
                 round(d["core"] * HOMOGRAPH_MAX_SHARE))
    rest = d["core"] - n_mixed - n_homo
    base, rem = divmod(rest, 3)
    alloc = {k: base for k in CORE_STRATA}
    for k in ("A/B", "B", "A")[:rem]:
        alloc[k] += 1
    alloc["MIXED"] = n_mixed
    if n_homo:
        alloc["HOMOGRAPH"] = n_homo
    if d["mh"]:
        alloc["MH"] = d["mh"]
    if d["nonpaper"]:
        alloc["NONPAPER"] = d["nonpaper"]
    return alloc


def draw(corpus: str, source: Source, lex: Lexicon, *, out_root: Path = GOLD_DIR, git: dict, progress: bool = True,
         dev: bool = False) -> dict:
    if corpus not in DESIGN:
        raise GoldError(f"no gold design for {corpus}")
    sid = sample_id(corpus, lex)
    frozen = FROZEN_SAMPLES.get(corpus)
    if frozen and frozen["sample_id"] != sid and not dev:
        raise GoldError(f"the {corpus} gold sample is frozen as {frozen['sample_id']} (R1); this lexicon/sampler would draw "
                        f"{sid}. A redraw would change the dev/validation/test split: refused (Ori only, with --dev and a decision)")
    out = Path(out_root) / corpus / sid
    if (out / "manifest.json").exists():
        raise GoldError(f"{out} already exists (a sample is drawn once; delete nothing — it is identical by design)")
    con = connect()
    cands, popc = _candidates(con, source, corpus, lex, progress=progress)
    con.register("cands_in", cands)
    con.register("popc_in", popc)
    pop_key = {(r["stratum"], r["cap_key"]): r["n"] for r in con.sql(
        "SELECT stratum, cap_key, sum(n)::BIGINT AS n FROM popc_in GROUP BY ALL").to_arrow_table().to_pylist()}
    pop_stratum: dict[str, int] = {}
    for (st, _), n in pop_key.items():
        pop_stratum[st] = pop_stratum.get(st, 0) + n
    alloc = allocate(corpus, pop_stratum)
    # global cap per key, then per stratum the first n by hash
    sel = con.sql(f"""
        WITH c AS (SELECT * FROM (SELECT *, row_number() OVER (PARTITION BY stratum, cap_key ORDER BY h) AS rk FROM cands_in)
                   WHERE rk <= CASE WHEN stratum = 'NONPAPER' THEN {NONPAPER_CAP_PER_LEMMA} WHEN stratum = 'HOMOGRAPH' THEN {HOMOGRAPH_CAP_PER_KEY} ELSE {CAP_PER_KEY} END),
             r AS (SELECT *, row_number() OVER (PARTITION BY stratum ORDER BY h) - 1 AS rank FROM c)
        SELECT * EXCLUDE (rk) FROM r""").to_arrow_table().to_pylist()
    rows = [x for x in sel if x["rank"] < alloc.get(x["stratum"], 0)]
    test_only = DESIGN[corpus]["test_only"]
    for x in rows:
        x["split"] = "test" if test_only else SPLITS[min(x["rank"] % 4, 2)]
    # agreement subset: by a second hash within each split
    if corpus in AGREEMENT_CORPORA:
        for sp, n in AGREEMENT.items():
            pool = sorted((x for x in rows if x["split"] == sp),
                          key=lambda x: hashlib.sha256(f"{salt(corpus)}agreement:{x['instance_key']}".encode()).hexdigest())
            keep = {x["instance_key"] for x in pool[:n]}
            for x in rows:
                if x["split"] == sp:
                    x["agreement"] = x["instance_key"] in keep
    order = {k: i for i, k in enumerate(STRATA_ORDER)}
    rows.sort(key=lambda x: (order[x["stratum"]], x["rank"]))
    # design-based inclusion probabilities (see the module docstring)
    pool: dict[str, int] = {}
    for (st, _), n in pop_key.items():
        pool[st] = pool.get(st, 0) + min(n, cap_of(st))
    m_st: dict[str, int] = {}
    s_key: dict[tuple, int] = {}
    for x in rows:
        m_st[x["stratum"]] = m_st.get(x["stratum"], 0) + 1
        s_key[(x["stratum"], x["cap_key"])] = s_key.get((x["stratum"], x["cap_key"]), 0) + 1
    sampled_pop: dict[str, int] = {}
    for (st, k) in s_key:
        sampled_pop[st] = sampled_pop.get(st, 0) + pop_key[(st, k)]
    for i, x in enumerate(rows, 1):
        st = x["stratum"]
        x["item_id"] = f"{corpus[:2].upper()}{i:04d}"
        x["pop_stratum"] = pop_stratum.get(st, 0)
        x["pop_key"] = pop_key.get((st, x["cap_key"]), 0)
        x["pool_stratum"] = pool.get(st, 0)
        x["pi"] = (m_st[st] / pool[st]) * (min(x["pop_key"], cap_of(st)) / x["pop_key"])
        x["weight_ht"] = 1 / x["pi"]
        x["weight"] = (x["pop_key"] / s_key[(st, x["cap_key"])]) * (pop_stratum[st] / sampled_pop[st])
        x.setdefault("agreement", False)
        x["sample_id"] = sid
    fp = items_fingerprint(rows)
    frozen_check = None
    if frozen and frozen["sample_id"] == sid:
        if fp != frozen["items_sha256"] and not dev:
            raise GoldError(f"the {corpus} gold sample is frozen ({sid}) but this draw gives different items "
                            f"({fp[:12]} vs {frozen['items_sha256'][:12]}): STOP and report to Ori (nothing written)")
        frozen_check = {"items_match": fp == frozen["items_sha256"]}
    shortfall = {st: n - sum(1 for x in rows if x["stratum"] == st) for st, n in alloc.items()
                 if sum(1 for x in rows if x["stratum"] == st) < n}
    cols = ["sample_id", "item_id", "instance_key", "sent_id", "piece_idx", "word_idx", "run_id", "shard", "doc_id",
            "verb_key", "members", "match_method", "lemma", "stratum", "cap_key", "split", "agreement", "rank", "h",
            "pop_stratum", "pop_key", "pool_stratum", "pi", "weight_ht", "weight"]
    sample = pa.Table.from_pylist([{c: x.get(c) for c in cols} for x in rows])
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_parquet(sample, out / "sample.parquet")
    write_csv(sample.drop(["h"]), out / "sample.csv")
    popt = pa.Table.from_pylist([{"stratum": k[0], "cap_key": k[1], "n": v} for k, v in sorted(pop_key.items())])
    atomic_write_parquet(popt, out / "population.parquet")
    _write_sheets(con, source, corpus, rows, out / "sheets")
    if frozen_check is not None:
        frozen_check["sample_file_matches"] = (hashlib.sha256((out / "sample.parquet").read_bytes()).hexdigest()
                                               == frozen.get("sample_sha256"))
    m = write_manifest(out, what="gold sample (ids only + local sheets)", git=git, source=source.describe(corpus),
                       extra={"corpus": corpus, "sample_id": sid, "sampler_version": SAMPLER_VERSION,
                              "guideline_version": GUIDELINE_VERSION, "lexicon_sha256": lex.sha256, "salt": salt(corpus),
                              "design": DESIGN[corpus], "cap_per_key": CAP_PER_KEY,
                              "homograph_cap_per_key": HOMOGRAPH_CAP_PER_KEY, "homograph_max_share": HOMOGRAPH_MAX_SHARE,
                              "supersedes": SUPERSEDES.get(corpus), "redraw_reason": REDRAW_REASON if corpus in SUPERSEDES else None,
                              "forms_rule": lex.forms_meta.get("rule_version"), "morph_version": lex.forms_meta.get("morph_version"),
                              "weight_check": {st: round(sum(x["weight"] for x in rows if x["stratum"] == st) / pop_stratum[st], 6)
                                               for st in sorted({x["stratum"] for x in rows})},
                              "weight_ht_ratio": {st: round(sum(x["weight_ht"] for x in rows if x["stratum"] == st) / pop_stratum[st], 3)
                                                  for st in sorted({x["stratum"] for x in rows})},
                              "keys_sampled_share_of_pop": {st: round(sampled_pop[st] / pop_stratum[st], 4) for st in sorted(sampled_pop)},
                              "items_sha256": fp, "frozen_check": frozen_check,
                              "nonpaper_cap_per_lemma": NONPAPER_CAP_PER_LEMMA, "allocation": alloc,
                              "population_by_stratum": pop_stratum, "shortfall": shortfall,
                              "n_items": len(rows), "by_split": {sp: sum(1 for x in rows if x["split"] == sp) for sp in SPLITS},
                              "agreement_items": sum(1 for x in rows if x["agreement"]),
                              "local_only": ["sheets/ (quote corpus text: never git, D-042)"]})
    return m


def _write_sheets(con, source: Source, corpus: str, rows: list[dict], folder: Path) -> None:
    """Local annotation sheets (they quote corpus text: D-042, never git)."""
    keys = pa.table({"sent_id": [x["sent_id"] for x in rows], "piece_idx": [x["piece_idx"] for x in rows]})
    con.register("want", keys)
    units = {r["sent_id"]: r for r in con.sql(
        f"SELECT u.sent_id, u.text_norm, u.ref, d.subcorpus, d.source FROM {source.units_sql(corpus, ('sent_id', 'doc_id', 'text_norm', 'ref'))} u "
        f"LEFT JOIN {source.documents_sql()} d USING (doc_id) WHERE u.sent_id IN (SELECT sent_id FROM want)").to_arrow_table().to_pylist()}
    words: dict[tuple, list] = {}
    tgt: dict[tuple, dict] = {}
    want_runs = {x["run_id"] for x in rows}
    for run in source.runs(corpus):
        if run.run_id not in want_runs:
            continue
        for r in con.sql(f"SELECT t.sent_id, t.piece_idx, t.word_idx, t.surface, t.char_start, t.char_end FROM {source.tokens_sql(run)} t "
                         "SEMI JOIN want w ON w.sent_id = t.sent_id AND w.piece_idx = t.piece_idx").to_arrow_table().to_pylist():
            words.setdefault((r["sent_id"], r["piece_idx"]), []).append(r)
            tgt[(r["sent_id"], r["piece_idx"], r["word_idx"])] = r
    header = ["item_id", "split", "agreement", "stratum", "where", "verb_key", "target", "sentence", "words", *ANNOTATION_COLUMNS]
    by_file: dict[str, list] = {sp: [] for sp in SPLITS}
    by_file["agreement"] = []
    for x in rows:
        u = units[x["sent_id"]]
        t = tgt[(x["sent_id"], x["piece_idx"], x["word_idx"])]
        text = u["text_norm"]
        sentence = text[:t["char_start"]] + "[[" + text[t["char_start"]:t["char_end"]] + "]]" + text[t["char_end"]:]
        ws = sorted(words[(x["sent_id"], x["piece_idx"])], key=lambda r: r["word_idx"])
        where = u["ref"] or " / ".join(v for v in (u.get("source"), u.get("subcorpus")) if v) or x["doc_id"]
        line = [x["item_id"], x["split"], "Y" if x["agreement"] else "", x["stratum"], where, x["verb_key"], t["surface"],
                sentence, " ".join(f"{r['word_idx']}:{r['surface']}" for r in ws), *[""] * len(ANNOTATION_COLUMNS)]
        by_file[x["split"]].append(line)
        if x["agreement"]:
            by_file["agreement"].append(line)
    for name, lines in by_file.items():
        if not lines and name == "agreement":
            continue
        _write_rows(folder / f"{name}.csv", header, lines)


def _write_rows(path: Path, header: list[str], lines: list[list]) -> None:
    import io

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(lines)
    atomic_write_text("﻿" + buf.getvalue(), path)


# --------------------------------------------------------------------------------------------- gold check
def _idx(v: str) -> bool:
    return v.isdigit()


#: annotator names that denote an AI tool: never accepted as HUMAN gold (D-061). AI labels are SILVER and go only
#: through ``hebloc loc silver`` (hebloc.loc.silver), which marks every row ``label_source = ai``.
AI_ANNOTATOR_NAMES = ("claude_code", "claude", "ai", "llm", "silver")


def row_problems(v: dict, members: list, n_words: int, w: str = "") -> list[str]:
    """The format checks of one annotated row (guideline §2), shared by the human gold check and the SILVER QC."""
    probs = []
    if v["is_target_verb"] not in ("Y", "N"):
        probs.append(f"{w} is_target_verb must be Y or N")
    if v["member"] and v["member"] not in members:
        probs.append(f"{w} member must be one of {members} (or empty)")
    if v["is_target_verb"] == "Y":
        if v["locative"] not in ("Y", "N", "?"):
            probs.append(f"{w} locative must be Y, N or ?")
        if v["frame"] not in FRAMES:
            probs.append(f"{w} frame must be one of {FRAMES}")
        if v["locative"] == "N" and v["frame"] not in ("NON_LOCATIVE", ""):
            probs.append(f"{w} locative N needs frame NON_LOCATIVE")
    for c in ("do", "bare_np", "locatum", "location"):
        x = v[c]
        if x and not (_idx(x) and int(x) < n_words) and x not in ("suffix", "subject", "elided", "none"):
            probs.append(f"{w} {c} must be a word index (< {n_words}), suffix, subject, elided or none")
    for pp in filter(None, v["pps"].split(";")):
        ix, _, prep = pp.strip().partition(":")
        if not (_idx(ix.strip()) and int(ix.strip()) < n_words and prep.strip()):
            probs.append(f"{w} pps entry {pp!r} must be <word index>:<preposition>")
    return probs


def check_sheet(sheet: Path, sample_dir: Path, annotator: str, out_dir: Path) -> dict:
    """Validate a filled sheet against its sample and write the TEXT-FREE gold file (I4) for its split(s).

    HUMAN gold only: an AI annotator name is refused (D-061; AI labels are SILVER, ``hebloc loc silver``)."""
    if (annotator or "").strip().lower() in AI_ANNOTATOR_NAMES:
        raise GoldError(f"annotator {annotator!r} is an AI tool: AI labels are SILVER, never gold "
                        "(D-061; use `hebloc loc silver`)")
    sample = {r["item_id"]: r for r in __import__("pyarrow.parquet", fromlist=["x"]).read_table(
        Path(sample_dir) / "sample.parquet").to_pylist()}
    man = read_json(Path(sample_dir) / "manifest.json")
    with open(sheet, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    probs, out_rows = [], []
    for i, r in enumerate(rows, 2):
        w = f"line {i} ({r.get('item_id')}):"
        s = sample.get(r.get("item_id", ""))
        if s is None:
            probs.append(f"{w} unknown item_id")
            continue
        if r.get("split") != s["split"]:
            probs.append(f"{w} split {r.get('split')!r} != sample {s['split']!r}")
        n_words = len((r.get("words") or "").split())
        v = {c: (r.get(c) or "").strip() for c in ANNOTATION_COLUMNS}
        if not any(v[c] for c in ANNOTATION_COLUMNS if c != "notes"):
            continue    # not annotated yet: skipped, reported as pending
        probs += row_problems(v, list(s["members"] or []), n_words, w)
        out_rows.append({"sample_id": s["sample_id"], "item_id": s["item_id"], "instance_key": s["instance_key"],
                         "split": s["split"], "stratum": s["stratum"], "agreement": s["agreement"],
                         "annotator": annotator, "label_source": "human", "guideline_version": GUIDELINE_VERSION,
                         **{c: v[c] for c in ANNOTATION_COLUMNS if c != "notes"}, "has_notes": bool(v["notes"])})
    pending = sum(1 for r in rows if not any((r.get(c) or "").strip() for c in ANNOTATION_COLUMNS if c != "notes"))
    if probs:
        return {"ok": False, "problems": probs, "annotated": len(out_rows), "pending": pending}
    written = []
    corpus = man["corpus"]
    for sp in SPLITS:
        part = [x for x in out_rows if x["split"] == sp]
        if part:
            p = Path(out_dir) / f"{corpus}_{sp}_{annotator}.csv"
            write_csv(pa.Table.from_pylist(part), p)
            written.append(str(p))
    return {"ok": True, "problems": [], "annotated": len(out_rows), "pending": pending, "written": written}
