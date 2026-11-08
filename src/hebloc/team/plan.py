"""The team's parse work plan: slices, measured sizes, balanced assignment, gate, progress.

``config/parse_plan.yaml`` holds the human decisions (status, coverage, settings, people, slice
definitions). ``hebloc plan measure`` counts every slice's model sub-words with the pinned
tokenizer (the unit of run time) and ``hebloc plan assign`` splits the slices between the people
with a longest-first greedy balance. Both write ``config/work_plan.json`` and
``docs/WORK_PLAN.md``. ``hebloc plan check`` proves the slices are disjoint and cover every unit.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import yaml

from hebloc.catalog import DOCUMENTS_PATH
from hebloc.paths import CONFIG_DIR, CORPORA, DOCS_DIR, UNITS_DIR
from hebloc.store.io import atomic_write_json, atomic_write_text, sql_list, sql_str

PLAN_PATH = CONFIG_DIR / "parse_plan.yaml"
WORK_PLAN_JSON = CONFIG_DIR / "work_plan.json"
WORK_PLAN_MD = DOCS_DIR / "WORK_PLAN.md"
COVERAGES = ("A", "B")
RATE_SUBWORDS_PER_S = 534     # measured, base + topk, M3 benchmark (pilot_report.md §11)


@dataclass(frozen=True)
class Slice:
    id: str
    corpus: str
    subcorpus: tuple[str, ...] | None = None
    source: tuple[str | None, ...] | None = None
    bucket: int | None = None
    buckets: int | None = None
    coverage: tuple[str, ...] = COVERAGES

    def doc_condition(self, alias: str = "d") -> str:
        """SQL condition on a documents row (``alias``) selecting this slice's documents."""
        c = [f"{alias}.corpus_id = {sql_str(self.corpus)}"]
        if self.subcorpus:
            c.append(f"{alias}.subcorpus IN ({', '.join(sql_str(s) for s in self.subcorpus)})")
        if self.source:
            named = [s for s in self.source if s is not None]
            parts = [f"{alias}.source IN ({', '.join(sql_str(s) for s in named)})"] if named else []
            if None in self.source:
                parts.append(f"{alias}.source IS NULL")
            c.append("(" + " OR ".join(parts) + ")")
        if self.buckets:
            c.append(f"{bucket_sql(alias + '.doc_id', self.buckets)} = {int(self.bucket)}")
        return " AND ".join(c)


def doc_bucket(doc_id: str, buckets: int) -> int:
    return int(doc_id[:8], 16) % buckets


def bucket_sql(col: str, buckets: int) -> str:
    return f"(CAST(('0x' || substr({col}, 1, 8)) AS BIGINT) % {int(buckets)})"


@dataclass(frozen=True)
class Plan:
    status: str
    coverage: str
    settings: dict
    people: tuple[str, ...]
    pins: dict
    slices: tuple[Slice, ...]
    sha256: str

    def slice(self, slice_id: str) -> Slice:
        for s in self.slices:
            if s.id == slice_id:
                return s
        raise KeyError(f"unknown slice {slice_id!r}; see `uv run hebloc plan show`")

    @property
    def approved(self) -> bool:
        return self.status == "approved" and self.coverage in COVERAGES

    def run_ref(self, s: Slice) -> str:
        return f"{s.corpus}/{self.settings['settings_id']}__{s.id}"

    @property
    def sizes_key(self) -> str:
        """What the measured sizes depend on: slice definitions + tokenizer (model) + budget.
        Status, coverage, people and pins can change without re-measuring (`hebloc plan assign`)."""
        payload = json.dumps([[s.id, s.corpus, s.subcorpus, s.source, s.bucket, s.buckets] for s in self.slices]
                             + [self.settings["model"], self.settings["budget"]], sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()


def load(path: Path = PLAN_PATH) -> Plan:
    raw = path.read_bytes()
    cfg = yaml.safe_load(raw)
    if cfg.get("status") not in ("draft", "approved"):
        raise ValueError(f"{path.name}: status must be draft|approved")
    if cfg.get("coverage") not in ("pending",) + COVERAGES:
        raise ValueError(f"{path.name}: coverage must be pending|A|B")
    slices = []
    for sid, d in (cfg.get("slices") or {}).items():
        if d["corpus"] not in CORPORA:
            raise ValueError(f"slice {sid}: unknown corpus {d['corpus']!r}")
        if ("bucket" in d) != ("buckets" in d):
            raise ValueError(f"slice {sid}: bucket and buckets go together")
        cov = tuple(d.get("coverage") or COVERAGES)
        if not set(cov) <= set(COVERAGES):
            raise ValueError(f"slice {sid}: coverage must be a subset of {COVERAGES}")
        slices.append(Slice(sid, d["corpus"], tuple(d["subcorpus"]) if d.get("subcorpus") else None,
                            tuple(d["source"]) if d.get("source") else None, d.get("bucket"), d.get("buckets"), cov))
    people = tuple(cfg.get("people") or ())
    if not people or len(set(people)) != len(people):
        raise ValueError(f"{path.name}: people must be a non-empty list of distinct names")
    pins = cfg.get("pins") or {}
    for sid, who in pins.items():
        if who not in people or sid not in {s.id for s in slices}:
            raise ValueError(f"{path.name}: bad pin {sid}: {who}")
    for k in ("settings_id", "model", "mst_fix", "lex_topk", "budget", "batch_size", "max_batch_subwords", "shard_size"):
        if k not in (cfg.get("settings") or {}):
            raise ValueError(f"{path.name}: settings.{k} missing")
    return Plan(cfg["status"], cfg["coverage"], dict(cfg["settings"]), people, pins, tuple(slices),
                hashlib.sha256(raw).hexdigest())


# ------------------------------------------------------------------ units of a slice

def _unit_files(corpus: str, units_root: Path) -> list[Path]:
    files = sorted((units_root / corpus).glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no units for {corpus} under {units_root} (run: uv run hebloc prepare)")
    return files


def units_sql(s: Slice, columns: str = "u.sent_id, u.text_norm", *, units_root: Path = UNITS_DIR,
              documents_path: Path = DOCUMENTS_PATH, limit: int | None = None) -> str:
    sql = (f"SELECT {columns} FROM read_parquet({sql_list(_unit_files(s.corpus, units_root))}) u "
           f"JOIN read_parquet({sql_str(documents_path)}) d USING (doc_id) WHERE {s.doc_condition('d')} "
           f"ORDER BY u.sent_id")
    return sql + (f" LIMIT {int(limit)}" if limit else "")


def slice_units(s: Slice, *, limit: int | None = None, **paths) -> list[tuple[str, str]]:
    """[(sent_id, text_norm)] of the slice, in sent_id order (deterministic shards)."""
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    return con.execute(units_sql(s, limit=limit, **paths)).fetchall()


# ------------------------------------------------------------------ partition check

def check_partition(plan: Plan, *, units_root: Path = UNITS_DIR, documents_path: Path = DOCUMENTS_PATH) -> dict:
    """Every unit must fall in exactly one slice (coverage A), and option B must leave out only
    whole slices that are A-only."""
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    out, ok = {}, True
    for corpus in CORPORA:
        mine = [s for s in plan.slices if s.corpus == corpus]
        hits = " + ".join(f"CAST({s.doc_condition('d')} AS INTEGER)" for s in mine) or "0"
        n, none, multi = con.execute(
            f"SELECT count(*), count(*) FILTER (WHERE h = 0), count(*) FILTER (WHERE h > 1) FROM ("
            f"SELECT {hits} AS h FROM read_parquet({sql_list(_unit_files(corpus, units_root))}) u "
            f"JOIN read_parquet({sql_str(documents_path)}) d USING (doc_id))").fetchone()
        out[corpus] = {"units": n, "in_no_slice": none, "in_several_slices": multi}
        ok &= none == 0 and multi == 0
    return {"ok": ok, "per_corpus": out, "slices": len(plan.slices),
            "coverage_B_excludes": [s.id for s in plan.slices if "B" not in s.coverage]}


# ------------------------------------------------------------------ sizes and assignment

def measure(plan: Plan, *, units_root: Path = UNITS_DIR, documents_path: Path = DOCUMENTS_PATH,
            progress: bool = True) -> dict:
    """Units, whitespace tokens and model sub-words (pinned tokenizer, no special tokens) per slice."""
    from hebloc.parse import models as M

    tok = _tokenizer(plan.settings["model"])
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    sizes = {}
    it = plan.slices
    if progress:
        from tqdm import tqdm
        it = tqdm(plan.slices, desc="measure", unit="slice")
    for s in it:
        units = nonempty = ws = sub = multi = 0
        sql = units_sql(s, "u.text_norm, u.is_empty_norm, u.n_tokens_norm", units_root=units_root,
                        documents_path=documents_path)
        for batch in con.sql(sql).to_arrow_reader(20_000):
            d = batch.to_pydict()
            texts = [t for t, e in zip(d["text_norm"], d["is_empty_norm"]) if not e]
            units += batch.num_rows
            nonempty += len(texts)
            ws += sum(w or 0 for w in d["n_tokens_norm"])
            if texts:
                lens = [len(x) for x in tok(texts, add_special_tokens=False)["input_ids"]]
                sub += sum(lens)
                multi += sum(1 for L in lens if L > plan.settings["budget"])
        sizes[s.id] = {"corpus": s.corpus, "units": units, "units_nonempty": nonempty, "ws_tokens": ws,
                       "subwords": sub, "units_over_budget": multi}
    m = M.registry()["models"][plan.settings["model"]]
    return {"tokenizer": f"{m['repo']}@{m['revision'][:12]}", "sizes": sizes}


def _tokenizer(model: str):
    import os

    from transformers import AutoTokenizer

    from hebloc.parse import models as M

    os.environ["HF_HUB_OFFLINE"] = "1"
    m = M.registry()["models"][model]
    return AutoTokenizer.from_pretrained(M.MODELS_DIR / m["dir"])


def assign(plan: Plan, sizes: dict[str, dict], coverage: str) -> dict:
    """Longest-first greedy balance of sub-words; pinned slices placed first."""
    chosen = [s for s in plan.slices if coverage in s.coverage]
    load = {p: 0 for p in plan.people}
    out = {p: [] for p in plan.people}
    for s in chosen:
        if s.id in plan.pins:
            out[plan.pins[s.id]].append(s.id)
            load[plan.pins[s.id]] += sizes[s.id]["subwords"]
    for s in sorted((s for s in chosen if s.id not in plan.pins), key=lambda s: (-sizes[s.id]["subwords"], s.id)):
        who = min(plan.people, key=lambda p: (load[p], plan.people.index(p)))
        out[who].append(s.id)
        load[who] += sizes[s.id]["subwords"]
    total = sum(load.values())
    return {"coverage": coverage, "total_subwords": total,
            "people": {p: {"slices": out[p], "subwords": load[p],
                           "hours_at_reference_rate": round(load[p] / RATE_SUBWORDS_PER_S / 3600, 1)} for p in plan.people},
            "imbalance": round(max(load.values()) / (total / len(load)), 3) if total else None}


def write_work_plan(plan: Plan, measured: dict, path_json: Path = WORK_PLAN_JSON, path_md: Path = WORK_PLAN_MD) -> dict:
    wp = {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "plan_sha256": plan.sha256,
          "sizes_key": plan.sizes_key, "settings_id": plan.settings["settings_id"], "tokenizer": measured["tokenizer"],
          "reference_rate_subwords_per_s": RATE_SUBWORDS_PER_S, "sizes": measured["sizes"],
          "assignment": {c: assign(plan, measured["sizes"], c) for c in COVERAGES}}
    atomic_write_json(wp, path_json)
    atomic_write_text(render_markdown(plan, wp), path_md)
    return wp


def reassign(plan: Plan, path_json: Path = WORK_PLAN_JSON, path_md: Path = WORK_PLAN_MD) -> dict:
    """Re-balance and re-render from the STORED sizes (seconds), e.g. after Ori approves the plan.
    Refuses if the slices, model or budget changed since measuring (sizes would be stale)."""
    wp = load_work_plan(path_json)
    if wp.get("sizes_key") != plan.sizes_key:
        raise ValueError("slice definitions, model or budget changed since `hebloc plan measure`: re-measure")
    return write_work_plan(plan, {"tokenizer": wp["tokenizer"], "sizes": wp["sizes"]}, path_json, path_md)


def load_work_plan(path: Path = WORK_PLAN_JSON) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"{path} missing (run: uv run hebloc plan measure)")
    return json.loads(path.read_text(encoding="utf-8"))


def owner(plan: Plan, wp: dict, slice_id: str, coverage: str) -> str | None:
    for p, d in wp["assignment"][coverage]["people"].items():
        if slice_id in d["slices"]:
            return p
    return None


def render_markdown(plan: Plan, wp: dict) -> str:
    sz = wp["sizes"]
    lines = ["# Work Plan: who parses what (generated)", "",
             f"*Generated {wp['generated_utc']} by `uv run hebloc plan measure` from "
             f"`config/parse_plan.yaml` (sha256 `{wp['plan_sha256'][:12]}`). Do not edit by hand.*", "",
             f"**Plan status: `{plan.status}`, coverage: `{plan.coverage}`, settings: `{plan.settings['settings_id']}`.** "
             "While the status is `draft`, `hebloc parse` refuses real slices: wait for Ori's go-ahead.", "",
             f"Sizes are exact model sub-word counts ({wp['tokenizer']} tokenizer). Hours assume the reference "
             f"rate of {wp['reference_rate_subwords_per_s']} sub-words/s measured on Ori's laptop (base + `topk`); "
             "your machine may differ, and `hebloc agreement` reports your actual rate.", ""]
    for c in COVERAGES:
        a = wp["assignment"][c]
        title = {"A": "Option A: all of Modern", "B": "Option B: Modern with a 10% Haaretz document sample"}[c]
        lines += [f"## {title}", "",
                  f"Total {a['total_subwords'] / 1e6:,.1f} M sub-words; largest share / average share = {a['imbalance']}.", "",
                  "| Person | Sub-words | Hours (reference rate) | Slices |", "|---|---|---|---|"]
        for p, d in a["people"].items():
            lines.append(f"| {p.capitalize()} | {d['subwords'] / 1e6:,.1f} M | {d['hours_at_reference_rate']} | "
                         + ", ".join(f"`{x}`" for x in d["slices"]) + " |")
        lines.append("")
    lines += ["## Slices", "", "| Slice | Corpus | Units | Whitespace tokens | Sub-words | Units over budget | In option |",
              "|---|---|---|---|---|---|---|"]
    for s in plan.slices:
        d = sz[s.id]
        lines.append(f"| `{s.id}` | {s.corpus} | {d['units']:,} | {d['ws_tokens']:,} | {d['subwords']:,} | "
                     f"{d['units_over_budget']:,} | {', '.join(s.coverage)} |")
    lines += ["", "Run id of a slice: `<corpus>/<settings_id>__<slice>`, e.g. "
              f"`{plan.run_ref(plan.slices[0])}`.", ""]
    return "\n".join(lines)


# ------------------------------------------------------------------ progress / merge state

def status(plan: Plan, wp: dict | None = None, coverage: str | None = None) -> list[dict]:
    """Per slice of the coverage: owner, expected run, and its state on THIS machine."""
    from hebloc.parse.checks import run_fingerprint
    from hebloc.store.io import read_json
    from hebloc.store.runs import resolve

    coverage = coverage or (plan.coverage if plan.coverage in COVERAGES else "A")
    wp = wp or (load_work_plan() if WORK_PLAN_JSON.exists() else None)
    rows = []
    for s in plan.slices:
        if coverage not in s.coverage:
            continue
        ref = plan.run_ref(s)
        row = {"slice": s.id, "owner": owner(plan, wp, s.id, coverage) if wp else None, "run": ref,
               "present": False, "complete": False, "checks_ok": False}
        try:
            r = resolve(ref)
        except FileNotFoundError:
            rows.append(row)
            continue
        st = r.status()
        cj = r.path / "checks.json"
        checks = read_json(cj) if cj.exists() else {}
        row.update({"present": True, "complete": st["complete"],
                    "checks_ok": bool(checks.get("ok")) and checks.get("fingerprint") == run_fingerprint(r.path),
                    "units": st["units"]})
        rows.append(row)
    return rows


def registry_entries(plan: Plan, rows: list[dict]) -> dict[str, list[str]]:
    """corpus → run refs of complete, valid slice runs (what `hebloc plan register` would write)."""
    out: dict[str, list[str]] = {}
    for row in rows:
        if row["complete"] and row["checks_ok"]:
            out.setdefault(plan.slice(row["slice"]).corpus, []).append(row["run"])
    return out
