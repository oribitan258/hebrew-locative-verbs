"""CoNLL-U export of a parse run, from the stored raw output (no model run).

The UD lines are produced by Dicta's own ``convert_output_to_ud`` (vendored, unmodified) applied
to a deep copy of each piece's ``raw_json``; D-023 verified that this equals what Dicta's
``predict(output_style="ud" | "iahlt_ud")`` returns. Styles: ``ud`` (HTB conventions, Dicta's
default) and ``iahlt_ud``.

One CoNLL-U sentence per **piece** (a multi-piece unit has no single tree, D-021). Comments:

    # sent_id = <sent_id>            (multi-piece units: <sent_id>~p<piece_idx>)
    # text = <piece text>            (from Dicta: the exact text parsed)
    # hebloc_sent_id = <sent_id>     parent unit → hebloc.data.trace() → source file/line
    # hebloc_piece = <piece_idx>/<n_pieces>    0-based index / count
    # hebloc_norm_span = <start>-<end>          the piece's span in the unit's text_norm
    # hebloc_ref = <human reference>
    # hebloc_run = <collection>/<run_id>
    # hebloc_status = ok | mst_fallback
    # hebloc_tree_valid = true | false          false → word-level tree is not a tree (D-025)

Only change to Dicta's lines: an empty field (e.g. FEATS of a word with no features) is written as
``_``, as CoNLL-U requires. Pieces with ``status = error`` have no analysis and are counted, not
written. Pieces lacking an annotation layer are counted and skipped (Dicta's converter would
otherwise terminate the process).
"""

from __future__ import annotations

import copy
import json
import os
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pyarrow.parquet as pq

from hebloc.paths import DATA_DIR, UNITS_DIR, CORPORA, assert_not_in_corpora
from hebloc.store.io import sql_list
from hebloc.store.runs import Run, resolve

EXPORT_DIR = DATA_DIR / "exports" / "conllu"
STYLES = {"ud": "htb", "iahlt_ud": "iahlt"}


def _converter():
    from hebloc.parse.dicta_code.BertForJointParsing import convert_output_to_ud
    from hebloc.parse.dicta_code.BertForPrefixMarking import DEFAULT_PREFIX_CONFIG

    # Both pinned models have prefix_cfg = null in config.json, so the model uses
    # DEFAULT_PREFIX_CONFIG (BertForPrefixMarking.__init__); checked by a test when models exist.
    return convert_output_to_ud, SimpleNamespace(prefix_cfg=DEFAULT_PREFIX_CONFIG)


def has_all_layers(out: dict) -> bool:
    for t in out.get("tokens") or []:
        m, s = t.get("morph"), t.get("syntax")
        if not (t.get("seg") and "lex" in t and isinstance(m, dict) and isinstance(s, dict)):
            return False
        if not ({"pos", "feats", "prefixes", "suffix"} <= m.keys() and {"dep_head_idx", "dep_func"} <= s.keys()):
            return False
    return bool(out.get("tokens"))


def piece_lines(out: dict, *, style: str = "ud", conv=None) -> list[str]:
    """Dicta's UD lines for one piece (header comments included), empty fields → ``_``."""
    convert, cfg = conv or _converter()
    lines = convert([copy.deepcopy(out)], cfg, style=STYLES[style])[0]
    fixed = []
    for ln in lines:
        if ln.startswith("#"):
            fixed.append(ln)
        else:
            fixed.append("\t".join(f if f != "" else "_" for f in ln.split("\t")))
    return fixed


def piece_block(out: dict, *, sent_id: str, piece_idx: int, n_pieces: int, span: tuple[int, int],
                ref: str | None, run_ref: str, status: str, tree_valid: bool, style: str = "ud", conv=None) -> str:
    lines = piece_lines(out, style=style, conv=conv)
    assert lines[0].startswith("# sent_id = ") and lines[1].startswith("# text = ")
    ud_id = sent_id if n_pieces == 1 else f"{sent_id}~p{piece_idx}"
    meta = [f"# sent_id = {ud_id}", lines[1],
            f"# hebloc_sent_id = {sent_id}", f"# hebloc_piece = {piece_idx}/{n_pieces}",
            f"# hebloc_norm_span = {span[0]}-{span[1]}"]
    if ref:
        meta.append(f"# hebloc_ref = {ref}")
    meta += [f"# hebloc_run = {run_ref}", f"# hebloc_status = {status}",
             f"# hebloc_tree_valid = {'true' if tree_valid else 'false'}"]
    return "\n".join(meta + lines[2:]) + "\n\n"


def export_run(ref: str | Path | Run, out_path: Path | None = None, *, corpus: str | None = None,
               sent_ids: list[str] | None = None, style: str = "ud", valid_only: bool = False,
               units_root: Path = UNITS_DIR) -> dict:
    """Write a run (optionally one corpus / some units) as CoNLL-U. Returns counts and the path."""
    from hebloc.parse.checks import tree_problems

    if style not in STYLES:
        raise ValueError(f"style must be one of {list(STYLES)}")
    if corpus is not None and corpus not in CORPORA:
        raise ValueError(f"unknown corpus {corpus!r}")
    run = resolve(ref)
    name = f"{run.collection}__{run.run_id}" + (f"__{corpus}" if corpus else "") + f"__{style}.conllu"
    out_path = Path(out_path) if out_path else EXPORT_DIR / name
    assert_not_in_corpora(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wanted = set(sent_ids) if sent_ids is not None else None
    conv = _converter()
    con = duckdb.connect()
    unit_files = sorted(f for c in CORPORA for f in (units_root / c).glob("*.parquet"))
    c = Counter()
    tmp = out_path.with_name(f".{out_path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            for shard in run.shards():
                pieces = {(p["sent_id"], p["piece_idx"]): p
                          for p in pq.read_table(run.part_file("pieces", shard)).to_pylist()}
                raws = pq.read_table(run.part_file("dicta_raw", shard)).to_pylist()
                raws = [r for r in raws if (corpus is None or r["sent_id"].startswith(corpus + ":"))
                        and (wanted is None or r["sent_id"] in wanted)]
                if not raws:
                    continue
                refs = dict(con.execute(
                    f"SELECT sent_id, ref FROM read_parquet({sql_list(unit_files)}) "
                    f"WHERE sent_id IN (SELECT unnest(?::VARCHAR[]))", [sorted({r['sent_id'] for r in raws})]
                ).fetchall()) if unit_files else {}
                for r in sorted(raws, key=lambda r: (r["sent_id"], r["piece_idx"])):
                    if r["status"] == "error":
                        c["skipped_error_piece"] += 1
                        continue
                    out = json.loads(r["raw_json"])
                    if not has_all_layers(out):
                        c["skipped_missing_layer"] += 1
                        continue
                    valid = not tree_problems(out)
                    if valid_only and not valid:
                        c["skipped_invalid_tree"] += 1
                        continue
                    p = pieces[(r["sent_id"], r["piece_idx"])]
                    fh.write(piece_block(out, sent_id=r["sent_id"], piece_idx=r["piece_idx"], n_pieces=p["n_pieces"],
                                         span=(p["norm_char_start"], p["norm_char_end"]), ref=refs.get(r["sent_id"]),
                                         run_ref=run.ref, status=r["status"], tree_valid=valid, style=style, conv=conv))
                    c["pieces_written"] += 1
                    c["invalid_tree_written"] += not valid
        os.replace(tmp, out_path)
    finally:
        tmp.unlink(missing_ok=True)
    return {"path": str(out_path), "run": run.ref, "style": style, "corpus": corpus, **dict(c)}
