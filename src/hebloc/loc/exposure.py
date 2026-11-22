"""The exposure register of the frozen gold samples (D-059 P8.1; test independence).

An item is EXPOSED when its instance was seen outside annotation before its label exists:
- ``TOKEN``    the item's own token was read (a review, a screen) or is one of the paper's examples, whose frame
               the paper states;
- ``SENTENCE`` the same sentence (Mikra: verse) was read for another token;
- ``META``     only its sample metadata (key, lemma, split) was looked at, and that look prompted a rule (a manual
               entry in ``annotation/gold/EXPOSURE_MANUAL.csv``).
Exposed validation and test items never inform a choice; the primary validation choice and test scores use the
clean sets, full-set figures are secondary (P8.2). The register holds ids only (no corpus text, D-042) and is
regenerated at every STOP (``hebloc loc gold exposure``); any new reading outside annotation is added to the manual
register before it is used.

Sources read automatically: the R1 quality-review readings in ``data/loc/review/quality/`` (sense screens,
suspect keys, the form/combined/unidentified audits, the Modern homograph readings), the lexicon's paper
references and (D-065) the Phase C I-3 sense-screen draws (``data/loc/draws/screen/``: their SILVER is read by the
developer at C1). The items covered are the frozen samples and every registered supplement
(``gold.FROZEN_SUPPLEMENTS``). Texts are compared by program; only ids are written or printed.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hebloc.loc.gold import FROZEN_SAMPLES, FROZEN_SUPPLEMENTS, GOLD_DIR
from hebloc.loc.lexicon import Lexicon
from hebloc.loc.manifest import write_csv
from hebloc.loc.source import Source, connect
from hebloc.paths import DATA_DIR, ROOT

QUALITY_DIR = DATA_DIR / "loc" / "review" / "quality"
DRAWS_DIR = DATA_DIR / "loc" / "draws"
EXPOSURE_PATH = ROOT / "annotation" / "gold" / "EXPOSURE.csv"
MANUAL_PATH = ROOT / "annotation" / "gold" / "EXPOSURE_MANUAL.csv"
LEVELS = ("TOKEN", "SENTENCE", "META")
COLUMNS = ("item_id", "sample_id", "corpus", "split", "agreement", "level", "source", "note")
REF_RE = re.compile(r"^(?:I{1,2}\s+)?[A-Z][A-Za-z ]+ \d+:\d+$")


def _bracket(ctx: str | None) -> str | None:
    m = re.search(r"\[([^\]]+)\]", ctx or "")
    return m.group(1) if m else None


def _items(corpus: str, source: Source, gold_dir: Path) -> list[dict]:
    rows = []
    for sid in [FROZEN_SAMPLES[corpus]["sample_id"]] + sorted(FROZEN_SUPPLEMENTS.get(corpus, {})):
        f = Path(gold_dir) / corpus / sid / "sample.parquet"
        if f.exists():
            rows += pq.read_table(f, columns=["sample_id", "item_id", "sent_id", "piece_idx", "word_idx", "verb_key", "split",
                                              "agreement"]).to_pylist()
    if not rows:
        return []
    con = connect()
    con.register("want", pa.table({"sent_id": sorted({r["sent_id"] for r in rows})}))
    unit = {r[0]: (r[1], r[2]) for r in con.sql(f"SELECT sent_id, ref, text_norm FROM {source.units_sql(corpus, ('sent_id', 'ref', 'text_norm'))} "
                                                "SEMI JOIN want USING (sent_id)").fetchall()}
    form = {}
    for run in source.runs(corpus):
        for r in con.sql(f"SELECT sent_id, piece_idx, word_idx, form, host FROM {source.tokens_sql(run, ('sent_id', 'piece_idx', 'word_idx', 'form', 'host'))} "
                         "SEMI JOIN want USING (sent_id)").fetchall():
            form[(r[0], r[1], r[2])] = (r[3], r[4])
    for r in rows:
        r["corpus"] = corpus
        r["ref"], r["text"] = unit.get(r["sent_id"], (None, ""))
        r["form"], r["host"] = form.get((r["sent_id"], r["piece_idx"], r["word_idx"]), (None, None))
    return rows


def _same_token(it: dict, word: str | None, key: str | None) -> bool:
    if word is None:
        return False
    f, h = it["form"], it["host"]
    tok = word == f or word == h or bool(f and f.endswith(word)) or bool(h and word.endswith(h))
    same_key = key is None or any(m in key.split("|") for m in it["verb_key"].split("|"))
    return tok and same_key


def compute(lex: Lexicon, source: Source, *, gold_dir: Path = GOLD_DIR, quality_dir: Path = QUALITY_DIR,
            manual_path: Path = MANUAL_PATH, draws_dir: Path = DRAWS_DIR) -> list[dict]:
    """Every (item, source) exposure of the frozen samples and registered supplements, deterministic order."""
    items = {c: _items(c, source, gold_dir) for c in FROZEN_SAMPLES}
    by_ref, by_sent = defaultdict(list), defaultdict(list)
    for c, rows in items.items():
        for it in rows:
            by_sent[it["sent_id"]].append(it)
            if it["ref"]:
                by_ref[(c, it["ref"])].append(it)
    hits: dict[tuple, dict] = {}

    def hit(it: dict, level: str, src: str, note: str = "") -> None:
        k = (it["corpus"], it["item_id"], src)
        old = hits.get(k)
        if old is None or LEVELS.index(level) < LEVELS.index(old["level"]):
            hits[k] = {"item_id": it["item_id"], "sample_id": it["sample_id"], "corpus": it["corpus"], "split": it["split"],
                       "agreement": bool(it["agreement"]), "level": level, "source": src, "note": note}

    def check(cands: list[dict], word: str | None, key: str | None, src: str) -> None:
        for it in cands:
            hit(it, "TOKEN" if _same_token(it, word, key) else "SENTENCE", src)

    q = Path(quality_dir)
    for c in ("mikra", "modern"):
        f = q / f"sense_screen_{c}.csv"
        if f.exists():
            with open(f, encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    cands = by_ref.get((c, row["ref"]), []) if c == "mikra" else by_sent.get(row["ref"], [])
                    check(cands, _bracket(row.get("context")), row.get("key"), f"R1 sense screen ({c})")
    for fn, label in (("mikra_B_suspect_keys.txt", "R1 suspect-key reading (mikra)"),
                      ("mikra_form_combined_blocked_audit.txt", "R1 form/combined/unidentified audit (mikra)")):
        f = q / fn
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3 and REF_RE.match(parts[0]):
                km = re.search(r"key=(\S+)", parts[1])
                check(by_ref.get(("mikra", parts[0]), []), _bracket(parts[-1]), km.group(1) if km else None, label)
    f = q / "modern_homographs.txt"
    if f.exists():
        modern = [it for it in items.get("modern", [])]
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.startswith("===") or "|" not in line:
                continue
            ctx = line.split("|", 1)[1].strip()
            plain = re.sub(r"[\[\]]", "", ctx)
            chunks = [x for x in re.split(r"\s{2,}", plain) if len(x) >= 20] or [plain]
            probe = max(chunks, key=len)[:40]
            for it in modern:
                if probe and probe in it["text"]:
                    check([it], _bracket(ctx), None, "R1 homograph reading (modern)")
    for f in sorted(Path(draws_dir).glob("screen/*/*/ids.csv")):
        c = f.parent.parent.name
        with open(f, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                sid, _, rest = row["instance_key"].partition("|")
                for it in by_sent.get(sid, []):
                    if it["corpus"] != c:
                        continue
                    same = f"{it['sent_id']}|{it['piece_idx']}|{it['word_idx']}" == row["instance_key"]
                    hit(it, "TOKEN" if same else "SENTENCE", f"I-3 sense screen ({f.parent.name})")
    for e in lex.entries:
        for r in e.paper_refs:
            ref = r.get("he")
            for it in by_ref.get(("mikra", ref), []):
                lvl = "TOKEN" if e.id in it["verb_key"].split("|") else "SENTENCE"
                hit(it, lvl, "paper example (the paper states its frame)" if lvl == "TOKEN" else "paper example verse",
                    f"{e.id} {r.get('where', '')}".strip())
    if Path(manual_path).exists():
        idx = {(it["corpus"], it["item_id"]): it for rows in items.values() for it in rows}
        with open(manual_path, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                it = idx.get((row["corpus"], row["item_id"]))
                if it is not None and row["level"] in LEVELS:
                    hit(it, row["level"], row["source"], row.get("note", ""))
    return sorted(hits.values(), key=lambda r: (r["corpus"], r["item_id"], r["source"]))


def write(rows: list[dict], path: Path = EXPOSURE_PATH) -> dict:
    t = pa.Table.from_pylist([{c: r[c] for c in COLUMNS} for r in rows]) if rows else pa.table({c: [] for c in COLUMNS})
    write_csv(t, path)
    summary: dict = defaultdict(lambda: defaultdict(set))
    for r in rows:
        summary[r["corpus"]][r["split"]].add(r["item_id"])
    return {c: {sp: len(ids) for sp, ids in d.items()} for c, d in summary.items()}


def load(path: Path = EXPOSURE_PATH) -> dict[str, set[str]]:
    """corpus -> exposed item ids (any level)."""
    out: dict[str, set[str]] = defaultdict(set)
    if Path(path).exists():
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                out[r["corpus"]].add(r["item_id"])
    return dict(out)
