"""Manual audit sheets (for the user and project partners) and their scoring.

Nothing here makes a linguistic judgment: the sheets are PRE-FILLED WITH DICTA'S OUTPUT ONLY and
every judgment column is left blank. ``score`` counts only rows a human has filled in and reports
"not yet annotated" otherwise — automatic results are never presented as human-validated.

Selection (deterministic): per corpus, 30 units from the pilot sample — 25 from its *random* part
and 5 from its *targeted* part — restricted to units of at most ``MAX_WORDS`` Dicta words so that a
person can check them (this restriction is stated in the report as a limitation).
"""

from __future__ import annotations

import csv
import hashlib
import math
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq

from hebloc.paths import ANNOTATION_DIR, CORPORA
from hebloc.pilot import sample as S
from hebloc.pilot.runs import run_dir, unit_rows

UNITS_SHEET = ANNOTATION_DIR / "pilot_audit.csv"
WORDS_SHEET = ANNOTATION_DIR / "pilot_audit_words.csv"
PER_CORPUS = (25, 5)   # random, targeted
MAX_WORDS = 60
SEED = "m3-audit-2026"
UNIT_JUDGMENTS = ["segmentation_ok", "normalization_ok", "main_predicate_ok", "n_lemma_errors", "n_pos_errors",
                  "n_feature_errors", "n_prefix_seg_errors", "n_head_errors", "n_deprel_errors", "annotator", "notes"]
WORD_JUDGMENTS = ["seg_ok", "lemma_ok", "pos_ok", "feats_ok", "head_ok", "deprel_ok", "comment"]


def _h(s: str) -> str:
    return hashlib.md5((s + SEED).encode()).hexdigest()


def build(rid: str = "base__default") -> dict:
    toks = defaultdict(list)
    for t in pq.read_table(run_dir(rid) / "tokens" / "tokens.parquet").to_pylist():
        toks[t["sent_id"]].append(t)
    sample = S.load()
    chosen = []
    for c in CORPORA:
        rows = [r for r in sample if r["corpus_id"] == c and 0 < len(toks.get(r["sent_id"], [])) <= MAX_WORDS]
        rnd = sorted([r for r in rows if r["selection"] == "random"], key=lambda r: _h(r["sent_id"]))[:PER_CORPUS[0]]
        tgt = sorted([r for r in rows if r["selection"] != "random"], key=lambda r: _h(r["sent_id"]))[:PER_CORPUS[1]]
        chosen += rnd + tgt
    texts = {s: (raw, norm) for s, raw, norm in unit_rows([r["sent_id"] for r in chosen], "sent_id, text_raw, text_norm")}
    unit_out, word_out = [], []
    for i, r in enumerate(chosen, 1):
        aid = f"A{i:03d}"
        ts = sorted(toks[r["sent_id"]], key=lambda t: t["sent_word_idx"])
        forms = {t["sent_word_idx"]: t["form"] for t in ts}
        lines = []
        for t in ts:
            head = "ROOT" if t["head_sent"] == -1 else f"{t['head_sent'] + 1}:{forms.get(t['head_sent'], '?')}"
            seg = f"{t['prefix']}+{t['host']}" if t["prefix"] else t["host"]
            lines.append(f"{t['sent_word_idx'] + 1} {seg} [{t['lemma']}] {t['upos']} {t['feats'] or ''} → {head} {t['deprel']}".strip())
            word_out.append({"audit_id": aid, "corpus_id": r["corpus_id"], "sent_id": r["sent_id"],
                             "word_no": t["sent_word_idx"] + 1, "surface": t["surface"], "segmentation": seg,
                             "lemma": t["lemma"], "upos": t["upos"], "feats": t["feats"] or "",
                             "suffix": t["suffix"] or "", "head_no": 0 if t["head_sent"] == -1 else t["head_sent"] + 1,
                             "head_word": "ROOT" if t["head_sent"] == -1 else forms.get(t["head_sent"], "?"),
                             "deprel": t["deprel"], **{k: "" for k in WORD_JUDGMENTS}})
        unit_out.append({"audit_id": aid, "corpus_id": r["corpus_id"], "sent_id": r["sent_id"], "ref": r["ref"],
                         "selection": r["selection"], "n_words": len(ts), "n_pieces": ts[0]["n_pieces"],
                         "text_raw": texts[r["sent_id"]][0], "text_norm": texts[r["sent_id"]][1],
                         "dicta_analysis": "\n".join(lines), **{k: "" for k in UNIT_JUDGMENTS}})
    for path, rows in ((UNITS_SHEET, unit_out), (WORDS_SHEET, word_out)):
        if path.exists() and _has_judgments(path):
            raise RuntimeError(f"{path} already contains human judgments; refusing to overwrite")
        with path.open("w", encoding="utf-8-sig", newline="") as fh:  # BOM: Excel shows Hebrew correctly
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    return {"units": len(unit_out), "words": len(word_out), "run": rid,
            "per_corpus": {c: sum(1 for r in unit_out if r["corpus_id"] == c) for c in CORPORA}}


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _has_judgments(path: Path) -> bool:
    cols = UNIT_JUDGMENTS if path == UNITS_SHEET else WORD_JUDGMENTS
    return any(any((r.get(k) or "").strip() for k in cols if k not in ("annotator",)) for r in _read(path))


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(c - h, 4), round(c + h, 4)


def score() -> dict:
    """Accuracy per corpus and layer from the WORD sheet (only human-filled cells count)."""
    out: dict = {}
    if not WORDS_SHEET.exists():
        return {"status": "no sheet"}
    rows = _read(WORDS_SHEET)
    yes, no = {"y", "yes", "1", "true", "כן", "v", "✓"}, {"n", "no", "0", "false", "לא", "x", "✗"}
    for c in CORPORA:
        rs = [r for r in rows if r["corpus_id"] == c]
        res = {}
        for k in ("seg_ok", "lemma_ok", "pos_ok", "feats_ok", "head_ok", "deprel_ok"):
            vals = [r[k].strip().lower() for r in rs if r[k].strip()]
            good = sum(v in yes for v in vals)
            bad = sum(v in no for v in vals)
            res[k] = {"judged": good + bad, "accuracy": round(good / (good + bad), 4) if good + bad else None,
                      "ci95": _wilson(good, good + bad), "unrecognized": len(vals) - good - bad}
        out[c] = res
    judged = sum(v["judged"] for c in out.values() for v in c.values())
    return {"status": "not yet annotated" if judged == 0 else "partially or fully annotated", "per_corpus": out}
