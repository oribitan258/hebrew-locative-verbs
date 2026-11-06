"""Immutability guard for corpora/ (decisions D-002, D-010).

* Fast (default): the set of files, their sizes and mtimes must equal the recorded baseline.
* Slow (``uv run pytest -m slow``): additionally, every file's SHA-256 must equal the baseline.
* Self-test: the guard logic is proven to detect tampering, using a temporary copy (never corpora/).
"""

from __future__ import annotations

import os

import pytest

from hebloc.baseline import compare_to_baseline, compute_baseline, read_baseline
from hebloc.paths import BASELINE_PATH, CORPORA_DIR

needs_baseline = pytest.mark.skipif(
    not BASELINE_PATH.exists(), reason="No baseline yet — run `uv run hebloc baseline` first."
)


def _report(drift) -> str:
    return (
        f"missing={len(drift.missing)} {drift.missing[:5]} | added={len(drift.added)} {drift.added[:5]} "
        f"| changed={len(drift.changed)} {drift.changed[:5]}"
    )


@needs_baseline
def test_corpora_unchanged_fast():
    drift = compare_to_baseline(read_baseline(), CORPORA_DIR, deep=False)
    assert drift.clean, _report(drift)


@needs_baseline
@pytest.mark.slow
def test_corpora_unchanged_deep():
    drift = compare_to_baseline(read_baseline(), CORPORA_DIR, deep=True)
    assert drift.clean, _report(drift)


def test_guard_detects_tampering(tmp_path):
    root = tmp_path / "fake_corpora"
    (root / "A").mkdir(parents=True)
    (root / "A" / "keep.txt").write_bytes("שלום".encode("utf-8"))
    (root / "A" / "edit.txt").write_bytes(b"abc")
    (root / "A" / "gone.txt").write_bytes(b"x")
    base = compute_baseline(root, workers=2, progress=False)
    assert compare_to_baseline(base, root, deep=True).clean

    # Same-size content change with mtime restored: only the deep check can see it.
    st = os.stat(root / "A" / "edit.txt")
    (root / "A" / "edit.txt").write_bytes(b"abd")
    os.utime(root / "A" / "edit.txt", ns=(st.st_atime_ns, st.st_mtime_ns))
    (root / "A" / "gone.txt").unlink()
    (root / "A" / "new.txt").write_bytes(b"y")

    fast = compare_to_baseline(base, root, deep=False)
    assert fast.missing == ["A/gone.txt"] and fast.added == ["A/new.txt"] and fast.changed == []
    deep = compare_to_baseline(base, root, deep=True)
    assert deep.changed == ["A/edit.txt"]
