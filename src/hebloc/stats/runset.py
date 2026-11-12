"""Which parse runs feed which corpus, and the completeness gate (D-045, D-046).

A *run set* maps each corpus to the runs that analyse it: an explicit list now
(``--runs mikra/base-topk-v1__mikra,…``) or the registered canonical runs after the merge
(``config/annotations.yaml``, ``hebloc.store.runs.canonical_runs``). Same code path for both.

Before anything is computed, each corpus is checked:
* the runs together contain every unit of the corpus exactly once (no missing, extra or duplicated
  ``sent_id``), compared with ``data/units/<corpus>`` (full view);
* every run's ``checks.json`` is ``ok`` and still describes the run (fingerprint).
A corpus that fails is refused, unless ``scale_test`` is set (timing only; never published).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from hebloc.paths import ANNOTATIONS_DIR, CORPORA, UNITS_DIR
from hebloc.store.io import read_json, sql_list, sql_str
from hebloc.store.runs import ANNOTATIONS_CONFIG, Run, canonical_runs, resolve


class RunSetRefusal(RuntimeError):
    """The run set does not cover its corpora completely and validly."""


@dataclass
class RunSet:
    runs: dict[str, list[Run]]                 # corpus → runs (corpus order of CORPORA)
    source: str                                # "explicit" | "registered"
    checks: dict[str, dict] = field(default_factory=dict)   # corpus → completeness report

    def refs(self) -> dict[str, list[str]]:
        return {c: [r.ref for r in rs] for c, rs in self.runs.items()}

    @property
    def corpora(self) -> list[str]:
        return list(self.runs)

    def complete(self) -> bool:
        return bool(self.checks) and all(c["complete"] for c in self.checks.values())

    def status(self) -> str:
        """``final`` only for the registered runs of all five corpora, all complete (D-045)."""
        if self.source == "registered" and set(self.runs) == set(CORPORA) and self.complete():
            return "final"
        return "provisional"


def _order(d: dict[str, list[Run]]) -> dict[str, list[Run]]:
    return {c: sorted(d[c], key=lambda r: r.ref) for c in CORPORA if d.get(c)}


def from_refs(refs: list[str], root: Path = ANNOTATIONS_DIR) -> RunSet:
    """Explicit run list. A run's corpus is its collection (M5 layout ``<corpus>/runs/<run_id>``);
    pilot/agreement runs are not corpus runs and are refused."""
    by: dict[str, list[Run]] = {}
    for ref in refs:
        run = resolve(ref.strip(), root)
        if run.collection not in CORPORA:
            raise RunSetRefusal(f"{run.ref}: not a corpus run (collection {run.collection!r}); "
                                f"statistics use M5 runs under data/annotations/<corpus>/runs/")
        if any(r.ref == run.ref for r in by.get(run.collection, [])):
            raise RunSetRefusal(f"{run.ref} given twice")
        by.setdefault(run.collection, []).append(run)
    if not by:
        raise RunSetRefusal("no runs given")
    return RunSet(_order(by), "explicit")


def from_registry(root: Path = ANNOTATIONS_DIR, config: Path = ANNOTATIONS_CONFIG) -> RunSet:
    reg = canonical_runs(root=root, config=config)
    if not reg:
        raise RunSetRefusal(f"no canonical runs registered in {config} (after the merge: hebloc plan register --write)")
    return RunSet(_order(reg), "registered")


def _validation(run: Run) -> dict:
    from hebloc.parse.checks import run_fingerprint

    p = run.path / "checks.json"
    if not p.exists():
        return {"ok": False, "fingerprint_current": False, "fingerprint": None, "problem": "no checks.json"}
    rep = read_json(p)
    fp = run_fingerprint(run.path)
    return {"ok": bool(rep.get("ok")), "fingerprint_current": rep.get("fingerprint") == fp, "fingerprint": fp}


def check_corpus(corpus: str, runs: list[Run], units_root: Path = UNITS_DIR) -> dict:
    """Do ``runs`` contain every full-view unit of ``corpus`` exactly once, with valid checks?"""
    files = [f for r in runs for s in r.shards() if (f := r.part_file("inputs", s)).exists()]
    units_glob = (units_root / corpus / "*.parquet").as_posix()
    con = duckdb.connect()
    con.execute(f"CREATE VIEW u AS SELECT sent_id FROM read_parquet({sql_str(units_glob)}) WHERE in_full_view")
    if files:
        con.execute(f"CREATE VIEW i AS SELECT sent_id FROM read_parquet({sql_list(files)}) "
                    f"WHERE sent_id LIKE {sql_str(corpus + ':%')}")
    else:
        con.execute("CREATE VIEW i AS SELECT CAST(NULL AS VARCHAR) AS sent_id WHERE false")
    expected, present, rows = con.execute(
        "SELECT (SELECT count(*) FROM u), (SELECT count(DISTINCT sent_id) FROM i), (SELECT count(*) FROM i)").fetchone()
    missing = con.execute("SELECT count(*) FROM u ANTI JOIN i USING (sent_id)").fetchone()[0]
    extra = con.execute("SELECT count(*) FROM (SELECT DISTINCT sent_id FROM i) ANTI JOIN u USING (sent_id)").fetchone()[0]
    validations = {r.ref: _validation(r) for r in runs}
    bad = [ref for ref, v in validations.items() if not (v["ok"] and v["fingerprint_current"])]
    rep = {"corpus": corpus, "runs": [r.ref for r in runs], "units_expected": expected, "units_in_runs": present,
           "units_missing": missing, "units_not_in_corpus": extra, "duplicated_rows": rows - present,
           "runs_not_validated": bad, "validations": validations}
    rep["complete"] = expected > 0 and missing == 0 and extra == 0 and rows == present and not bad
    return rep


def check(rs: RunSet, *, scale_test: bool = False, units_root: Path = UNITS_DIR) -> RunSet:
    """Fill ``rs.checks``; raise ``RunSetRefusal`` for an incomplete corpus unless ``scale_test``."""
    rs.checks = {c: check_corpus(c, runs, units_root) for c, runs in rs.runs.items()}
    bad = [c for c, r in rs.checks.items() if not r["complete"]]
    if bad and not scale_test:
        lines = [f"{c}: {r['units_in_runs']:,}/{r['units_expected']:,} units, missing {r['units_missing']:,}, "
                 f"not in corpus {r['units_not_in_corpus']:,}, duplicated {r['duplicated_rows']:,}, "
                 f"runs not validated {r['runs_not_validated'] or 'none'}" for c, r in rs.checks.items() if c in bad]
        raise RunSetRefusal("incomplete or invalid corpus (statistics need complete corpora, D-045):\n  " + "\n  ".join(lines))
    return rs
