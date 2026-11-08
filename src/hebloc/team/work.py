"""Parse an assigned slice (partners) and merge everyone's results (Ori).

``hebloc parse --slice S --as NAME``
    Refuses unless the plan is approved, the slice is in the chosen coverage, and NAME owns it
    (no two people can parse the same units by accident). Parses the slice's units
    (``units.text_norm``, sent_id order) into ``data/annotations/<corpus>/runs/<settings_id>__<slice>``,
    resumable, then validates the run against ``units.text_norm`` and runs the integrity check.
    ``--limit N`` makes a SMOKE run instead (first N units; allowed in draft; collection ``smoke``,
    never canonical).

``hebloc merge <bundle.zip>...``
    For each bundle: verify (sha256, anchor), restore, integrity-check the run against this
    machine's units, and check that it is a run of the current plan. Then report plan progress.
    ``hebloc plan register --write`` puts the complete, valid slice runs in config/annotations.yaml.
"""

from __future__ import annotations

from pathlib import Path

from hebloc.paths import ANNOTATIONS_DIR


class PlanRefusal(RuntimeError):
    pass


def run_slice(slice_id: str, person: str, *, threads: int = 8, limit: int | None = None) -> dict:
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
    if not smoke:
        if not plan.approved:
            raise PlanRefusal(f"the plan is not approved yet (status={plan.status}, coverage={plan.coverage}); "
                              "real slices wait for Ori's go-ahead. A smoke test is allowed: add --limit 200")
        if plan.coverage not in s.coverage:
            raise PlanRefusal(f"slice {slice_id} is not part of coverage option {plan.coverage}")
        who = P.owner(plan, P.load_work_plan(), slice_id, plan.coverage)
        if who != person:
            raise PlanRefusal(f"slice {slice_id} is assigned to {who!r}, not {person!r} (docs/WORK_PLAN.md)")
    units = P.slice_units(s, limit=limit)
    if not units:
        raise PlanRefusal(f"slice {slice_id} selects no units on this machine (run hebloc prepare?)")
    run_id = f"{st['settings_id']}__{slice_id}" + (f"__{person}__n{limit}" if smoke else "")
    collection = "smoke" if smoke else s.corpus
    rdir = ANNOTATIONS_DIR / collection / "runs" / run_id
    lm = M.load(st["model"], threads=threads)
    manifest = run(units, lm, rdir, RunConfig(
        run_id=run_id, variant="default", budget=st["budget"], batch_size=st["batch_size"],
        max_batch_subwords=st["max_batch_subwords"], mst_fix=st["mst_fix"], lex_topk=st["lex_topk"],
        shard_size=st["shard_size"], threads=threads,
        extra={"slice": slice_id, "person": person, "settings_id": st["settings_id"], "plan_sha256": plan.sha256,
               "smoke": smoke}))
    checks = validate_run(rdir, expected=dict(units))
    import duckdb
    integrity = check_run(resolve(rdir), duckdb.connect())
    return {"run": f"{collection}/{run_id}", "units": manifest["units"], "pieces": manifest["pieces"],
            "status": manifest["status"], "parse_seconds": manifest["parse_seconds"],
            "subwords_per_second": round(manifest["subwords"] / manifest["parse_seconds"], 1) if manifest["parse_seconds"] else None,
            "validation_ok": checks["ok"], "integrity_ok": integrity["ok"], "problems": integrity["problems"],
            "invalid_tree_share": checks["model_invalid_tree_share"],
            "next": f"uv run hebloc bundle create {collection}/{run_id}" if checks["ok"] and integrity["ok"] else
                    "send data/team/doctor.json and the run's checks.json to Ori"}


def merge(bundles: list[Path], *, overwrite: bool = False) -> dict:
    """Verify + restore bundles, integrity-check each restored run, report plan progress."""
    import duckdb

    from hebloc.store import bundle as B
    from hebloc.store.integrity import check_run
    from hebloc.store.runs import resolve
    from hebloc.team import plan as P

    plan = P.load()
    expected_refs = {plan.run_ref(s): s.id for s in plan.slices}
    out = []
    con = duckdb.connect()
    from hebloc.store.io import file_sha256

    for z in bundles:
        v = B.verify(Path(z))
        row = {"bundle": str(z), "run": v.get("run"), "verified": v["ok"], "problems": list(v["problems"])}
        side = Path(str(z) + ".sha256")              # whole-file digest written by `bundle create`
        if side.exists():
            row["sidecar"] = "match" if side.read_text(encoding="utf-8").split()[0] == file_sha256(Path(z)) else "MISMATCH"
            if row["sidecar"] == "MISMATCH":
                row["problems"].append("zip does not match its .sha256 file (damaged or altered in transfer)")
        else:
            row["sidecar"] = "missing"
            row["problems"].append("note: no .zip.sha256 next to the zip (members were still verified)")
        if v["ok"] and row["sidecar"] != "MISMATCH":
            res = B.restore(Path(z), overwrite=overwrite)
            run = resolve(res["path"])
            ci = check_run(run, con)
            m = run.manifest
            in_plan = run.ref in expected_refs
            smoke = run.collection == "smoke"
            same_settings = (m.get("extra") or {}).get("settings_id") == plan.settings["settings_id"]
            row.update({"restored": res["written"], "validation_ok": res["validation_ok"],
                        "integrity_ok": ci["ok"], "integrity_problems": ci["problems"],
                        "slice": (m.get("extra") or {}).get("slice"), "in_plan": in_plan, "smoke": smoke,
                        "same_settings": same_settings, "person": (m.get("extra") or {}).get("person")})
            # a smoke run tests the chain but is never part of the plan (never registered)
            row["ok"] = res["validation_ok"] and ci["ok"] and same_settings and (in_plan or smoke)
        else:
            row["ok"] = False
        out.append(row)
    return {"bundles": out, "progress": P.status(plan)}


def register(write: bool = False) -> dict:
    """Canonical registry entries for every complete, valid slice run of the current plan."""
    from hebloc.store.runs import ANNOTATIONS_CONFIG
    from hebloc.team import plan as P

    plan = P.load()
    if not plan.approved:
        raise PlanRefusal("registering canonical runs requires an approved plan")
    rows = P.status(plan)
    entries = P.registry_entries(plan, rows)
    missing = [r["slice"] for r in rows if not (r["complete"] and r["checks_ok"])]
    text = None
    if write:
        import re

        import yaml

        cur = ANNOTATIONS_CONFIG.read_text(encoding="utf-8")
        m = re.search(r"^canonical:", cur, re.M)          # the real key, not the commented example
        head = cur[:m.start()] if m else cur
        text = head + yaml.safe_dump({"canonical": entries}, sort_keys=True, allow_unicode=True)
        from hebloc.store.io import atomic_write_text
        atomic_write_text(text, ANNOTATIONS_CONFIG)
    return {"entries": entries, "slices_not_ready": missing, "written": write}
