"""Parser accuracy: Dicta vs BHSA on ALL of Mikra (docs/m6_design.md §2.3; final now, D-045).

Reuses the M3 comparison unchanged (``hebloc.pilot.experiments.bhsa_eval`` / ``hebloc.pilot.bhsa``:
written-word alignment, convention-aware POS mapping, Qere reading, verses aligned < 80% excluded
and listed). BHSA is an expert annotation with other conventions, so the figures are
**convention-aware agreement, not gold accuracy**; it has no dependency trees, so syntax is not
measured here.

Cross-check: restricted to the pilot's 500 random verses, the full run must reproduce the pilot's
figures (pilot report §8.1) exactly: same model, normalization and MST fix, and ``topk`` output is
byte-identical to the original code (D-029).

Outputs (``results/stats/accuracy/``, git): ``mikra_vs_bhsa.json`` (everything, with provenance),
``layers.csv`` (agreement + Wilson 95% intervals), ``pos_confusion.csv``, ``tense_confusion.csv``,
``excluded_verses.csv`` (references only, no corpus text).
"""

from __future__ import annotations

import csv
import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from hebloc.paths import EXTERNAL_DIR, RESULTS_DIR

ACCURACY_DIR = RESULTS_DIR / "stats" / "accuracy"
PILOT_REFERENCE = ("base__mikra_h500_default", "base_vs_tiny_bhsa", "base")   # run, hypotheses.json keys
LAYERS = (("hebrew", "pos", "POS, strict mapping"),
          ("hebrew", "pos_lenient", "POS, convention-tolerant"),
          ("hebrew", "prefix_segmentation", "Prefix segmentation"),
          ("hebrew", "lemma_noun", "Noun lemma"),
          ("hebrew", "lemma_verb_qal", "Verb lemma, qal"),
          ("hebrew", "lemma_verb_other_stem", "Verb lemma, other stems"),
          ("hebrew", "verb_person", "Verb person"),
          ("hebrew", "verb_number", "Verb number"),
          ("hebrew", "verb_gender", "Verb gender"),
          ("aramaic", "pos", "Aramaic words: POS, strict"))


def wilson(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return (math.nan, math.nan)
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 4), round(c + h, 4))


def _public(d: dict) -> dict:
    return json.loads(json.dumps({k: v for k, v in d.items() if not k.startswith("_")}, ensure_ascii=False))


def pilot_reproduction(run_ref: str) -> dict:
    """Full-run analysis restricted to the pilot's 500 verses == the stored pilot result?"""
    from hebloc.parse.run import read_run
    from hebloc.pilot import PILOT_DIR
    from hebloc.pilot.experiments import bhsa_eval
    from hebloc.pilot.runs import run_dir

    rid, k1, k2 = PILOT_REFERENCE
    ref_file = PILOT_DIR / "results" / "hypotheses.json"
    if not ref_file.exists() or not run_dir(rid).exists():
        return {"checked": False, "reason": "pilot reference not on this computer"}
    reference = json.loads(ref_file.read_text(encoding="utf-8"))[k1][k2]
    ids = set(read_run(run_dir(rid), "inputs").column("sent_id").to_pylist())
    mine = _public(bhsa_eval(run_ref, "qere", restrict=ids))
    strip = lambda d: {k: v for k, v in d.items() if k != "run"}  # noqa: E731
    diffs = sorted(k for k in set(strip(reference)) | set(strip(mine)) if strip(reference).get(k) != strip(mine).get(k))
    return {"checked": True, "pilot_run": rid, "verses": len(ids), "identical": not diffs, "differing_keys": diffs}


def mikra_vs_bhsa(run_ref: str = "mikra/base-topk-v1__mikra", out_dir: Path = ACCURACY_DIR) -> dict:
    from hebloc.inventory import _git_commit
    from hebloc.parse.checks import run_fingerprint
    from hebloc.pilot.experiments import bhsa_eval
    from hebloc.store.io import atomic_write_json, atomic_write_text, read_json
    from hebloc.store.runs import resolve

    run = resolve(run_ref)
    full = bhsa_eval(run_ref, "qere")
    summary = _public(full)
    excluded = [{"sent_id": e["sent_id"], "ref": e["ref"], "align_ratio": e["align_ratio"]}
                for e in full["_excluded"]]
    layers = []
    for group, key, label in LAYERS:
        r = summary[group][key]
        lo, hi = wilson(r["agree"], r["n"]) if r["agree"] is not None else (None, None)
        layers.append({"layer": label, "language": group, "key": key, "n": r["n"], "agreement": r["agree"],
                       "ci95_low": lo, "ci95_high": hi})
    result = {
        "what": "Dicta (base, topk, MST fix) vs BHSA on all Mikra verses: convention-aware agreement, not gold accuracy",
        "run": run.ref, "run_fingerprint": run_fingerprint(run.path), "code_commit": _git_commit(),
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bhsa_source": read_json(EXTERNAL_DIR / "bhsa" / "SOURCE.json") | {"files": "see data/external/bhsa/SOURCE.json"},
        "reading": "qere", "min_alignment": 0.8, "layers": layers, "summary": summary,
        "excluded_verses": excluded, "pilot_reproduction": pilot_reproduction(run_ref),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(result, out_dir / "mikra_vs_bhsa.json")
    atomic_write_text(_csv(layers), out_dir / "layers.csv")
    atomic_write_text(_csv([{"bhsa_sp_to_dicta_upos": k, "n": n} for k, n in summary["pos_confusion"]]),
                      out_dir / "pos_confusion.csv")
    atomic_write_text(_csv([{"bhsa_vt_to_dicta_tense": k, "n": n} for k, n in summary["tense_confusion"]]),
                      out_dir / "tense_confusion.csv")
    atomic_write_text(_csv(excluded or [{"sent_id": "", "ref": "", "align_ratio": ""}]), out_dir / "excluded_verses.csv")
    return result


def _csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()
