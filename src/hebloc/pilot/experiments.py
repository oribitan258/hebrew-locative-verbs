"""M3 experiments: normalization hypotheses (D-018), BHSA agreement, base vs tiny, piece census,
descriptive quality diagnostics. Results are written to ``data/annotations/pilot/results/*.json``
and summarized in ``docs/pilot_report.md``. Defaults in ``hebloc.normalize`` are never changed.
"""

from __future__ import annotations

import difflib
import json
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

from hebloc import units as U
from hebloc.catalog import DOCUMENTS_PATH, documents
from hebloc.data import iter_units
from hebloc.parse import models as M
from hebloc.parse.checks import validate_run
from hebloc.parse.run import RunConfig, run
from hebloc.paths import CORPORA, UNITS_DIR
from hebloc.pilot import PILOT_DIR
from hebloc.pilot import bhsa as B
from hebloc.pilot import variants as V
from hebloc.pilot.runs import run_dir

RESULTS = PILOT_DIR / "results"
SEED = "m3-hypotheses-2026"


def _save(name: str, obj) -> dict:
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{name}.json").write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return obj


def _con():
    con = duckdb.connect()
    con.execute(f"CREATE VIEW u AS SELECT * FROM read_parquet('{(UNITS_DIR / '*' / '*.parquet').as_posix()}')")
    return con


# ------------------------------------------------------------------ hypothesis input sets

def mikra_sets() -> dict[str, list[tuple]]:
    con = _con()
    cols = "sent_id, ref, text_raw, text_norm, text_norm_alt"
    kq = con.execute(f"SELECT {cols} FROM u WHERE corpus_id='mikra' AND text_norm_alt IS NOT NULL ORDER BY sent_id").fetchall()
    h500 = con.execute(f"""SELECT {cols} FROM u WHERE corpus_id='mikra' AND NOT is_empty_norm
                           ORDER BY md5(sent_id || '{SEED}') LIMIT 500""").fetchall()
    return {"kq": kq, "h500": h500}


def run_variants(lm_base: M.LoadedModel, lm_tiny: M.LoadedModel | None = None, threads: int = 8) -> dict:
    sets = mikra_sets()
    defaults = V.check_mikra_defaults([(r[2], r[3], r[4]) for r in _con().execute(
        "SELECT sent_id, ref, text_raw, text_norm, text_norm_alt FROM u WHERE corpus_id='mikra'").fetchall()])
    jobs = [
        ("base__mikra_kq_qere", lm_base, [(r[0], r[3]) for r in sets["kq"]]),
        ("base__mikra_kq_ketiv", lm_base, [(r[0], r[4]) for r in sets["kq"]]),
        ("base__mikra_h500_default", lm_base, [(r[0], r[3]) for r in sets["h500"]]),
        ("base__mikra_h500_maqaf_keep", lm_base, [(r[0], V.mikra_text(r[2], maqaf="keep")) for r in sets["h500"]]),
        ("base__mikra_h500_sofpasuq_drop", lm_base, [(r[0], V.mikra_text(r[2], sof_pasuq="drop")) for r in sets["h500"]]),
        ("base__mikra_voc60", lm_base, [(r[0], V.mikra_text(r[2], strip_points=False)) for r in sets["h500"][:60]]),
    ]
    if lm_tiny is not None:
        jobs.append(("tiny__mikra_h500_default", lm_tiny, [(r[0], r[3]) for r in sets["h500"]]))
    out = {"defaults_reproduced": defaults, "runs": {}}
    for rid, lm, units in jobs:
        m = run(units, lm, run_dir(rid), RunConfig(run_id=rid, variant=rid.split("__", 1)[1], threads=threads))
        c = validate_run(run_dir(rid), expected=dict(units))
        out["runs"][rid] = {"units": m["units"], "status": m["status"], "checks_ok": c["ok"], "checks": c["checks"]}
    return _save("variant_runs", out)


# ------------------------------------------------------------------ diacritics (exhaustive)

def diacritics_tokenizer_test(lm: M.LoadedModel, name: str = "diacritics_tokenizer") -> dict:
    """Every unit whose normalization stripped points: does the model input change if we keep them?"""
    con = _con()
    docs = {d["doc_id"]: d for d in documents(None, view="full", columns=U.DOC_COLUMNS).to_dict("records")}
    rows = con.execute("""SELECT corpus_id, sent_id, doc_id, k, text_raw, text_norm, norm_flags FROM u
                          WHERE list_contains(norm_flags, 'diacritics_stripped')""").fetchall()
    tok = lm.tokenizer
    res: dict[str, Counter] = defaultdict(Counter)
    examples = []
    batch: list[tuple] = []

    def flush():
        a = tok([b[2] for b in batch])["input_ids"]
        n = tok([b[3] for b in batch])["input_ids"]
        for (cid, sid, voc, norm), x, y in zip(batch, a, n):
            same = x == y
            res[cid]["identical_input_ids" if same else "different_input_ids"] += 1
            if not same and len(examples) < 10:
                examples.append({"sent_id": sid, "vocalized": voc[:200], "norm": norm[:200],
                                 "voc_tokens": tok.convert_ids_to_tokens(x)[:40], "norm_tokens": tok.convert_ids_to_tokens(y)[:40]})
        batch.clear()

    for cid, sid, doc_id, k, raw, norm, flags in rows:
        if cid == "mikra":
            voc = V.mikra_text(raw, strip_points=False)
        else:
            with V.points_kept():
                voc = U._normalize(docs[doc_id], raw, line_start=(k == 0),
                                   first_text_line="haaretz_header_removed" in flags).text
        if V.strip_points(voc) != norm:
            res[cid]["variant_not_reconstructible"] += 1
            continue
        batch.append((cid, sid, voc, norm))
        if len(batch) >= 2000:
            flush()
    if batch:
        flush()
    return _save(name, {"per_corpus": {k: dict(v) for k, v in res.items()}, "examples": examples,
                                         "tokenizer": lm.model_id})


def compare_outputs_ignoring_offsets(rid_a: str, rid_b: str) -> dict:
    """Do two runs give the same analyses word by word (offsets/text excluded)?"""
    def load(rid):
        t = pq.read_table(run_dir(rid) / "tokens" / "tokens.parquet").to_pylist()
        d = defaultdict(list)
        for r in t:
            d[r["sent_id"]].append((r["form"], r["prefix"], r["lemma"], r["upos"], r["feats"], r["suffix"], r["head"], r["deprel"]))
        return d
    a, b = load(rid_a), load(rid_b)
    common = sorted(set(a) & set(b))
    same = sum(1 for s in common if a[s] == b[s])
    return {"units_compared": len(common), "identical_units": same}


# ------------------------------------------------------------------ BHSA evaluation

_BHSA_CACHE: dict = {}


def _bhsa_index():
    if not _BHSA_CACHE:
        t = B.build_words()
        bm = B.book_map(sorted(documents("mikra", columns=["work"]).work), sorted(set(t.column("book").to_pylist())))
        _BHSA_CACHE["idx"] = B.verse_words_index(t, bm)
    return _BHSA_CACHE["idx"]


def _run_tokens_by_unit(rid: str) -> dict[str, list[dict]]:
    d = defaultdict(list)
    for r in pq.read_table(run_dir(rid) / "tokens" / "tokens.parquet").to_pylist():
        d[r["sent_id"]].append(r)
    return d


def _refs(sent_ids) -> dict[str, str]:
    con = _con()
    return dict(con.execute(f"SELECT sent_id, ref FROM u WHERE corpus_id='mikra' AND sent_id IN ({','.join(repr(s) for s in sent_ids)})").fetchall())


def bhsa_eval(rid: str, reading: str = "qere", min_align: float = 0.8, restrict: set[str] | None = None) -> dict:
    idx = _bhsa_index()
    toks = _run_tokens_by_unit(rid)
    toks = {s: v for s, v in toks.items() if s.startswith("mikra:") and (restrict is None or s in restrict)}
    refs = _refs(toks)
    rows, n_b, n_d, excluded, per_verse = [], 0, 0, [], {}
    for sid, ts in toks.items():
        words = idx.get(refs[sid], [])
        bg = B.ortho_groups(words, reading)
        dg = B.dicta_groups(ts)
        pairs = B.align(dg, bg)
        ratio = len(pairs) / max(len(bg), 1)
        if not words or ratio < min_align:
            excluded.append({"sent_id": sid, "ref": refs[sid], "align_ratio": round(ratio, 3)})
            continue
        n_b += len(bg)
        n_d += len(dg)
        cmp = B.compare(pairs)
        per_verse[sid] = cmp
        rows += cmp
    s = B.summarize(rows, n_b, n_d)
    s.update({"run": rid, "reading": reading, "verses": len(toks), "verses_excluded_low_alignment": len(excluded),
              "excluded_examples": excluded[:15]})
    s["_rows"] = rows
    s["_per_verse"] = per_verse
    return s


def _strip(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def stability(rid_a: str, rid_b: str) -> dict:
    """Share of words (aligned by consonantal form) whose analysis is identical in two runs."""
    a, b = _run_tokens_by_unit(rid_a), _run_tokens_by_unit(rid_b)
    c = Counter()
    for sid in set(a) & set(b):
        ga, gb = B.dicta_groups(a[sid]), B.dicta_groups(b[sid])
        sm = difflib.SequenceMatcher(a=[g["cons"] for g in ga], b=[g["cons"] for g in gb], autojunk=False)
        for blk in sm.get_matching_blocks():
            for i in range(blk.size):
                x, y = ga[blk.a + i]["host"], gb[blk.b + i]["host"]
                c["words"] += 1
                c["same_upos"] += x["upos"] == y["upos"]
                c["same_lemma"] += x["lemma"] == y["lemma"]
                c["same_deprel"] += x["deprel"] == y["deprel"]
                c["same_all"] += (x["upos"], x["lemma"], x["deprel"], x["feats"]) == (y["upos"], y["lemma"], y["deprel"], y["feats"])
        c["unaligned_a"] += len(ga) - sum(blk.size for blk in sm.get_matching_blocks())
    n = c["words"] or 1
    return {"words_aligned": c["words"], **{k: round(c[k] / n, 4) for k in ("same_upos", "same_lemma", "same_deprel", "same_all")},
            "unaligned_words_a": c["unaligned_a"]}


def hypotheses_report() -> dict:
    out = {}
    # Qere vs Ketiv: overall agreement, agreement on K/Q words, and stability of the rest
    q = bhsa_eval("base__mikra_kq_qere", "qere")
    k = bhsa_eval("base__mikra_kq_ketiv", "ketiv")
    kq_only = lambda s: B.summarize([r for r in s["_rows"] if r["is_kq"]], 1, 1)["hebrew"]  # noqa: E731
    out["ketiv_qere"] = {"qere_run": _strip(q), "ketiv_run": _strip(k),
                         "kq_words_qere_vs_bhsa": kq_only(q), "kq_words_ketiv_vs_bhsa": kq_only(k),
                         "stability_non_kq_words": stability("base__mikra_kq_qere", "base__mikra_kq_ketiv")}
    for name, rid in (("maqaf_keep", "base__mikra_h500_maqaf_keep"), ("sofpasuq_drop", "base__mikra_h500_sofpasuq_drop")):
        out[name] = {"default_vs_bhsa": _strip(bhsa_eval("base__mikra_h500_default")),
                     "variant_vs_bhsa": _strip(bhsa_eval(rid)),
                     "stability_vs_default": stability("base__mikra_h500_default", rid)}
    out["diacritics_parse_check"] = compare_outputs_ignoring_offsets("base__mikra_h500_default", "base__mikra_voc60")
    if (run_dir("tiny__mikra_h500_default") / "tokens").exists():
        out["base_vs_tiny_bhsa"] = {"base": _strip(bhsa_eval("base__mikra_h500_default")),
                                    "tiny": _strip(bhsa_eval("tiny__mikra_h500_default"))}
    return _save("hypotheses", out)


# ------------------------------------------------------------------ base vs tiny, diagnostics

def _corpus_of(rid: str) -> dict[str, str]:
    from hebloc.parse.run import read_run
    return {s: s.split(":", 1)[0] for s in read_run(run_dir(rid), "inputs").column("sent_id").to_pylist()}


def tree_depths(tokens: list[dict]) -> dict[tuple[str, int], int]:
    """Depth (nodes on the longest root→leaf path; root = 1) per (sent_id, piece)."""
    by = defaultdict(list)
    for t in tokens:
        by[(t["sent_id"], t["piece_idx"])].append(t)
    out = {}
    for key, ts in by.items():
        heads = [t["head"] for t in sorted(ts, key=lambda t: t["word_idx"])]
        memo = {}

        def depth(i, guard=0):
            if i in memo:
                return memo[i]
            h = heads[i]
            d = 1 if h == -1 or guard > len(heads) else 1 + depth(h, guard + 1)
            memo[i] = d
            return d
        out[key] = max(depth(i) for i in range(len(heads)))
    return out


def diagnostics(rid: str) -> dict:
    toks = pq.read_table(run_dir(rid) / "tokens" / "tokens.parquet").to_pylist()
    meta = _corpus_of(rid)
    depths = tree_depths(toks)
    by_c = defaultdict(list)
    for t in toks:
        by_c[meta[t["sent_id"]]].append(t)
    pieces = pq.read_table(str(run_dir(rid) / "pieces")).to_pylist()
    npieces = {p["sent_id"]: p["n_pieces"] for p in pieces}
    out = {}
    for c in CORPORA:
        ts = by_c.get(c, [])
        units = {t["sent_id"] for t in ts}
        if not ts:
            continue
        single = [d for (s, _), d in depths.items() if meta[s] == c and npieces[s] == 1]
        multi_units = [s for s in units if npieces[s] > 1]
        words_per_unit = Counter(t["sent_id"] for t in ts)
        out[c] = {
            "units": len(units), "words": len(ts),
            "multi_piece_units": len(multi_units),
            "mean_words_single": round(sum(words_per_unit[s] for s in units if npieces[s] == 1) / max(1, len(units) - len(multi_units)), 1),
            "mean_words_multi": round(sum(words_per_unit[s] for s in multi_units) / max(1, len(multi_units)), 1) if multi_units else None,
            "mean_depth_single_piece": round(sum(single) / len(single), 2) if single else None,
            "lemma_blank_rate": round(sum(t["lemma_blank"] for t in ts) / len(ts), 4),
            "unk_rate": round(sum("[UNK]" in (t["form"] or "") or t["form"] == "unk" for t in ts) / len(ts), 4),
            "punct_rate": round(sum(t["upos"] == "PUNCT" for t in ts) / len(ts), 4),
            "prefix_rate": round(sum(t["prefix"] is not None for t in ts) / len(ts), 4),
            "suffix_rate": round(sum(t["suffix"] is not None for t in ts) / len(ts), 4),
            "root_upos": Counter(t["upos"] for t in ts if t["head"] == -1).most_common(6),
            "upos_top": Counter(t["upos"] for t in ts).most_common(8),
            "deprel_top": Counter(t["deprel"] for t in ts).most_common(8),
        }
    return out


def model_agreement(rid_a: str, rid_b: str) -> dict:
    """Word-level agreement between two runs over the same texts (same tokenization required)."""
    a, b = _run_tokens_by_unit(rid_a), _run_tokens_by_unit(rid_b)
    corpus = _corpus_of(rid_a)
    c = defaultdict(Counter)
    for sid in set(a) & set(b):
        x, y = a[sid], b[sid]
        cc = c[corpus[sid]]
        if [t["surface"] for t in x] != [t["surface"] for t in y]:
            cc["units_different_tokenization"] += 1
            continue
        for s, t in zip(x, y):
            cc["words"] += 1
            cc["upos"] += s["upos"] == t["upos"]
            cc["lemma"] += s["lemma"] == t["lemma"]
            cc["prefix"] += s["prefix"] == t["prefix"]
            cc["head"] += s["head_sent"] == t["head_sent"]
            cc["head_deprel"] += (s["head_sent"], s["deprel"]) == (t["head_sent"], t["deprel"])
    return {k: {m: (round(v[m] / v["words"], 4) if m not in ("words", "units_different_tokenization") else v[m])
                for m in ("words", "upos", "lemma", "prefix", "head", "head_deprel", "units_different_tokenization")}
            for k, v in c.items()}


# ------------------------------------------------------------------ piece census (all units)

def piece_census(lm: M.LoadedModel, budget: int = M.BUDGET, batch: int = 4096) -> dict:
    """Sub-word length of EVERY unit with the model tokenizer: how many need > 1 piece (D-021)."""
    tok = lm.tokenizer
    out = {}
    for c in CORPORA:
        n = multi = sub_total = 0
        multi_words = 0
        words_total = 0
        hist = Counter()
        for rb in iter_units(c, columns=["text_norm", "n_tokens_norm", "is_empty_norm"], batch_size=batch):
            d = rb.to_pydict()
            texts = [t for t, e in zip(d["text_norm"], d["is_empty_norm"]) if not e]
            ws = [w for w, e in zip(d["n_tokens_norm"], d["is_empty_norm"]) if not e]
            lens = [len(x) for x in tok(texts, add_special_tokens=False)["input_ids"]]
            for L, w in zip(lens, ws):
                n += 1
                sub_total += L
                words_total += w
                hist[min(L // 64, 16)] += 1
                if L > budget:
                    multi += 1
                    multi_words += w
        out[c] = {"units": n, "subwords": sub_total, "ws_tokens": words_total,
                  "subwords_per_ws_token": round(sub_total / max(words_total, 1), 3),
                  "units_over_budget": multi, "share_units_over_budget": round(multi / max(n, 1), 6),
                  "ws_tokens_in_units_over_budget": multi_words,
                  "share_tokens_in_units_over_budget": round(multi_words / max(words_total, 1), 5),
                  "subword_length_hist_64": {f"{k * 64}-{k * 64 + 63}" if k < 16 else "1024+": v for k, v in sorted(hist.items())}}
    return _save("piece_census", {"budget": budget, "tokenizer": lm.model_id, "per_corpus": out})
