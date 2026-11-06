"""Basic environment and write-guard tests."""

from __future__ import annotations

import sys

import pytest

from hebloc.paths import CORPORA, CORPORA_DIR, DATA_DIR, assert_not_in_corpora


def test_python_version_is_pinned():
    assert sys.version_info[:2] == (3, 12)


def test_all_five_corpora_present():
    for folder in CORPORA.values():
        assert (CORPORA_DIR / folder).is_dir(), f"missing corpus folder: {folder}"


def test_write_guard_blocks_corpora():
    with pytest.raises(PermissionError):
        assert_not_in_corpora(CORPORA_DIR / "Mikra" / "anything.txt")
    with pytest.raises(PermissionError):
        assert_not_in_corpora(CORPORA_DIR)


def test_write_guard_allows_data_dir():
    assert_not_in_corpora(DATA_DIR / "catalog" / "x.parquet")  # must not raise
