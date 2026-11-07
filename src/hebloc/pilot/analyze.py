"""Aggregate the pilot results into ``data/annotations/pilot/results/analysis.json`` (for the report)."""

from __future__ import annotations

import json
from collections import Counter, defaultdict

import pyarrow.parquet as pq

from hebloc.parse.run import read_run
from hebloc.pilot import experiments as E
from hebloc.pilot import sample as S
from hebloc.pilot.runs import run_dir


def _manifest(rid: str) -> dict:
    m = json.loads((run_dir(rid) / "run.json").read_text(encoding="utf-8"))
    c = json.loads((run_dir(rid) / "checks.json").read_text(encoding="utf-8"))
    return {"manifest": m, "checks": {k: c[k] for k in ("ok", "status", "checks", "tokens", "errors_logged", "problem_examples")}}


def mst_bug_impact() -> dict:
    """Original (unfixed) MST vs fixed: invalid trees, and how many pieces' outputs differ."""
    orig = {(r["sent_id"], r["piece_idx"]): r["raw_json"] for r in read_run(run_dir("base__default__orig_mst"), "dicta_raw").to_pylist()}
    fixed = {(r["sent_id"], r["piece_idx"]): r["raw_json"] for r in read_run(run_dir("base__default"), "dicta_raw").to_pylist()}
    keys = set(orig) & set(fixed)
    differ = [k for k in keys if orig[k] != fixed[k]]
    c = json.loads((run_dir("base__default__orig_mst") / "checks.json").read_text(encoding="utf-8"))
    return {"pieces": len(keys), "pieces_with_different_output": len(differ),
            "invalid_trees_original": c["checks"].get("model_invalid_trees", 0),
            "tree_problem_kinds_original": {k: v for k, v in c["checks"].items() if k.startswith("model_tree:")},
            "invalid_trees_fixed": json.loads((run_dir("base__default") / "checks.json").read_text(encoding="utf-8"))["checks"].get("model_invalid_trees", 0),
            "examples": c["problem_examples"][:5]}


def multi_piece_units(rid: str = "base__default") -> dict:
    pieces = read_run(run_dir(rid), "pieces").to_pylist()
    sample = {r["sent_id"]: r for r in S.load()}
    by = defaultdict(list)
    for p in pieces:
        if p["n_pieces"] > 1 and p["piece_idx"] == 0:
            r = sample[p["sent_id"]]
            by[r["corpus_id"]].append({"sent_id": p["sent_id"], "ref": r["ref"], "selection": r["selection"],
                                       "n_pieces": p["n_pieces"], "ws_tokens": int(r["n_tokens_norm"])})
    return {c: {"count": len(v), "units": sorted(v, key=lambda x: -x["ws_tokens"])[:10]} for c, v in by.items()}


def bhsa_on_pilot(rid: str) -> dict:
    mikra_ids = {r["sent_id"] for r in S.load() if r["corpus_id"] == "mikra"}
    s = E.bhsa_eval(rid, "qere", restrict=mikra_ids)
    return {k: v for k, v in s.items() if not k.startswith("_")}


def invalid_tree_cause(rid: str = "base__default") -> dict:
    """Pieces whose word-level tree is invalid, by corpus (cause analysed in M3: heads into ## pieces)."""
    from hebloc.parse.checks import tree_problems
    c = Counter()
    for r in read_run(run_dir(rid), "dicta_raw").to_pylist():
        if r["status"] != "error":
            c[r["sent_id"].split(":", 1)[0] + (":invalid" if tree_problems(json.loads(r["raw_json"])) else ":valid")] += 1
    return dict(c)


def run_all() -> dict:
    out = {
        "runs": {rid: _manifest(rid) for rid in ("base__default", "tiny__default", "base__default__orig_mst")},
        "mst_bug_impact": mst_bug_impact(),
        "invalid_trees_by_corpus": {"base": invalid_tree_cause("base__default"), "tiny": invalid_tree_cause("tiny__default")},
        "multi_piece_units_in_sample": multi_piece_units(),
        "diagnostics": {"base": E.diagnostics("base__default"), "tiny": E.diagnostics("tiny__default")},
        "base_vs_tiny_agreement": E.model_agreement("base__default", "tiny__default"),
        "bhsa_pilot_sample": {"base": bhsa_on_pilot("base__default"), "tiny": bhsa_on_pilot("tiny__default")},
        "hypotheses": E.hypotheses_report(),
    }
    return E._save("analysis", out)
