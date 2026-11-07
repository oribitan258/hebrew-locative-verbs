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

    p = sub.add_parser("verify-units-v2", help="M2.1: verify regenerated units against data/units_v1 (segment v1 → v2).")
    p.set_defaults(func=_cmd_verify_units_v2)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
