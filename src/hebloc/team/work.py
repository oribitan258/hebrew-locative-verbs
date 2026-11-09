"""Run a person's whole workload (partners), and merge everyone's results (Ori).

``hebloc work [--as NAME]``  (the one command a partner runs to parse)
    Preflight (corpora = anchor, data fingerprints, model sha256, agreement, work plan in sync), then
    for every slice the work plan assigns to NAME: parse (resumable), validate against this machine's
    units, integrity-check, and package a verified bundle into ``data/outbox/<name>/`` together with
    ``DELIVERY.json`` (what was delivered, sha256 of every bundle) and ``HOW_TO_SEND.txt``. Re-running
    it continues where it stopped and skips slices already packaged. REFUSED while the plan is a draft.
``hebloc work --rehearsal N``
    The same chain on the first N units of each assigned slice (collection ``rehearsal``, never
    canonical), allowed in draft: proves setup → parse → package → merge end to end.

``hebloc parse --slice S``: one slice (same gate); ``--limit N``: a SMOKE run of any slice.

``hebloc merge <folder or bundle.zip>...`` (Ori)
    Collects every bundle in the given folders, checks each against its ``.zip.sha256`` and the
    ``DELIVERY.json`` that lists it, drops byte-identical duplicate copies, refuses two DIFFERENT
    bundles of the same run, verifies + restores + integrity-checks each run, checks that the run
    holds EXACTLY its slice's units (same sent_ids, same text) and was made by the slice's owner with
    the plan's settings, then reports completeness: missing slices, duplicated units (must be 0).
``hebloc plan register --write`` registers the runs only when the whole coverage is complete.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

from hebloc.paths import ANNOTATIONS_DIR, DATA_DIR

OUTBOX_DIR = DATA_DIR / "outbox"
TEAM_DIR = DATA_DIR / "team"
MERGE_REPORT = TEAM_DIR / "merge_report.json"
COVERAGE_CACHE = TEAM_DIR / "coverage_cache.json"
LOCK_PATH = TEAM_DIR / "work.lock"
LOG_PATH = TEAM_DIR / "work.log"
REHEARSAL = "rehearsal"


class PlanRefusal(RuntimeError):
    pass


class WorkFailed(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rehearsal_run_id(settings_id: str, slice_id: str, n: int, coverage: str) -> str:
    return f"{settings_id}__{slice_id}__r{int(n)}{coverage}"


# ------------------------------------------------------------------ one slice

def _threads(settings: dict, requested: int | None, *, real: bool) -> int:
    """Torch threads: the plan's pinned value; another value only for smoke/rehearsal runs."""
    pinned = int(settings.get("threads", 8))
    if requested is None or requested == pinned:
        return pinned
    if real:
        raise PlanRefusal(f"full runs use the plan's threads={pinned} (the setting the agreement check verified)")
    return requested


def run_slice(slice_id: str, person: str, *, threads: int | None = None, limit: int | None = None,
              rehearsal: int | None = None, coverage: str | None = None, lm=None, progress: bool = True) -> dict:
    from hebloc.parse import models as M
    from hebloc.parse.checks import validate_run
    from hebloc.parse.run import RunConfig, run
    from hebloc.store.integrity import check_run
    from hebloc.store.runs import resolve
    from hebloc.team import plan as P

    plan = P.load()
    s = plan.slice(slice_id)
    if person not in plan.people:
        raise PlanRefusal(f"{person!r} is not in the plan's people {list(plan.people)}")
    st = plan.settings
    smoke = limit is not None
    if smoke and rehearsal is not None:
        raise PlanRefusal("use either --limit (smoke) or --rehearsal, not both")
    n = limit if smoke else rehearsal
    threads = _threads(st, threads, real=not smoke and rehearsal is None)
    if not smoke:
        if rehearsal is None:
            if not plan.approved:
                raise PlanRefusal(f"the plan is not approved yet (status={plan.status}, coverage={plan.coverage}); "
                                  "full runs wait for Ori's go-ahead. A rehearsal is allowed: --rehearsal 40")
            cov = plan.coverage
        else:
            cov = coverage or (plan.coverage if plan.coverage in P.COVERAGES else "A")
        if cov not in s.coverage:
            raise PlanRefusal(f"slice {slice_id} is not part of coverage option {cov}")
        who = P.owner(plan, P.load_work_plan(), slice_id, cov)
        if who != person:
            raise PlanRefusal(f"slice {slice_id} is assigned to {who!r}, not {person!r} (docs/WORK_PLAN.md)")
    units = P.slice_units(s, limit=n)
    if not units:
        raise PlanRefusal(f"slice {slice_id} selects no units on this machine (run hebloc prepare?)")
    if smoke:
        run_id, collection = f"{st['settings_id']}__{slice_id}__{person}__n{limit}", "smoke"
    elif rehearsal is not None:
        run_id, collection = rehearsal_run_id(st["settings_id"], slice_id, rehearsal, cov), REHEARSAL
    else:
        run_id, collection = f"{st['settings_id']}__{slice_id}", s.corpus
    rdir = ANNOTATIONS_DIR / collection / "runs" / run_id
    lm = lm or M.load(st["model"], threads=threads)
    from hebloc.team.awake import keep_awake

    with keep_awake():
        manifest = run(units, lm, rdir, RunConfig(
            run_id=run_id, variant="default", budget=st["budget"], batch_size=st["batch_size"],
            max_batch_subwords=st["max_batch_subwords"], mst_fix=st["mst_fix"], lex_topk=st["lex_topk"],
            shard_size=st["shard_size"], threads=threads,
            extra={"slice": slice_id, "person": person, "settings_id": st["settings_id"], "plan_sha256": plan.sha256,
                   "smoke": smoke, "limit": limit, "rehearsal": rehearsal,
                   "coverage": None if smoke else cov}), progress=progress)
    checks = validate_run(rdir, expected=dict(units))
    import duckdb
    integrity = check_run(resolve(rdir), duckdb.connect())
    ok = checks["ok"] and integrity["ok"]
    return {"slice": slice_id, "run": f"{collection}/{run_id}", "units": manifest["units"], "pieces": manifest["pieces"],
            "status": manifest["status"], "parse_seconds": manifest["parse_seconds"],
            "subwords_per_second": round(manifest["subwords"] / manifest["parse_seconds"], 1) if manifest["parse_seconds"] else None,
            "validation_ok": checks["ok"], "integrity_ok": integrity["ok"], "problems": integrity["problems"],
            "invalid_tree_share": checks["model_invalid_tree_share"],
            "next": f"uv run hebloc bundle create {collection}/{run_id}" if ok else
                    "send data/team/doctor.json and the run's checks.json to Ori"}


# ------------------------------------------------------------------ preflight

def preflight(person: str, *, rehearsal: bool) -> list[str]:
    """Everything that must be true before this machine's output can be merged with the others."""
    from hebloc.baseline import anchor_mismatches, read_anchor, read_baseline
    from hebloc.parse import models as M
    from hebloc.paths import ANCHOR_PATH, BASELINE_PATH
    from hebloc.team import agreement as A
    from hebloc.team import fingerprint as F
    from hebloc.team import plan as P

    probs = []
    plan = P.load()
    if not BASELINE_PATH.exists() or anchor_mismatches(read_baseline(BASELINE_PATH), read_anchor(ANCHOR_PATH)):
        probs.append("corpora not verified against the anchor -> uv run hebloc corpora verify")
    try:
        ref = F.read_reference()
        hard = [p for p in F.compare(F.compute(), ref) if not p.startswith("note:")] if ref else ["no reference"]
        if hard:
            probs.append(f"derived data differ from the reference ({hard[:2]}) -> uv run hebloc inventory; "
                         "uv run hebloc prepare; uv run hebloc fingerprint")
    except FileNotFoundError as e:
        probs.append(f"derived data missing ({e}) -> uv run hebloc inventory; uv run hebloc prepare")
    mp = M.verify(plan.settings["model"])
    if mp:
        probs.append(f"model not verified ({mp[:2]}) -> uv run hebloc models fetch")
    res = json.loads(A.RESULT_PATH.read_text(encoding="utf-8")) if A.RESULT_PATH.exists() else None
    if not res or not res.get("ok") or res.get("settings", {}).get("settings_id") != plan.settings["settings_id"]:
        probs.append(f"cross-machine agreement not passed with the current settings -> uv run hebloc agreement --as {person}")
    try:
        wp = P.load_work_plan()
        if wp.get("sizes_key") != plan.sizes_key:
            probs.append("docs/WORK_PLAN.md is out of date for config/parse_plan.yaml -> git pull (Ori: hebloc plan assign)")
    except FileNotFoundError as e:
        probs.append(str(e))
    if not rehearsal and not plan.approved:
        probs.insert(0, f"full runs are not enabled: the plan is not approved (status={plan.status}, "
                        f"coverage={plan.coverage}). This is expected until Ori starts the parsing phase")
    return probs


# ------------------------------------------------------------------ the whole workload

def _bundle_ok(path: Path) -> bool:
    from hebloc.store.io import file_sha256

    side = Path(str(path) + ".sha256")
    return path.exists() and side.exists() and side.read_text(encoding="utf-8").split()[0] == file_sha256(path)


def work(person: str, *, rehearsal: int | None = None, coverage: str | None = None, threads: int | None = None,
         outbox_root: Path = OUTBOX_DIR, progress: bool = True, echo=print) -> dict:
    """The whole workload; one instance per computer (lock), progress also appended to data/team/work.log."""
    from hebloc.team import plan as P

    threads = _threads(P.load().settings, threads, real=rehearsal is None)
    log = _logger(echo)
    with work_lock(person, "full" if rehearsal is None else f"rehearsal{rehearsal}"):
        log(f"--- hebloc work started {_now()} (person={person}, rehearsal={rehearsal}, threads={threads})")
        try:
            r = _work(person, rehearsal=rehearsal, coverage=coverage, threads=threads, outbox_root=outbox_root,
                      progress=progress, echo=log)
        except (PlanRefusal, WorkFailed) as e:
            log(f"--- stopped {_now()}: {type(e).__name__}: {e}")
            raise
        log(f"--- WORK COMPLETE {_now()}: {r['slices']} slices, {r['units']:,} units")
        return r


def _logger(echo):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        echo(msg)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")
    return log


def _pid_alive(pid: int) -> bool:
    import psutil

    try:
        p = psutil.Process(pid)
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def read_lock() -> dict | None:
    """The running `hebloc work` on this computer (None if none; a stale lock counts as none)."""
    if not LOCK_PATH.exists():
        return None
    try:
        lk = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return lk if _pid_alive(int(lk.get("pid", -1))) else None


class work_lock:
    """At most one `hebloc work` per computer: two would parse the same shards."""

    def __init__(self, person: str, mode: str):
        self.rec = {"pid": __import__("os").getpid(), "person": person, "mode": mode, "started_utc": _now()}

    def __enter__(self):
        from hebloc.store.io import atomic_write_json

        cur = read_lock()
        if cur and cur["pid"] != self.rec["pid"]:
            raise PlanRefusal(f"hebloc work is already running on this computer (pid {cur['pid']}, started "
                              f"{cur['started_utc']}). Check it with: uv run python -m hebloc work --status")
        atomic_write_json(self.rec, LOCK_PATH)
        return self

    def __exit__(self, *exc):
        try:
            if json.loads(LOCK_PATH.read_text(encoding="utf-8")).get("pid") == self.rec["pid"]:
                LOCK_PATH.unlink()
        except (OSError, json.JSONDecodeError):
            pass
        return False


def _work(person: str, *, rehearsal: int | None, coverage: str | None, threads: int, outbox_root: Path,
          progress: bool, echo) -> dict:
    from hebloc.inventory import _git_commit
    from hebloc.parse import models as M
    from hebloc.store import bundle as B
    from hebloc.store.io import atomic_write_json, atomic_write_text, file_sha256
    from hebloc.store.runs import resolve
    from hebloc.team import plan as P
    from hebloc.team.awake import keep_awake

    plan = P.load()
    if rehearsal is None and coverage:
        raise PlanRefusal("--coverage is only for rehearsals; full runs use the plan's approved coverage")
    probs = preflight(person, rehearsal=rehearsal is not None)
    if probs:
        raise PlanRefusal("not ready:\n  - " + "\n  - ".join(probs))
    wp = P.load_work_plan()
    cov = plan.coverage if rehearsal is None else (coverage or (plan.coverage if plan.coverage in P.COVERAGES else "A"))
    mine = wp["assignment"][cov]["people"].get(person)
    if not mine or not mine["slices"]:
        raise PlanRefusal(f"{person!r} has no slices in coverage {cov}")
    mode = "full" if rehearsal is None else "rehearsal"
    outbox = outbox_root / (person if mode == "full" else f"{person}-rehearsal{rehearsal}{cov}")
    outbox.mkdir(parents=True, exist_ok=True)
    delivery_path = outbox / "DELIVERY.json"
    delivery = json.loads(delivery_path.read_text(encoding="utf-8")) if delivery_path.exists() else {}
    if delivery and (delivery.get("plan_sha256") != plan.sha256 or delivery.get("coverage") != cov):
        raise PlanRefusal(f"{outbox} holds a delivery for a different plan/coverage; ask Ori before continuing")
    done = {d["slice"]: d for d in delivery.get("slices", [])}
    slices = list(mine["slices"])
    echo(f"{person.capitalize()}: {len(slices)} slice(s), coverage {cov}, mode {mode}"
         + (f" ({rehearsal} units per slice)" if rehearsal else f", ~{mine['hours_at_reference_rate']} h at the reference rate"))

    def save(complete: bool) -> None:
        rec = {"format": 1, "person": person, "mode": mode, "rehearsal_units": rehearsal, "coverage": cov,
               "plan_sha256": plan.sha256, "settings_id": plan.settings["settings_id"], "code_commit": _git_commit(),
               "updated_utc": _now(), "assigned_slices": slices, "complete": complete,
               "slices": [done[s] for s in slices if s in done]}
        atomic_write_json(rec, delivery_path)
        atomic_write_text(_how_to_send(person, outbox, rec), outbox / "HOW_TO_SEND.txt")

    lm = None
    with keep_awake() as awake:
        if not awake:
            echo("note: could not stop the computer from sleeping automatically; disable sleep in the power settings")
        for i, sid in enumerate(slices, 1):
            d = done.get(sid)
            if d and _bundle_ok(outbox / d["bundle"]):
                echo(f"[{i}/{len(slices)}] {sid}: already packaged ({d['bundle']})")
                continue
            echo(f"[{i}/{len(slices)}] {sid}: parsing (resumes automatically if it was interrupted)")
            lm = lm or M.load(plan.settings["model"], threads=threads)
            r = run_slice(sid, person, threads=threads, rehearsal=rehearsal, coverage=cov if rehearsal else None,
                          lm=lm, progress=progress)
            if not (r["validation_ok"] and r["integrity_ok"]):
                save(False)
                raise WorkFailed(f"slice {sid} failed its checks: validation_ok={r['validation_ok']}, "
                                 f"integrity_ok={r['integrity_ok']}, problems={r['problems'][:3]}")
            b = B.create(r["run"], out_dir=outbox)
            v = B.verify(Path(b["path"]))
            if not v["ok"] or not _bundle_ok(Path(b["path"])):
                save(False)
                raise WorkFailed(f"bundle of {sid} failed verification: {v['problems']}")
            run = resolve(r["run"])
            done[sid] = {"slice": sid, "run": r["run"], "bundle": Path(b["path"]).name, "bundle_sha256": b["sha256"],
                         "bundle_bytes": b["bytes"], "units": r["units"], "pieces": r["pieces"],
                         "parse_hours": round(run.manifest.get("parse_seconds", 0) / 3600, 3),
                         "run_fingerprint": (json.loads((run.path / "checks.json").read_text(encoding="utf-8"))
                                             .get("fingerprint")), "packaged_utc": _now()}
            save(False)
            echo(f"[{i}/{len(slices)}] {sid}: OK, {r['units']:,} units, packaged as {done[sid]['bundle']}")
    # final self-check of the whole outbox, as Ori's merge will check it: every assigned slice present once,
    # each bundle intact, each with exactly the number of sentences the work plan expects
    problems = []
    if sorted(done) != sorted(slices):
        problems.append(f"outbox slices {sorted(done)} != assigned {sorted(slices)}")
    for sid, d in done.items():
        if not _bundle_ok(outbox / d["bundle"]) or file_sha256(outbox / d["bundle"]) != d["bundle_sha256"]:
            problems.append(f"{d['bundle']}: damaged")
        expected = wp["sizes"][sid]["units"] if rehearsal is None else min(rehearsal, wp["sizes"][sid]["units"])
        if d["units"] != expected:
            problems.append(f"{sid}: {d['units']:,} units, expected {expected:,}")
    if problems:
        save(False)
        raise WorkFailed("outbox check failed: " + "; ".join(problems))
    save(True)
    return {"person": person, "mode": mode, "coverage": cov, "outbox": str(outbox), "slices": len(slices),
            "units": sum(d["units"] for d in done.values()),
            "bytes": sum(d["bundle_bytes"] for d in done.values()), "complete": True}


def _how_to_send(person: str, outbox: Path, rec: dict) -> str:
    state = "COMPLETE" if rec["complete"] else f"IN PROGRESS ({len(rec['slices'])}/{len(rec['assigned_slices'])} slices)"
    return "\n".join([
        f"Results of {person.capitalize()} ({rec['mode']}, coverage {rec['coverage']}): {state}",
        "",
        "Send this WHOLE folder to Ori, unchanged:",
        f"  {outbox}",
        "It holds one .zip + .zip.sha256 per slice, DELIVERY.json (the list Ori's merge checks), and this file.",
        "",
        "How (choose one):",
        "  - Google Drive or OneDrive: in the browser, upload the folder itself (drag it into the page), wait",
        "    until the upload has finished, then share it with Ori (right-click > Share > Ori's email).",
        "  - USB drive: copy the folder onto it and give it to Ori.",
        "Never upload it to GitHub. Tell Ori when it is uploaded or copied.",
        "Keep everything on this computer (the project's data folder) until Ori confirms that",
        "`hebloc merge` reported MERGE OK: your copy is the backup.",
        "",
        "Ori merges with:  uv run hebloc merge \"<path to this folder>\"",
        "",
    ])


# ------------------------------------------------------------------ progress and detached runs

def status(person: str, *, rehearsal: int | None = None, coverage: str | None = None,
           outbox_root: Path = OUTBOX_DIR) -> dict:
    """Where the person's workload stands on THIS computer (cheap: manifests only, no parsing)."""
    from hebloc.team import plan as P

    plan = P.load()
    wp = P.load_work_plan()
    lock = read_lock()
    running = bool(lock and lock.get("person") == person)
    if rehearsal is None and not plan.approved:
        return {"person": person, "state": "waiting for Ori's approval (the plan is a draft); nothing to run yet",
                "running": running, "complete": False}
    cov = plan.coverage if rehearsal is None else (coverage or (plan.coverage if plan.coverage in P.COVERAGES else "A"))
    slices = wp["assignment"][cov]["people"][person]["slices"]
    outbox = outbox_root / (person if rehearsal is None else f"{person}-rehearsal{rehearsal}{cov}")
    dp = outbox / "DELIVERY.json"
    delivery = json.loads(dp.read_text(encoding="utf-8")) if dp.exists() else {}
    packaged = {d["slice"] for d in delivery.get("slices", [])}
    rows, tot = [], {"units": 0, "units_done": 0, "sub": 0.0, "sub_done": 0.0, "secs": 0.0, "sub_measured": 0}
    for sid in slices:
        size = wp["sizes"][sid]
        exp_units = size["units"] if rehearsal is None else min(rehearsal, size["units"])
        exp_sub = size["subwords"] * (exp_units / max(size["units"], 1))
        s = plan.slice(sid)
        if rehearsal is None:
            rdir = ANNOTATIONS_DIR / s.corpus / "runs" / f"{plan.settings['settings_id']}__{sid}"
        else:
            rdir = ANNOTATIONS_DIR / REHEARSAL / "runs" / rehearsal_run_id(plan.settings["settings_id"], sid, rehearsal, cov)
        u = sw = 0
        for f in sorted((rdir / "_shards").glob("shard-*.json")):
            m = json.loads(f.read_text(encoding="utf-8"))
            u += m["units"]
            sw += m["subwords"]
            tot["secs"] += m["seconds"]
            tot["sub_measured"] += m["subwords"]
        state = "packaged" if sid in packaged else ("in progress" if u else "waiting")
        done_units = exp_units if state == "packaged" else u
        tot["units"] += exp_units
        tot["units_done"] += done_units
        tot["sub"] += exp_sub
        tot["sub_done"] += exp_sub if state == "packaged" else sw
        rows.append({"slice": sid, "state": state, "units_done": done_units, "units": exp_units})
    rate = tot["sub_measured"] / tot["secs"] if tot["secs"] else None
    complete = all(r["state"] == "packaged" for r in rows) and bool(delivery.get("complete"))
    left_h = round((tot["sub"] - tot["sub_done"]) / rate / 3600, 1) if rate and not complete else (0 if complete else None)
    state = ("complete" if complete else "running" if running else
             "stopped: run it again to resume" if tot["units_done"] else "not started")
    return {"person": person, "coverage": cov, "mode": "full" if rehearsal is None else "rehearsal", "state": state,
            "running": running, "pid": lock.get("pid") if running else None, "complete": complete,
            "slices_packaged": sum(r["state"] == "packaged" for r in rows), "slices": len(rows),
            "units_done": tot["units_done"], "units": tot["units"],
            "percent": round(100 * tot["sub_done"] / tot["sub"], 1) if tot["sub"] else 0.0,
            "subwords_per_second": round(rate, 1) if rate else None, "hours_left_estimate": left_h,
            "outbox": str(outbox), "log": str(LOG_PATH), "per_slice": rows}


def detach(person: str, *, rehearsal: int | None = None, coverage: str | None = None) -> dict:
    """Start `hebloc work` in its own window/session, independent of the Claude Code session that asked."""
    import os
    import platform
    import subprocess
    import sys

    from hebloc.paths import ROOT

    cur = read_lock()
    if cur:
        raise PlanRefusal(f"hebloc work is already running on this computer (pid {cur['pid']}); "
                          "check it with: uv run python -m hebloc work --status")
    probs = preflight(person, rehearsal=rehearsal is not None)
    if probs:
        raise PlanRefusal("not ready:\n  - " + "\n  - ".join(probs))
    args = [sys.executable, "-m", "hebloc", "work", "--as", person]
    args += ["--rehearsal", str(rehearsal)] if rehearsal is not None else []
    args += ["--coverage", coverage] if coverage else []
    env = dict(os.environ, PYTHONUTF8="1", PYTHONUNBUFFERED="1")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if platform.system() == "Windows":
        q = lambda x: "'" + str(x).replace("'", "''") + "'"  # noqa: E731  PowerShell single-quoted literal
        title = f"hebloc work ({person.capitalize()}) - keep this window open"
        ps = (f"$Host.UI.RawUI.WindowTitle = {q(title)}; Set-Location -LiteralPath {q(ROOT)}; "
              f"& {' '.join(q(a) for a in args)}; Write-Host ''; "
              "Write-Host 'hebloc work has stopped (see the last lines above). You may close this window.'")
        cmd = ["powershell.exe", "-NoProfile", "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", ps]
        base = subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP
        try:      # leave the caller's job object, so closing Claude Code does not end the run
            proc = subprocess.Popen(cmd, cwd=ROOT, env=env, creationflags=base | 0x01000000)  # CREATE_BREAKAWAY_FROM_JOB
        except OSError:
            proc = subprocess.Popen(cmd, cwd=ROOT, env=env, creationflags=base)
    else:         # (untested) macOS/Linux: a new session, output in the log
        out = open(LOG_PATH, "a", encoding="utf-8")
        proc = subprocess.Popen(args, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=out,
                                stderr=subprocess.STDOUT, start_new_session=True)
    return {"launcher_pid": proc.pid, "log": str(LOG_PATH)}


# ------------------------------------------------------------------ merging (Ori)

def _read_manifest(z: Path) -> dict | None:
    from hebloc.store.bundle import MANIFEST_NAME

    try:
        with zipfile.ZipFile(z) as zf:
            return json.loads(zf.read(MANIFEST_NAME))
    except (zipfile.BadZipFile, zlib.error, KeyError, json.JSONDecodeError, OSError, ValueError, EOFError):
        return None


def collect(paths: list[Path]) -> tuple[list[Path], list[Path], list[str]]:
    zips, deliveries, probs = [], [], []
    for p in map(Path, paths):
        if p.is_dir():
            zips += sorted(p.rglob("*.zip"))
            deliveries += sorted(p.rglob("DELIVERY.json"))
        elif p.is_file() and p.suffix.lower() == ".zip":
            zips.append(p)
            if (p.parent / "DELIVERY.json").exists():
                deliveries.append(p.parent / "DELIVERY.json")
        else:
            probs.append(f"not found or not a folder/.zip: {p}")
    return list(dict.fromkeys(zips)), list(dict.fromkeys(deliveries)), probs


def coverage_check(run, plan) -> dict:
    """The run holds EXACTLY its slice's units on THIS machine: same sent_ids, same text, no repeats."""
    from hebloc.parse.run import read_run
    from hebloc.team import plan as P

    extra = run.manifest.get("extra") or {}
    s = plan.slice(extra["slice"])
    n = extra.get("limit") or extra.get("rehearsal")
    exp = {sid: hashlib.sha1(t.encode("utf-8")).hexdigest() for sid, t in P.slice_units(s, limit=n)}
    t = read_run(run.path, "inputs").select(["sent_id", "text_sha1"]).to_pydict()
    got = dict(zip(t["sent_id"], t["text_sha1"]))
    repeats = len(t["sent_id"]) - len(got)
    missing = [k for k in exp if k not in got]
    extra_ids = [k for k in got if k not in exp]
    changed = [k for k in exp if k in got and got[k] != exp[k]]
    return {"ok": not (repeats or missing or extra_ids or changed), "expected_units": len(exp), "units": len(got),
            "repeated": repeats, "missing": len(missing), "unexpected": len(extra_ids), "text_differs": len(changed),
            "examples": (missing + extra_ids + changed)[:3]}


def _cached_coverage(run, plan) -> dict:
    from hebloc.store.io import atomic_write_json, read_json

    checks = read_json(run.path / "checks.json") if (run.path / "checks.json").exists() else {}
    key = f"{run.ref}|{checks.get('fingerprint')}|{plan.sha256}"
    cache = read_json(COVERAGE_CACHE) if COVERAGE_CACHE.exists() else {}
    if key in cache:
        return cache[key]
    res = coverage_check(run, plan)
    cache[key] = res
    atomic_write_json(cache, COVERAGE_CACHE)
    return res


def merge(paths: list[Path], *, overwrite: bool = False) -> dict:
    """Verify + restore every bundle found, check each run exactly, then report completeness."""
    import duckdb

    from hebloc.store import bundle as B
    from hebloc.store.integrity import check_run
    from hebloc.store.io import atomic_write_json, file_sha256
    from hebloc.store.runs import resolve
    from hebloc.team import plan as P

    plan = P.load()
    wp = P.load_work_plan()
    zips, deliveries, probs = collect(paths)
    rows, by_run = [], {}
    for z in zips:
        man = _read_manifest(z)
        if man is None:
            rows.append({"bundle": str(z), "ok": False, "problems": ["not a hebloc bundle (no BUNDLE_MANIFEST.json)"]})
            continue
        by_run.setdefault(man["run"], []).append(z)
    # deliveries: everything listed must be present and identical
    listed: dict[str, str] = {}
    for dpath in deliveries:
        d = json.loads(dpath.read_text(encoding="utf-8"))
        for s in d.get("slices", []):
            f = dpath.parent / s["bundle"]
            listed[str(f.resolve())] = s["bundle_sha256"]
            if not f.exists():
                probs.append(f"MISSING: {dpath} lists {s['bundle']} but the file is not there (incomplete upload?)")
        if not d.get("complete"):
            probs.append(f"note: {dpath.parent.name}: delivery in progress "
                         f"({len(d.get('slices', []))}/{len(d.get('assigned_slices', []))} slices)")
    con = duckdb.connect()
    for ref, zs in sorted(by_run.items()):
        shas = {z: file_sha256(z) for z in zs}
        distinct = sorted(set(shas.values()))
        if len(distinct) > 1:
            for z in zs:
                rows.append({"bundle": str(z), "run": ref, "ok": False,
                             "problems": [f"CONFLICT: {len(distinct)} different bundles of the same run {ref}; "
                                          "none merged (ask who made each)"]})
            continue
        z, dupes = zs[0], zs[1:]
        row = {"bundle": str(z), "run": ref, "problems": [],
               "duplicate_copies_ignored": [str(x) for x in dupes]}
        side = Path(str(z) + ".sha256")
        if side.exists():
            row["sidecar"] = "match" if side.read_text(encoding="utf-8").split()[0] == shas[z] else "MISMATCH"
        else:
            row["sidecar"] = "missing"
        if row["sidecar"] == "MISMATCH":
            row["problems"].append("zip does not match its .sha256 file (damaged or altered in transfer)")
        if str(z.resolve()) in listed and listed[str(z.resolve())] != shas[z]:
            row["problems"].append("zip does not match the sha256 in DELIVERY.json")
        if row["problems"]:                         # damaged: do not even open its members
            row.update({"ok": False, "verified": False})
            rows.append(row)
            continue
        try:
            v = B.verify(z)
        except (zipfile.BadZipFile, zlib.error, OSError, ValueError, EOFError, KeyError) as e:   # corrupt member
            v = {"ok": False, "problems": [f"zip is damaged: {type(e).__name__}: {e}"]}
        row["verified"] = v["ok"]
        row["problems"] += v["problems"]
        if row["problems"]:
            row["ok"] = False
            rows.append(row)
            continue
        try:
            res = B.restore(z, overwrite=overwrite)
        except RuntimeError as e:
            row.update({"ok": False, "problems": row["problems"] + [f"restore refused: {e}"]})
            rows.append(row)
            continue
        run = resolve(res["path"])
        ci = check_run(run, con)
        m = run.manifest
        extra = m.get("extra") or {}
        kind = "smoke" if run.collection == "smoke" else (REHEARSAL if run.collection == REHEARSAL else "full")
        same_settings = extra.get("settings_id") == plan.settings["settings_id"]
        cov = extra.get("coverage")
        expected_owner = P.owner(plan, wp, extra.get("slice"), cov) if kind != "smoke" and cov else None
        owner_ok = kind == "smoke" or expected_owner == extra.get("person")
        in_plan = kind != "full" or run.ref == plan.run_ref(plan.slice(extra.get("slice")))
        cc = _cached_coverage(run, plan)
        row.update({"kind": kind, "slice": extra.get("slice"), "person": extra.get("person"), "coverage": cov,
                    "restored_files": res["written"], "validation_ok": res["validation_ok"],
                    "integrity_ok": ci["ok"], "integrity_problems": ci["problems"], "same_settings": same_settings,
                    "owner_ok": owner_ok, "in_plan": in_plan, "exact_units": cc})
        if not same_settings:
            row["problems"].append("made with different parse settings")
        if not owner_ok:
            row["problems"].append(f"made by {extra.get('person')!r} but the slice belongs to {expected_owner!r}")
        if not cc["ok"]:
            row["problems"].append(f"units differ from this machine's slice: {cc}")
        row["ok"] = res["validation_ok"] and ci["ok"] and same_settings and owner_ok and in_plan and cc["ok"]
        rows.append(row)
    kinds = sorted({(r.get("kind"), r.get("coverage"), r.get("person") if r.get("kind") == REHEARSAL else None)
                    for r in rows if r.get("ok") and r.get("kind") in ("full", REHEARSAL)})
    summaries = []
    if any(k == "full" for k, _, _ in kinds) or plan.approved:
        summaries.append(completeness(plan, wp, mode="full", coverage=plan.coverage if plan.approved else "A"))
    for cov in sorted({c for k, c, _ in kinds if k == REHEARSAL}):
        summaries.append(completeness(plan, wp, mode=REHEARSAL, coverage=cov))
    ok = all(r["ok"] for r in rows) and not [p for p in probs if not p.startswith("note:")]
    rep = {"when_utc": _now(), "inputs": [str(p) for p in paths], "bundles_found": len(zips), "runs": len(by_run),
           "bundles": rows, "problems": probs, "ok": ok, "completeness": summaries}
    atomic_write_json(rep, MERGE_REPORT)
    return rep


def completeness(plan, wp: dict, *, mode: str, coverage: str) -> dict:
    """Per slice of the coverage: is exactly one valid run present here, holding exactly its units?
    Plus a global count of units that appear in more than one run (must be 0)."""
    import duckdb

    from hebloc.parse.checks import run_fingerprint
    from hebloc.store.io import read_json, sql_list
    from hebloc.store.runs import list_runs, resolve
    from hebloc.team import plan as P

    rows, files = [], []
    rehearsal_runs = [r for r in list_runs() if r.collection == REHEARSAL] if mode == REHEARSAL else []
    for s in plan.slices:
        if coverage not in s.coverage:
            continue
        row = {"slice": s.id, "owner": P.owner(plan, wp, s.id, coverage), "state": "missing"}
        if mode == "full":
            try:
                cands = [resolve(plan.run_ref(s))]
            except FileNotFoundError:
                cands = []
        else:
            pre = f"{plan.settings['settings_id']}__{s.id}__r"
            cands = [r for r in rehearsal_runs if r.run_id.startswith(pre) and r.run_id.endswith(coverage)
                     and r.run_id[len(pre):-len(coverage)].isdigit()]
        if len(cands) > 1:
            row.update({"state": "DUPLICATE", "runs": [r.ref for r in cands]})
        elif cands:
            r = cands[0]
            st = r.status()
            cj = r.path / "checks.json"
            checks = read_json(cj) if cj.exists() else {}
            valid = st["complete"] and bool(checks.get("ok")) and checks.get("fingerprint") == run_fingerprint(r.path)
            cc = _cached_coverage(r, plan) if valid else {"ok": False}
            row.update({"run": r.ref, "units": st["units"], "state": "ok" if valid and cc["ok"] else "INVALID",
                        "exact_units": cc.get("ok")})
            if valid:
                files += r.part_files("inputs")
        rows.append(row)
    dup_units = total = 0
    if files:
        con = duckdb.connect()
        total, distinct = con.execute(f"SELECT count(*), count(DISTINCT sent_id) FROM read_parquet({sql_list(files)})").fetchone()
        dup_units = total - distinct
    expected = (sum(wp["sizes"][r["slice"]]["units"] for r in rows) if mode == "full"
                else sum(r.get("units") or 0 for r in rows if r["state"] == "ok"))
    missing = [r["slice"] for r in rows if r["state"] == "missing"]
    bad = [r["slice"] for r in rows if r["state"] in ("INVALID", "DUPLICATE")]
    return {"mode": mode, "coverage": coverage, "slices_expected": len(rows),
            "slices_ok": sum(r["state"] == "ok" for r in rows), "missing": missing,
            "missing_by_owner": {p: [r["slice"] for r in rows if r["state"] == "missing" and r["owner"] == p]
                                 for p in plan.people},
            "invalid_or_duplicate": bad, "units_expected": expected, "units_present": total,
            "units_in_more_than_one_run": dup_units,
            "complete": not missing and not bad and dup_units == 0 and total == expected, "slices": rows}


def register(write: bool = False) -> dict:
    """Canonical registry entries for the plan's slice runs; writing requires the WHOLE coverage complete."""
    from hebloc.store.runs import ANNOTATIONS_CONFIG
    from hebloc.team import plan as P

    plan = P.load()
    if not plan.approved:
        raise PlanRefusal("registering canonical runs requires an approved plan")
    rows = P.status(plan)
    entries = P.registry_entries(plan, rows)
    missing = [r["slice"] for r in rows if not (r["complete"] and r["checks_ok"])]
    comp = completeness(plan, P.load_work_plan(), mode="full", coverage=plan.coverage)
    if write and not comp["complete"]:
        raise PlanRefusal(f"not writing: the coverage is not complete (missing {comp['missing']}, invalid "
                          f"{comp['invalid_or_duplicate']}, duplicated units {comp['units_in_more_than_one_run']}, "
                          f"units {comp['units_present']}/{comp['units_expected']})")
    if write:
        import re

        import yaml

        from hebloc.store.io import atomic_write_text

        cur = ANNOTATIONS_CONFIG.read_text(encoding="utf-8")
        m = re.search(r"^canonical:", cur, re.M)          # the real key, not the commented example
        head = cur[:m.start()] if m else cur
        atomic_write_text(head + yaml.safe_dump({"canonical": entries}, sort_keys=True, allow_unicode=True),
                          ANNOTATIONS_CONFIG)
    return {"entries": entries, "slices_not_ready": missing, "complete": comp["complete"], "written": write}
