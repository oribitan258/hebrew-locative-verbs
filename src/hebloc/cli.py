"""Command-line entry point: ``uv run hebloc <command>``.

Commands are added milestone by milestone. Each one is a thin wrapper around library code.
"""

from __future__ import annotations

import argparse
import sys
import time


def _cmd_baseline(args: argparse.Namespace) -> int:
    from hebloc.baseline import compute_baseline, write_baseline
    from hebloc.paths import BASELINE_PATH, CORPORA_DIR

    if BASELINE_PATH.exists() and not args.force:
        print(f"Baseline already exists: {BASELINE_PATH} (use --force to recompute deliberately).")
        return 0
    t0 = time.perf_counter()
    table = compute_baseline(CORPORA_DIR, workers=args.workers)
    path = write_baseline(table, force=args.force)
    total = sum(table.column("size").to_pylist())
    print(
        f"Recorded baseline for {table.num_rows:,} files ({total / 2**20:,.1f} MiB) "
        f"in {time.perf_counter() - t0:,.0f}s -> {path}"
    )
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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
