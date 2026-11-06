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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
