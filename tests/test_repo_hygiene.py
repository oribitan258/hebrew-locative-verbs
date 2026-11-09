"""What git tracks must stay safe to push to the PUBLIC GitHub repository (decisions D-034, D-042):
no corpora, no corpus-text sheets, no generated data, no large/binary data files, no secrets."""

from __future__ import annotations

import re
import subprocess

import pytest

from hebloc.paths import ROOT

MAX_BYTES = 2_000_000                       # largest tracked file today: ~0.3 MB
FORBIDDEN_DIRS = ("corpora/", "data/", ".venv/")
FORBIDDEN_EXT = (".parquet", ".zip", ".safetensors", ".bin", ".pt", ".duckdb", ".7z", ".env", ".pem", ".key")
SECRET = re.compile(r"(gh[pousr]_[A-Za-z0-9]{30,}|hf_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}"
                    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
# Course documents and the M2 sample review (quotes corpus text) stay out of the repository (D-034).
UNTRACKED_DOCS = ("project.pdf", "DoronDubnov_revised.pdf", "nlp-intro-short.pptx", "docs/m2_sample_review.md",
                  # manual-audit sheets quote full corpus sentences (D-042)
                  "annotation/pilot_audit.csv", "annotation/pilot_audit_words.csv")


def _tracked() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return [p for p in out.decode("utf-8").split("\0") if p]


def test_no_corpora_or_generated_data_tracked():
    bad = [p for p in _tracked() if p.startswith(FORBIDDEN_DIRS) or p.lower().endswith(FORBIDDEN_EXT)]
    assert not bad, f"must never be committed: {bad[:10]}"


def test_course_documents_not_tracked():
    assert not [p for p in _tracked() if p in UNTRACKED_DOCS]


def test_no_large_files_tracked():
    big = [(p, (ROOT / p).stat().st_size) for p in _tracked()
           if (ROOT / p).is_file() and (ROOT / p).stat().st_size > MAX_BYTES]
    assert not big, f"files over {MAX_BYTES:,} bytes: {big}"


def test_no_secrets_tracked():
    hits = []
    for p in _tracked():
        f = ROOT / p
        if f.is_file() and f.stat().st_size < MAX_BYTES:
            m = SECRET.search(f.read_bytes().decode("utf-8", errors="ignore"))
            if m:
                hits.append((p, m.group(0)[:12] + "…"))
    assert not hits, f"possible secrets: {hits}"


def test_gitignore_protects_data():
    lines = {ln.strip() for ln in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()}
    assert {"/corpora/", "/data/", "/annotation/pilot_audit.csv", "/annotation/pilot_audit_words.csv"} <= lines
