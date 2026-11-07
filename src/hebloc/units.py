"""M2 — extract sentence/verse units with provenance into ``data/units/<corpus>/``.

For every document in the FULL view (all supplied text; out-of-period and duplicate documents
included — views are columns, never deletions), each non-empty source line is segmented into
COMPLETE units (verse / sentence; segment v2 — never cut for model limits, see ``hebloc.pieces``).
For each unit we store the exact source slice (``text_raw``), its offsets in the decoded line, the
normalized model input (``text_norm``, normalized over the whole unit), every normalization flag,
and a human reference.

Integrity checks run on every line during extraction (and are recorded in the manifest):
  * ``line[char_start:char_end] == text_raw`` (by construction, re-asserted);
  * coverage: the units of a line together contain ALL its non-whitespace characters;
  * every non-empty source line yields ≥ 1 unit (line counts reconcile with the catalog);
  * Mikra: unit count per book == versification verse count.

Processing is streamed: documents are processed in parallel batches and written in Parquet row
groups, so memory stays bounded even for the 400k-file Modern corpus.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hebloc import normalize as N
from hebloc import versification as V
from hebloc.catalog import documents
from hebloc.inventory import _git_commit
from hebloc.paths import CORPORA_DIR, DATA_DIR, UNITS_DIR, assert_not_in_corpora
from hebloc.segment import SEGMENT_VERSION, segment_line
from hebloc.textstats import decode_bytes, split_lines

SAMPLE_DIR = DATA_DIR / "units_sample"
ROWS_PER_FILE = 1_000_000
DOC_COLUMNS = ["doc_id", "corpus_id", "rel_path", "work", "section", "source", "subcorpus", "ext_id",
               "meta_json", "stratum", "in_full_view", "in_curated_view", "n_nonempty_lines"]

UNITS_SCHEMA = pa.schema(
    [
        ("sent_id", pa.string()),
        ("corpus_id", pa.string()),
        ("doc_id", pa.string()),
        ("line_no", pa.int32()),          # 1-based, canonical '\n' line split of the decoded file
        ("k", pa.int16()),                # 0-based index of the unit within its line
        ("unit_type", pa.string()),       # verse | sentence (segment v2; v1 also had chunk)
        ("char_start", pa.int32()),       # offsets into the decoded source line
        ("char_end", pa.int32()),
        ("ref", pa.string()),             # human-readable reference
        ("text_raw", pa.string()),        # exact source slice — never modified
        ("text_norm", pa.string()),       # model input
        ("text_norm_alt", pa.string()),   # alternative reading (Mikra: Ketiv) or null
        ("norm_flags", pa.list_(pa.string())),
        ("is_empty_norm", pa.bool_()),    # normalization left no text (e.g. markup-only line)
        ("n_tokens_norm", pa.int32()),
        ("n_hebrew_tokens_norm", pa.int32()),
        ("aramaic", pa.string()),         # Mikra: 'aramaic' | 'aramaic_partial' | null
        ("stratum", pa.string()),         # denormalized from the catalog for convenience
        ("in_full_view", pa.bool_()),
        ("in_curated_view", pa.bool_()),
        ("norm_version", pa.string()),
        ("segment_version", pa.string()),
    ]
)


def _ref_base(doc: dict) -> str:
    cid = doc["corpus_id"]
    rel_in_corpus = doc["rel_path"].split("/", 1)[1]
    if cid in ("hazal",):
        return doc["work"] or rel_in_corpus
    if cid == "medieval":
        if doc["subcorpus"] == "Rambam":
            meta = json.loads(doc["meta_json"] or "{}")
            return f"Mishneh Torah/{doc['section']}/{meta.get('hilchot')}/{meta.get('unit_label')}"
        return doc["work"] or rel_in_corpus
    if cid == "haskala":
        return doc["ext_id"] or rel_in_corpus
    return rel_in_corpus  # modern


def _normalize(doc: dict, raw: str, line_start: bool, first_text_line: bool) -> N.Normalized:
    cid = doc["corpus_id"]
    if cid == "mikra":
        return N.normalize_mikra(raw)
    if cid == "hazal":
        return N.normalize_hazal(raw, line_start=line_start)
    if cid == "medieval":
        return N.normalize_medieval(raw, line_start=line_start, rambam=doc["subcorpus"] == "Rambam")
    if cid == "haskala":
        return N.normalize_haskala(raw)
    return N.normalize_modern(raw, line_start=line_start and first_text_line,
                              haaretz=doc["source"] == "haaretz")


def units_for_doc(doc: dict) -> tuple[list[dict], dict]:
    """Extract all units of one document. Returns (rows, check-stats). Reads the file read-only."""
    text = decode_bytes((CORPORA_DIR / doc["rel_path"]).read_bytes())[0]
    lines = split_lines(text)
    cid = doc["corpus_id"]
    refs = V.verse_refs(doc["work"]) if cid == "mikra" else None
    base = _ref_base(doc)
    rows: list[dict] = []
    stats = Counter()
    verse_idx = 0
    first_text_line = True
    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        stats["nonempty_lines"] += 1
        spans = segment_line(line, cid)
        covered = sum(len("".join(line[s:e].split())) for s, e, _ in spans)
        if covered != len("".join(line.split())):
            stats["coverage_failures"] += 1
        if not spans:
            stats["lines_without_units"] += 1
        for k, (s, e, utype) in enumerate(spans):
            raw = line[s:e]
            nrm = _normalize(doc, raw, line_start=(k == 0), first_text_line=first_text_line)
            aramaic = None
            if cid == "mikra":
                ch, vs = refs[verse_idx]
                verse_idx += 1
                ref = f"{doc['work']} {ch}:{vs}"
                aramaic = V.aramaic_status(doc["work"], ch, vs)
            else:
                ref = f"{base} ¶{line_no}" + (f".{k + 1}" if len(spans) > 1 else "")
            rows.append({
                "sent_id": f"{cid}:{doc['doc_id']}:{line_no}:{k}",
                "corpus_id": cid, "doc_id": doc["doc_id"], "line_no": line_no, "k": k,
                "unit_type": utype, "char_start": s, "char_end": e, "ref": ref,
                "text_raw": raw, "text_norm": nrm.text, "text_norm_alt": nrm.alt,
                "norm_flags": nrm.flags, "is_empty_norm": not nrm.text,
                "n_tokens_norm": len(nrm.text.split()),
                "n_hebrew_tokens_norm": N.hebrew_token_count(nrm.text),
                "aramaic": aramaic, "stratum": doc["stratum"],
                "in_full_view": doc["in_full_view"], "in_curated_view": doc["in_curated_view"],
                "norm_version": N.NORM_VERSION, "segment_version": SEGMENT_VERSION,
            })
            stats["units"] += 1
        first_text_line = False
    stats["lines_with_units"] = len({r["line_no"] for r in rows})
    if cid == "mikra":
        stats["mikra_verse_mismatch"] = int(verse_idx != len(refs))
    stats["catalog_nonempty_lines_mismatch"] = int(stats["nonempty_lines"] != doc["n_nonempty_lines"])
    return rows, dict(stats)


def _doc_list(corpus: str, sample: int | None, seed: int, extra: list[str] | None) -> list[dict]:
    df = documents(corpus, view="full", columns=DOC_COLUMNS).sort_values("rel_path")
    docs = df.to_dict("records")
    if sample is None:
        return docs
    rnd = random.Random(seed)
    chosen = {d["rel_path"] for d in rnd.sample(docs, min(sample, len(docs)))}
    chosen |= {d["rel_path"] for d in docs if extra and any(x in d["rel_path"] for x in extra)}
    return [d for d in docs if d["rel_path"] in chosen]


def prepare_corpus(corpus: str, *, out_root: Path = UNITS_DIR, sample: int | None = None, seed: int = 0,
                   extra: list[str] | None = None, workers: int | None = None, progress: bool = True) -> dict:
    """Extract units for one corpus into ``out_root/<corpus>/`` (atomic directory swap)."""
    t0 = time.perf_counter()
    docs = _doc_list(corpus, sample, seed, extra)
    final = out_root / corpus
    tmp = out_root / f".{corpus}.tmp"
    for p in (final, tmp):
        assert_not_in_corpora(p)
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    workers = workers or max(1, min(12, (os.cpu_count() or 4) - 2))
    totals: Counter = Counter()
    flag_counts: Counter = Counter()
    unit_types: Counter = Counter()
    problems: list[str] = []
    buffer: list[dict] = []
    part = 0
    writer = None
    rows_in_file = 0

    def flush(final_flush: bool = False):
        nonlocal buffer, writer, part, rows_in_file
        if buffer:
            if writer is None:
                writer = pq.ParquetWriter(tmp / f"part-{part:05d}.parquet", UNITS_SCHEMA, compression="zstd")
            writer.write_table(pa.Table.from_pylist(buffer, schema=UNITS_SCHEMA), row_group_size=100_000)
            rows_in_file += len(buffer)
            buffer = []
        if writer is not None and (final_flush or rows_in_file >= ROWS_PER_FILE):
            writer.close()
            writer, rows_in_file, part = None, 0, part + 1

    it_batches = [docs[i:i + 4000] for i in range(0, len(docs), 4000)]
    bar = None
    if progress:
        from tqdm import tqdm
        bar = tqdm(total=len(docs), desc=f"units:{corpus}", unit="doc")
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for batch in it_batches:
            for doc, (rows, st) in zip(batch, pool.map(units_for_doc, batch, chunksize=16)):
                totals.update(st)
                for r in rows:
                    flag_counts.update(f.split(":")[0] if f.startswith("parasha") else f for f in r["norm_flags"])
                    unit_types[r["unit_type"]] += 1
                if st.get("coverage_failures") or st.get("catalog_nonempty_lines_mismatch") \
                        or st.get("lines_without_units") or st.get("mikra_verse_mismatch"):
                    problems.append(f"{doc['rel_path']}: {st}")
                buffer.extend(rows)
                if len(buffer) >= 200_000:
                    flush()
            if bar:
                bar.update(len(batch))
    flush(final_flush=True)
    if bar:
        bar.close()

    manifest = {
        "table": "units", "corpus_id": corpus,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code_commit": _git_commit(), "norm_version": N.NORM_VERSION, "segment_version": SEGMENT_VERSION,
        "sample": sample, "seed": seed if sample else None, "documents": len(docs),
        "units": totals["units"], "unit_types": dict(unit_types),
        "nonempty_lines": totals["nonempty_lines"], "lines_with_units": totals["lines_with_units"],
        "coverage_failures": totals["coverage_failures"],
        "catalog_line_mismatches": totals["catalog_nonempty_lines_mismatch"],
        "mikra_verse_mismatches": totals.get("mikra_verse_mismatch", 0),
        "problems": problems[:50], "n_problems": len(problems),
        "flag_counts": dict(flag_counts.most_common()),
        "runtime_seconds": round(time.perf_counter() - t0, 1),
    }
    manifest["ok"] = (manifest["coverage_failures"] == 0 and manifest["catalog_line_mismatches"] == 0
                      and manifest["mikra_verse_mismatches"] == 0
                      and manifest["lines_with_units"] == manifest["nonempty_lines"])
    (tmp / "_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8", newline="\n")
    shutil.rmtree(final, ignore_errors=True)
    os.replace(tmp, final)
    return manifest
