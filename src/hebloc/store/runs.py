"""Parse-run discovery, references and the canonical-run registry.

Layout (M3 pilot, and M5 per corpus)::

    data/annotations/<collection>/runs/<run_id>/
        inputs/ pieces/ dicta_raw/      shard-NNNNN.parquet   written by hebloc.parse.run
        _shards/shard-NNNNN.json        shard commit marker (written last)
        tokens/shard-NNNNN.parquet      derived from dicta_raw (hebloc.parse.tokens)
        tokens/_manifest.json           per-shard source hashes → skip what is up to date
        run.json  checks.json

``<collection>`` is ``pilot`` or a corpus id. A run is referred to as ``"<collection>/<run_id>"``
(e.g. ``"pilot/base__default"``) or by its directory.

Which runs feed the default ``tokens`` of each corpus is a *recorded decision*, not a guess: the
git-tracked ``config/annotations.yaml`` lists the canonical run(s) per corpus. It is empty until
M5. Several runs per corpus are allowed (e.g. Modern parsed in parts) but they may not share a
``sent_id`` (``hebloc check`` enforces this).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import yaml

from hebloc.paths import ANNOTATIONS_DIR, CONFIG_DIR, CORPORA

ANNOTATIONS_CONFIG = CONFIG_DIR / "annotations.yaml"
RUN_PARTS = ("inputs", "pieces", "dicta_raw")      # written by the parser, per shard
DERIVED_PARTS = ("tokens",)                         # derived from RUN_PARTS, per shard
ALL_PARTS = RUN_PARTS + DERIVED_PARTS


@dataclass(frozen=True)
class Run:
    collection: str
    run_id: str
    path: Path

    @property
    def ref(self) -> str:
        return f"{self.collection}/{self.run_id}"

    @cached_property
    def manifest(self) -> dict:
        from hebloc.store.io import read_json

        p = self.path / "run.json"
        return read_json(p) if p.exists() else {}

    def shards(self) -> list[str]:
        """Committed shards (their manifest exists), sorted."""
        return sorted(p.stem for p in (self.path / "_shards").glob("shard-*.json"))

    def part_file(self, part: str, shard: str) -> Path:
        return self.path / part / f"{shard}.parquet"

    def part_files(self, part: str) -> list[Path]:
        return sorted((self.path / part).glob("shard-*.parquet"))

    def status(self) -> dict:
        """Completeness of the run on disk (cheap: file existence and manifests only)."""
        from hebloc.parse.tokens import tokens_status

        shards = self.shards()
        missing = [f"{part}/{s}" for s in shards for part in RUN_PARTS if not self.part_file(part, s).exists()]
        uncommitted = sorted({p.stem for part in RUN_PARTS for p in self.part_files(part)} - set(shards))
        m = self.manifest
        complete = bool(m) and m.get("shards") == len(shards) and not missing
        return {"ref": self.ref, "model": m.get("model"), "variant": m.get("variant"), "units": m.get("units"),
                "shards": len(shards), "complete": complete, "missing_part_files": missing,
                "uncommitted_shards": uncommitted, "tokens": tokens_status(self.path)}


def resolve(ref: str | Path | Run, root: Path = ANNOTATIONS_DIR) -> Run:
    """``"pilot/base__default"`` | a run directory | a ``Run`` → ``Run`` (must exist)."""
    if isinstance(ref, Run):
        return ref
    p = Path(ref)
    if not p.is_absolute() and len(p.parts) == 2:
        collection, run_id = p.parts
        path = root / collection / "runs" / run_id
    else:
        path = p.resolve()
        collection, run_id = path.parent.parent.name, path.name
    if not path.is_dir():
        raise FileNotFoundError(f"no parse run {str(ref)!r} at {path}")
    return Run(collection, run_id, path)


def list_runs(root: Path = ANNOTATIONS_DIR) -> list[Run]:
    out = []
    for d in sorted(root.glob("*/runs/*")):
        if d.is_dir() and ((d / "_shards").is_dir() or (d / "run.json").exists()):
            out.append(Run(d.parent.parent.name, d.name, d))
    return out


def run_dir_for(corpus: str, run_id: str, root: Path = ANNOTATIONS_DIR) -> Path:
    """Where an M5 run for ``corpus`` lives (not created here)."""
    if corpus not in CORPORA:
        raise ValueError(f"unknown corpus {corpus!r}")
    return root / corpus / "runs" / run_id


def load_registry(path: Path = ANNOTATIONS_CONFIG) -> dict[str, list[str]]:
    """corpus → [run refs] from ``config/annotations.yaml`` (empty mapping if absent/empty)."""
    if not path.exists():
        return {}
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    reg = cfg.get("canonical") or {}
    out = {}
    for corpus, refs in reg.items():
        if corpus not in CORPORA:
            raise ValueError(f"{path}: unknown corpus {corpus!r}")
        out[corpus] = [refs] if isinstance(refs, str) else list(refs or [])
    return out


def canonical_runs(corpus: str | None = None, *, root: Path = ANNOTATIONS_DIR,
                   config: Path = ANNOTATIONS_CONFIG) -> dict[str, list[Run]]:
    """corpus → canonical ``Run``s (only corpora that have any)."""
    reg = load_registry(config)
    corpora = [corpus] if corpus else list(CORPORA)
    return {c: [resolve(r, root) for r in reg[c]] for c in corpora if reg.get(c)}
