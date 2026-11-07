"""Pilot parse runs over the sample (default inputs = units.text_norm) and their validation."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from hebloc.parse import models as M
from hebloc.parse.checks import validate_run
from hebloc.parse.run import RunConfig, run
from hebloc.paths import UNITS_DIR
from hebloc.pilot import PILOT_DIR
from hebloc.pilot import sample as S


def unit_rows(sent_ids: list[str], columns: str = "sent_id, text_norm") -> list[tuple]:
    con = duckdb.connect()
    con.execute("CREATE TEMP TABLE ids (sent_id VARCHAR, ord INTEGER)")
    con.executemany("INSERT INTO ids VALUES (?, ?)", [(s, i) for i, s in enumerate(sent_ids)])
    rows = con.execute(f"""SELECT {columns} FROM read_parquet('{(UNITS_DIR / '*' / '*.parquet').as_posix()}') u
                           JOIN ids USING (sent_id) ORDER BY ids.ord""").fetchall()
    if len(rows) != len(sent_ids):
        raise KeyError(f"{len(sent_ids) - len(rows)} sample units not found in data/units")
    return rows


def sample_ids(limit_per_corpus: int | None = None) -> list[str]:
    rows = S.load()
    if limit_per_corpus is None:
        return [r["sent_id"] for r in rows]
    out, seen = [], {}
    for r in rows:
        if r["selection"] == "random" and seen.get(r["corpus_id"], 0) < limit_per_corpus:
            seen[r["corpus_id"]] = seen.get(r["corpus_id"], 0) + 1
            out.append(r["sent_id"])
    return out


def run_default(model: str, run_id: str | None = None, limit_per_corpus: int | None = None,
                lm: M.LoadedModel | None = None, **cfg) -> tuple[dict, dict]:
    """Parse the sample's text_norm with ``model``; validate against units.text_norm."""
    ids = sample_ids(limit_per_corpus)
    units = [(s, t) for s, t in unit_rows(ids)]
    run_id = run_id or f"{model}__default" + (f"__smoke{limit_per_corpus}" if limit_per_corpus else "")
    lm = lm or M.load(model, threads=cfg.pop("threads", 8))
    rdir = PILOT_DIR / "runs" / run_id
    manifest = run(units, lm, rdir, RunConfig(run_id=run_id, variant="default", **cfg))
    checks = validate_run(rdir, expected=dict(units))
    return manifest, checks


def summary(manifest: dict, checks: dict) -> str:
    return json.dumps({k: manifest[k] for k in ("run_id", "units", "pieces", "multi_piece_units", "ws_tokens",
                                                 "status", "parse_seconds", "ws_tokens_per_second", "peak_mem_bytes")}
                      | {"checks_ok": checks["ok"], "checks": checks["checks"], "tokens": checks["tokens"]},
                      ensure_ascii=False)


def run_dir(run_id: str) -> Path:
    return PILOT_DIR / "runs" / run_id
