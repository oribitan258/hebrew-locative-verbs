"""Sharded, resumable Dicta parse runner (used by the M3 pilot; designed to be reused by M5).

A *run* parses a list of units ``(sent_id, text)`` with one pinned model and writes, under
``<run_dir>/``::

    inputs/shard-NNNNN.parquet     the exact unit texts parsed (sent_id, text, sha1)
    pieces/shard-NNNNN.parquet     PIECES_SCHEMA rows (hebloc.pieces; budget in model sub-words)
    dicta_raw/shard-NNNNN.parquet  one row per piece: status + the model's JSON output, verbatim
    _shards/shard-NNNNN.json       shard manifest, written LAST (commit marker + resume key)
    run.json                       run manifest (model revision, code commit, versions, totals)

Lossless: ``raw_json`` is ``json.dumps`` of exactly what ``BertForJointParsing.predict`` returned
(``output_style='json'``, ``per_token_ner=True``). Everything else (tokens, statistics, UD) is
derived from it; the UD styles are a deterministic function of it (verified in M3, D-008).

Robustness: parquet files are written to a temp name and renamed; a shard is skipped on resume
only if its manifest exists and its key (inputs + model + parameters) matches. A batch that fails
is retried piece by piece; a tree-decoder failure ("Stuck in endless loop") is retried with
``compute_syntax_mst=False`` and flagged ``mst_fallback``; any other failure is stored as
``status='error'`` with the message — never dropped.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hebloc.inventory import _git_commit
from hebloc.normalize import NORM_VERSION
from hebloc.parse.models import BUDGET, LoadedModel, subword_cost
from hebloc.paths import assert_not_in_corpora
from hebloc.pieces import PIECE_VERSION, PIECES_SCHEMA, piece_rows
from hebloc.segment import SEGMENT_VERSION

RUNNER_VERSION = "1"
INPUTS_SCHEMA = pa.schema([("sent_id", pa.string()), ("text", pa.string()), ("text_sha1", pa.string())])
RAW_SCHEMA = pa.schema([
    ("sent_id", pa.string()),
    ("piece_idx", pa.int16()),
    ("status", pa.string()),        # ok | mst_fallback | error
    ("compute_mst", pa.bool_()),
    ("error", pa.string()),
    ("raw_json", pa.string()),      # verbatim model output for the piece (null on error)
])


@dataclass
class RunConfig:
    run_id: str
    variant: str = "default"        # which input text was parsed (default = units.text_norm)
    budget: int = BUDGET
    batch_size: int = 32
    # Padded sub-words per batch. The lexeme head materializes ~128k-vocabulary scores per sub-word
    # (and the original code fully sorts them): ~2 MB per padded sub-word, so 1024 → ~2 GB peak.
    max_batch_subwords: int = 1024
    mst_fix: bool = True            # hebloc.parse.dicta_fixes.mst_seq_len (correctness)
    lex_topk: bool = False          # hebloc.parse.dicta_fixes.lex_topk (performance; needs approval)
    shard_size: int = 500
    threads: int | None = None
    extra: dict = field(default_factory=dict)


def _peak_mem_bytes() -> int:
    import psutil

    mi = psutil.Process().memory_info()
    return int(getattr(mi, "peak_wset", 0) or mi.rss)


def _atomic_write(table: pa.Table, path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    pq.write_table(table, tmp, compression="zstd")
    os.replace(tmp, path)


def _shard_key(lm: LoadedModel, cfg: RunConfig, units: list[tuple[str, str]]) -> str:
    h = hashlib.sha256()
    h.update(json.dumps([lm.repo, lm.revision, cfg.variant, cfg.budget, PIECE_VERSION, RUNNER_VERSION,
                         cfg.mst_fix, cfg.lex_topk]).encode())
    for sid, text in units:
        h.update(f"{sid}\t{text}\n".encode("utf-8"))
    return h.hexdigest()


def _predict(lm: LoadedModel, texts: list[str], mst: bool = True) -> list[dict]:
    import torch

    with torch.inference_mode():
        out = lm.model.predict(texts, lm.tokenizer, output_style="json", per_token_ner=True,
                               compute_syntax_mst=mst)
    return [out] if isinstance(out, dict) else out


def _parse_pieces(lm: LoadedModel, items: list[tuple[int, str, int]], cfg: RunConfig) -> dict[int, dict]:
    """items: (key, text, cost). Returns key -> {status, compute_mst, error, raw_json}."""
    results: dict[int, dict] = {}
    order = sorted(items, key=lambda x: -x[2])
    batches, cur, cur_max = [], [], 0
    for it in order:
        new_max = max(cur_max, it[2] + 2)
        if cur and (len(cur) >= cfg.batch_size or new_max * (len(cur) + 1) > cfg.max_batch_subwords):
            batches.append(cur)
            cur, new_max = [], it[2] + 2
        cur.append(it)
        cur_max = new_max
    if cur:
        batches.append(cur)
    for batch in batches:
        try:
            outs = _predict(lm, [t for _, t, _ in batch])
            for (k, _, _), o in zip(batch, outs):
                results[k] = {"status": "ok", "compute_mst": True, "error": None,
                              "raw_json": json.dumps(o, ensure_ascii=False, separators=(",", ":"))}
        except Exception:  # noqa: BLE001 — isolate the failing piece(s)
            for k, t, _ in batch:
                results[k] = _parse_single(lm, t)
    return results


def _parse_single(lm: LoadedModel, text: str) -> dict:
    try:
        o = _predict(lm, [text])[0]
        return {"status": "ok", "compute_mst": True, "error": None,
                "raw_json": json.dumps(o, ensure_ascii=False, separators=(",", ":"))}
    except Exception as e:  # noqa: BLE001
        first = f"{type(e).__name__}: {e}"
        if "Stuck in endless loop" in str(e):
            try:
                o = _predict(lm, [text], mst=False)[0]
                return {"status": "mst_fallback", "compute_mst": False, "error": first,
                        "raw_json": json.dumps(o, ensure_ascii=False, separators=(",", ":"))}
            except Exception as e2:  # noqa: BLE001
                first += f" | retry without MST: {type(e2).__name__}: {e2}"
        return {"status": "error", "compute_mst": True, "error": first[:2000], "raw_json": None}


def run(units: list[tuple[str, str]], lm: LoadedModel, run_dir: Path, cfg: RunConfig,
        progress: bool = True) -> dict:
    """Parse ``units`` = [(sent_id, text)] into ``run_dir`` (resumable). Returns the run manifest."""
    import torch
    import transformers

    from hebloc.parse import dicta_fixes

    assert_not_in_corpora(run_dir)
    fixes = dicta_fixes.apply(mst_seq_len=cfg.mst_fix, lex_topk=cfg.lex_topk)
    if cfg.threads:
        torch.set_num_threads(cfg.threads)
    for sub in ("inputs", "pieces", "dicta_raw", "_shards"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
    if len({s for s, _ in units}) != len(units):
        raise ValueError("duplicate sent_id in run input")
    cost = subword_cost(lm.tokenizer)
    cost_unit = f"{lm.model_id}:subword"
    shards = [units[i:i + cfg.shard_size] for i in range(0, len(units), cfg.shard_size)]
    t_run = time.perf_counter()
    bar = None
    if progress:
        from tqdm import tqdm
        bar = tqdm(total=len(units), desc=f"parse:{cfg.run_id}", unit="unit")
    for si, shard in enumerate(shards):
        name = f"shard-{si:05d}"
        key = _shard_key(lm, cfg, shard)
        mpath = run_dir / "_shards" / f"{name}.json"
        if mpath.exists() and json.loads(mpath.read_text(encoding="utf-8")).get("key") == key:
            if bar:
                bar.update(len(shard))
            continue
        t0 = time.perf_counter()
        inputs, pieces, items, meta = [], [], [], {}
        for sid, text in shard:
            inputs.append({"sent_id": sid, "text": text, "text_sha1": hashlib.sha1(text.encode("utf-8")).hexdigest()})
            for r in piece_rows(sid, text, cfg.budget, cost, cost_unit):
                pieces.append(r)
                k = len(items)
                items.append((k, text[r["norm_char_start"]:r["norm_char_end"]], r["cost"]))
                meta[k] = (sid, r["piece_idx"])
        res = _parse_pieces(lm, items, cfg)
        raw = [{"sent_id": meta[k][0], "piece_idx": meta[k][1], **res[k]} for k in range(len(items))]
        seconds = time.perf_counter() - t0
        _atomic_write(pa.Table.from_pylist(inputs, schema=INPUTS_SCHEMA), run_dir / "inputs" / f"{name}.parquet")
        _atomic_write(pa.Table.from_pylist(pieces, schema=PIECES_SCHEMA), run_dir / "pieces" / f"{name}.parquet")
        _atomic_write(pa.Table.from_pylist(raw, schema=RAW_SCHEMA), run_dir / "dicta_raw" / f"{name}.parquet")
        sm = {"key": key, "units": len(shard), "pieces": len(pieces),
              "units_empty": sum(1 for _, t in shard if not t.strip()),
              "multi_piece_units": len({p["sent_id"] for p in pieces if p["n_pieces"] > 1}),
              "ws_tokens": sum(len(t.split()) for _, t in shard), "subwords": sum(p["cost"] for p in pieces),
              "status": {s: sum(1 for r in raw if r["status"] == s) for s in ("ok", "mst_fallback", "error")},
              "seconds": round(seconds, 3), "peak_mem_bytes": _peak_mem_bytes()}
        tmp = mpath.with_suffix(".tmp")
        tmp.write_text(json.dumps(sm, indent=1), encoding="utf-8")
        os.replace(tmp, mpath)
        if bar:
            bar.update(len(shard))
    if bar:
        bar.close()
    shard_ms = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((run_dir / "_shards").glob("*.json"))]
    tot = lambda k: sum(m[k] for m in shard_ms)  # noqa: E731
    manifest = {
        "run_id": cfg.run_id, "variant": cfg.variant, "runner_version": RUNNER_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code_commit": _git_commit(), "model": lm.name, "repo": lm.repo, "revision": lm.revision,
        "norm_version": NORM_VERSION, "segment_version": SEGMENT_VERSION, "piece_version": PIECE_VERSION,
        "fixes": fixes, "budget": cfg.budget, "cost_unit": cost_unit, "batch_size": cfg.batch_size,
        "max_batch_subwords": cfg.max_batch_subwords, "shard_size": cfg.shard_size,
        "threads": torch.get_num_threads(), "torch": torch.__version__, "transformers": transformers.__version__,
        "python": platform.python_version(), "machine": platform.processor(),
        "shards": len(shard_ms), "units": tot("units"), "units_empty": tot("units_empty"), "pieces": tot("pieces"),
        "multi_piece_units": tot("multi_piece_units"), "ws_tokens": tot("ws_tokens"), "subwords": tot("subwords"),
        "status": {s: sum(m["status"][s] for m in shard_ms) for s in ("ok", "mst_fallback", "error")},
        "parse_seconds": round(tot("seconds"), 2), "wall_seconds_this_session": round(time.perf_counter() - t_run, 2),
        "peak_mem_bytes": max(m["peak_mem_bytes"] for m in shard_ms) if shard_ms else 0,
        "extra": cfg.extra,
    }
    manifest["ws_tokens_per_second"] = round(manifest["ws_tokens"] / manifest["parse_seconds"], 1) if manifest["parse_seconds"] else None
    (run_dir / "run.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def read_run(run_dir: Path, part: str) -> pa.Table:
    files = sorted((run_dir / part).glob("shard-*.parquet"))
    return pa.concat_tables([pq.read_table(f) for f in files]) if files else pa.table({})
