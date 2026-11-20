"""Provenance for every hebloc.loc output (EFRAT_SECTION_6.md §7 I5).

``manifest.json`` records: the methodology version, the exact code (commit, tag, a boolean
``dirty``), the lexicon and noun-type hashes, the data source (repo run fingerprints or the package
``VERIFICATION.json`` hash), the sha256 + row count of every file written, and the Python and
package versions.
"""

from __future__ import annotations

import io
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa

from hebloc.loc import METHODOLOGY
from hebloc.paths import ROOT
from hebloc.store.io import atomic_write_json, atomic_write_text, file_sha256, parquet_rows, read_json

CSV_BOM = "﻿"   # UTF-8 with BOM: Excel shows Hebrew correctly; pandas/DuckDB read it unchanged


class ReleaseRefusal(Exception):
    """The code state does not allow this step (e.g. a dirty tree without --dev)."""


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def git_state() -> dict:
    """``{git_commit, git_tag, git_describe, dirty}``; values are None when git is unavailable."""
    try:
        commit = _git("rev-parse", "HEAD")
        dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
        tags = [t for t in _git("tag", "--points-at", "HEAD").splitlines() if t]
        try:
            describe = _git("describe", "--tags", "--always")
        except subprocess.CalledProcessError:
            describe = commit[:12]
        return {"git_commit": commit, "git_tag": sorted(tags)[0] if tags else None, "git_describe": describe,
                "dirty": dirty}
    except Exception:  # noqa: BLE001 — git missing: provenance is recorded as unknown
        return {"git_commit": None, "git_tag": None, "git_describe": None, "dirty": None}


def require_clean(dev: bool) -> dict:
    """R1 steps refuse a dirty tree unless ``--dev`` (Ori's development runs; recorded)."""
    st = git_state()
    if st["dirty"] and not dev:
        raise ReleaseRefusal("tracked files are modified (git status). Outputs must come from committed code; "
                             "commit or restore first (Ori only: --dev for a development run).")
    st["dev_override"] = bool(dev and st["dirty"])
    return st


def versions() -> dict:
    import duckdb
    import pyarrow
    import yaml

    out = {"python": platform.python_version(), "pyarrow": pyarrow.__version__, "duckdb": duckdb.__version__,
           "pyyaml": yaml.__version__}
    try:
        import pandas

        out["pandas"] = pandas.__version__
    except ImportError:  # pragma: no cover
        pass
    return out


def write_csv(table: pa.Table, path: Path) -> Path:
    """CSV copy with a UTF-8 BOM (lists are joined with '; ')."""
    import pyarrow.compute as pc
    import pyarrow.csv as pacsv

    cols = {}
    for name in table.column_names:
        col = table[name]
        if pa.types.is_list(col.type):
            col = pc.binary_join(pc.cast(col, pa.list_(pa.string())), "; ")
        cols[name] = col
    buf = io.BytesIO()
    pacsv.write_csv(pa.table(cols), buf)
    return atomic_write_text(CSV_BOM + buf.getvalue().decode("utf-8"), Path(path))


def write_manifest(folder: Path, *, what: str, git: dict, source: dict | None, extra: dict | None = None) -> dict:
    """Hash every file in ``folder`` (recursively, except the manifest) and write ``manifest.json``."""
    folder = Path(folder)
    files = {}
    for p in sorted(folder.rglob("*")):
        if p.is_file() and p.name != "manifest.json" and not p.name.endswith(".tmp"):
            rel = p.relative_to(folder).as_posix()
            entry = {"sha256": file_sha256(p), "bytes": p.stat().st_size}
            if p.suffix == ".parquet":
                entry["rows"] = parquet_rows(p)
            files[rel] = entry
    m = {"methodology": METHODOLOGY, "what": what,
         "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         **{k: git.get(k) for k in ("git_commit", "git_tag", "git_describe", "dirty", "dev_override")},
         "source": source, **(extra or {}), "versions": versions(), "files": files}
    atomic_write_json(m, folder / "manifest.json")
    return m


def verify(folder: Path) -> list[str]:
    """Re-hash every file listed in ``folder/manifest.json``; return problems (empty = OK)."""
    folder = Path(folder)
    mp = folder / "manifest.json"
    if not mp.exists():
        return [f"no manifest.json in {folder}"]
    m = read_json(mp)
    probs = []
    for rel, e in m.get("files", {}).items():
        p = folder / rel
        if not p.exists():
            probs.append(f"missing {rel}")
        elif file_sha256(p) != e["sha256"]:
            probs.append(f"changed {rel}")
    return probs
