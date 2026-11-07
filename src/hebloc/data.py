"""Public read API for the project's data layer: catalog, units and parser annotations.

Typical use::

    from hebloc import data
    df = data.units("mikra", columns=["sent_id", "ref", "text_norm"])        # pandas
    df = data.units("hazal", view="curated")                                 # curated view
    for batch in data.iter_units("modern", columns=["sent_id", "text_norm"]):  # streaming
        ...
    data.trace("mikra:<doc_id>:2:0")      # unit → exact source file/line/offsets, verified

    data.runs()                                                    # parse runs + status
    toks = data.tokens("mikra", run="pilot/base__default", columns=["sent_id", "lemma", "upos"])
    toks = data.tokens("hazal", view="curated", where="upos = 'VERB'")       # canonical run (M5+)
    data.sentence("mikra:<doc_id>:2:0", run="pilot/base__default")  # unit + pieces + tokens
    data.trace_token("mikra:<doc_id>:2:0", 3, run="pilot/base__default")     # word → source, verified
    data.coverage()                                                # parsed / multi-piece / invalid trees
    con = data.connect(); con.sql("SELECT corpus_id, count(*) FROM tokens GROUP BY 1")

Views (decision D-015): ``view=None`` → everything; ``"full"`` → the full view (primary reference);
``"curated"`` → the curated historical/deduplicated view. For annotations the view is applied
through ``documents`` (``doc_id`` is part of ``sent_id``).

Which annotations: ``run=None`` reads the **canonical** run(s) registered for the corpus in
``config/annotations.yaml`` (set in M5; at most one analysis per unit). ``run="pilot/<run_id>"``
(or any ``<collection>/<run_id>``) reads one specific run. Nothing is ever guessed: with no
canonical run registered, ``run=`` is required.

Statistics caveats carried by the columns, never silently applied (D-021, D-025): ``n_pieces > 1``
→ the unit has no single tree; ``piece_tree_valid = false`` → the piece's word-level tree is not a
tree; error pieces have no tokens (see ``coverage()``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import duckdb
import pyarrow as pa
import pyarrow.dataset as ds

from hebloc.catalog import DOCUMENTS_PATH
from hebloc.paths import CORPORA, CORPORA_DIR, UNITS_DIR
from hebloc.textstats import decode_bytes, split_lines

VIEWS = (None, "full", "curated")


# ------------------------------------------------------------------ units (M2)

def _units_dataset(corpus: str | list[str] | None, root: Path = UNITS_DIR) -> ds.Dataset:
    corpora = list(CORPORA) if corpus is None else ([corpus] if isinstance(corpus, str) else list(corpus))
    paths = []
    for c in corpora:
        if c not in CORPORA:
            raise ValueError(f"unknown corpus {c!r}")
        files = sorted((root / c).glob("*.parquet"))
        if not files:
            raise FileNotFoundError(f"No units for {c!r} under {root}. Run: uv run hebloc prepare --corpus {c}")
        paths += [str(p) for p in files]
    return ds.dataset(paths, format="parquet")


def _filter(view: str | None):
    if view not in VIEWS:
        raise ValueError(f"view must be one of {VIEWS}")
    return None if view is None else (ds.field(f"in_{view}_view") == True)  # noqa: E712


def units(corpus: str | list[str] | None = None, *, view: str | None = None,
          columns: list[str] | None = None, root: Path = UNITS_DIR):
    """Load units as a pandas DataFrame (use ``iter_units`` for the large Modern corpus)."""
    return _units_dataset(corpus, root).to_table(columns=columns, filter=_filter(view)).to_pandas()


def iter_units(corpus: str | list[str] | None = None, *, view: str | None = None,
               columns: list[str] | None = None, batch_size: int = 50_000,
               root: Path = UNITS_DIR) -> Iterator[pa.RecordBatch]:
    """Stream units as Arrow record batches (bounded memory)."""
    scanner = _units_dataset(corpus, root).scanner(columns=columns, filter=_filter(view), batch_size=batch_size)
    yield from scanner.to_batches()


def unit(sent_id: str, root: Path = UNITS_DIR) -> dict:
    """One unit row as a dict."""
    corpus = sent_id.split(":", 1)[0]
    t = _units_dataset(corpus, root).to_table(filter=ds.field("sent_id") == sent_id)
    if t.num_rows != 1:
        raise KeyError(f"sent_id not found: {sent_id}")
    return t.to_pylist()[0]


def trace(sent_id: str, root: Path = UNITS_DIR) -> dict:
    """Map a unit back to its exact source and VERIFY it: re-read the original file (read-only),
    take the line and the character span, and check it equals the stored ``text_raw``."""
    u = unit(sent_id, root)
    doc = duckdb.connect().execute(f"SELECT rel_path, encoding, sha256 FROM read_parquet('{DOCUMENTS_PATH.as_posix()}') "
                                   "WHERE doc_id = ?", [u["doc_id"]]).fetchone()
    rel_path, encoding, sha = doc
    text, detected, _ = decode_bytes((CORPORA_DIR / rel_path).read_bytes())
    line = split_lines(text)[u["line_no"] - 1]
    source_slice = line[u["char_start"]:u["char_end"]]
    return {
        "sent_id": sent_id, "ref": u["ref"], "rel_path": rel_path, "encoding": detected,
        "file_sha256": sha, "line_no": u["line_no"], "char_start": u["char_start"], "char_end": u["char_end"],
        "source_line": line, "text_raw": u["text_raw"], "text_norm": u["text_norm"],
        "norm_flags": u["norm_flags"], "verified": source_slice == u["text_raw"],
    }


# ------------------------------------------------------------------ catalog / annotations (M4)

def connect(root: Path = UNITS_DIR, **paths) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with every catalog view (``hebloc.store.catalog``): ``documents``, ``units``,
    ``runs``, canonical ``inputs``/``pieces``/``dicta_raw``/``tokens``, all-run ``*_all`` views,
    ``piece_status`` and ``parse_coverage``. No data is copied."""
    from hebloc.store import catalog

    return catalog.connect(units_root=root, **paths)


def runs(**paths):
    """Every parse run on disk with its manifest, completeness and canonical role (pandas)."""
    from hebloc.store import catalog

    return catalog.runs_table(**{k: v for k, v in paths.items() if k in ("root", "config")}).to_pandas()


def _relation(part: str, corpus: str | list[str] | None, run, view: str | None, where: str | None,
              columns: list[str] | None) -> str:
    """SQL for one annotation part: chosen run (or canonical runs), corpus, view and filter."""
    from hebloc.store.catalog import _part_union
    from hebloc.store.runs import canonical_runs, resolve

    if view not in VIEWS:
        raise ValueError(f"view must be one of {VIEWS}")
    corpora = list(CORPORA) if corpus is None else ([corpus] if isinstance(corpus, str) else list(corpus))
    for c in corpora:
        if c not in CORPORA:
            raise ValueError(f"unknown corpus {c!r}")
    if run is not None:
        src = _part_union(part, [(resolve(run), None)])
    else:
        canon = canonical_runs()
        missing = [c for c in corpora if c not in canon] if corpus is not None else []
        if missing or not canon:
            raise LookupError(f"no canonical parse run registered for {missing or 'any corpus'} in "
                              "config/annotations.yaml (set in M5). Pass run='<collection>/<run_id>', "
                              "e.g. run='pilot/base__default'; see data.runs().")
        src = _part_union(part, [(r, c) for c, rs in canon.items() if c in corpora for r in rs])
    conds = [f"corpus_id IN ({', '.join(repr(c) for c in corpora)})"]
    if view is not None:
        conds.append(f"doc_id IN (SELECT doc_id FROM read_parquet('{DOCUMENTS_PATH.as_posix()}') "
                     f"WHERE in_{view}_view)")
    if where:
        conds.append(f"({where})")
    cols = ", ".join(f'"{c}"' for c in columns) if columns else "*"
    return f"SELECT {cols} FROM ({src}) WHERE {' AND '.join(conds)}"


def _query(part, corpus, run, view, where, columns, order: str | None = None) -> duckdb.DuckDBPyConnection:
    sql = _relation(part, corpus, run, view, where, columns)
    if order:
        sql += f" ORDER BY {order}"
    return duckdb.connect().execute(sql)


def tokens(corpus: str | list[str] | None = None, *, run=None, view: str | None = None,
           columns: list[str] | None = None, where: str | None = None):
    """Tokens (one row per Dicta word) as pandas, with ``run``, ``corpus_id`` and ``doc_id`` added.
    ``where`` is an SQL condition on token columns (e.g. ``"upos = 'VERB'"``). For whole-Modern
    scans use ``iter_tokens`` or ``connect()``."""
    return _query("tokens", corpus, run, view, where, columns,
                  order="sent_id, piece_idx, word_idx").df()


def iter_tokens(corpus: str | list[str] | None = None, *, run=None, view: str | None = None,
                columns: list[str] | None = None, where: str | None = None,
                batch_size: int = 100_000) -> Iterator[pa.RecordBatch]:
    """Stream tokens as Arrow record batches (bounded memory; file order)."""
    con = duckdb.connect()
    reader = con.sql(_relation("tokens", corpus, run, view, where, columns)).to_arrow_reader(batch_size)
    yield from reader


def pieces(corpus: str | list[str] | None = None, *, run=None, view: str | None = None,
           columns: list[str] | None = None, where: str | None = None):
    """Piece metadata (``PIECES_SCHEMA``) as pandas."""
    return _query("pieces", corpus, run, view, where, columns,
                  order="sent_id, piece_idx").df()


def _sid_where(sent_id: str) -> str:
    return "sent_id = " + "'" + sent_id.replace("'", "''") + "'"


def raw(sent_id: str, *, run=None) -> list[dict]:
    """The verbatim Dicta output of each piece of a unit: ``[{piece_idx, status, error, output}]``."""
    corpus = sent_id.split(":", 1)[0]
    rows = _query("dicta_raw", corpus, run, None, _sid_where(sent_id), None, order="piece_idx").fetchall()
    cols = ["run", "corpus_id", "doc_id", "sent_id", "piece_idx", "status", "compute_mst", "error", "raw_json"]
    out = []
    for r in rows:
        d = dict(zip(cols, r))
        out.append({"run": d["run"], "piece_idx": d["piece_idx"], "status": d["status"], "error": d["error"],
                    "output": json.loads(d["raw_json"]) if d["raw_json"] else None})
    if not out:
        raise KeyError(f"{sent_id} has no parse in {'run ' + str(run) if run else 'the canonical run'}")
    return out


def sentence(sent_id: str, *, run=None) -> dict:
    """A unit with its pieces and tokens (for inspection)."""
    corpus = sent_id.split(":", 1)[0]
    u = unit(sent_id)
    ps = pieces(corpus, run=run, where=_sid_where(sent_id))
    ts = tokens(corpus, run=run, where=_sid_where(sent_id))
    return {"unit": {k: u[k] for k in ("sent_id", "ref", "unit_type", "text_raw", "text_norm", "norm_flags", "stratum")},
            "pieces": ps, "tokens": ts,
            "complete_tree": bool(len(ps) == 1 and ts["piece_tree_valid"].all()) if len(ts) else False}


def trace_token(sent_id: str, sent_word_idx: int, *, run=None) -> dict:
    """A word → its unit → its source line, each step VERIFIED: the token's span in the parsed text
    equals its ``surface``, the parsed text equals ``units.text_norm`` (default runs), and the unit
    equals its span in the original file (``trace``). Note: normalization keeps no character
    alignment, so the word is located in the source at unit level (the line and the unit's span)."""
    corpus = sent_id.split(":", 1)[0]
    t = tokens(corpus, run=run, where=f"{_sid_where(sent_id)} AND sent_word_idx = {int(sent_word_idx)}")
    if len(t) != 1:
        raise KeyError(f"token {sent_id}#{sent_word_idx} not found")
    tok = t.iloc[0].to_dict()
    parsed = _query("inputs", corpus, run, None, _sid_where(sent_id), ["text"]).fetchone()[0]
    src = trace(sent_id)
    return {"token": {k: tok[k] for k in ("run", "sent_id", "piece_idx", "word_idx", "sent_word_idx", "char_start",
                                           "char_end", "surface", "form", "lemma", "upos", "feats", "deprel",
                                           "piece_tree_valid")},
            "surface_verified": parsed[tok["char_start"]:tok["char_end"]] == tok["surface"],
            "parsed_text_is_text_norm": parsed == src["text_norm"],
            "unit": src, "verified": (parsed[tok["char_start"]:tok["char_end"]] == tok["surface"]) and src["verified"]}


def coverage(**paths):
    """Per corpus × stratum: units, parsed units, multi-piece units, units with an error piece or an
    invalid word-level tree, over the CANONICAL runs. What every statistic must report."""
    return connect(**paths).execute("SELECT * FROM parse_coverage").df()


def conllu(sent_id: str, *, run=None, style: str = "ud") -> str:
    """CoNLL-U of one unit (one block per piece), with provenance comments."""
    from hebloc.parse.checks import tree_problems
    from hebloc.store.conllu import piece_block

    corpus = sent_id.split(":", 1)[0]
    ref = unit(sent_id)["ref"]
    ps = {p["piece_idx"]: p for p in pieces(corpus, run=run, where=_sid_where(sent_id)).to_dict("records")}
    out = []
    for r in raw(sent_id, run=run):
        if r["output"] is None:
            continue
        p = ps[r["piece_idx"]]
        out.append(piece_block(r["output"], sent_id=sent_id, piece_idx=r["piece_idx"], n_pieces=p["n_pieces"],
                               span=(p["norm_char_start"], p["norm_char_end"]), ref=ref, run_ref=r["run"],
                               status=r["status"], tree_valid=not tree_problems(r["output"]), style=style))
    return "".join(out)
