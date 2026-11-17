"""Package the work in analyses/ for Ori: one zip in to-ori/ (no data, no self-test scratch files).

    uv run python -m hebpack.deliver
"""

from __future__ import annotations

import sys
import zipfile
from datetime import datetime

from hebpack import ANALYSES, ROOT


def main() -> int:
    files = [f for f in ANALYSES.rglob("*") if f.is_file() and "_selftest" not in f.parts
             and "__pycache__" not in f.parts]
    if not files:
        print("Nothing to send yet: analyses/ is empty.")
        return 1
    if not (ANALYSES / "REPORT.md").exists():
        print("Note: analyses/REPORT.md is missing (Ori needs a short summary of the findings).")
    out = ROOT / "to-ori" / f"analyses-efrat-{datetime.now():%Y%m%d-%H%M}.zip"
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f.relative_to(ROOT).as_posix())
    size = out.stat().st_size / 2**20
    print(f"Ready to send: {out}  ({len(files)} files, {size:.1f} MB)")
    print("Upload this one file to Google Drive (or OneDrive) and share it with Ori.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
