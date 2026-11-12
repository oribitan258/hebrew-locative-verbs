"""Command-line entry point: ``uv run hebloc <command>``.

Commands are added milestone by milestone. Each one is a thin wrapper around library code.
"""

from __future__ import annotations

import argparse
import sys
import time


def _cmd_baseline(args: argparse.Namespace) -> int:
    """Record the corpora baseline. If a git-tracked anchor exists, the (re)computed baseline
    must match it — otherwise nothing is written. Without an anchor, both are written."""
    from hebloc.baseline import (
        anchor_mismatches,
        compute_baseline,
        make_anchor,
        read_anchor,
        read_baseline,
        write_anchor,
        write_baseline,
    )
    from hebloc.paths import ANCHOR_PATH, BASELINE_PATH, CORPORA_DIR

    if BASELINE_PATH.exists() and not args.force:
        print(f"Baseline already exists: {BASELINE_PATH} (use --force to recompute deliberately).")
        if ANCHOR_PATH.exists():
            problems = anchor_mismatches(read_baseline(BASELINE_PATH), read_anchor(ANCHOR_PATH))
            print("Anchor check: OK" if not problems else "Anchor check FAILED:\n  " + "\n  ".join(problems))
            return 0 if not problems else 1
        return 0

    t0 = time.perf_counter()
    table = compute_baseline(CORPORA_DIR, workers=args.workers)
    total = sum(table.column("size").to_pylist())
    print(f"Computed baseline: {table.num_rows:,} files ({total / 2**20:,.1f} MiB) "
          f"in {time.perf_counter() - t0:,.0f}s")

    if ANCHOR_PATH.exists():
        problems = anchor_mismatches(table, read_anchor(ANCHOR_PATH))
        if problems:
            print("REFUSING to write: recomputed baseline does not match the git-tracked anchor "
                  f"{ANCHOR_PATH}. Either corpora/ changed or the wrong folder is in place:\n  "
                  + "\n  ".join(problems))
            return 1
        write_baseline(table, BASELINE_PATH, force=True)
        print(f"Matches anchor -> wrote {BASELINE_PATH}")
    else:
        write_baseline(table, BASELINE_PATH, force=args.force)
        write_anchor(make_anchor(table), ANCHOR_PATH)
        print(f"Wrote {BASELINE_PATH} and new anchor {ANCHOR_PATH} (commit the anchor to git).")
    return 0


def _cmd_anchor(args: argparse.Namespace) -> int:
    """Pin the existing baseline by writing the git-tracked anchor (first time only)."""
    from hebloc.baseline import make_anchor, read_baseline, write_anchor
    from hebloc.paths import ANCHOR_PATH, BASELINE_PATH

    if ANCHOR_PATH.exists() and not args.force:
        print(f"Anchor already exists: {ANCHOR_PATH}. Re-anchoring changes the source of truth; "
              "use --force only after a deliberate, documented corpus change.")
        return 1
    anchor = make_anchor(read_baseline(BASELINE_PATH))
    write_anchor(anchor, ANCHOR_PATH, force=args.force)
    print(f"Wrote {ANCHOR_PATH}: {anchor['file_count']:,} files, {anchor['total_bytes']:,} bytes, "
          f"manifest_sha256={anchor['manifest_sha256']}")
    return 0


def _cmd_inventory(args: argparse.Namespace) -> int:
    from hebloc.catalog import DOCUMENTS_PATH
    from hebloc.inventory import run_inventory
    from hebloc.inventory_report import write_reports

    table, manifest = run_inventory(workers=args.workers)
    print(f"Catalog: {table.num_rows:,} documents -> {DOCUMENTS_PATH} "
          f"({manifest['runtime_seconds']}s). Verification: "
          + ", ".join(f"{k}={v}" for k, v in manifest["verification"].items() if isinstance(v, bool)))
    for p in write_reports(table):
        print(f"  wrote {p}")
    return 0


SAMPLE_EXTRA = [  # difficult documents always included in --sample runs
    "Tanakh - Prophets - Ezekiel", "Tanakh - Writings - Daniel", "Tanakh - Writings - Ruth",
    "Mishnah Beitzah", "Midrash - Halakhah - Sifra", "Pesikta Rabbati",
    "Rambam/NASHIM/aishowt", "Rambam/AHAVA/brkowt/000001", "Musar - Rishonim - Shaarei Teshuvah",
    "Ytext1044001", "Ytext1003001",
    "news/haaretz/0/14178.txt", "news/haaretz/0/15413.txt", "news/a7/news/104500-104599/104506.txt",
    "blogs/4906.txt", "kneset/16/00133504.txt",
]


def _cmd_prepare(args: argparse.Namespace) -> int:
    from hebloc.catalog import DOCUMENTS_PATH
    from hebloc.paths import CORPORA, UNITS_DIR
    from hebloc.units import SAMPLE_DIR, prepare_corpus
    from hebloc.units_review import write_review

    corpora = list(CORPORA) if args.corpus == "all" else [args.corpus]
    out_root = SAMPLE_DIR if args.sample else UNITS_DIR
    ok = True
    for c in corpora:
        m = prepare_corpus(c, out_root=out_root, sample=args.sample, seed=args.seed,
                           extra=SAMPLE_EXTRA if args.sample else None, workers=args.workers)
        ok &= m["ok"]
        print(f"{c:9} docs={m['documents']:,} units={m['units']:,} types={m['unit_types']} "
              f"coverage_failures={m['coverage_failures']} line_mismatch={m['catalog_line_mismatches']} "
              f"ok={m['ok']} ({m['runtime_seconds']}s)")
    if args.sample:
        from hebloc.paths import DOCS_DIR
        print("review:", write_review(out_root, DOCUMENTS_PATH, DOCS_DIR / "m2_sample_review.md"))
    return 0 if ok else 1


def _cmd_verify_units_v2(args: argparse.Namespace) -> int:
    """M2.1: exhaustive v1 → v2 comparison (needs the preserved v1 copy in data/units_v1)."""
    from hebloc.units_migrate import OUT_DIR, run

    r = run()
    for c, x in r["corpora"].items():
        print(f"{c:9} units {x['units_old']:,} -> {x['units_new']:,} (chunks {x['chunks_old']:,} -> "
              f"{x['chunked_sentences']:,} sentences) unaffected rows differing={x['unaffected_rows_differing']} "
              f"reconciles={x['count_reconciles']}")
    print("difference counts:", r["difference_counts"] or "none")
    print(f"structural_ok={r['structural_ok']} -> {OUT_DIR}")
    return 0 if r["structural_ok"] else 1


def _cmd_pilot(args: argparse.Namespace) -> int:
    """M3 pilot steps (see hebloc.pilot.steps)."""
    from hebloc.pilot.steps import step

    return step(args.step, threads=args.threads)


def _cmd_versification(args: argparse.Namespace) -> int:
    """(Network, one-off) fetch Tanakh chapter lengths and verify them against the Mikra files."""
    from hebloc import versification as V
    from hebloc.catalog import documents

    mikra = documents("mikra", columns=["work", "n_nonempty_lines"])
    body = V.fetch(sorted(mikra.work))
    bad = [(w, sum(body["books"][w]), n) for w, n in zip(mikra.work, mikra.n_nonempty_lines)
           if sum(body["books"][w]) != n]
    print(f"Wrote {V.VERSIFICATION_PATH}: {len(body['books'])} books; per-book verse-count mismatches: {bad or 'none'}")
    return 1 if bad else 0


def _cmd_runs(args: argparse.Namespace) -> int:
    """M4: list parse runs with completeness, tokens status and canonical role."""
    from hebloc.store.catalog import runs_table

    t = runs_table().to_pylist()
    if not t:
        print("No parse runs under data/annotations/.")
    for r in t:
        print(f"{r['run']:42} model={r['model'] or '?':5} variant={r['variant'] or '?':26} units={r['units'] or 0:>9,} "
              f"shards={r['shards']:>5} complete={r['complete']!s:5} tokens_up_to_date={r['tokens_shards_up_to_date']}"
              f"/{r['shards']} canonical_for={r['canonical_for'] or '-'}")
    return 0


def _cmd_tokens(args: argparse.Namespace) -> int:
    """M4: (re)derive the tokens of runs from their raw output, incrementally per shard."""
    from hebloc.parse.tokens import derive, migrate_legacy
    from hebloc.store.runs import list_runs, resolve

    runs = list_runs() if args.run == "all" else [resolve(args.run)]
    for r in runs:
        mig = migrate_legacy(r.path)
        s = derive(r.path, force=args.force, progress=True)
        print(f"{r.ref}: shards={s['shards']} derived={s['derived']} up_to_date={s['skipped_up_to_date']} "
              f"rows={s['rows']:,}" + (f" (legacy tokens.parquet migrated, identical: {mig['rows']:,} rows)"
                                       if mig.get("legacy") else "")
              + (f" INCOMPLETE shards: {s['incomplete_shards']}" if s["incomplete_shards"] else ""))
    return 0


def _cmd_catalog(args: argparse.Namespace) -> int:
    """M4: write the persistent DuckDB catalog (views only) to data/hebloc.duckdb."""
    from hebloc.store import catalog

    path = catalog.build()
    con = catalog.duckdb.connect(str(path), read_only=True)
    views = [r[0] for r in con.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal ORDER BY 1").fetchall()]
    n_runs = con.execute("SELECT count(*) FROM runs").fetchone()[0]
    canon = con.execute("SELECT count(*) FROM runs WHERE canonical_for IS NOT NULL").fetchone()[0]
    con.close()
    print(f"Wrote {path}\n  views: {', '.join(views)}\n  runs: {n_runs} ({canon} canonical)")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    """M4: integrity of the whole data layer (read-only)."""
    from hebloc.store.integrity import REPORT_PATH, check_all

    t0 = time.perf_counter()
    r = check_all(deep=args.deep, runs=args.run or None, skip_units=args.skip_units)
    d = r["documents"]
    print(f"documents: ok={d['ok']} rows={d.get('rows', 0):,} {d['problems'] or ''}")
    for c, u in r["units"].items():
        print(f"units/{c:9} ok={u['ok']} rows={u.get('rows', 0):,} {u['problems'] or ''}")
    for ref, x in r["runs"].items():
        mo = x["model_output"]
        print(f"run {ref:42} ok={x['ok']!s:5} validation={x['validation']['source']} "
              f"invalid_tree_share={mo['model_invalid_tree_share']} errors={mo['errors_logged']} "
              f"{x['problems'] or ''}")
    print(f"canonical: ok={r['canonical']['ok']} registered={r['canonical']['registered'] or 'none'} "
          f"{r['canonical']['problems'] or ''}")
    print(f"OK={r['ok']} failed={r['failed'] or 'none'} ({time.perf_counter() - t0:.0f}s) -> {REPORT_PATH}")
    return 0 if r["ok"] else 1


def _cmd_export_conllu(args: argparse.Namespace) -> int:
    from hebloc.store.conllu import export_run

    r = export_run(args.run, args.out, corpus=args.corpus, style=args.style, valid_only=args.valid_only)
    print(r)
    return 0


def _cmd_bundle(args: argparse.Namespace) -> int:
    """M4 (D-012): create / verify / restore verified backup bundles of parse runs."""
    from pathlib import Path

    from hebloc.store import bundle as B
    from hebloc.store.runs import list_runs

    if args.action == "create":
        refs = [r.ref for r in list_runs() if args.target == "all" or r.collection == args.target] \
            if args.target in ("all", "pilot") or "/" not in args.target else [args.target]
        for ref in refs:
            r = B.create(ref)
            print(f"{ref}: {r['path']} ({r['bytes'] / 2**20:,.1f} MiB, {r['files']} files) sha256={r['sha256']}")
        return 0
    if args.action == "verify":
        r = B.verify(Path(args.target))
        print(r)
        return 0 if r["ok"] else 1
    if args.action == "restore":
        r = B.restore(Path(args.target), overwrite=args.overwrite)
        print(r)
        return 0 if r["validation_ok"] and r["fingerprint_matches"] else 1
    raise SystemExit(f"unknown bundle action {args.action!r}")


def _json(obj) -> None:
    import json

    print(json.dumps(obj, indent=1, ensure_ascii=False, default=str))


def _cmd_corpora(args: argparse.Namespace) -> int:
    """Team: install the corpora from a download and verify them against the anchor."""
    from pathlib import Path

    from hebloc.team import corpora as C

    if args.action == "write-names-reference":
        r = C.write_names_reference()
        print(f"wrote {C.NAMES_PATH} ({r['files']:,} files)")
        return 0
    if args.action == "install":
        if not args.source:
            raise SystemExit("usage: hebloc corpora install --from <archive, folder of parts, or extracted folder>")
        try:
            r = C.install([Path(s) for s in args.source], workers=args.workers)
        except (C.InstallError, FileExistsError, FileNotFoundError) as e:
            print(f"INSTALL FAILED (nothing was installed): {e}")
            return 1
        print(f"found the corpora at '{r['root_in_download']}' in the download; file-name decoding: "
              f"{r['names']['decoding']}; OS junk files ignored: {r['ignored_os_files']}; "
              f"duplicate entries across parts: {r['duplicate_entries']}")
        v = r["verify"]
        if not v["ok"]:
            print("nothing was installed (the download is not byte-identical to the project's corpora)")
    else:
        v = C.verify(workers=args.workers)
    print(f"{v['files']:,} files, {v['bytes']:,} bytes: " + ("IDENTICAL to the project's corpora (anchor OK)" if v["ok"]
          else "DIFFERENT from the project's corpora:\n  " + "\n  ".join(v["problems"])))
    return 0 if v["ok"] else 1


def _cmd_whoami(args: argparse.Namespace) -> int:
    from hebloc.team import identity as I

    try:
        if args.name:
            r = I.set_identity(args.name, change=args.change)
            print(f"This computer is set up for: {r['person'].capitalize()}  (data/team/identity.json)")
            return 0
        who = I.get()
    except I.IdentityError as e:
        print(f"REFUSED: {e}")
        return 2
    print(f"This computer is set up for: {who.capitalize()}" if who else
          "Not set. Run: uv run hebloc whoami --set <ori|efrat|adi>")
    return 0 if who else 1


def _cmd_work(args: argparse.Namespace) -> int:
    from hebloc.team.work import PlanRefusal, WorkFailed, detach, read_lock, status, work

    if args.status:
        st = status(args.person, rehearsal=args.rehearsal, coverage=args.coverage)
        print(f"{st['person'].capitalize()}: {st['state']}")
        if "slices" in st:
            eta = st["hours_left_estimate"]
            print(f"  slices packaged {st['slices_packaged']}/{st['slices']}; sentences {st['units_done']:,}/"
                  f"{st['units']:,} ({st['percent']}% of the work)"
                  + (f"; speed {st['subwords_per_second']} sub-words/s; about {eta} h left" if eta else ""))
            for r in st["per_slice"]:
                print(f"    {r['slice']:22} {r['state']:12} {r['units_done']:>10,}/{r['units']:,}")
            print(f"  results folder: {st['outbox']}")
            print(f"  log: {st['log']}")
        return 0
    if args.detach:
        import time

        try:
            d = detach(args.person, rehearsal=args.rehearsal, coverage=args.coverage)
        except PlanRefusal as e:
            print(f"REFUSED: {e}")
            return 2
        for _ in range(120):                       # wait until the new window has taken the lock
            lk = read_lock()
            if lk and lk.get("person") == args.person:
                print(f"STARTED in its own window (pid {lk['pid']}). It keeps running if Claude Code or VS Code is "
                      f"closed. Progress: uv run python -m hebloc work --status   log: {d['log']}")
                return 0
            time.sleep(1)
        print(f"NOT STARTED within 2 minutes: read the new window and {d['log']}")
        return 1
    try:
        r = work(args.person, rehearsal=args.rehearsal, coverage=args.coverage, threads=args.threads)
    except PlanRefusal as e:
        print(f"REFUSED: {e}")
        return 2
    except WorkFailed as e:
        print(f"FAILED: {e}\nSend Ori this output, data/team/doctor.json and data/outbox/*/DELIVERY.json")
        return 1
    _json(r)
    print("\n".join([
        f"WORK COMPLETE ({r['mode']}, coverage {r['coverage']}).",
        f"Produced: {r['slices']} slice(s), {r['units']:,} sentences parsed, validated against this computer's data,",
        f"          and packaged as {r['slices']} checksum-verified bundles ({r['bytes'] / 2**20:,.0f} MiB).",
        f"Send Ori: the WHOLE folder {r['outbox']}",
        f"          ({r['slices']} .zip + {r['slices']} .zip.sha256 + DELIVERY.json + HOW_TO_SEND.txt), unchanged,",
        "          by Google Drive, OneDrive or a USB drive (see HOW_TO_SEND.txt in that folder). Never GitHub.",
        "Keep everything on this computer until Ori confirms that `hebloc merge` reported MERGE OK."]))
    return 0


def _cmd_models(args: argparse.Namespace) -> int:
    """Team: download the pinned Dicta models (network) and/or verify their sha256."""
    from hebloc.parse import models as M

    names = ["base", "tiny"] if args.all else ["base"]
    ok = True
    for n in names:
        if args.action == "fetch":
            M.fetch(n)
        probs = M.verify(n)
        ok &= not probs
        m = M.registry()["models"][n]
        print(f"{n}: {m['repo']}@{m['revision'][:12]} " + ("OK (all files match the pinned sha256)" if not probs
                                                            else f"PROBLEMS: {probs}"))
    return 0 if ok else 1


def _cmd_fingerprint(args: argparse.Namespace) -> int:
    from hebloc.team import fingerprint as F

    fp = F.compute()
    if args.write_reference:
        print("wrote", F.write_reference(fp))
        return 0
    ref = F.read_reference()
    probs = F.compare(fp, ref) if ref else ["no reference"]
    for name, d in fp["tables"].items():
        print(f"{name:16} rows={d['rows']:>10,} digest={d['digest']}")
    hard = [p for p in probs if not p.startswith("note:")]
    print("IDENTICAL to the reference" if not hard else "DIFFERENT:\n  " + "\n  ".join(probs))
    return 0 if not hard else 1


def _cmd_doctor(args: argparse.Namespace) -> int:
    from hebloc.team import doctor as D

    r = D.run(args.person, quick=args.quick)
    for sec, rows in r["sections"].items():
        for x in rows:
            print(f"[{x['status']:4}] {sec:8} {x['check']:20} {x['detail']}")
            if x["status"] in ("FAIL", "TODO") and x["fix"]:
                print(f"{'':16}-> {x['fix']}")
    print(f"\nready_for_setup={r['ready_for_setup']}  ready_to_parse={r['ready_to_parse']}  {r['counts']}  "
          f"-> {D.REPORT_PATH}")
    return 0 if r["ready_for_setup"] else 1


def _cmd_agreement(args: argparse.Namespace) -> int:
    from pathlib import Path

    from hebloc.team import agreement as A

    if args.write_reference:
        from hebloc.parse import models as M
        from hebloc.store.runs import resolve
        from hebloc.team.plan import load

        st = load().settings
        r = A.write_reference(resolve(args.write_reference).path, st, M.registry()["models"][st["model"]]["revision"])
        print(r)
        return 0
    if args.compare:
        from pathlib import Path

        _json(A.compare_bundle(Path(args.compare)))
        return 0
    r = A.run(args.person, threads=args.threads, limit=args.limit)
    _json({k: v for k, v in r.items() if k != "different_examples"})
    print("AGREEMENT OK: this machine reproduces the reference output exactly" if r["ok"] else
          "AGREEMENT NOT OK: send Ori data/team/agreement.json"
          + (f" and the folder {Path(r['package']).parent}" if r.get("package") and Path(r["package"]).exists() else "")
          + " (Ori compares it token by token: hebloc agreement --compare <zip>)")
    return 0 if r["ok"] else 1


def _cmd_plan(args: argparse.Namespace) -> int:
    from hebloc.team import plan as P

    plan = P.load()
    if args.action == "check":
        r = P.check_partition(plan)
        _json(r)
        return 0 if r["ok"] else 1
    if args.action == "measure":
        wp = P.write_work_plan(plan, P.measure(plan))
        _json(wp["assignment"])
        print(f"wrote {P.WORK_PLAN_JSON} and {P.WORK_PLAN_MD}")
        return 0
    if args.action == "assign":
        wp = P.reassign(plan)
        _json({c: {p: d["slices"] for p, d in a["people"].items()} for c, a in wp["assignment"].items()})
        print(f"re-rendered {P.WORK_PLAN_JSON} and {P.WORK_PLAN_MD} from the stored sizes")
        return 0
    if args.action == "show":
        print(f"status={plan.status} coverage={plan.coverage} settings={plan.settings}")
        print(P.WORK_PLAN_MD.read_text(encoding="utf-8") if P.WORK_PLAN_MD.exists() else "(no work plan yet: hebloc plan measure)")
        return 0
    if args.action == "status":
        for r in P.status(plan, coverage=args.coverage):
            print(f"{r['slice']:22} owner={r['owner'] or '?':6} present={r['present']!s:5} complete={r['complete']!s:5} "
                  f"checks_ok={r['checks_ok']!s:5} {r['run']}")
        return 0
    if args.action == "register":
        from hebloc.team.work import register

        _json(register(write=args.write))
        return 0
    raise SystemExit(f"unknown plan action {args.action!r}")


def _cmd_parse(args: argparse.Namespace) -> int:
    from hebloc.team.work import PlanRefusal, run_slice

    try:
        r = run_slice(args.slice, args.person, threads=args.threads, limit=args.limit)
    except PlanRefusal as e:
        print(f"REFUSED: {e}")
        return 2
    _json(r)
    return 0 if r["validation_ok"] and r["integrity_ok"] else 1


def _cmd_stats(args: argparse.Namespace) -> int:
    """M6 (docs/m6_design.md): run | accuracy | report | verify."""
    from pathlib import Path

    from hebloc.stats import compute as C
    from hebloc.stats import report as REP
    from hebloc.stats import runset as R

    if args.action == "run":
        if bool(args.runs) == args.registered:
            print("REFUSED: give either --runs <run,...> or --registered")
            return 2
        try:
            rs = R.from_registry() if args.registered else R.from_refs([r for x in args.runs for r in x.split(",") if r])
            R.check(rs, scale_test=args.scale_test)
        except R.RunSetRefusal as e:
            print(f"REFUSED: {e}")
            return 2
        for c, rep in rs.checks.items():
            print(f"{c}: {rep['units_in_runs']:,}/{rep['units_expected']:,} units, complete={rep['complete']} "
                  f"({', '.join(rep['runs'])})")
        try:
            m = C.compute(rs, Path(args.out) if args.out else None, scale_test=args.scale_test)
        except (C.StatsProblem, FileExistsError, ValueError) as e:
            print(f"STOPPED: {e}")
            return 1
        print(f"status={m['status']} -> {m['path']}  ({m['timings_s']['total']} s)")
        if m["reconciliation_problems"]:
            print("reconciliation problems (scale test only):", *m["reconciliation_problems"], sep="\n  ")
        if not args.scale_test and not args.no_report:
            _json(REP.render(Path(m["path"])))
        return 0
    if args.action == "accuracy":
        from hebloc.stats.accuracy import mikra_vs_bhsa

        r = mikra_vs_bhsa(args.run)
        for layer in r["layers"]:
            print(f"{layer['layer']:32} n={layer['n']:>8,}  {100 * layer['agreement']:.1f}%  "
                  f"[{100 * layer['ci95_low']:.1f}-{100 * layer['ci95_high']:.1f}]")
        print("pilot reproduction:", r["pilot_reproduction"])
        return 0 if r["pilot_reproduction"].get("identical", True) else 1
    if args.action == "report":
        _json(REP.render(Path(args.stats_dir)))
        return 0
    if args.action == "verify":
        probs = C.verify(Path(args.stats_dir))
        print("OK" if not probs else "\n".join(probs))
        return 0 if not probs else 1
    raise SystemExit(f"unknown stats action {args.action!r}")


def _cmd_merge(args: argparse.Namespace) -> int:
    from pathlib import Path

    from hebloc.team.work import merge

    r = merge([Path(z) for z in args.paths], overwrite=args.overwrite)
    print(f"{r['bundles_found']} bundle file(s) found, {r['runs']} distinct run(s)")
    for b in r["bundles"]:
        dup = f" (+{len(b['duplicate_copies_ignored'])} identical copy ignored)" if b.get("duplicate_copies_ignored") else ""
        print(f"{'OK  ' if b['ok'] else 'FAIL'} {b.get('run')} slice={b.get('slice')} person={b.get('person')}{dup}"
              + ("" if b["ok"] else f"\n     {b['bundle']}\n     {b.get('problems') or ''}{b.get('integrity_problems') or ''}"))
    for p in r["problems"]:
        print(("     " if p.startswith("note:") else "FAIL ") + p)
    for c in r["completeness"]:
        print(f"\n{c['mode']} coverage {c['coverage']}: {c['slices_ok']}/{c['slices_expected']} slices OK; "
              f"units {c['units_present']:,}/{c['units_expected']:,}; units in more than one run: "
              f"{c['units_in_more_than_one_run']}; " + ("COMPLETE" if c["complete"] else "NOT complete"))
        for p, sl in c["missing_by_owner"].items():
            if sl:
                print(f"   missing from {p}: {', '.join(sl)}")
        if c["invalid_or_duplicate"]:
            print(f"   INVALID or DUPLICATE: {', '.join(c['invalid_or_duplicate'])}")
    print(f"\nMERGE {'OK' if r['ok'] else 'HAS PROBLEMS'} -> data/team/merge_report.json")
    return 0 if r["ok"] else 1


def _utf8_console() -> None:
    """Windows consoles default to a legacy code page; paths/text here are Hebrew."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _utf8_console()
    parser = argparse.ArgumentParser(prog="hebloc", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("baseline", help="Record sha256 baseline of corpora/ (immutability reference).")
    p.add_argument("--force", action="store_true", help="Recompute and overwrite an existing baseline.")
    p.add_argument("--workers", type=int, default=8, help="Hashing threads (default 8).")
    p.set_defaults(func=_cmd_baseline)

    p = sub.add_parser("anchor", help="Pin the existing baseline in git-tracked config/corpora_anchor.json.")
    p.add_argument("--force", action="store_true", help="Overwrite an existing anchor (deliberate re-anchoring).")
    p.set_defaults(func=_cmd_anchor)

    p = sub.add_parser("inventory", help="M1: build data/catalog/documents.parquet (+ verification, summary tables).")
    p.add_argument("--workers", type=int, default=None, help="Worker processes (default: cores-2, max 12).")
    p.set_defaults(func=_cmd_inventory)

    p = sub.add_parser("versification", help="(network) fetch Tanakh chapter lengths into config/reference/.")
    p.set_defaults(func=_cmd_versification)

    p = sub.add_parser("prepare", help="M2: extract sentence/verse units into data/units/<corpus>/.")
    p.add_argument("--corpus", default="all", help="Corpus id or 'all' (default).")
    p.add_argument("--sample", type=int, default=None,
                   help="Validation run: N random docs per corpus + known difficult docs → data/units_sample/.")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--workers", type=int, default=None)
    p.set_defaults(func=_cmd_prepare)

    p = sub.add_parser("pilot", help="M3 Dicta pilot steps: fetch-models, fetch-bhsa, sample, smoke, parse, "
                       "variants, diacritics, census, analyze, audit, audit-score, bench.")
    p.add_argument("step")
    p.add_argument("--threads", type=int, default=8)
    p.set_defaults(func=_cmd_pilot)

    p = sub.add_parser("verify-units-v2", help="M2.1: verify regenerated units against data/units_v1 (segment v1 → v2).")
    p.set_defaults(func=_cmd_verify_units_v2)

    p = sub.add_parser("runs", help="M4: list parse runs (completeness, tokens status, canonical role).")
    p.set_defaults(func=_cmd_runs)

    p = sub.add_parser("tokens", help="M4: (re)derive tokens from dicta_raw, incrementally per shard.")
    p.add_argument("run", help="'<collection>/<run_id>' (e.g. pilot/base__default) or 'all'.")
    p.add_argument("--force", action="store_true", help="Re-derive every shard even if up to date.")
    p.set_defaults(func=_cmd_tokens)

    p = sub.add_parser("catalog", help="M4: write the DuckDB catalog (views over all Parquet) to data/hebloc.duckdb.")
    p.set_defaults(func=_cmd_catalog)

    p = sub.add_parser("check", help="M4: integrity checks of documents, units, runs and the canonical registry.")
    p.add_argument("--deep", action="store_true", help="Re-validate every run (else trust checks.json if its fingerprint is current).")
    p.add_argument("--run", action="append", help="Only this run (repeatable).")
    p.add_argument("--skip-units", action="store_true", help="Skip the units checks (~20 s).")
    p.set_defaults(func=_cmd_check)

    p = sub.add_parser("export-conllu", help="M4: export a run as CoNLL-U (Dicta's UD conversion + provenance comments).")
    p.add_argument("run", help="'<collection>/<run_id>'.")
    p.add_argument("--corpus", default=None)
    p.add_argument("--style", default="ud", choices=["ud", "iahlt_ud"])
    p.add_argument("--valid-only", action="store_true", help="Skip pieces whose word-level tree is invalid (D-025).")
    p.add_argument("--out", default=None, help="Output file (default data/exports/conllu/…).")
    p.set_defaults(func=_cmd_export_conllu)

    p = sub.add_parser("bundle", help="M4 (D-012): create|verify|restore verified backup bundles of runs.")
    p.add_argument("action", choices=["create", "verify", "restore"])
    p.add_argument("target", help="create: '<collection>/<run_id>', a collection (e.g. 'pilot') or 'all'; "
                                  "verify/restore: path to the .zip.")
    p.add_argument("--overwrite", action="store_true", help="restore: replace different existing files (deliberate).")
    p.set_defaults(func=_cmd_bundle)

    # ---- team collaboration (docs/PARTNERS.md)
    p = sub.add_parser("corpora", help="Team: install the corpora from the course download and verify them.")
    p.add_argument("action", choices=["install", "verify", "write-names-reference"])
    p.add_argument("--from", dest="source", action="append", default=None,
                   help="install: the downloaded archive (.zip/.7z/.rar/.tar.*), a folder of archive parts, or an "
                        "extracted folder; repeat --from for each part of a multi-part download")
    p.add_argument("--workers", type=int, default=8)
    p.set_defaults(func=_cmd_corpora)

    p = sub.add_parser("whoami", help="Team: show or set who this computer belongs to (ori | efrat | adi).")
    p.add_argument("--set", dest="name", default=None)
    p.add_argument("--change", action="store_true", help="deliberately replace a different stored name")
    p.set_defaults(func=_cmd_whoami)

    p = sub.add_parser("work", help="Team: parse ALL your assigned slices and package them for Ori (resumable).")
    p.add_argument("--as", dest="person", default=None)
    p.add_argument("--rehearsal", type=int, default=None, metavar="N",
                   help="dress rehearsal on the first N units of each of your slices (allowed before approval)")
    p.add_argument("--coverage", default=None, choices=["A", "B"], help="rehearsal only (default: the plan's, else A)")
    p.add_argument("--threads", type=int, default=None, help="rehearsal only; full runs use the plan's threads")
    p.add_argument("--detach", action="store_true", help="start in its own window (survives closing Claude Code)")
    p.add_argument("--status", action="store_true", help="show progress on this computer and exit")
    p.set_defaults(func=_cmd_work)

    p = sub.add_parser("models", help="Team: download (fetch) or verify the pinned Dicta models.")
    p.add_argument("action", choices=["fetch", "verify"])
    p.add_argument("--all", action="store_true", help="also the tiny model (base only by default)")
    p.set_defaults(func=_cmd_models)

    p = sub.add_parser("fingerprint", help="Team: content digests of catalog + units vs the reference.")
    p.add_argument("--write-reference", action="store_true", help="(Ori) pin this machine's digests")
    p.set_defaults(func=_cmd_fingerprint)

    p = sub.add_parser("doctor", help="Team: check this machine end to end (setup, data, models, readiness).")
    p.add_argument("--as", dest="person", default=None)
    p.add_argument("--quick", action="store_true", help="skip the corpora file-list scan")
    p.set_defaults(func=_cmd_doctor)

    p = sub.add_parser("agreement", help="Team: parse the pilot sample and compare with the reference output.")
    p.add_argument("--as", dest="person", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--threads", type=int, default=None, help="diagnostics only (default: the plan's threads)")
    p.add_argument("--write-reference", default=None, metavar="RUN", help="(Ori) pin RUN as the reference")
    p.add_argument("--compare", default=None, metavar="ZIP", help="(Ori) token-level comparison of a partner's agreement bundle")
    p.set_defaults(func=_cmd_agreement)

    p = sub.add_parser("plan", help="Team: work plan: show | check | measure | assign | status | register.")
    p.add_argument("action", choices=["show", "check", "measure", "assign", "status", "register"])
    p.add_argument("--coverage", default=None, choices=["A", "B"])
    p.add_argument("--write", action="store_true", help="register: write config/annotations.yaml")
    p.set_defaults(func=_cmd_plan)

    p = sub.add_parser("parse", help="Team: parse ONE assigned slice (`hebloc work` does all of them).")
    p.add_argument("--slice", required=True)
    p.add_argument("--as", dest="person", default=None)
    p.add_argument("--limit", type=int, default=None, help="SMOKE run of the first N units (allowed in draft)")
    p.add_argument("--threads", type=int, default=None)
    p.set_defaults(func=_cmd_parse)

    p = sub.add_parser("stats", help="M6: descriptive statistics (project.pdf §4) and parser accuracy (docs/m6_design.md).")
    p.add_argument("action", choices=["run", "accuracy", "report", "verify"])
    p.add_argument("stats_dir", nargs="?", help="report/verify: a data/stats/<id> folder")
    p.add_argument("--runs", action="append", help="run: explicit runs, comma-separated (now, before the merge)")
    p.add_argument("--registered", action="store_true", help="run: the canonical runs of config/annotations.yaml (after the merge)")
    p.add_argument("--scale-test", action="store_true", help="run: allow partial corpora; timing only, written to --out, never published")
    p.add_argument("--out", help="run: output folder (required with --scale-test)")
    p.add_argument("--no-report", action="store_true", help="run: skip CSV/PNG/Markdown")
    p.add_argument("--run", default="mikra/base-topk-v1__mikra", help="accuracy: the full Mikra run")
    p.set_defaults(func=_cmd_stats)

    p = sub.add_parser("merge", help="Team (Ori): verify, restore and check partners' result folders/bundles.")
    p.add_argument("paths", nargs="*", help="folders (e.g. a partner's outbox folder) and/or bundle .zip files; "
                                            "none = only report completeness")
    p.add_argument("--overwrite", action="store_true")
    p.set_defaults(func=_cmd_merge)

    args = parser.parse_args(argv)
    if getattr(args, "person", None) is not None or getattr(args, "func", None) in (_cmd_agreement, _cmd_parse, _cmd_work):
        if not (getattr(args, "func", None) is _cmd_agreement and (args.write_reference or args.compare)):
            from hebloc.team.identity import IdentityError, resolve

            try:
                args.person = resolve(args.person)
            except IdentityError as e:
                print(f"REFUSED: {e}")
                return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
