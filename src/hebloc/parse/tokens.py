"""Derive the ``tokens`` table (one row per Dicta word) from a run's raw output — never from the model.

PROPOSED schema (M3; to be confirmed at the M3 gate). Character offsets are in the PARSED unit
text (``inputs.text``; for default runs this is ``units.text_norm``, checked by
``hebloc.parse.checks``), so every token maps back to the unit and from there to the source file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hebloc.parse.run import read_run

TOKENS_VERSION = "1"
FEATS = ("Gender", "Number", "Person", "Tense")
TOKENS_SCHEMA = pa.schema([
    ("sent_id", pa.string()),
    ("piece_idx", pa.int16()),
    ("n_pieces", pa.int16()),          # 1 → the unit has one complete tree
    ("word_idx", pa.int32()),          # 0-based position in the piece
    ("sent_word_idx", pa.int32()),     # 0-based position in the unit (across pieces)
    ("char_start", pa.int32()),        # span in the parsed unit text
    ("char_end", pa.int32()),
    ("ws_idx", pa.int32()),            # whitespace-token index in the unit text containing the word
    ("form", pa.string()),             # the model's (normalized) word string
    ("surface", pa.string()),          # exact unit-text slice [char_start:char_end]
    ("prefix", pa.string()),           # segmented prefix letters (e.g. "וב"), null if none
    ("host", pa.string()),             # word without the prefix
    ("lemma", pa.string()),            # Dicta lexeme; "[BLANK]" kept verbatim when the model abstains
    ("lemma_blank", pa.bool_()),
    ("upos", pa.string()),
    ("feats", pa.string()),            # UD-style "Gender=Masc|Number=Sing" (only these 4 features exist)
    ("gender", pa.string()), ("number", pa.string()), ("person", pa.string()), ("tense", pa.string()),
    ("prefix_upos", pa.list_(pa.string())),   # POS of the prefixes predicted by the morph head
    ("suffix", pa.string()),           # PRON | ADP_PRON | null
    ("suffix_feats", pa.string()),
    ("head", pa.int32()),              # piece-local word index of the head; -1 = root of the piece
    ("head_sent", pa.int32()),         # head as sent_word_idx; -1 = root
    ("deprel", pa.string()),
    ("ner", pa.string()),
    ("status", pa.string()),           # ok | mst_fallback (tree decoded without MST)
    # False when the piece's WORD-level tree is not a tree (cycle / self-loop / ≠1 root). Dicta decodes
    # a valid tree over SUB-WORDS, then maps each word to its first sub-word's head; a head inside
    # another word's continuation sub-word can create word-level cycles (M3 finding). Never repaired.
    ("piece_tree_valid", pa.bool_()),
    ("tokens_version", pa.string()),
])


def _feats(d: dict | None) -> str | None:
    return "|".join(f"{k}={v}" for k, v in d.items()) if d else None


def derive_rows(text: str, piece: dict, raw: dict, status: str, word_offset: int) -> list[dict]:
    from hebloc.parse.checks import tree_problems

    out = json.loads(raw) if isinstance(raw, str) else raw
    valid = not tree_problems(out)
    base = piece["norm_char_start"]
    rows = []
    ws_starts = []  # whitespace-token starts in the unit text, for ws_idx
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i < n:
            ws_starts.append(i)
        while i < n and not text[i].isspace():
            i += 1
    import bisect

    for wi, t in enumerate(out["tokens"]):
        s, e = t["offsets"]["start"] + base, t["offsets"]["end"] + base
        seg = t.get("seg") or [t["token"]]
        m = t.get("morph") or {}
        f = m.get("feats") or {}
        syn = t.get("syntax") or {}
        head = syn.get("dep_head_idx")
        rows.append({
            "sent_id": piece["sent_id"], "piece_idx": piece["piece_idx"], "n_pieces": piece["n_pieces"],
            "word_idx": wi, "sent_word_idx": word_offset + wi, "char_start": s, "char_end": e,
            "ws_idx": bisect.bisect_right(ws_starts, s) - 1, "form": t["token"], "surface": text[s:e],
            "prefix": seg[0] if len(seg) > 1 else None, "host": seg[-1],
            "lemma": t.get("lex"), "lemma_blank": t.get("lex") == "[BLANK]",
            "upos": m.get("pos"), "feats": _feats(f),
            "gender": f.get("Gender"), "number": f.get("Number"), "person": f.get("Person"), "tense": f.get("Tense"),
            "prefix_upos": list(m.get("prefixes") or []),
            "suffix": m.get("suffix") or None, "suffix_feats": _feats(m.get("suffix_feats")),
            "head": head, "head_sent": -1 if head in (None, -1) else word_offset + head,
            "deprel": syn.get("dep_func"), "ner": t.get("ner"), "status": status, "piece_tree_valid": valid,
            "tokens_version": TOKENS_VERSION,
        })
    return rows


def derive(run_dir: Path, write: bool = True) -> pa.Table:
    """Build tokens for the whole run from inputs + pieces + dicta_raw (errors produce no tokens)."""
    texts = dict(zip(*read_run(run_dir, "inputs").select(["sent_id", "text"]).to_pydict().values()))
    pieces = {(p["sent_id"], p["piece_idx"]): p for p in read_run(run_dir, "pieces").to_pylist()}
    raws = sorted(read_run(run_dir, "dicta_raw").to_pylist(), key=lambda r: (r["sent_id"], r["piece_idx"]))
    rows, offset, cur = [], 0, None
    for r in raws:
        if r["sent_id"] != cur:
            cur, offset = r["sent_id"], 0
        if r["status"] == "error":
            continue
        new = derive_rows(texts[r["sent_id"]], pieces[(r["sent_id"], r["piece_idx"])], r["raw_json"], r["status"], offset)
        offset += len(new)
        rows += new
    table = pa.Table.from_pylist(rows, schema=TOKENS_SCHEMA)
    if write:
        (run_dir / "tokens").mkdir(exist_ok=True)
        tmp = run_dir / "tokens" / "tokens.tmp"
        pq.write_table(table, tmp, compression="zstd")
        tmp.replace(run_dir / "tokens" / "tokens.parquet")
    return table
