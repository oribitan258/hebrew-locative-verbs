"""Throughput / memory / storage benchmark on Modern units outside the pilot sample.

Bounded first (300 units, configuration grid), then — only if outputs validate — scaled
(3,000 units) for the configurations that matter. Storage is measured on the real Parquet outputs.
Projections use the full-corpus whitespace-token counts from the piece census.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from hebloc.parse import models as M
from hebloc.parse.checks import validate_run
from hebloc.parse.run import RunConfig, read_run, run
from hebloc.paths import UNITS_DIR
from hebloc.pilot import PILOT_DIR
from hebloc.pilot import sample as S

BENCH_DIR = PILOT_DIR / "bench"
SEED = "m3-bench-2026"


def bench_units(n: int) -> list[tuple[str, str]]:
    excl = {r["sent_id"] for r in S.load()}
    con = duckdb.connect()
    rows = con.execute(f"""SELECT sent_id, text_norm FROM read_parquet('{(UNITS_DIR / 'modern' / '*.parquet').as_posix()}')
                           WHERE NOT is_empty_norm ORDER BY md5(sent_id || '{SEED}') LIMIT {n + 1000}""").fetchall()
    return [r for r in rows if r[0] not in excl][:n]


def _dir_bytes(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*.parquet")) if p.exists() else 0


def one(lm: M.LoadedModel, units, name: str, **cfg) -> dict:
    rdir = BENCH_DIR / name
    m = run(units, lm, rdir, RunConfig(run_id=name, variant="default", **cfg), progress=False)
    c = validate_run(rdir, expected=dict(units))
    ws = m["ws_tokens"]
    sizes = {k: _dir_bytes(rdir / k) for k in ("inputs", "pieces", "dicta_raw", "tokens")}
    return {"name": name, "model": lm.name, "threads": m["threads"], "max_batch_subwords": m["max_batch_subwords"],
            "fixes": m["fixes"], "units": m["units"], "ws_tokens": ws, "seconds": m["parse_seconds"],
            "ws_tokens_per_second": m["ws_tokens_per_second"], "peak_mem_gb": round(m["peak_mem_bytes"] / 2**30, 2),
            "status": m["status"], "checks_ok": c["ok"],
            "bytes_per_ws_token": {k: round(v / ws, 1) for k, v in sizes.items()},
            "bytes_per_ws_token_total": round(sum(sizes.values()) / ws, 1)}


def raw_equal(name_a: str, name_b: str) -> dict:
    a = {(r["sent_id"], r["piece_idx"]): r["raw_json"] for r in read_run(BENCH_DIR / name_a, "dicta_raw").to_pylist()}
    b = {(r["sent_id"], r["piece_idx"]): r["raw_json"] for r in read_run(BENCH_DIR / name_b, "dicta_raw").to_pylist()}
    keys = set(a) & set(b)
    diff = [k for k in keys if a[k] != b[k]]
    return {"pieces_compared": len(keys), "identical": len(keys) - len(diff), "differing_examples": [list(k) for k in diff[:5]]}


def save(name: str, obj) -> None:
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    (BENCH_DIR / f"{name}.json").write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
