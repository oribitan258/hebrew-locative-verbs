"""Immutability guard for corpora/ (decisions D-002, D-010).

* Fast (default): the set of files, their sizes and mtimes must equal the recorded baseline.
* Slow (``uv run pytest -m slow``): additionally, every file's SHA-256 must equal the baseline.
* Self-test: the guard logic is proven to detect tampering, using a temporary copy (never corpora/).
"""

from __future__ import annotations

import os

import pyarrow as pa
import pytest

from hebloc import cli
from hebloc import paths as hpaths
from hebloc.baseline import (
    anchor_mismatches,
    canonical_digest,
    compare_to_baseline,
    compute_baseline,
    read_anchor,
    read_baseline,
)
from hebloc.paths import ANCHOR_PATH, BASELINE_PATH, CORPORA_DIR

# Independent reference: file counts measured during project discovery (2026-11-06), before any
# baseline code existed. If the anchor ever disagrees with these, something is badly wrong.
DISCOVERY_FILE_COUNTS = {"Haskala": 320, "Hazal": 204, "Medieval": 1128, "Mikra": 39, "Modern": 402603}

needs_baseline = pytest.mark.skipif(
    not BASELINE_PATH.exists(), reason="No baseline yet — run `uv run hebloc baseline` first."
)


def _report(drift) -> str:
    return (
        f"missing={len(drift.missing)} {drift.missing[:5]} | added={len(drift.added)} {drift.added[:5]} "
        f"| changed={len(drift.changed)} {drift.changed[:5]}"
    )


def test_anchor_is_tracked_and_matches_discovery():
    assert ANCHOR_PATH.exists(), "config/corpora_anchor.json (git-tracked) is missing"
    anchor = read_anchor(ANCHOR_PATH)
    assert {k: v["files"] for k, v in anchor["per_corpus"].items()} == DISCOVERY_FILE_COUNTS
    assert anchor["file_count"] == sum(DISCOVERY_FILE_COUNTS.values()) == 404_294
    assert anchor["total_bytes"] == sum(v["bytes"] for v in anchor["per_corpus"].values())


@needs_baseline
def test_baseline_matches_git_anchor():
    """A regenerated/replaced baseline must not silently become the source of truth."""
    problems = anchor_mismatches(read_baseline(BASELINE_PATH), read_anchor(ANCHOR_PATH))
    assert not problems, "baseline disagrees with git-tracked anchor:\n" + "\n".join(problems)


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


def test_canonical_digest_ignores_row_order_and_mtime(tmp_path):
    root = tmp_path / "c"
    (root / "X").mkdir(parents=True)
    for name, data in [("a.txt", b"1"), ("b.txt", b"22"), ("c.txt", "ג".encode())]:
        (root / "X" / name).write_bytes(data)
    base = compute_baseline(root, workers=2, progress=False)
    shuffled = base.take([2, 0, 1])
    idx = base.schema.get_field_index("mtime_ns")
    touched = base.set_column(idx, "mtime_ns", pa.array([0, 0, 0], type=pa.int64()))
    assert canonical_digest(base) == canonical_digest(shuffled) == canonical_digest(touched)
    # ...but any content change (here: one sha256) must change the digest.
    sidx = base.schema.get_field_index("sha256")
    tampered = base.set_column(sidx, "sha256", pa.array(["0" * 64] + base.column("sha256").to_pylist()[1:]))
    assert canonical_digest(tampered) != canonical_digest(base)


def test_cli_refuses_regenerated_baseline_that_disagrees_with_anchor(tmp_path, monkeypatch):
    """End-to-end on a temp tree (never the real corpora/ or data/)."""
    corpora = tmp_path / "corpora"
    (corpora / "Mikra").mkdir(parents=True)
    (corpora / "Mikra" / "Genesis.txt").write_bytes("בראשית".encode())
    baseline_path = tmp_path / "data" / "catalog" / "corpora_baseline.parquet"
    anchor_path = tmp_path / "config" / "corpora_anchor.json"
    monkeypatch.setattr(hpaths, "CORPORA_DIR", corpora)
    monkeypatch.setattr(hpaths, "BASELINE_PATH", baseline_path)
    monkeypatch.setattr(hpaths, "ANCHOR_PATH", anchor_path)

    assert cli.main(["baseline", "--workers", "1"]) == 0             # first run: baseline + anchor
    assert baseline_path.exists() and anchor_path.exists()
    pinned_anchor = anchor_path.read_bytes()

    assert cli.main(["baseline", "--force", "--workers", "1"]) == 0  # unchanged tree: allowed
    (corpora / "Mikra" / "Genesis.txt").write_bytes("שמות".encode())  # simulate corpus drift
    assert cli.main(["baseline", "--force", "--workers", "1"]) == 1  # must refuse
    assert cli.main(["anchor"]) == 1                                 # no silent re-anchoring
    assert anchor_path.read_bytes() == pinned_anchor
    # The refused run must not have replaced the stored baseline with the drifted one.
    assert canonical_digest(read_baseline(baseline_path)) == read_anchor(anchor_path)["manifest_sha256"]
