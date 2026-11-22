"""Phase C identification CANDIDATES (D-059 addendum, pre-registered rules I-1 … I-5; code D-065, stage C0).

A candidate is a FOLDER ``data/loc/ident/<candidate id>/`` holding its own ``locative_verbs.yaml`` and
``locative_verb_forms.yaml`` (the same file names as the config, so ``Lexicon.sha256`` is comparable), ``changes.csv``
(what differs from R1, per entry x host, with token counts; lemmas and forms only, no corpus text) and
``manifest.json`` (the rules, inputs and hashes). It never touches ``config/``: R1 stays the default everywhere, and a
candidate is used only by naming its folder (``--ident <folder>`` on ``loc extract | resolve | classify | stats |
gold supplement``).

The candidates (the rules are fixed; they are DECIDED on dev silver at C1, never here):
- I-1 ``lexicon-v2`` draft: the P5 variant evidence (frozen job ``variant``) applied where both passes agree;
  ``undecided`` rows are not applied. Built at C1 (C0 only tests the code on synthetic evidence).
- I-2 lemma-only partners ``~<root>.<T>`` (hebloc.loc.lexicon ``lemma_partners``; hebloc.loc.identify).
- I-3 forms-v3: an established self-lemma is foreign (``established_self_foreign``); decided per key by the sense
  screen (hebloc.loc.draws).
- I-4 V2 generated forms for clean keys (``generated="clean_keys"``).
- I-5 is report-only (the ``function_lemma`` flag, hebloc.loc.report): no candidate folder.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import yaml

from hebloc.loc import lexicon as L
from hebloc.loc.manifest import write_csv, write_manifest
from hebloc.paths import DATA_DIR
from hebloc.store.io import atomic_write_text, file_sha256

IDENT_VERSION = "ident-c0"
IDENT_DIR = DATA_DIR / "loc" / "ident"
#: the forms options of each candidate (I-1 is a lexicon file, not a forms option)
OPTIONS = {"I-2": {"lemma_partners": True}, "I-3": {"established_self_foreign": True}, "I-4": {"generated": "clean_keys"}}
CANDIDATES = ("I-1", "I-2", "I-3", "I-4")
LEXICON_NAME = L.LEXICON_PATH.name
FORMS_NAME = L.FORMS_PATH.name
V2_OTHER = "another verb or meaning (P5 SILVER evidence, D-061)"


class IdentError(Exception):
    pass


def parse_candidates(text: str) -> list[str]:
    cands = sorted({c.strip().upper() for c in (text or "").split(",") if c.strip()})
    bad = [c for c in cands if c not in CANDIDATES]
    if not cands or bad:
        raise IdentError(f"--candidate must list some of {', '.join(CANDIDATES)} (I-5 is report-only); got {text!r}")
    return cands


def candidate_id(cands: list[str], lexicon_sha: str, inventory_sha: str) -> str:
    h = hashlib.sha256(f"{IDENT_VERSION}|{'+'.join(cands)}|{lexicon_sha}|{inventory_sha}".encode()).hexdigest()[:10]
    return f"{'+'.join(cands)}-{h}"


def inventory_fingerprint(inventory) -> str:
    rows = sorted(zip(inventory["corpus"].to_pylist(), inventory["lemma"].to_pylist(), inventory["host"].to_pylist(),
                      inventory["n"].to_pylist()), key=lambda r: tuple("" if x is None else str(x) for x in r))
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()


# ============================================================================================ I-1 (lexicon-v2 draft)
def lexicon_v2_draft(lexicon_text: str, evidence_rows: list[dict]) -> tuple[str, dict]:
    """Apply the P5 variant evidence to the lexicon YAML (the I-1 candidate). Only rows whose two passes agree
    (``agree`` true, ``suggestion`` = ``<decision>:<entry>``) are applied; ``undecided`` rows are not. Returns the new
    YAML text and a summary. The draft is validated by the caller (``lexicon.problems``); a problem is a refusal,
    never a silent fix (adding a flag is Ori's lexicon decision, G4)."""
    raw = yaml.safe_load(lexicon_text)
    by_id = {e["id"]: e for e in raw.get("entries") or []}
    applied = defaultdict(list)
    skipped = defaultdict(int)
    for r in evidence_rows:
        agree = str(r.get("agree", "")).strip().lower() in ("true", "1", "yes")
        sug = (r.get("suggestion") or "").strip()
        lemma = (r.get("lemma") or "").strip()
        if not agree or not sug or sug == "undecided" or ":" not in sug:
            skipped["undecided"] += 1
            continue
        decision, entry = sug.split(":", 1)
        if decision == "exclude":
            applied["exclude"].append(lemma)     # not added to any entry (R1 does not list it either)
            continue
        if entry not in by_id:
            skipped["unknown_entry"] += 1
            continue
        e = by_id[entry]
        if decision == "dicta_lemma":
            va, vb = (r.get("voice_a") or "").strip(), (r.get("voice_b") or "").strip()
            voice = va if va == vb and va in L.VOICES else "active"
            e.setdefault("dicta_lemmas", [])
            if lemma not in {d.get("lemma") for d in e["dicta_lemmas"]}:
                e["dicta_lemmas"].append({"lemma": lemma, "voice": voice})
                applied["dicta_lemma"].append(f"{lemma}->{entry}")
        elif decision == "shared_lemma":
            e.setdefault("shared_lemmas", [])
            if lemma not in {d.get("lemma") for d in e["shared_lemmas"]}:
                e["shared_lemmas"].append({"lemma": lemma, "other": V2_OTHER})
                applied["shared_lemma"].append(f"{lemma}->{entry}")
        else:
            skipped["unknown_decision"] += 1
    meta = raw.setdefault("meta", {})
    meta["lexicon_version"] = "v2-draft"
    meta["draft_of"] = "lexicon-v2 (Phase C candidate I-1; D-059 P5; Ori decides at G4, file level)"
    text = ("# Phase C candidate I-1 (lexicon-v2 DRAFT; hebloc.loc.ident). Not the config; Ori decides at G4.\n"
            + yaml.safe_dump(raw, allow_unicode=True, sort_keys=False, width=200))
    return text, {"applied": {k: len(v) for k, v in applied.items()}, "skipped": dict(skipped),
                  "applied_rows": {k: sorted(v) for k, v in applied.items()}}


def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# ============================================================================================ build
def _zone(lex_forms: dict, lex_amb: dict, eid: str, host: str) -> str:
    if host not in set(lex_forms.get(eid, [])):
        return "absent"
    p = lex_amb.get(eid, {}).get(host)
    return ("ambiguous:" + " ".join(p)) if p else "clean"


def changes(r1: L.Lexicon, cand: L.Lexicon, inventory) -> list[dict]:
    """Per entry x host: R1's zone vs the candidate's (absent / clean / ~partners), the I-2 lemma partners, and the
    host's VERB tokens per corpus (pooled inventory). Lemmas and forms only."""
    by_host: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for host, n, c in zip(inventory["host"].to_pylist(), inventory["n"].to_pylist(), inventory["corpus"].to_pylist()):
        if host:
            by_host[host][c] += n
    rows = []
    ids = sorted({e.id for e in cand.entries} | {e.id for e in r1.entries})
    for eid in ids:
        hosts = (set(r1.forms.get(eid, [])) | set(cand.forms.get(eid, [])) | set((cand.lemma_partners or {}).get(eid, {})))
        for h in sorted(hosts):
            z1, z2 = _zone(r1.forms, r1.ambiguous, eid, h), _zone(cand.forms, cand.ambiguous, eid, h)
            lp = " ".join((cand.lemma_partners or {}).get(eid, {}).get(h, []))
            if z1 == z2 and not lp:
                continue
            kind = ("lemma_partner" if z1 == z2 else "added" if z1 == "absent" else "removed" if z2 == "absent"
                    else "zone_changed")
            rows.append({"entry": eid, "host": h, "change": kind, "r1": z1, "candidate": z2, "lemma_partners": lp,
                         **{f"n_{c}": by_host[h].get(c, 0) for c in ("mikra", "hazal", "medieval", "haskala", "modern")},
                         "n_total": sum(by_host[h].values())})
    return rows


def build(cands: list[str], r1: L.Lexicon, inventory, *, git: dict, out_root: Path = IDENT_DIR,
          lexicon_path: Path = L.LEXICON_PATH, variant_evidence: Path | None = None, inventory_info: dict | None = None) -> dict:
    """Write one candidate folder (any combination of I-1 … I-4) from the CURRENT config lexicon and the pooled
    inventory. Refused if the folder exists or the draft lexicon is invalid."""
    if "I-1" in cands and variant_evidence is None:
        raise IdentError("I-1 needs --variant-evidence <the frozen variant job's paper_variants_evidence.csv> (stage C1)")
    lex_text = Path(lexicon_path).read_text(encoding="utf-8")
    i1 = None
    if "I-1" in cands:
        lex_text, i1 = lexicon_v2_draft(lex_text, _read_csv(Path(variant_evidence)))
    lex_sha = hashlib.sha256(lex_text.encode("utf-8")).hexdigest()
    cid = candidate_id(cands, lex_sha, inventory_fingerprint(inventory))
    out = Path(out_root) / cid
    if (out / "manifest.json").exists():
        raise IdentError(f"{out} already exists (a candidate is built once; it is identical by design)")
    out.mkdir(parents=True, exist_ok=True)
    lpath, fpath = out / LEXICON_NAME, out / FORMS_NAME
    if "I-1" in cands:
        atomic_write_text(lex_text, lpath)
    else:
        shutil.copyfile(lexicon_path, lpath)
    draft = L.load(lpath, out / "absent.yaml", validate=False)
    probs = L.problems(draft)
    if probs:
        shutil.rmtree(out)
        raise IdentError("the candidate lexicon is invalid (a lexicon decision for Ori at C1/G4, never fixed here):\n  "
                         + "\n  ".join(probs[:20]))
    opts: dict = {}
    for c in cands:
        opts.update(OPTIONS.get(c, {}))
    L.write_forms(draft, inventory, fpath, inventory_info, lexicon_path=lpath, candidates=cands,
                  generated=opts.get("generated", L.FORMS_GENERATED_POLICY),
                  established_self_foreign=bool(opts.get("established_self_foreign")),
                  lemma_partners=bool(opts.get("lemma_partners")))
    cand = L.load(lpath, fpath)
    ch = changes(r1, cand, inventory)
    write_csv(pa.Table.from_pylist(ch) if ch else pa.table({"entry": [], "host": [], "change": []}), out / "changes.csv")
    by_kind: dict[str, int] = defaultdict(int)
    for r in ch:
        by_kind[r["change"]] += 1
    return write_manifest(out, what=f"Phase C identification candidate {'+'.join(cands)} (never the config)", git=git,
                          source={"lexicon_file": str(lexicon_path), "lexicon_file_sha256": file_sha256(Path(lexicon_path)),
                                  "variant_evidence": str(variant_evidence) if variant_evidence else None,
                                  "variant_evidence_sha256": file_sha256(Path(variant_evidence)) if variant_evidence else None,
                                  "inventory": inventory_info or {}},
                          extra={"candidate_id": cid, "candidates": cands, "ident_version": IDENT_VERSION, "options": opts,
                                 "r1_lexicon_sha256": r1.sha256, "candidate_lexicon_sha256": cand.sha256,
                                 "forms_rule": cand.forms_meta.get("rule_version"), "i1": i1,
                                 "changes_by_kind": dict(by_kind), "n_changes": len(ch),
                                 "tokens_affected": {c: sum(r[f"n_{c}"] for r in ch)
                                                     for c in ("mikra", "hazal", "medieval", "haskala", "modern")},
                                 "decided": "at C1 on dev silver by the pre-registered rules (D-059 addendum); never here"})


def load(folder: Path) -> L.Lexicon:
    """The candidate lexicon of a folder (refused if the folder is not a built candidate)."""
    folder = Path(folder)
    if not (folder / "manifest.json").exists() or not (folder / LEXICON_NAME).exists() or not (folder / FORMS_NAME).exists():
        raise IdentError(f"{folder} is not a candidate folder (hebloc loc ident build)")
    return L.load(folder / LEXICON_NAME, folder / FORMS_NAME)


def lexicon_paths(folder: Path | None) -> tuple[Path, Path]:
    if folder is None:
        return L.LEXICON_PATH, L.FORMS_PATH
    return Path(folder) / LEXICON_NAME, Path(folder) / FORMS_NAME
