"""Derive the ``tokens`` table (one row per Dicta word) from a run's raw output — never from the model.

PROPOSED schema (M3; to be confirmed at the M3 gate). Character offsets are in the PARSED unit
text (``inputs.text``; for default runs this is ``units.text_norm``, checked by
``hebloc.parse.checks``), so every token maps back to the unit and from there to the source file.

Storage (M4): one ``tokens/shard-NNNNN.parquet`` per committed run shard, plus
``tokens/_shards/shard-NNNNN.json`` recording the sha256 of the three source files it was derived
from and ``tokens_version``. ``derive`` is incremental: a shard is re-derived only if its sources
or the tokens version changed. All pieces of a unit are in the same shard, so per-shard derivation
is exact. Memory is bounded by one shard.
"""

from __future__ import annotations

import bisect
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hebloc.store.io import atomic_write_json, atomic_write_parquet, file_sha256, read_json

TOKENS_VERSION = "1"
SOURCE_PARTS = ("inputs", "pieces", "dicta_raw")
FEATS = ("Gender", "Number", "Person", "Tense")
TOKENS_SCHEMA = pa.schema([
    ("sent_id", pa.string()),
    ("piece_idx", pa.int16()),
    ("n_pieces", pa.int16()),          # 1 → the unit has one complete tree
    ("word_idx", pa.int32()),          # 0-based position in the piece
    ("sent_word_idx", pa.int32()),     # 0-based position in the unit (across pieces); null if an
                                       # earlier piece of the unit failed (offset unknown)
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
    ("head_sent", pa.int32()),         # head as sent_word_idx; -1 = root; null if offset unknown
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


def _ws_starts(text: str) -> list[int]:
    starts, i, n = [], 0, len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i < n:
            starts.append(i)
        while i < n and not text[i].isspace():
            i += 1
    return starts


def derive_rows(text: str, piece: dict, raw: dict | str, status: str, word_offset: int | None) -> list[dict]:
    """Rows for one piece. ``word_offset`` = words in the unit's earlier pieces (None if unknown)."""
    from hebloc.parse.checks import tree_problems

    out = json.loads(raw) if isinstance(raw, str) else raw
    valid = not tree_problems(out)
    base = piece["norm_char_start"]
    ws_starts = _ws_starts(text)
    rows = []
    for wi, t in enumerate(out["tokens"]):
        s, e = t["offsets"]["start"] + base, t["offsets"]["end"] + base
        seg = t.get("seg") or [t["token"]]
        m = t.get("morph") or {}
        f = m.get("feats") or {}
        syn = t.get("syntax") or {}
        head = syn.get("dep_head_idx")
        if head in (None, -1):
            head_sent = None if head is None else -1
        else:
            head_sent = None if word_offset is None else word_offset + head
        rows.append({
            "sent_id": piece["sent_id"], "piece_idx": piece["piece_idx"], "n_pieces": piece["n_pieces"],
            "word_idx": wi, "sent_word_idx": None if word_offset is None else word_offset + wi,
            "char_start": s, "char_end": e,
            "ws_idx": bisect.bisect_right(ws_starts, s) - 1, "form": t["token"], "surface": text[s:e],
            "prefix": seg[0] if len(seg) > 1 else None, "host": seg[-1],
            "lemma": t.get("lex"), "lemma_blank": t.get("lex") == "[BLANK]",
            "upos": m.get("pos"), "feats": _feats(f),
            "gender": f.get("Gender"), "number": f.get("Number"), "person": f.get("Person"), "tense": f.get("Tense"),
            "prefix_upos": list(m.get("prefixes") or []),
            "suffix": m.get("suffix") or None, "suffix_feats": _feats(m.get("suffix_feats")),
            "head": head, "head_sent": head_sent,
            "deprel": syn.get("dep_func"), "ner": t.get("ner"), "status": status, "piece_tree_valid": valid,
            "tokens_version": TOKENS_VERSION,
        })
    return rows


def derive_table(inputs: pa.Table, pieces: pa.Table, raws: pa.Table) -> pa.Table:
    """Pure: tokens for the given run rows (one shard or more). Error pieces produce no tokens and
    make the unit-level index (``sent_word_idx``/``head_sent``) of its LATER pieces unknown (null)."""
    texts = dict(zip(inputs.column("sent_id").to_pylist(), inputs.column("text").to_pylist()))
    by_key = {(p["sent_id"], p["piece_idx"]): p for p in pieces.to_pylist()}
    rows, offset, cur = [], 0, None
    for r in sorted(raws.to_pylist(), key=lambda r: (r["sent_id"], r["piece_idx"])):
        if r["sent_id"] != cur:
            cur, offset = r["sent_id"], 0
        if r["status"] == "error":
            offset = None
            continue
        new = derive_rows(texts[r["sent_id"]], by_key[(r["sent_id"], r["piece_idx"])], r["raw_json"], r["status"], offset)
        if offset is not None:
            offset += len(new)
        rows += new
    return pa.Table.from_pylist(rows, schema=TOKENS_SCHEMA)


# ---------------------------------------------------------------- per-shard storage

def _committed_shards(run_dir: Path) -> list[str]:
    return sorted(p.stem for p in (run_dir / "_shards").glob("shard-*.json"))


def _tokens_path(run_dir: Path, shard: str) -> Path:
    return run_dir / "tokens" / f"{shard}.parquet"


def _tokens_manifest_path(run_dir: Path, shard: str) -> Path:
    return run_dir / "tokens" / "_shards" / f"{shard}.json"


def _sources(run_dir: Path, shard: str) -> dict[str, str]:
    return {part: file_sha256(run_dir / part / f"{shard}.parquet") for part in SOURCE_PARTS}


def derive_shard(run_dir: Path, shard: str) -> pa.Table:
    """Tokens of one shard, in memory (nothing written)."""
    return derive_table(*(pq.read_table(run_dir / part / f"{shard}.parquet") for part in SOURCE_PARTS))


def shard_up_to_date(run_dir: Path, shard: str, verify_hashes: bool = True) -> bool:
    mp, tp = _tokens_manifest_path(run_dir, shard), _tokens_path(run_dir, shard)
    if not (mp.exists() and tp.exists()):
        return False
    m = read_json(mp)
    if m.get("tokens_version") != TOKENS_VERSION:
        return False
    if not verify_hashes:
        return True
    return m.get("sources") == _sources(run_dir, shard) and m.get("sha256") == file_sha256(tp)


def tokens_status(run_dir: Path, verify_hashes: bool = False) -> dict:
    shards = _committed_shards(run_dir)
    up = [s for s in shards if shard_up_to_date(run_dir, s, verify_hashes)]
    present = {p.stem for p in (run_dir / "tokens").glob("shard-*.parquet")}
    return {"shards": len(shards), "up_to_date": len(up), "stale_or_missing": len(shards) - len(up),
            "orphans": sorted(present - set(shards)),
            "legacy_single_file": (run_dir / "tokens" / "tokens.parquet").exists()}


def derive(run_dir: Path, *, force: bool = False, progress: bool = False) -> dict:
    """Incrementally (re)derive ``tokens`` for every committed shard of the run.

    Tokens files of shards that are not committed (orphans) are removed: they cannot be trusted and
    would otherwise be read as data. Returns a summary."""
    run_dir = Path(run_dir)
    shards = _committed_shards(run_dir)
    done = skipped = rows = 0
    it = shards
    if progress and len(shards) > 20:
        from tqdm import tqdm
        it = tqdm(shards, desc=f"tokens:{run_dir.name}", unit="shard")
    incomplete = []
    for s in it:
        if not all((run_dir / part / f"{s}.parquet").exists() for part in SOURCE_PARTS):
            incomplete.append(s)          # reported by hebloc.parse.checks as shard_part_missing
            continue
        if not force and shard_up_to_date(run_dir, s):
            skipped += 1
            rows += pq.ParquetFile(_tokens_path(run_dir, s)).metadata.num_rows
            continue
        sources = _sources(run_dir, s)
        table = derive_shard(run_dir, s)
        out = atomic_write_parquet(table, _tokens_path(run_dir, s))
        atomic_write_json({"shard": s, "tokens_version": TOKENS_VERSION, "sources": sources,
                           "rows": table.num_rows, "sha256": file_sha256(out)}, _tokens_manifest_path(run_dir, s))
        done += 1
        rows += table.num_rows
    orphans = tokens_status(run_dir)["orphans"]
    for s in orphans:
        _tokens_path(run_dir, s).unlink(missing_ok=True)
        _tokens_manifest_path(run_dir, s).unlink(missing_ok=True)
    return {"shards": len(shards), "derived": done, "skipped_up_to_date": skipped, "rows": rows,
            "orphans_removed": orphans, "incomplete_shards": incomplete}


def read_tokens(run_dir: Path) -> pa.Table:
    """All tokens of a run (committed shards, in shard order). For big runs use DuckDB/hebloc.data."""
    files = [_tokens_path(run_dir, s) for s in _committed_shards(run_dir)]
    return pa.concat_tables([pq.read_table(f) for f in files]) if files else TOKENS_SCHEMA.empty_table()


def _sort_key(t: pa.Table) -> pa.Table:
    return t.sort_by([("sent_id", "ascending"), ("piece_idx", "ascending"), ("word_idx", "ascending")])


def migrate_legacy(run_dir: Path) -> dict:
    """M3 runs stored one ``tokens/tokens.parquet``. Re-derive per shard, check the result has the
    same rows (order-independent), and only then remove the legacy file. Raises if they differ."""
    run_dir = Path(run_dir)
    legacy = run_dir / "tokens" / "tokens.parquet"
    if not legacy.exists():
        return {"legacy": False}
    summary = derive(run_dir)
    old, new = _sort_key(pq.read_table(legacy)), _sort_key(read_tokens(run_dir))
    if not old.equals(new):
        raise RuntimeError(f"{run_dir}: per-shard tokens differ from the legacy tokens.parquet "
                           f"({old.num_rows} vs {new.num_rows} rows); legacy file kept")
    legacy.unlink()
    return {"legacy": True, "rows": old.num_rows, "identical": True, **summary}
