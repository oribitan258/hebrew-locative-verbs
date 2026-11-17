"""Check that every file of the package arrived intact (size + sha256 against MANIFEST.json).

    python -m hebpack.verify            # full check (reads every file, a few minutes)
    python -m hebpack.verify --sizes    # sizes only (seconds)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys

from hebpack import ROOT


def sha256(path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def check(sizes_only: bool = False) -> list[str]:
    man = json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
    probs = []
    for rel, meta in man["files"].items():
        f = ROOT / rel
        if not f.exists():
            probs.append(f"MISSING  {rel}")
        elif f.stat().st_size != meta["bytes"]:
            probs.append(f"SIZE     {rel}")
        elif not sizes_only and sha256(f) != meta["sha256"]:
            probs.append(f"CHANGED  {rel}")
    return probs


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sizes", action="store_true")
    a = p.parse_args(argv)
    man = json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
    probs = check(a.sizes)
    n = len(man["files"])
    if not a.sizes:
        from hebpack import state

        state.record("verify_full", not probs, f"{len(probs)} problems")
    if probs:
        print("\n".join(probs[:50]))
        print(f"VERIFY FAIL: {len(probs)} of {n} files missing or different. Download again or tell Ori.")
        return 1
    print(f"VERIFY OK: {n} files, {man['total_bytes'] / 2**30:.2f} GiB, "
          f"{'sizes' if a.sizes else 'sizes and sha256'} match MANIFEST.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
