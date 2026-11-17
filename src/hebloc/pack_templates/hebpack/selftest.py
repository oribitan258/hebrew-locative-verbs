"""Recompute the official §4 statistics from the package data and compare them with official/.

    python -m hebpack.selftest --quick        # Mikra, Hazal, Medieval, Haskala (a few minutes)
    python -m hebpack.selftest                # all five corpora incl. Modern (about 40 minutes)
    python -m hebpack.selftest --corpus hazal

It runs the verbatim official code (hebpack/_official) on the package's tokens, pieces and run units, then compares
the per-unit measures and all 11 tables with the official ones: integers exactly, decimals to 1e-12 (relative).
PASS means the data in this package reproduces the official statistics. Nothing in data/ or official/ is written;
recomputed files go to a temporary folder (kept with --keep under analyses/_selftest/).
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from hebpack import ANALYSES, CORPORA
from hebpack.db import OFFICIAL_TABLES, stats_dir

QUICK = ("mikra", "hazal", "medieval", "haskala")


def _same(a: pd.DataFrame, b: pd.DataFrame, key: list[str] | None = None) -> tuple[bool, str]:
    if list(a.columns) != list(b.columns):
        return False, f"columns differ: {list(a.columns)} vs {list(b.columns)}"
    if len(a) != len(b):
        return False, f"rows {len(a)} vs {len(b)}"
    key = key or list(a.columns)
    a = a.sort_values(key, kind="stable").reset_index(drop=True)
    b = b.sort_values(key, kind="stable").reset_index(drop=True)
    for c in a.columns:
        x, y = a[c], b[c]
        if pd.api.types.is_float_dtype(x) or pd.api.types.is_float_dtype(y):
            xv, yv = x.astype("float64").to_numpy(), y.astype("float64").to_numpy()
            if not np.allclose(xv, yv, rtol=1e-12, atol=0, equal_nan=True):
                return False, f"column {c} differs"
        elif not x.astype(object).where(x.notna(), None).equals(y.astype(object).where(y.notna(), None)):
            return False, f"column {c} differs"
    return True, ""


def _same_units(new_files: list[Path], off_files: list[Path]) -> tuple[bool, str]:
    """Per-unit measures, exactly (NULL-safe): EXCEPT ALL in both directions, in DuckDB (spills to disk; Modern has
    8.9M units, which must not be compared in pandas on a 16 GB machine)."""
    from hebpack.db import duck

    lst = lambda fs: "[" + ", ".join("'" + Path(f).as_posix().replace("'", "''") + "'" for f in fs) + "]"  # noqa: E731
    con = duck()
    cols = ", ".join(f'"{c}"' for c in pq.read_schema(off_files[0]).names)
    off, new = f"SELECT {cols} FROM read_parquet({lst(off_files)})", f"SELECT {cols} FROM read_parquet({lst(new_files)})"
    n_off, n_new = (con.execute(f"SELECT count(*) FROM ({q})").fetchone()[0] for q in (off, new))
    d1 = con.execute(f"SELECT count(*) FROM ({off} EXCEPT ALL {new})").fetchone()[0]
    d2 = con.execute(f"SELECT count(*) FROM ({new} EXCEPT ALL {off})").fetchone()[0]
    con.close()
    if n_off != n_new or d1 or d2:
        return False, f"rows {n_off} vs {n_new}; {d1} official rows not reproduced, {d2} extra"
    return True, ""


def run(corpora: list[str], keep: bool = False) -> bool:
    from hebpack import official as O

    sd = stats_dir()
    work = Path(tempfile.mkdtemp(prefix="hebpack-selftest-"))
    ok_all = True
    try:
        for corpus in corpora:
            t0 = time.time()
            files = []
            for rid in O.run_ids(corpus):
                tab = O.unit_metrics_run(corpus, rid, progress=True)
                f = work / "unit_metrics" / corpus / f"{rid}.parquet"
                f.parent.mkdir(parents=True, exist_ok=True)
                pq.write_table(tab, f)
                files.append(f)
            results = {"unit_metrics": _same_units(files, sorted((sd / "unit_metrics" / corpus).glob("*.parquet")))}
            tabs, probs = O.corpus_tables(corpus, files)
            for name in OFFICIAL_TABLES:
                off = pq.read_table(sd / f"{name}.parquet").to_pandas()
                off = off[off["corpus_id"] == corpus]
                results[name] = _same(off, tabs[name].to_pandas()[list(off.columns)])
            ok = all(r[0] for r in results.values()) and not probs
            ok_all &= ok
            print(f"\n{CORPORA[corpus]}: {'PASS' if ok else 'FAIL'}  ({time.time() - t0:.0f} s)")
            for name, (same, why) in results.items():
                print(f"  {name:16} {'identical' if same else 'DIFFERENT: ' + why}")
            print(f"  reconciliation   {'0 problems' if not probs else probs}")
        if keep:
            dst = ANALYSES / "_selftest"
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(work, dst)
            print(f"\nrecomputed unit metrics kept in {dst}")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("\nSELFTEST " + ("PASS: the package reproduces the official statistics." if ok_all else "FAIL: report this to Ori."))
    from hebpack import state

    if set(QUICK) <= set(corpora):
        state.record("selftest_quick", ok_all, ",".join(corpora))
    if set(CORPORA) <= set(corpora):
        state.record("selftest_all", ok_all, ",".join(corpora))
    return ok_all


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--quick", action="store_true", help="Mikra, Hazal, Medieval, Haskala only")
    g.add_argument("--corpus", action="append", choices=list(CORPORA))
    p.add_argument("--keep", action="store_true", help="keep the recomputed unit metrics in analyses/_selftest/")
    a = p.parse_args(argv)
    corpora = list(QUICK) if a.quick else (a.corpus or list(CORPORA))
    return 0 if run(corpora, a.keep) else 1


if __name__ == "__main__":
    sys.exit(main())
