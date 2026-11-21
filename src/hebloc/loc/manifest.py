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


#: I3 column names are binding (EFRAT_SECTION_6.md §7): every R2 table must carry at least these columns
REQUIRED_COLUMNS = {
    "instances": ("instance_id", "corpus", "subcorpus", "run_id", "shard", "doc_id", "sent_id", "piece_idx", "word_idx",
                  "sent_word_idx", "ref", "in_full_view", "in_curated_view", "form", "lemma", "upos", "verb_key", "in_lexicon",
                  "paper_class", "match_method", "voice", "template_proxy", "signature", "has_do", "do_kind", "n_pp",
                  "has_bare_np", "flags"),
    "arguments": ("instance_id", "arg_idx", "slot", "head_word_idx", "head_form", "head_lemma", "head_upos", "is_pronoun",
                  "pron_feats", "deprel", "p_exact", "p_family", "flags"),
    "roles": ("instance_id", "resolver_id", "outcome", "reason", "locatum_arg_idx", "location_arg_idx", "decided_by"),
    "verb_profiles": ("verb_key", "n_tokens"),
    "verb_preps": ("verb_key", "frame", "p_family", "p_exact", "count", "example_ids"),
    "verb_classes": ("verb_key", "class", "class_basis", "k", "nonlocative_share", "paper_class", "agrees_with_paper",
                     "identity_verdict", "identity_family", "putting_removal", "deciding_ids"),
    "swap_candidates": ("verb_key", "p_family", "n_swap_nouns", "swap_nouns", "n_as_do", "n_as_pobj", "example_ids"),
}


def table_of(rel: str) -> str | None:
    """The I3 table a parquet file belongs to (``instances/<run>.parquet`` or ``verb_classes.parquet``)."""
    parts = Path(rel).parts
    for name in (Path(rel).stem, *(parts[:-1][-1:] if len(parts) > 1 else ())):
        if name in REQUIRED_COLUMNS:
            return name
    return None


def verify(folder: Path) -> list[str]:
    """Re-hash every file listed in ``folder/manifest.json``, and check that every I3 table has its binding columns;
    return problems (empty = OK)."""
    import pyarrow.parquet as pq

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
        elif p.suffix == ".parquet" and table_of(rel):
            cols = set(pq.read_schema(p).names)
            miss = [c for c in REQUIRED_COLUMNS[table_of(rel)] if c not in cols]
            if miss and pq.read_metadata(p).num_rows:
                probs.append(f"schema {rel}: missing I3 columns {miss}")
    return probs
