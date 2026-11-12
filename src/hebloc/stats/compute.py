"""Compute the §4 statistics for a checked run set → ``data/stats/<stats_id>/`` (docs/m6_design.md §4).

Layout of a stats folder (never overwritten; a new run set or code commit gives a new id)::

    data/stats/<status>-<YYYYMMDD>-<hash>/
        unit_metrics/<corpus>/<run_id>.parquet   one row per unit (hebloc.stats.metrics)
        <table>.parquet                           corpus-level tables, all corpora (hebloc.stats.tables)
        manifest.json                             runs + fingerprints, code commit, versions, checks,
                                                  row counts and sha256 of every file

The folder is assembled under ``<id>.partial`` and renamed only after every reconciliation check
passed, so a published folder is always complete and consistent. ``--scale-test`` runs write to an
explicit folder outside ``data/stats`` and ``results`` and are never published (D-045).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pyarrow as pa

from hebloc.inventory import _git_commit
from hebloc.paths import RESULTS_DIR, STATS_DIR
from hebloc.stats import STATS_VERSION
from hebloc.stats import metrics as M
from hebloc.stats import tables as T
from hebloc.stats.runset import RunSet
from hebloc.store.io import atomic_write_json, atomic_write_parquet, file_sha256

TABLES = ("coverage", "lexicon", "word_freq", "lemma_freq", "sentence_stats", "distributions",
          "depth_by_length", "tree_status", "pos", "features", "deprel")


class StatsProblem(RuntimeError):
    """A reconciliation check failed: nothing is published."""


def stats_code_sha256() -> str:
    """Hash of the hebloc.stats sources: a code change gives a new stats folder even before a commit."""
    return hashlib.sha256(b"".join(f.read_bytes() for f in sorted(Path(__file__).parent.glob("*.py")))).hexdigest()


def stats_id(rs: RunSet, commit: str, today: str | None = None) -> str:
    ident = {"runs": rs.refs(), "stats_version": STATS_VERSION, "code_commit": commit,
             "stats_code_sha256": stats_code_sha256(),
             "fingerprints": {c: {ref: v["fingerprint"] for ref, v in rep["validations"].items()}
                              for c, rep in rs.checks.items()}}
    h = hashlib.sha256(json.dumps(ident, sort_keys=True).encode()).hexdigest()[:10]
    return f"{rs.status()}-{today or datetime.now(timezone.utc).strftime('%Y%m%d')}-{h}"


def _inside(path: Path, parent: Path) -> bool:
    path, parent = path.resolve(), parent.resolve()
    return path == parent or parent in path.parents


def _token_files(rs: RunSet, corpus: str) -> list[Path]:
    files = []
    for run in rs.runs[corpus]:
        for s in run.shards():
            f = run.path / "tokens" / f"{s}.parquet"
            if not f.exists():
                raise FileNotFoundError(f"{run.ref}: tokens missing for {s} (run: hebloc tokens {run.ref})")
            files.append(f)
    return files


def compute(rs: RunSet, out_dir: Path | None = None, *, scale_test: bool = False, progress: bool = True) -> dict:
    """Compute every table for ``rs`` (already ``runset.check``-ed). Returns the manifest."""
    if not rs.checks:
        raise ValueError("run set not checked (hebloc.stats.runset.check)")
    commit = _git_commit()
    sid = stats_id(rs, commit)
    if scale_test:
        if out_dir is None:
            raise ValueError("--scale-test needs an explicit output folder")
        out_dir = Path(out_dir)
        if _inside(out_dir, STATS_DIR) or _inside(out_dir, RESULTS_DIR):
            raise ValueError("a scale test never writes into data/stats or results (D-045)")
        sid = f"scaletest-{sid}"
    else:
        out_dir = Path(out_dir) if out_dir else STATS_DIR / sid
        if out_dir.exists():
            raise FileExistsError(f"{out_dir} already exists (same run set and code): nothing to do")
    work = out_dir.with_name(out_dir.name + ".partial")
    if work.exists():                     # our own unfinished attempt: never published data
        shutil.rmtree(work)
    work.mkdir(parents=True)

    t0 = time.time()
    timings, problems, per_table = {}, [], {name: [] for name in TABLES}
    metric_files: dict[str, list[Path]] = {}
    for corpus, runs in rs.runs.items():
        tc = time.time()
        metric_files[corpus] = []
        for run in runs:
            tab = M.run_metrics(run, corpus, progress=progress)
            metric_files[corpus].append(atomic_write_parquet(tab, work / "unit_metrics" / corpus / f"{run.run_id}.parquet"))
        tm = time.time()
        con = duckdb.connect()
        T.setup(con, corpus, _token_files(rs, corpus), metric_files[corpus])
        tabs = T.corpus_tables(con, corpus)
        problems += T.reconcile(con, corpus, tabs, rs.checks[corpus]["units_expected"]
                                if rs.checks[corpus]["complete"] else rs.checks[corpus]["units_in_runs"])
        con.close()
        for name in TABLES:
            per_table[name].append(tabs[name])
        timings[corpus] = {"unit_metrics_s": round(tm - tc, 1), "tables_s": round(time.time() - tm, 1)}
        if progress:
            print(f"{corpus}: unit metrics {timings[corpus]['unit_metrics_s']} s, tables {timings[corpus]['tables_s']} s", flush=True)
    if problems and not scale_test:
        raise StatsProblem("reconciliation failed; nothing published (partial output kept in "
                           f"{work}):\n  " + "\n  ".join(problems))

    files = {}
    for name in TABLES:
        tab = pa.concat_tables(per_table[name], promote_options="default")
        path = atomic_write_parquet(tab, work / f"{name}.parquet")
        files[f"{name}.parquet"] = {"rows": tab.num_rows, "sha256": file_sha256(path)}
    for corpus, fs in metric_files.items():
        for f in fs:
            files[f.relative_to(work).as_posix()] = {"rows": None, "sha256": file_sha256(f)}

    manifest = {
        "stats_id": sid, "status": "scale_test" if scale_test else rs.status(), "stats_version": STATS_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "code_commit": commit,
        "stats_code_sha256": stats_code_sha256(), "design": "docs/m6_design.md", "decisions": ["D-015", "D-021", "D-025", "D-045", "D-046"],
        "view": "full", "run_source": rs.source, "runs": rs.refs(),
        "corpus_checks": {c: {k: v for k, v in rep.items()} for c, rep in rs.checks.items()},
        "reconciliation_problems": problems, "timings_s": {**timings, "total": round(time.time() - t0, 1)},
        "files": files,
    }
    atomic_write_json(manifest, work / "manifest.json")
    os.replace(work, out_dir)
    manifest["path"] = str(out_dir)
    return manifest


def load(stats_dir: Path) -> dict[str, pa.Table]:
    import pyarrow.parquet as pq

    return {name: pq.read_table(Path(stats_dir) / f"{name}.parquet") for name in TABLES}


def verify(stats_dir: Path) -> list[str]:
    """Re-hash every file of a stats folder against its manifest."""
    stats_dir = Path(stats_dir)
    man = json.loads((stats_dir / "manifest.json").read_text(encoding="utf-8"))
    probs = []
    for rel, meta in man["files"].items():
        f = stats_dir / rel
        if not f.exists():
            probs.append(f"missing {rel}")
        elif file_sha256(f) != meta["sha256"]:
            probs.append(f"changed {rel}")
    return probs
