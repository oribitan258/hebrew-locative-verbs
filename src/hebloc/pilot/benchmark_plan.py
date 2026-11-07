"""Benchmark sequence: bounded grid → equivalence/invariance checks → scaled runs → projections."""

from __future__ import annotations

import json

import duckdb

from hebloc.parse import models as M
from hebloc.paths import CORPORA, UNITS_DIR
from hebloc.pilot import bench as Bn
from hebloc.pilot.experiments import RESULTS


def _stratum_tokens() -> dict:
    con = duckdb.connect()
    rows = con.execute(f"""SELECT corpus_id, stratum, count(*), sum(n_tokens_norm), sum(in_curated_view::INT),
                                  sum(CASE WHEN in_curated_view THEN n_tokens_norm ELSE 0 END)
                           FROM read_parquet('{(UNITS_DIR / '*' / '*.parquet').as_posix()}') WHERE NOT is_empty_norm
                           GROUP BY ALL ORDER BY ALL""").fetchall()
    return {f"{c}|{s}": {"units": n, "ws_tokens": int(w), "curated_units": int(cu), "curated_ws_tokens": int(cw)}
            for c, s, n, w, cu, cw in rows}


def run_all(threads_grid=(4, 8, 12)) -> dict:
    u300, u3000 = Bn.bench_units(300), Bn.bench_units(3000)
    lms = {m: M.load(m) for m in ("base", "tiny")}
    out = {"bounded": [], "checks": {}, "scaled": []}
    for m in ("base", "tiny"):
        for th in threads_grid:
            out["bounded"].append(Bn.one(lms[m], u300, f"{m}_t{th}_c1024", threads=th))
    best = {m: max((r for r in out["bounded"] if r["model"] == m), key=lambda r: r["ws_tokens_per_second"])["threads"]
            for m in ("base", "tiny")}
    out["best_threads"] = best
    for cap in (512, 2048):
        out["bounded"].append(Bn.one(lms["base"], u300, f"base_t{best['base']}_c{cap}", threads=best["base"], max_batch_subwords=cap))
    for m in ("base", "tiny"):
        out["bounded"].append(Bn.one(lms[m], u300, f"{m}_t{best[m]}_c1024_topk", threads=best[m], lex_topk=True))
        out["checks"][f"{m}_topk_equivalence"] = Bn.raw_equal(f"{m}_t{best[m]}_c1024", f"{m}_t{best[m]}_c1024_topk")
    out["bounded"].append(Bn.one(lms["base"], u300[:100], "base_b1", threads=best["base"], batch_size=1))
    out["checks"]["batch_invariance_base"] = Bn.raw_equal(f"base_t{best['base']}_c1024", "base_b1")
    out["checks"]["all_bounded_runs_valid"] = all(r["checks_ok"] for r in out["bounded"])
    Bn.save("bounded", out)
    if not out["checks"]["all_bounded_runs_valid"]:
        return out  # do not scale a parser configuration that fails validation
    for m in ("base", "tiny"):
        for topk in (False, True):
            out["scaled"].append(Bn.one(lms[m], u3000, f"{m}_scaled{'_topk' if topk else ''}", threads=best[m], lex_topk=topk))
    out["projection"] = project(out["scaled"])
    Bn.save("benchmark", out)
    return out


def project(scaled: list[dict]) -> dict:
    """Hours and GB per corpus for each scaled configuration, using sub-word throughput and the census."""
    census = json.loads((RESULTS / "piece_census.json").read_text(encoding="utf-8"))["per_corpus"]
    strata = _stratum_tokens()
    res = {"configs": {}, "strata": strata}
    for r in scaled:
        rdir = Bn.BENCH_DIR / r["name"]
        man = json.loads((rdir / "run.json").read_text(encoding="utf-8"))
        import statistics
        shard_rates = [m["subwords"] / m["seconds"] for m in
                       (json.loads(f.read_text(encoding="utf-8")) for f in sorted((rdir / "_shards").glob("*.json")))]
        sub_per_s_total = man["subwords"] / man["parse_seconds"]      # includes any system stalls
        sub_per_s = statistics.median(shard_rates)                     # robust to a stalled shard
        bpw = r["bytes_per_ws_token_total"]
        bps = bpw * man["ws_tokens"] / man["subwords"]          # bytes per sub-word
        per = {}
        for c in CORPORA:
            cc = census[c]
            # Extrapolated from Modern text: time and storage scale with sub-words (historical text
            # has more sub-words per word); long multi-piece inputs are slower per sub-word.
            per[c] = {"ws_tokens": cc["ws_tokens"], "subwords": cc["subwords"],
                      "hours": round(cc["subwords"] / sub_per_s / 3600, 1),
                      "hours_incl_stalls": round(cc["subwords"] / sub_per_s_total / 3600, 1),
                      "gb": round(cc["subwords"] * bps / 1e9, 2)}
        res["configs"][r["name"]] = {"subwords_per_second": round(sub_per_s, 1),
                                     "subwords_per_second_incl_stalls": round(sub_per_s_total, 1),
                                     "shard_subword_rates": [round(x, 1) for x in shard_rates], "ws_tokens_per_second": r["ws_tokens_per_second"],
                                     "bytes_per_ws_token": bpw, "bytes_per_subword": round(bps, 1),
                                     "peak_mem_gb": r["peak_mem_gb"], "per_corpus": per,
                                     "historical_total_hours": round(sum(per[c]["hours"] for c in CORPORA if c != "modern"), 1)}
    return res
