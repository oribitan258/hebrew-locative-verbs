"""Validation of a parse run (no model needed): completeness, coverage/truncation, trees, provenance.

``validate_run`` returns a report dict; ``ok`` is True only if every check passes. The per-piece
checks are pure functions so they are unit-tested on small fixtures.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import Counter
from pathlib import Path

from hebloc.parse.run import read_run
from hebloc.parse.tokens import derive
from hebloc.pieces import Piece, verify_pieces


def _ignorable(ch: str) -> bool:
    return ch.isspace() or unicodedata.category(ch).startswith("M")


def coverage_problems(text: str, out: dict) -> list[str]:
    """Every non-whitespace character of the piece text lies in exactly one output word, in order.

    A failure here means the model dropped (e.g. truncated) or duplicated input."""
    toks = out.get("tokens") or []
    covered = [0] * len(text)
    prev_end = 0
    probs = []
    for t in toks:
        s, e = t["offsets"]["start"], t["offsets"]["end"]
        if not (0 <= s < e <= len(text)) or s < prev_end:
            probs.append(f"bad/overlapping offsets {s}-{e}")
            continue
        prev_end = e
        for i in range(s, e):
            covered[i] += 1
    missing = [i for i, ch in enumerate(text) if not _ignorable(ch) and covered[i] == 0]
    if missing:
        probs.append(f"uncovered chars: {len(missing)} (first at {missing[0]}: {text[missing[0]:missing[0] + 20]!r})")
    return probs


def tree_problems(out: dict) -> list[str]:
    toks = out.get("tokens") or []
    n = len(toks)
    if n == 0:
        return ["no tokens"]
    probs = []
    try:
        heads = [t["syntax"]["dep_head_idx"] for t in toks]
    except (KeyError, TypeError):
        return ["missing syntax"]
    roots = [i for i, h in enumerate(heads) if h == -1]
    if len(roots) != 1:
        probs.append(f"roots={len(roots)}")
    if any(not (-1 <= h < n) for h in heads):
        probs.append("head out of range")
    if any(h == i for i, h in enumerate(heads)):
        probs.append("self-loop")
    for i in range(n):  # acyclic: every word reaches the root within n steps
        j, steps = i, 0
        while j != -1 and steps <= n and 0 <= j < n:
            j, steps = heads[j], steps + 1
        if steps > n:
            probs.append("cycle")
            break
    if roots and out.get("root_idx") != roots[0]:
        probs.append("root_idx mismatch")
    for t in toks:
        if not {"seg", "lex", "morph", "syntax"} <= set(t):
            probs.append("missing annotation layer")
            break
        if "".join(t["seg"]) != t["token"]:
            probs.append("seg does not rebuild the word")
            break
    return probs


def validate_run(run_dir: Path, expected: dict[str, str] | None = None) -> dict:
    """``expected``: sent_id → text that must have been parsed (e.g. units.text_norm)."""
    inputs = read_run(run_dir, "inputs").to_pylist()
    pieces = read_run(run_dir, "pieces").to_pylist()
    raws = read_run(run_dir, "dicta_raw").to_pylist()
    texts = {r["sent_id"]: r["text"] for r in inputs}
    rep: dict = {"units": len(inputs), "pieces": len(pieces), "raw_rows": len(raws)}
    c = Counter()
    if expected is not None:
        c["units_not_in_expected"] = sum(1 for s in texts if s not in expected)
        c["expected_not_parsed"] = sum(1 for s in expected if s not in texts)
        c["text_differs_from_expected"] = sum(1 for s, t in texts.items() if s in expected and expected[s] != t)
    c["text_sha1_mismatch"] = sum(1 for r in inputs if hashlib.sha1(r["text"].encode("utf-8")).hexdigest() != r["text_sha1"])
    by_unit: dict[str, list[dict]] = {}
    for p in pieces:
        by_unit.setdefault(p["sent_id"], []).append(p)
    for sid, text in texts.items():
        ps = sorted(by_unit.get(sid, []), key=lambda p: p["piece_idx"])
        if not text.strip():
            c["empty_units_skipped"] += 1
            c["empty_unit_with_pieces"] += bool(ps)
            continue
        try:
            verify_pieces(text, [Piece(p["norm_char_start"], p["norm_char_end"], p["tok_start"], p["tok_end"], p["cost"]) for p in ps])
        except AssertionError:
            c["pieces_do_not_rebuild_text"] += 1
        if any(p["cost"] > p["budget"] for p in ps):
            c["piece_over_budget"] += 1
        if [p["piece_idx"] for p in ps] != list(range(len(ps))) or any(p["n_pieces"] != len(ps) for p in ps):
            c["piece_index_inconsistent"] += 1
    raw_keys = {(r["sent_id"], r["piece_idx"]) for r in raws}
    piece_keys = {(p["sent_id"], p["piece_idx"]) for p in pieces}
    c["pieces_without_raw"] = len(piece_keys - raw_keys)
    c["raw_without_piece"] = len(raw_keys - piece_keys)
    piece_by_key = {(p["sent_id"], p["piece_idx"]): p for p in pieces}
    status = Counter(r["status"] for r in raws)
    problem_examples = []
    for r in raws:
        if r["status"] == "error":
            continue
        p = piece_by_key.get((r["sent_id"], r["piece_idx"]))
        out = json.loads(r["raw_json"])
        ptext = texts[r["sent_id"]][p["norm_char_start"]:p["norm_char_end"]]
        if out.get("text") != ptext:
            c["raw_text_not_piece_text"] += 1
        cp, tp = coverage_problems(ptext, out), tree_problems(out)
        c["coverage_failures"] += bool(cp)
        c["model_invalid_trees"] += bool(tp)   # a property of the model output, reported not "fixed"
        for x in tp:
            c[f"model_tree:{x.split('=')[0]}"] += 1
        if (cp or tp) and len(problem_examples) < 20:
            problem_examples.append({"sent_id": r["sent_id"], "piece_idx": r["piece_idx"], "coverage": cp, "tree": tp})
    t1 = derive(run_dir, write=True)
    t2 = derive(run_dir, write=False)
    c["tokens_rederivation_differs"] = int(not t1.equals(t2))
    rep.update({"status": dict(status), "checks": dict(c), "problem_examples": problem_examples, "tokens": t1.num_rows})
    hard = ("units_not_in_expected", "expected_not_parsed", "text_differs_from_expected", "text_sha1_mismatch",
            "empty_unit_with_pieces", "pieces_do_not_rebuild_text", "piece_over_budget", "piece_index_inconsistent",
            "pieces_without_raw", "raw_without_piece", "raw_text_not_piece_text", "coverage_failures",
            "tokens_rederivation_differs")
    rep["ok"] = not any(c.get(k) for k in hard)   # pipeline integrity (not model quality)
    rep["model_invalid_tree_share"] = round(c["model_invalid_trees"] / max(1, len(raws) - status.get("error", 0)), 4)
    rep["errors_logged"] = status.get("error", 0)
    (run_dir / "checks.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return rep
