"""Gold tooling of R2: the paper-example dev set, scoring, the variant choice, κ, and the supplemental sampler
(S56-v1 §5.4, §5.8; S56_R1.md §3; D-057; D-059 P8).

TEST INDEPENDENCE (D-057 item 8; D-059 P8):
- ``dev`` (and the paper's examples) may be scored freely: it is what rules are developed against.
- ``validation`` is read ONLY by :func:`choose_variant`, the pre-registered choice between R0, R1 and R2, once per
  corpus (ledger ``annotation/gold/VALIDATION_CHOICE.json``).
- ``test`` is read ONLY with ``final_test=True``, once per corpus (ledger ``annotation/gold/FINAL_TEST.json``); a
  second final test is refused.
- Validation and test are scored on the CLEAN set (exposed items removed, ``annotation/gold/EXPOSURE.csv``), the full
  set is secondary.
- Claude Code never opens validation or test sheets or labels; these functions return aggregate numbers only.

SILVER (D-061): the labels are AI-made SILVER (``label_source = ai``; hebloc.loc.silver), read only from the received,
FROZEN files (``data/loc/silver/final/<split>/<corpus>_<split>_silver.csv``) whose hashes are recorded in
``annotation/silver/FROZEN_SILVER.json`` (SG2). Silver and human labels are never mixed. Every figure is "agreement
with SILVER labels", never accuracy. Abstained silver items (``abstained``, ``locative = ?``, ``frame = AMBIGUOUS``)
are left out of the primary frame metrics and counted (D-061 D-g); an ``agreed_only`` sensitivity set is reported.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hebloc.loc import METHODOLOGY
from hebloc.loc import exposure as EX
from hebloc.loc import gold as G
from hebloc.loc import silver as SV
from hebloc.loc import identify as ID
from hebloc.loc import tree as TR
from hebloc.loc.lexicon import Lexicon
from hebloc.loc.manifest import write_csv, write_manifest
from hebloc.loc.resolve import VARIANTS, _lst, _parts
from hebloc.loc.source import Source, connect
from hebloc.paths import ROOT
from hebloc.store.io import atomic_write_json, atomic_write_parquet, read_json

GOLD_FILES_DIR = ROOT / "annotation" / "gold"
FINAL_LEDGER = GOLD_FILES_DIR / "FINAL_TEST.json"
CHOICE_LEDGER = GOLD_FILES_DIR / "VALIDATION_CHOICE.json"
PAPER_EXAMPLES = GOLD_FILES_DIR / "mikra_paper_examples.csv"
SIMPLER_WINS_WITHIN = 0.01          # 1 F1 point (S56-v1 §5.4)
MCNEMAR_ALPHA = 0.05
SUPPLEMENT_VERSION = "gold-s1"


class ScoreError(Exception):
    pass


# ============================================================================================ gold files
LABEL_SOURCES = ("silver", "human")
SILVER_MEASURE = "agreement with SILVER labels (AI, two independent passes, adjudicated) - not validated accuracy"


def load_gold(corpus: str, split: str, *, gold_dir: Path | None = None, final_test: bool = False,
              _choice: bool = False, label_source: str = "silver", frozen_path: Path | None = None) -> list[dict]:
    """The text-free label rows (I4) of one split. Test needs ``final_test``; validation is only read through
    :func:`choose_variant`. ``silver`` (default, D-061): the received FROZEN silver file, its hash checked against
    FROZEN_SILVER.json; ``human``: human gold files (an AI row is refused). The two are never mixed."""
    if label_source not in LABEL_SOURCES:
        raise ScoreError(f"label_source must be one of {LABEL_SOURCES}")
    if split == "test" and not final_test:
        raise ScoreError("the test split is read once, at the end, with --final-test (D-057)")
    if split == "validation" and not _choice:
        raise ScoreError("the validation split is read only by the pre-registered variant choice (loc score --choose)")
    rows = []
    if label_source == "silver":
        for f in sorted((Path(gold_dir or SV.FINAL_DIR) / split).glob(f"{corpus}_{split}_silver.csv")):
            ok, why = SV.frozen_file_ok(f, Path(frozen_path or SV.FROZEN_PATH))
            if not ok:
                raise ScoreError(f"refused: {why}")
            with open(f, encoding="utf-8-sig", newline="") as fh:
                part = list(csv.DictReader(fh))
            if any(r.get("label_source") != "ai" for r in part):
                raise ScoreError(f"{f.name}: every SILVER row must have label_source = ai")
            rows += part
        return rows
    for f in sorted(Path(gold_dir or GOLD_FILES_DIR).glob(f"{corpus}_{split}_*.csv")):
        if f.name.endswith("_silver.csv"):
            continue
        with open(f, encoding="utf-8-sig", newline="") as fh:
            part = list(csv.DictReader(fh))
        if any(r.get("label_source") == "ai" or r.get("annotator", "").lower() in G.AI_ANNOTATOR_NAMES for r in part):
            raise ScoreError(f"{f.name}: an AI-labelled row in a human gold file: refused (D-061)")
        rows += part
    return rows


def _ledger(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}


# ============================================================================================ metrics
def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value (binomial on the discordant pairs)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    if not a or len(a) != len(b):
        return None
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    cats = sorted(set(a) | set(b))
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return None if pe == 1 else (po - pe) / (1 - pe)


def frame_metrics(pairs: list[tuple[str, str]]) -> dict:
    """``pairs`` = (gold frame, predicted outcome). Macro-F1 over A and B: a gold A/B the resolver leaves
    AMBIGUOUS / UNDETERMINED / NON_LOCATIVE is a miss (S56-v1 §5.4)."""
    out = {}
    for c in ("A", "B"):
        tp = sum(1 for g, p in pairs if g == c and p == c)
        fp = sum(1 for g, p in pairs if g != c and p == c)
        fn = sum(1 for g, p in pairs if g == c and p != c)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        out[c] = {"tp": tp, "fp": fp, "fn": fn, "precision": prec, "recall": rec,
                  "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0}
    nl_tp = sum(1 for g, p in pairs if g == "NON_LOCATIVE" and p == "NON_LOCATIVE")
    nl_fp = sum(1 for g, p in pairs if g != "NON_LOCATIVE" and p == "NON_LOCATIVE")
    nl_fn = sum(1 for g, p in pairs if g == "NON_LOCATIVE" and p != "NON_LOCATIVE")
    n = len(pairs)
    return {"n": n, "macro_f1": (out["A"]["f1"] + out["B"]["f1"]) / 2, "A": out["A"], "B": out["B"],
            "non_locative": {"precision": nl_tp / (nl_tp + nl_fp) if nl_tp + nl_fp else None,
                             "recall": nl_tp / (nl_tp + nl_fn) if nl_tp + nl_fn else None},
            "share_ambiguous": sum(1 for _, p in pairs if p == "AMBIGUOUS") / n if n else None,
            "share_undetermined": sum(1 for _, p in pairs if p == "UNDETERMINED") / n if n else None}


def _gold_frame(r: dict) -> str:
    if r.get("is_target_verb") != "Y":
        return "NOT_TARGET"
    if r.get("locative") == "N":
        return "NON_LOCATIVE"
    return r.get("frame") or "AMBIGUOUS"


def _predictions(extract_folder: Path, variant: str, keys: list[str]) -> dict[str, dict]:
    folder = Path(extract_folder)
    con = connect()
    con.register("want", pa.table({"instance_id": sorted(set(keys))}))
    rows = con.sql(f"""SELECT i.instance_id, r.outcome, i.do_kind, i.has_do
        FROM read_parquet({_lst(_parts(folder, 'instances'))}) i
        JOIN read_parquet({_lst(_parts(folder / f'roles-{variant}', 'roles'))}) r USING (instance_id)
        SEMI JOIN want USING (instance_id)""").to_arrow_table().to_pylist()
    args = con.sql(f"""SELECT instance_id, slot, do_kind, head_word_idx FROM read_parquet({_lst(_parts(folder, 'arguments'))})
        SEMI JOIN want USING (instance_id)""").to_arrow_table().to_pylist()
    out = {r["instance_id"]: {**r, "do_heads": set(), "pp_heads": set()} for r in rows}
    for a in args:
        x = out.get(a["instance_id"])
        if x is None:
            continue
        if a["slot"] in ("DO", "PASSIVE_SUBJ"):
            x["do_heads"].add("suffix" if a["do_kind"] == "suffix" else "subject" if a["slot"] == "PASSIVE_SUBJ" else str(a["head_word_idx"]))
        elif a["slot"] == "PP":
            x["pp_heads"].add(str(a["head_word_idx"]))
    return out


def score(corpus: str, split: str, extract_folder: Path, *, variants: tuple[str, ...] = VARIANTS, final_test: bool = False,
          gold_dir: Path | None = None, exposure_path: Path = EX.EXPOSURE_PATH, _choice: bool = False,
          label_source: str = "silver", frozen_path: Path | None = None) -> dict:
    """Aggregate scores of one split: identification precision, extraction recall, frame metrics per variant.
    Validation / test: the clean set is primary, the full set secondary. With SILVER labels every figure is
    agreement with silver (D-061), abstained items are left out of the frame metrics (D-g), and an ``agreed_only``
    sensitivity set is added."""
    gold = load_gold(corpus, split, gold_dir=gold_dir, final_test=final_test, _choice=_choice, label_source=label_source,
                     frozen_path=frozen_path)
    if not gold:
        return {"corpus": corpus, "split": split, "n_gold": 0, "label_source": label_source, "note": "no labels yet"}
    silver = label_source == "silver"
    if final_test:
        led = _ledger(FINAL_LEDGER)
        if corpus in led:
            raise ScoreError(f"the {corpus} test split was already scored on {led[corpus]['when']}: refused (read once)")
    exposed = EX.load(exposure_path).get(corpus, set())
    first = {}
    for r in gold:                       # one row per item (agreement items have two annotators: the first one scores)
        first.setdefault(r["item_id"], r)
    sets = {"full": list(first.values())}
    if split in ("validation", "test"):
        sets["clean"] = [r for r in first.values() if r["item_id"] not in exposed]
    primary = "clean" if "clean" in sets else "full"
    if silver:
        sets["agreed_only"] = [r for r in sets[primary] if r.get("silver_status") == "agreed"]
    res = {"corpus": corpus, "split": split, "n_gold": len(first), "exposed_excluded": len(first) - len(sets.get("clean", sets["full"])),
           "primary": primary, "label_source": label_source, "sets": {},
           **({"measure": SILVER_MEASURE} if silver else {})}
    for name, all_rows in sets.items():
        abst = [r for r in all_rows if silver and SV.is_abstention(r)]
        rows = [r for r in all_rows if not (silver and SV.is_abstention(r))]
        id_rows = [r for r in all_rows if r.get("is_target_verb") in ("Y", "N")]
        keys = [r["instance_key"] for r in rows]
        ident = {"n": len(id_rows), "target_Y": sum(1 for r in id_rows if r["is_target_verb"] == "Y")}
        ident["precision"] = ident["target_Y"] / ident["n"] if ident["n"] else None
        entry = {"identification": ident, "variants": {}, **({"abstained_excluded": len(abst)} if silver else {})}
        for v in variants:
            if not (Path(extract_folder) / f"roles-{v}" / "manifest.json").exists():
                continue
            pred = _predictions(extract_folder, v, keys)
            pairs = [(_gold_frame(r), pred.get(r["instance_key"], {}).get("outcome", "MISSING")) for r in rows]
            entry["variants"][v] = frame_metrics(pairs)
            entry.setdefault("_correct", {})[v] = {r["item_id"]: g == pr for r, (g, pr) in zip(rows, pairs) if g in ("A", "B")}
            if "extraction" not in entry:
                do_hit = do_n = pp_hit = pp_n = 0
                for r in rows:
                    if r["is_target_verb"] != "Y":
                        continue
                    p = pred.get(r["instance_key"], {"do_heads": set(), "pp_heads": set()})
                    if r.get("do") and r["do"] not in ("none", "elided"):
                        do_n += 1
                        do_hit += r["do"] in p["do_heads"]
                    for pp in filter(None, (r.get("pps") or "").split(";")):
                        pp_n += 1
                        pp_hit += pp.strip().partition(":")[0] in p["pp_heads"]
                entry["extraction"] = {"do_recall": do_hit / do_n if do_n else None, "do_n": do_n,
                                       "pp_recall": pp_hit / pp_n if pp_n else None, "pp_n": pp_n}
        res["sets"][name] = entry
    if final_test:
        led = _ledger(FINAL_LEDGER)
        led[corpus] = {"when": datetime.now(timezone.utc).isoformat(timespec="seconds"), "n_gold": len(first),
                       "label_source": label_source, "extract": str(extract_folder),
                       "variants": list(res["sets"][res["primary"]]["variants"])}
        atomic_write_json(led, FINAL_LEDGER)
    return res


def choose_variant(scores_by_corpus: dict[str, dict]) -> dict:
    """The pre-registered choice (S56-v1 §5.4) on the CLEAN validation sets: the best pooled macro-F1, but a simpler
    variant (R0 < R1 < R2) wins when it is within 1 F1 point of the best or not significantly different from it by
    the exact McNemar test (gold A/B items, pooled over corpora)."""
    pooled, correct = {}, {}
    for v in VARIANTS:
        f1s = []
        for c, s in scores_by_corpus.items():
            e = s.get("sets", {}).get(s.get("primary", ""), {})
            if v in e.get("variants", {}):
                f1s.append(e["variants"][v]["macro_f1"])
                correct.setdefault(v, {}).update({f"{c}:{k}": x for k, x in e.get("_correct", {}).get(v, {}).items()})
        if f1s:
            pooled[v] = sum(f1s) / len(f1s)
    if not pooled:
        return {"chosen": None, "note": "no validation scores"}
    best = max(pooled, key=lambda v: (pooled[v], -VARIANTS.index(v)))
    chosen, tests = best, {}
    for v in VARIANTS[:VARIANTS.index(best)]:
        if v not in pooled:
            continue
        ids = sorted(set(correct.get(best, {})) & set(correct.get(v, {})))
        b = sum(1 for i in ids if correct[best][i] and not correct[v][i])
        c = sum(1 for i in ids if correct[v][i] and not correct[best][i])
        p = mcnemar_exact(b, c)
        tests[f"{best}_vs_{v}"] = {"best_only_correct": b, "simpler_only_correct": c, "p": p,
                                  "f1_difference": pooled[best] - pooled[v]}
        if pooled[best] - pooled[v] <= SIMPLER_WINS_WITHIN or p >= MCNEMAR_ALPHA:
            chosen = v
            break
    return {"pooled_macro_f1": pooled, "best": best, "chosen": chosen, "mcnemar": tests,
            "rule": f"simpler wins within {SIMPLER_WINS_WITHIN} F1 or McNemar p >= {MCNEMAR_ALPHA}"}


def choose(folders: dict[str, Path], *, ledger: Path = CHOICE_LEDGER, gold_dir: Path | None = None,
           exposure_path: Path = EX.EXPOSURE_PATH, label_source: str = "silver", frozen_path: Path | None = None) -> dict:
    """Read the validation split ONCE (per the set of corpora given) for the pre-registered variant choice."""
    led = _ledger(ledger)
    if led:
        raise ScoreError(f"the validation split was already read for the variant choice on {led.get('when')}: refused")
    scores = {c: score(c, "validation", f, gold_dir=gold_dir, exposure_path=exposure_path, _choice=True,
                       label_source=label_source, frozen_path=frozen_path) for c, f in folders.items()}
    scores = {c: s for c, s in scores.items() if s.get("n_gold")}
    if not scores:
        return {"chosen": None, "note": "no validation labels yet: nothing read, nothing recorded"}
    ch = choose_variant(scores)
    public = {c: {k: v for k, v in s.items() if k != "sets"} | {"sets": {n: {k: v for k, v in e.items() if not k.startswith("_")}
                                                                        for n, e in s["sets"].items()}} for c, s in scores.items()}
    atomic_write_json({"when": datetime.now(timezone.utc).isoformat(timespec="seconds"), "label_source": label_source,
                       "choice": ch, "scores": public}, ledger)
    return ch


# ============================================================================================ paper examples (dev)
def paper_examples(extract_folder: Path, lex: Lexicon, *, out: Path = PAPER_EXAMPLES, gold_dir: Path = G.GOLD_DIR) -> dict:
    """The paper's examples with a stated frame, as dev items (labels = the paper's frame; Mikra only). Tokens that are
    frozen validation or test items are left out (D-059 P8.3); they stay in their split, flagged in the register."""
    folder = Path(extract_folder)
    con = connect()
    inst = con.sql(f"SELECT instance_id, ref, members FROM read_parquet({_lst(_parts(folder, 'instances'))}) WHERE ref IS NOT NULL").to_arrow_table().to_pylist()
    by_ref: dict[str, list] = {}
    for r in inst:
        by_ref.setdefault(r["ref"], []).append(r)
    frozen = G.FROZEN_SAMPLES["mikra"]["sample_id"]
    sp = Path(gold_dir) / "mikra" / frozen / "sample.parquet"
    split_of = {r["instance_key"]: r["split"] for r in pq.read_table(sp, columns=["instance_key", "split"]).to_pylist()} if sp.exists() else {}
    rows, missing, excluded = [], 0, 0
    for e in lex.entries:
        for pr in e.paper_refs:
            if pr.get("frame") not in ("A", "B"):
                continue
            cands = [r for r in by_ref.get(pr.get("he"), []) if e.id in (r["members"] or [])]
            if not cands:
                missing += 1
                rows.append({"instance_key": "", "entry_id": e.id, "frame": pr["frame"], "where": pr.get("where", ""),
                             "ref": pr.get("he"), "status": "not_identified", "frozen_split": ""})
                continue
            for c in cands:
                fs = split_of.get(c["instance_id"], "")
                # the paper labels ONE token: with several tokens of the entry in the verse the label is not attributed
                st = ("excluded_frozen_" + fs if fs in ("validation", "test")
                      else "dev" if len(cands) == 1 else "ambiguous_token_in_verse")
                excluded += st.startswith("excluded_frozen")
                rows.append({"instance_key": c["instance_id"], "entry_id": e.id, "frame": pr["frame"], "where": pr.get("where", ""),
                             "ref": pr.get("he"), "status": st, "frozen_split": fs})
    rows.sort(key=lambda r: (r["entry_id"], r["ref"] or "", r["instance_key"]))
    write_csv(pa.Table.from_pylist(rows), out)
    return {"rows": len(rows), "dev_items": sum(1 for r in rows if r["status"] == "dev"), "not_identified": missing,
            "ambiguous_token_in_verse": sum(1 for r in rows if r["status"] == "ambiguous_token_in_verse"),
            "excluded_frozen_validation_or_test": excluded, "out": str(out)}


# ============================================================================================ supplement
def supplement(corpus: str, source: Source, r1_lex: Lexicon, new_lex: Lexicon, *, approval: str | None, size: int,
               git: dict, out_root: Path = G.GOLD_DIR, progress: bool = True) -> dict:
    """The supplemental sampling procedure (S56_R1.md §3): tokens identified by the NEW lexicon/forms but not by R1 and
    not in any R1 sampling population (Modern: not in R1's NONPAPER frame) form a separate population; a sample is
    drawn from it with the gold strata (+ the candidate source: lemma or form match), cap per key, hash order and the
    1:1:2 split, under a new salt and id ``<corpus>-s1-<hash>``. Refused without Ori's approval id (a decision)."""
    if not approval:
        raise ScoreError("a supplement is drawn only with Ori's approval and a decision: --approval D-0xx")
    salt = f"{METHODOLOGY}:{corpus}:supplement:s1:"
    sid = f"{corpus}-s1-" + hashlib.sha256(f"{corpus}|{r1_lex.sha256}|{new_lex.sha256}|{size}|{salt}|{SUPPLEMENT_VERSION}".encode()).hexdigest()[:10]
    out = Path(out_root) / corpus / sid
    if (out / "manifest.json").exists():
        raise ScoreError(f"{out} already exists")
    con = connect()
    con.execute(f"CREATE OR REPLACE TEMP TABLE units AS SELECT sent_id, in_full_view FROM {source.units_sql(corpus, ('sent_id', 'in_full_view'))}")
    pops = []
    for run in source.runs(corpus):
        if progress:
            print(f"  supplement {corpus}: {run.run_id}", flush=True)
        con.execute(f"CREATE OR REPLACE TEMP TABLE tok AS SELECT t.* FROM {source.tokens_sql(run, G.TREE_COLUMNS)} t "
                    "JOIN units u USING (sent_id) WHERE u.in_full_view")
        ID.register(con, r1_lex)
        con.execute(f"CREATE OR REPLACE TEMP TABLE idn1 AS {ID.identify_sql('tok')}")
        ID.register(con, new_lex)
        con.execute(f"CREATE OR REPLACE TEMP TABLE idn2 AS {ID.identify_sql('tok')}")
        con.execute("CREATE OR REPLACE TEMP TABLE nw AS SELECT n.* FROM idn2 n ANTI JOIN idn1 USING (sent_id, piece_idx, word_idx)")
        if G.DESIGN[corpus]["nonpaper"]:
            con.execute("""CREATE OR REPLACE TEMP TABLE v AS SELECT t.sent_id, t.piece_idx, t.word_idx, t.suffix, 'unknown' AS voice
                           FROM tok t SEMI JOIN nw USING (sent_id, piece_idx, word_idx) WHERE NOT t.lemma_blank""")
            con.execute(f"CREATE OR REPLACE TEMP TABLE a AS {TR.arguments_sql('v', 'tok')}")
            con.execute("""CREATE OR REPLACE TEMP TABLE np AS SELECT sent_id, piece_idx, verb_word_idx AS word_idx FROM a GROUP BY ALL
                           HAVING bool_or(slot = 'DO') AND bool_or(p_family IN ('B', 'MIN'))""")
            con.execute("CREATE OR REPLACE TEMP TABLE nw AS SELECT * FROM nw ANTI JOIN np USING (sent_id, piece_idx, word_idx)")
        pops.append(con.sql(f"""SELECT n.sent_id, n.piece_idx, n.word_idx, n.verb_key, n.members, n.match_method,
                {G._stratum_sql()} AS stratum,
                CASE WHEN n.match_method IN ('lemma', 'both') THEN 'lemma' ELSE 'form' END AS candidate_source,
                t.lemma, t.run_id, t.shard, t.doc_id,
                n.sent_id || '|' || n.piece_idx || '|' || n.word_idx AS instance_key,
                sha256('{salt}' || n.sent_id || '|' || n.piece_idx || '|' || n.word_idx) AS h
            FROM nw n JOIN tok t USING (sent_id, piece_idx, word_idx)""").to_arrow_table())
    pop = pa.concat_tables(pops)
    con.register("pop", pop)
    con.execute("CREATE OR REPLACE TEMP TABLE p2 AS SELECT *, stratum || '/' || candidate_source AS sst FROM pop WHERE stratum <> 'OTHER'")
    pk = {(r[0], r[1]): r[2] for r in con.sql("SELECT sst, verb_key, count(*) FROM p2 GROUP BY ALL").fetchall()}
    pst: dict[str, int] = {}
    for (s, _), n in pk.items():
        pst[s] = pst.get(s, 0) + n
    total = sum(pst.values())
    alloc = {s: (size * n) // total for s, n in pst.items()} if total else {}
    for s in sorted(pst, key=lambda s: -((size * pst[s]) % max(total, 1)))[: size - sum(alloc.values())] if total else []:
        alloc[s] += 1
    sel = con.sql(f"""WITH c AS (SELECT *, row_number() OVER (PARTITION BY sst, verb_key ORDER BY h) AS rk FROM p2),
                          r AS (SELECT *, row_number() OVER (PARTITION BY sst ORDER BY h) - 1 AS rank FROM c WHERE rk <= {G.CAP_PER_KEY})
                     SELECT * EXCLUDE (rk) FROM r ORDER BY sst, rank""").to_arrow_table().to_pylist()
    rows = [x for x in sel if x["rank"] < alloc.get(x["sst"], 0)]
    s_key: dict[tuple, int] = {}
    for x in rows:
        s_key[(x["sst"], x["verb_key"])] = s_key.get((x["sst"], x["verb_key"]), 0) + 1
    sampled: dict[str, int] = {}
    for (s, k) in s_key:
        sampled[s] = sampled.get(s, 0) + pk[(s, k)]
    for i, x in enumerate(rows, 1):
        x.update({"sample_id": sid, "item_id": f"{corpus[:2].upper()}S{i:04d}", "split": G.SPLITS[min(x["rank"] % 4, 2)],
                  "agreement": False, "pop_stratum": pst[x["sst"]], "pop_key": pk[(x["sst"], x["verb_key"])],
                  "weight": (pk[(x["sst"], x["verb_key"])] / s_key[(x["sst"], x["verb_key"])]) * (pst[x["sst"]] / sampled[x["sst"]])})
    cols = ["sample_id", "item_id", "instance_key", "sent_id", "piece_idx", "word_idx", "run_id", "shard", "doc_id", "verb_key",
            "members", "match_method", "lemma", "stratum", "candidate_source", "split", "agreement", "rank", "h", "pop_stratum",
            "pop_key", "weight"]
    sample = pa.Table.from_pylist([{c: x.get(c) for c in cols} for x in rows]) if rows else pa.table({c: [] for c in cols})
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_parquet(sample, out / "sample.parquet")
    write_csv(sample.drop(["h"]) if rows else sample, out / "sample.csv")
    atomic_write_parquet(pa.Table.from_pylist([{"stratum": s, "verb_key": k, "n": n} for (s, k), n in sorted(pk.items())])
                         if pk else pa.table({"stratum": [], "verb_key": [], "n": []}), out / "population.parquet")
    if rows:
        G._write_sheets(con, source, corpus, rows, out / "sheets")
    return write_manifest(out, what="supplemental gold sample (ids only + local sheets)", git=git, source=source.describe(corpus),
                          extra={"corpus": corpus, "sample_id": sid, "supplement_version": SUPPLEMENT_VERSION, "approval": approval,
                                 "supplements": G.FROZEN_SAMPLES.get(corpus, {}).get("sample_id"), "salt": salt,
                                 "r1_lexicon_sha256": r1_lex.sha256, "new_lexicon_sha256": new_lex.sha256, "size": size,
                                 "allocation": alloc, "population_by_stratum": pst, "n_items": len(rows),
                                 "by_split": {s: sum(1 for x in rows if x["split"] == s) for s in G.SPLITS},
                                 "estimation": "two strata of one design: the frozen sample (domain-restricted) + this supplement",
                                 "local_only": ["sheets/ (quote corpus text: never git, D-042)"]})
