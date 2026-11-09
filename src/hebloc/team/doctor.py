"""``hebloc doctor``: is this machine set up correctly, and does it match everyone else's?

Each check returns PASS / WARN / FAIL / TODO with the exact command that fixes it. The report is
also written to ``data/team/doctor.json`` (send it to Ori if anything is not PASS).

- ready_for_setup: environment, packages, corpora, derived data, fingerprints and models are right;
- ready_to_parse:  additionally the agreement check passed with the current settings, and the plan is approved.
"""

from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata

from hebloc.paths import ANCHOR_PATH, BASELINE_PATH, CORPORA, CORPORA_DIR, DATA_DIR, ROOT, UNITS_DIR
from hebloc.store.io import atomic_write_json

REPORT_PATH = DATA_DIR / "team" / "doctor.json"
KEY_PACKAGES = ("torch", "transformers", "tokenizers", "safetensors", "huggingface-hub", "duckdb", "pyarrow",
                "numpy", "pandas", "pyyaml")


def _r(name, status, detail="", fix=""):
    return {"check": name, "status": status, "detail": detail, "fix": fix}


def _locked_versions() -> dict[str, str]:
    text = (ROOT / "uv.lock").read_text(encoding="utf-8")
    return {m.group(1): m.group(2) for m in re.finditer(r'\[\[package\]\]\nname = "([^"]+)"\nversion = "([^"]+)"', text)}


def check_python() -> list[dict]:
    out = []
    v = platform.python_version()
    out.append(_r("python 3.12", "PASS" if v.startswith("3.12.") else "FAIL", v,
                  "install Python 3.12 from python.org, then: uv sync"))
    base = getattr(sys, "_base_executable", sys.executable)
    uv_managed = "\\uv\\python\\" in base.lower() or "/uv/python/" in base.lower()
    out.append(_r("interpreter", "WARN" if platform.system() == "Windows" and uv_managed else "PASS", base,
                  "uv-managed Python is unsigned: Windows Smart App Control may block it. "
                  "Install python.org 3.12 and run `uv sync` (docs/PARTNERS.md)"))
    utf8 = bool(sys.flags.utf8_mode)
    out.append(_r("UTF-8 mode", "PASS" if utf8 or platform.system() != "Windows" else "WARN",
                  f"PYTHONUTF8={'1' if utf8 else 'unset'}", 'PowerShell: $env:PYTHONUTF8 = "1"'))
    locked = _locked_versions()
    bad = []
    for p in KEY_PACKAGES:
        try:
            have = metadata.version(p).split("+")[0]
        except metadata.PackageNotFoundError:
            have = None
        if have != locked.get(p):
            bad.append(f"{p} {have} != lock {locked.get(p)}")
    out.append(_r("packages = uv.lock", "FAIL" if bad else "PASS", "; ".join(bad) or f"{len(KEY_PACKAGES)} key packages match",
                  "uv sync"))
    return out


def check_git() -> list[dict]:
    def git(*a):
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout.strip()

    try:
        head = git("rev-parse", "--short", "HEAD")
    except OSError:
        return [_r("git", "WARN", "git not found")]
    dirty = [ln for ln in git("status", "--porcelain", "--untracked-files=no").splitlines() if ln]
    return [_r("git checkout", "WARN" if dirty else "PASS",
               f"{git('rev-parse', '--abbrev-ref', 'HEAD')} @ {head}" + (f"; {len(dirty)} modified file(s)" if dirty else ""),
               "commit or `git stash` your changes; then `git pull`")]


def check_corpora(quick: bool) -> list[dict]:
    from hebloc.baseline import anchor_mismatches, compare_to_baseline, read_anchor, read_baseline

    if not CORPORA_DIR.is_dir() or not all((CORPORA_DIR / f).is_dir() for f in CORPORA.values()):
        return [_r("corpora present", "TODO", f"{CORPORA_DIR} missing or incomplete",
                   "uv run hebloc corpora install --from <the course corpora archive (or its folder)>")]
    if not BASELINE_PATH.exists():
        return [_r("corpora = anchor", "TODO", "not verified yet", "uv run hebloc corpora verify")]
    probs = anchor_mismatches(read_baseline(BASELINE_PATH), read_anchor(ANCHOR_PATH))
    out = [_r("corpora = anchor", "FAIL" if probs else "PASS", "; ".join(probs[:3]) or "baseline matches the git-tracked anchor",
              "uv run hebloc corpora verify   (re-download the corpora if it still fails)")]
    if not quick:
        drift = compare_to_baseline(read_baseline(BASELINE_PATH), CORPORA_DIR, deep=False)
        out.append(_r("corpora unchanged", "PASS" if drift.clean else "FAIL",
                      "file list, sizes and times match the baseline" if drift.clean else
                      f"missing {len(drift.missing)}, added {len(drift.added)}, changed {len(drift.changed)} "
                      f"(e.g. {(drift.missing + drift.added + drift.changed)[:2]})",
                      "never edit corpora/; restore it from the download"))
    return out


def check_data() -> list[dict]:
    from hebloc.catalog import DOCUMENTS_PATH
    from hebloc.team import fingerprint as F

    out = []
    if not DOCUMENTS_PATH.exists():
        return [_r("catalog", "TODO", "no documents.parquet", "uv run hebloc inventory")]
    missing = [c for c in CORPORA if not list((UNITS_DIR / c).glob("*.parquet"))]
    if missing:
        return [_r("units", "TODO", f"missing for {missing}", "uv run hebloc prepare")]
    ref = F.read_reference()
    if ref is None:
        return [_r("data fingerprints", "WARN", "no reference in config/reference/fingerprints.json")]
    probs = F.compare(F.compute(), ref)
    hard = [p for p in probs if not p.startswith("note:")]
    out.append(_r("data fingerprints", "FAIL" if hard else "PASS",
                  "; ".join(probs) or f"documents + units of {len(CORPORA)} corpora identical to the reference",
                  "uv sync; uv run hebloc inventory; uv run hebloc prepare   (then tell Ori if it still differs)"))
    return out


def check_models(model: str) -> list[dict]:
    from hebloc.parse import models as M

    out = []
    for name in dict.fromkeys([model, "base"]):
        probs = M.verify(name)
        out.append(_r(f"model {name}", "FAIL" if probs and any("vendored" in p for p in probs) else ("TODO" if probs else "PASS"),
                      "; ".join(probs[:2]) or "all files match the pinned sha256", "uv run hebloc models fetch"))
    return out


def check_parse_readiness(person: str | None) -> list[dict]:
    from hebloc.team import agreement as A
    from hebloc.team import plan as P

    from hebloc.team import identity as I

    plan = P.load()
    out = []
    stored = I.get()
    out.append(_r("identity", "PASS" if stored else "TODO",
                  f"this computer is set up for {stored.capitalize()}" if stored else "not set",
                  "uv run hebloc whoami --set <ori|efrat|adi>"))
    res = json.loads(A.RESULT_PATH.read_text(encoding="utf-8")) if A.RESULT_PATH.exists() else None
    if res is None:
        out.append(_r("agreement check", "TODO", "not run", f"uv run hebloc agreement --as {person or '<name>'}"))
    else:
        same = res.get("settings", {}).get("settings_id") == plan.settings["settings_id"]
        out.append(_r("agreement check", "PASS" if res.get("ok") and same else ("TODO" if not same else "FAIL"),
                      (f"{res.get('pieces_identical')}/{res.get('pieces_compared')} pieces identical, "
                       f"{res.get('subwords_per_second')} sub-words/s" if res.get("compared") else res.get("reason", ""))
                      + ("" if same else " (made with other settings)"),
                      f"uv run hebloc agreement --as {person or '<name>'}   (send data/team/agreement.json to Ori if it fails)"))
    out.append(_r("plan approved", "PASS" if plan.approved else "TODO",
                  f"status={plan.status}, coverage={plan.coverage}, settings={plan.settings['settings_id']}",
                  "wait for Ori: parsing starts only after the M3 gate decisions"))
    if person:
        try:
            wp = P.load_work_plan()
            cov = plan.coverage if plan.coverage in P.COVERAGES else "A"
            mine = wp["assignment"][cov]["people"].get(person)
            out.append(_r("your slices", "PASS" if mine else "WARN",
                          (f"option {cov}: " + ", ".join(mine["slices"]) + f" (~{mine['hours_at_reference_rate']} h)") if mine
                          else f"{person!r} is not in the plan's people {list(plan.people)}"))
        except FileNotFoundError as e:
            out.append(_r("your slices", "WARN", str(e)))
    return out


def check_machine() -> list[dict]:
    import psutil

    out = []
    ram = psutil.virtual_memory().total / 2**30
    out.append(_r("RAM", "PASS" if ram >= 12 else "WARN", f"{ram:.1f} GB", "parsing needs ~2-4 GB free; close other programs"))
    free = shutil.disk_usage(DATA_DIR if DATA_DIR.exists() else ROOT).free / 2**30
    out.append(_r("free disk", "PASS" if free >= 15 else "WARN", f"{free:.0f} GB", "free at least 15 GB (30 GB to parse Modern)"))
    synced = [s for s in ("onedrive", "dropbox", "google drive", "icloud") if s in str(ROOT).lower()]
    out.append(_r("project folder", "WARN" if synced else "PASS",
                  f"{ROOT} ({len(str(ROOT))} characters)" + (f": inside a {synced[0]} synced folder" if synced else ""),
                  "clone the project into your home folder instead (PARTNER_START.md §0): syncing ~10 GB of "
                  "working files slows everything and can corrupt runs"))
    out.append(_r("CPU", "PASS", f"{platform.processor() or platform.machine()}; {psutil.cpu_count(logical=False)} cores / "
                  f"{psutil.cpu_count()} threads"))
    bat = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if bat is not None:
        out.append(_r("power", "PASS" if bat.power_plugged else "WARN", "plugged in" if bat.power_plugged else "on battery",
                      "plug in before parsing (battery mode throttles the CPU)"))
    if platform.system() == "Windows":
        known = {"381b4222-f694-41f0-9685-ff5bb260df2e": "Balanced", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c": "High performance",
                 "a1841308-3541-4fab-bc81-f71556f20b4a": "Power saver", "e9a42b02-d5df-448d-aa00-03f14749eb61": "Ultimate performance"}
        try:
            raw = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, timeout=10).stdout
            m = re.search(rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", raw)   # name is localized
            name = known.get(m.group(0).decode(), m.group(0).decode()) if m else "unknown"
            out.append(_r("power plan", "PASS", f"{name} (for long runs set Settings > System > Power > "
                          "Power mode: Best performance, and disable sleep)"))
        except (OSError, subprocess.SubprocessError):
            pass
    return out


def run(person: str | None = None, *, quick: bool = False, write: bool = True) -> dict:
    from hebloc.team import identity as I
    from hebloc.team import plan as P

    person = person or I.get()

    model = P.load().settings["model"]
    sections = {"python": check_python, "git": check_git, "corpora": lambda: check_corpora(quick),
                "data": check_data, "models": lambda: check_models(model),
                "parsing": lambda: check_parse_readiness(person), "machine": check_machine}
    results = {}
    for name, fn in sections.items():
        try:
            results[name] = fn()
        except Exception as e:  # noqa: BLE001 — a broken check must not hide the others
            results[name] = [_r(name, "FAIL", f"{type(e).__name__}: {e}")]
    flat = [r for rs in results.values() for r in rs]
    setup = [r for s in ("python", "corpora", "data", "models") for r in results[s]]
    rep = {"person": person, "when_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "platform": platform.platform(), "sections": results,
           "ready_for_setup": all(r["status"] in ("PASS", "WARN") for r in setup),
           "ready_to_parse": all(r["status"] in ("PASS", "WARN") for r in flat),
           "counts": {s: sum(r["status"] == s for r in flat) for s in ("PASS", "WARN", "TODO", "FAIL")}}
    if write:
        atomic_write_json(rep, REPORT_PATH)
    return rep
