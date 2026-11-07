"""Pinned Dicta parser models: verification, offline loading, and the sub-word cost function.

Every load (1) verifies the model files in ``data/models/<dir>`` against the sha256 checksums in
``config/models.yaml``, (2) verifies the vendored model code, (3) loads fully offline
(``HF_HUB_OFFLINE``) through the vendored class — never ``trust_remote_code`` — and (4) refuses to
continue if any weight is missing or unexpected.
"""

from __future__ import annotations

import functools
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml

from hebloc.paths import CONFIG_DIR, DATA_DIR

MODELS_CONFIG = CONFIG_DIR / "models.yaml"
MODELS_DIR = DATA_DIR / "models"
CODE_DIR = Path(__file__).parent / "dicta_code"
MAX_POSITIONS = 512
BUDGET = MAX_POSITIONS - 2  # sub-words per piece, excluding [CLS] and [SEP]


def registry() -> dict:
    return yaml.safe_load(MODELS_CONFIG.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 22):
            h.update(chunk)
    return h.hexdigest()


def verify(name: str) -> list[str]:
    """Problems with the local files of model ``name`` and with the vendored code (empty = OK)."""
    reg = registry()
    m = reg["models"][name]
    d = MODELS_DIR / m["dir"]
    problems = []
    for fname, (size, sha) in m["files"].items():
        p = d / fname
        if not p.is_file():
            problems.append(f"missing {p}")
        elif p.stat().st_size != size or _sha256(p) != sha:
            problems.append(f"checksum mismatch {p}")
    for fname, sha in reg["vendored_code"]["files"].items():
        if _sha256(CODE_DIR / fname) != sha:
            problems.append(f"vendored code changed: {fname}")
    return problems


@dataclass
class LoadedModel:
    name: str
    repo: str
    revision: str
    model: object
    tokenizer: object

    @property
    def model_id(self) -> str:
        return f"{self.repo}@{self.revision[:12]}"


def load(name: str, threads: int | None = None) -> LoadedModel:
    problems = verify(name)
    if problems:
        raise RuntimeError(f"model {name!r} failed verification: {problems}. Run: uv run hebloc pilot fetch-models")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import torch
    from transformers import AutoTokenizer

    from hebloc.parse.dicta_code.BertForJointParsing import BertForJointParsing

    if threads:
        torch.set_num_threads(threads)
    m = registry()["models"][name]
    d = MODELS_DIR / m["dir"]
    tokenizer = AutoTokenizer.from_pretrained(d)
    model, info = BertForJointParsing.from_pretrained(d, output_loading_info=True)
    bad = {k: v for k, v in info.items() if k in ("missing_keys", "unexpected_keys", "mismatched_keys") and v}
    if bad:
        raise RuntimeError(f"model {name!r} weights do not match the vendored code: {bad}")
    model.eval()
    return LoadedModel(name, m["repo"], m["revision"], model, tokenizer)


def fetch(name: str) -> Path:
    """(Network) download the pinned revision (safetensors only) and verify it."""
    from huggingface_hub import snapshot_download

    m = registry()["models"][name]
    p = Path(snapshot_download(m["repo"], revision=m["revision"], local_dir=MODELS_DIR / m["dir"],
                               ignore_patterns=["pytorch_model.bin"]))
    problems = verify(name)
    if problems:
        raise RuntimeError(f"downloaded files do not match the pinned checksums: {problems}")
    return p


def subword_cost(tokenizer) -> Callable[[str], int]:
    """Sub-words that one whitespace token costs in the model input (cached).

    The tokenizer's pre-tokenizer never crosses whitespace, so costs are additive over whitespace
    tokens; ``hebloc.parse.checks`` re-verifies this on every parsed piece."""

    @functools.lru_cache(maxsize=1_000_000)
    def cost(token: str) -> int:
        return len(tokenizer(token, add_special_tokens=False)["input_ids"])

    return cost
