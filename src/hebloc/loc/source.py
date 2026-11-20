"""One reader for the two data sources of S56-v1 (EFRAT_SECTION_6.md §7 I2).

- ``repo``: the canonical runs of ``config/annotations.yaml`` (committed shards only), the units in
  ``data/units/<corpus>/`` and the catalog ``data/catalog/documents.parquet``.
- ``package``: the D-051 analysis package (``<pkg>/data/tokens/<corpus>/<run_id>.parquet``,
  ``<pkg>/data/sentences/<corpus>/``, ``<pkg>/data/documents.parquet``), proved lossless against
  the official runs (``VERIFICATION.json``).

Both are exposed as the same DuckDB relations with the same columns, so every output computed from
them is identical whichever source is used (tested). Order is never assumed: every consumer sorts
explicitly by ``(sent_id, piece_idx, word_idx)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

from hebloc.paths import CATALOG_DIR, CORPORA, UNITS_DIR
from hebloc.store.io import file_sha256, sql_list, sql_str

#: Token columns read by hebloc.loc (all of TOKENS_SCHEMA except offsets/ner/status bookkeeping).
TOKEN_COLUMNS = ("sent_id", "piece_idx", "n_pieces", "word_idx", "sent_word_idx", "char_start", "char_end",
                 "ws_idx", "form", "surface", "prefix", "host", "lemma", "lemma_blank", "upos", "feats",
                 "gender", "number", "person", "tense", "prefix_upos", "suffix", "suffix_feats", "head",
                 "head_sent", "deprel", "piece_tree_valid")

UNIT_COLUMNS = ("sent_id", "doc_id", "ref", "text_norm", "stratum", "in_full_view", "in_curated_view",
                "is_empty_norm")


class SourceError(Exception):
    """The requested data source is missing or inconsistent (a STOP condition, never worked around)."""


@dataclass(frozen=True)
class RunPart:
    """The token files of one run: ``run_id`` and the parquet files holding it."""
    run_id: str
    files: tuple[Path, ...]


@dataclass(frozen=True)
class Source:
    kind: str                       # "repo" | "package"
    package: Path | None = None     # the extracted D-051 package folder (kind == "package")
    annotations_root: Path | None = None   # tests: repo layout elsewhere
    registry: Path | None = None
    units_root: Path | None = None
    documents: Path | None = None

    # ------------------------------------------------------------------ construction
    @classmethod
    def repo(cls, *, annotations_root: Path | None = None, registry: Path | None = None,
             units_root: Path | None = None, documents: Path | None = None) -> "Source":
        return cls("repo", None, annotations_root, registry, units_root, documents)

    @classmethod
    def from_package(cls, folder: Path | str) -> "Source":
        folder = Path(folder).resolve()
        if not (folder / "data" / "tokens").is_dir() or not (folder / "VERIFICATION.json").exists():
            raise SourceError(f"{folder} is not an extracted D-051 analysis package "
                              "(expected data/tokens/ and VERIFICATION.json)")
        return cls("package", folder)

    @classmethod
    def make(cls, kind: str, package: str | Path | None = None) -> "Source":
        if kind == "repo":
            if package:
                raise SourceError("--package is only used with --source package")
            return cls.repo()
        if kind == "package":
            if not package:
                raise SourceError("--source package needs --package <extracted package folder>")
            return cls.from_package(package)
        raise SourceError(f"unknown source {kind!r} (repo | package)")

    # ------------------------------------------------------------------ files
    def runs(self, corpus: str) -> list[RunPart]:
        """The runs of ``corpus``, sorted by run_id, each with its token files."""
        if corpus not in CORPORA:
            raise SourceError(f"unknown corpus {corpus!r}")
        if self.kind == "package":
            files = sorted((self.package / "data" / "tokens" / corpus).glob("*.parquet"))
            if not files:
                raise SourceError(f"package has no tokens for {corpus}")
            return [RunPart(f.stem, (f,)) for f in files]
        from hebloc.store import runs as R

        kw = {}
        if self.annotations_root is not None:
            kw["root"] = self.annotations_root
        if self.registry is not None:
            kw["config"] = self.registry
        reg = R.canonical_runs(corpus, **kw).get(corpus) or []
        if not reg:
            raise SourceError(f"no registered runs for {corpus} in config/annotations.yaml")
        out = []
        for run in sorted(reg, key=lambda r: r.run_id):
            files = []
            for s in run.shards():
                f = run.part_file("tokens", s)
                if not f.exists():
                    raise SourceError(f"{run.ref}: tokens missing for {s} (run: hebloc tokens {run.ref})")
                files.append(f)
            if not files:
                raise SourceError(f"{run.ref}: no committed shards")
            out.append(RunPart(run.run_id, tuple(files)))
        return out

    def units_files(self, corpus: str) -> list[Path]:
        root = (self.package / "data" / "sentences" if self.kind == "package" else (self.units_root or UNITS_DIR))
        files = sorted((root / corpus).glob("*.parquet"))
        if not files:
            raise SourceError(f"no units for {corpus} under {root}")
        return files

    def documents_path(self) -> Path:
        p = (self.package / "data" / "documents.parquet" if self.kind == "package"
             else (self.documents or CATALOG_DIR / "documents.parquet"))
        if not p.exists():
            raise SourceError(f"document catalog missing: {p}")
        return p

    # ------------------------------------------------------------------ relations
    def tokens_sql(self, run: RunPart, columns: tuple[str, ...] = TOKEN_COLUMNS) -> str:
        """SQL relation of one run's tokens: ``columns`` + ``run_id`` + ``shard`` + ``doc_id``.

        The repo stores one file per shard; the package stores one file per run with a ``shard``
        column. Both give the same rows and values."""
        cols = ", ".join(columns)
        rid = sql_str(run.run_id)
        doc = "split_part(sent_id, ':', 2) AS doc_id"
        if self.kind == "package":
            return (f"(SELECT {cols}, {rid} AS run_id, shard, {doc} "
                    f"FROM read_parquet({sql_list(run.files)}))")
        return (f"(SELECT {cols}, {rid} AS run_id, "
                f"regexp_extract(replace(filename, '\\', '/'), '/(shard-[0-9]+)\\.parquet$', 1) AS shard, {doc} "
                f"FROM read_parquet({sql_list(run.files)}, filename = true))")

    def units_sql(self, corpus: str, columns: tuple[str, ...] = UNIT_COLUMNS) -> str:
        return f"(SELECT {', '.join(columns)} FROM read_parquet({sql_list(self.units_files(corpus))}))"

    def documents_sql(self, columns: tuple[str, ...] = ("doc_id", "corpus_id", "subcorpus", "source", "stratum",
                                                         "in_full_view", "in_curated_view")) -> str:
        return f"(SELECT {', '.join(columns)} FROM read_parquet({sql_str(self.documents_path())}))"

    # ------------------------------------------------------------------ provenance
    def describe(self, corpus: str | None = None) -> dict:
        """What the manifest records about the data source (I5)."""
        if self.kind == "package":
            ver = self.package / "VERIFICATION.json"
            return {"kind": "package", "package": str(self.package), "verification_sha256": file_sha256(ver)}
        from hebloc.parse.checks import run_fingerprint
        from hebloc.store import runs as R

        kw = {}
        if self.annotations_root is not None:
            kw["root"] = self.annotations_root
        if self.registry is not None:
            kw["config"] = self.registry
        reg = R.canonical_runs(corpus, **kw)
        return {"kind": "repo", "runs": {r.ref: run_fingerprint(r.path) for c in sorted(reg) for r in reg[c]}}


def connect(threads: int | None = None) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    if threads:
        con.execute(f"SET threads = {int(threads)}")
    return con
