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

from hebloc.parse.tokens import derive
from hebloc.store.io import atomic_write_json
from hebloc.pieces import Piece, verify_pieces


def _ignorable(ch: str) -> bool:
    return ch.isspace() or unicodedata.category(ch).startswith("M")


DIAERESIS = "¨"


def _excused_diaeresis(text: str, i: int, spans: set[tuple[int, int]]) -> bool:
    """D-043: the ONLY excused uncovered character. Dicta's tokenizer turns a pair "¨¨" (U+00A8,
    forum-signature decoration such as ".·:*¨¨*:·.") into one [UNK] word whose offsets cover just
    the SECOND "¨". Excused iff text[i] and text[i+1] are both U+00A8 and text[i+1] is exactly one
    output word. Anything else uncovered (single/triple "¨", letters, truncation) still fails."""
    return (text[i] == DIAERESIS and i + 1 < len(text) and text[i + 1] == DIAERESIS
            and (i + 1, i + 2) in spans)


def coverage_problems(text: str, out: dict, excused: list[int] | None = None) -> list[str]:
    """Every non-whitespace character of the piece text lies in exactly one output word, in order.

    A failure here means the model dropped (e.g. truncated) or duplicated input. The single
    verified tokenizer artifact of D-043 is not a failure; its positions are appended to
    ``excused`` (when given) so that they are counted and reported, never silently ignored."""
    toks = out.get("tokens") or []
    covered = [0] * len(text)
    prev_end = 0
    probs = []
    spans = set()
    for t in toks:
        s, e = t["offsets"]["start"], t["offsets"]["end"]
        if not (0 <= s < e <= len(text)) or s < prev_end:
            probs.append(f"bad/overlapping offsets {s}-{e}")
            continue
        prev_end = e
        spans.add((s, e))
        for i in range(s, e):
            covered[i] += 1
    missing = [i for i, ch in enumerate(text) if not _ignorable(ch) and covered[i] == 0]
    ok = [i for i in missing if _excused_diaeresis(text, i, spans)]
    if excused is not None:
        excused.extend(ok)
    missing = [i for i in missing if i not in ok]
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


def _check_shard(inputs: list[dict], pieces: list[dict], raws: list[dict], expected: dict[str, str] | None,
                 c: Counter, status: Counter, problem_examples: list) -> None:
    """All per-unit/per-piece checks for one shard (every piece of a unit is in the unit's shard)."""
    texts = {r["sent_id"]: r["text"] for r in inputs}
    if expected is not None:
        c["units_not_in_expected"] += sum(1 for s in texts if s not in expected)
        c["text_differs_from_expected"] += sum(1 for s, t in texts.items() if s in expected and expected[s] != t)
    c["text_sha1_mismatch"] += sum(1 for r in inputs if hashlib.sha1(r["text"].encode("utf-8")).hexdigest() != r["text_sha1"])
    by_unit: dict[str, list[dict]] = {}
    for p in pieces:
        by_unit.setdefault(p["sent_id"], []).append(p)
    c["pieces_of_unknown_unit"] += sum(1 for s in by_unit if s not in texts)
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
    piece_by_key = {(p["sent_id"], p["piece_idx"]): p for p in pieces}
    c["pieces_without_raw"] += len(piece_by_key.keys() - raw_keys)
    c["raw_without_piece"] += len(raw_keys - piece_by_key.keys())
    status.update(r["status"] for r in raws)
    for r in raws:
        p = piece_by_key.get((r["sent_id"], r["piece_idx"]))
        if r["status"] == "error" or p is None:
            continue
        out = json.loads(r["raw_json"])
        ptext = texts[r["sent_id"]][p["norm_char_start"]:p["norm_char_end"]]
        if out.get("text") != ptext:
            c["raw_text_not_piece_text"] += 1
        excused: list[int] = []
        cp, tp = coverage_problems(ptext, out, excused), tree_problems(out)
        c["coverage_failures"] += bool(cp)
        if excused:   # D-043: reported, not a failure
            c["coverage_excused_diaeresis_pairs"] += len(excused)
            c["coverage_excused_pieces"] += 1
        c["model_invalid_trees"] += bool(tp)   # a property of the model output, reported not "fixed"
        for x in tp:
            c[f"model_tree:{x.split('=')[0]}"] += 1
        if (cp or tp) and len(problem_examples) < 20:
            problem_examples.append({"sent_id": r["sent_id"], "piece_idx": r["piece_idx"], "coverage": cp, "tree": tp})


def _duplicates(run_dir: Path, part: str, key: str, shards: list[str]) -> int:
    """Rows whose key occurs more than once ACROSS the run (DuckDB, bounded memory)."""
    import duckdb

    from hebloc.store.io import sql_list

    files = [run_dir / part / f"{s}.parquet" for s in shards]
    if not files:
        return 0
    return duckdb.connect().execute(
        f"SELECT count(*) - count(DISTINCT ({key})) FROM read_parquet({sql_list(files)})").fetchone()[0]


def run_fingerprint(run_dir: Path) -> str:
    """Identity of a run's committed content: shard names + shard keys (inputs, model, parameters)
    + tokens version. ``checks.json`` stores it, so a later check can tell whether the stored
    report still describes the run on disk without re-validating everything."""
    from hebloc.parse.tokens import TOKENS_VERSION

    h = hashlib.sha256(f"tokens={TOKENS_VERSION}\n".encode())
    for p in sorted((Path(run_dir) / "_shards").glob("shard-*.json")):
        h.update(f"{p.stem}\t{json.loads(p.read_text(encoding='utf-8')).get('key')}\n".encode())
    return h.hexdigest()


HARD_CHECKS = ("units_not_in_expected", "expected_not_parsed", "text_differs_from_expected", "text_sha1_mismatch",
               "empty_unit_with_pieces", "pieces_do_not_rebuild_text", "piece_over_budget", "piece_index_inconsistent",
               "pieces_without_raw", "raw_without_piece", "pieces_of_unknown_unit", "raw_text_not_piece_text",
               "coverage_failures", "tokens_rederivation_differs", "duplicate_sent_id", "duplicate_piece_key",
               "uncommitted_part_files", "shard_part_missing", "tokens_missing")


def validate_run(run_dir: Path, expected: dict[str, str] | None = None, write: bool = True,
                 derive_tokens: bool = True) -> dict:
    """Validate a run shard by shard (bounded memory). ``expected``: sent_id → text that must have
    been parsed (e.g. units.text_norm). Also (re)derives ``tokens`` incrementally and checks that
    the stored tokens equal a fresh derivation. ``write``: store the report as ``checks.json``.
    ``derive_tokens=False`` makes the validation read-only (missing tokens are then a failure)."""
    import pyarrow.parquet as pq

    from hebloc.parse.tokens import derive_shard

    run_dir = Path(run_dir)
    shards = sorted(p.stem for p in (run_dir / "_shards").glob("shard-*.json"))
    c, status, problem_examples = Counter(), Counter(), []
    n = Counter()
    parsed: set[str] | None = set() if expected is not None else None
    for part in ("inputs", "pieces", "dicta_raw"):
        present = {p.stem for p in (run_dir / part).glob("shard-*.parquet")}
        c["uncommitted_part_files"] += len(present - set(shards))
        c["shard_part_missing"] += len(set(shards) - present)
    if c["shard_part_missing"]:
        shards = [s for s in shards if all((run_dir / part / f"{s}.parquet").exists()
                                           for part in ("inputs", "pieces", "dicta_raw"))]
    if derive_tokens:
        derive(run_dir)                  # incremental: only stale/missing shards are written
    for s in shards:
        inputs, pieces, raws = (pq.read_table(run_dir / part / f"{s}.parquet").to_pylist()
                                for part in ("inputs", "pieces", "dicta_raw"))
        n["units"] += len(inputs)
        n["pieces"] += len(pieces)
        n["raw_rows"] += len(raws)
        if parsed is not None:
            parsed.update(r["sent_id"] for r in inputs)
        _check_shard(inputs, pieces, raws, expected, c, status, problem_examples)
        tpath = run_dir / "tokens" / f"{s}.parquet"
        if not tpath.exists():
            c["tokens_missing"] += 1
            continue
        stored = pq.read_table(tpath)
        c["tokens_rederivation_differs"] += int(not stored.equals(derive_shard(run_dir, s)))
        n["tokens"] += stored.num_rows
    if expected is not None:
        c["expected_not_parsed"] = sum(1 for s in expected if s not in parsed)
    c["duplicate_sent_id"] = _duplicates(run_dir, "inputs", "sent_id", shards)
    c["duplicate_piece_key"] = _duplicates(run_dir, "pieces", "sent_id, piece_idx", shards)
    rep: dict = {"units": n["units"], "pieces": n["pieces"], "raw_rows": n["raw_rows"], "shards": len(shards),
                 "status": dict(status), "checks": {k: v for k, v in c.items()},
                 "problem_examples": problem_examples, "tokens": n["tokens"]}
    rep["ok"] = not any(c.get(k) for k in HARD_CHECKS)   # pipeline integrity (not model quality)
    rep["model_invalid_tree_share"] = round(c["model_invalid_trees"] / max(1, n["raw_rows"] - status.get("error", 0)), 4)
    rep["errors_logged"] = status.get("error", 0)
    rep["fingerprint"] = run_fingerprint(run_dir)
    if write:
        atomic_write_json(rep, run_dir / "checks.json")
    return rep
