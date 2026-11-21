"""AI-only SILVER annotation (D-061; S56-v1 as amended; annotation/S56_SILVER_PROTOCOL.md).

Every label made by Claude Code is SILVER: ``label_source = ai``, never gold. It is measured only by its reliability
(two independent passes), its agreement with the independent references that exist (the paper's examples, Mikra) and
its abstention rate; no figure computed against it is called accuracy.

A *job* is one labelling task (``sentence`` per corpus x split, ``anchor``, ``worked``, ``noun`` per corpus, ``unit``,
``variant``, ``audit``). A job's items are built once (``items.json``, private: it quotes corpus text, under
``data/``). Each *pass* (A, B; A2/B2 with context; C adjudication; A3/B3 abstention context) is run in chunks, each
chunk by its own Claude Code session inside an ISOLATED WORKSPACE (SG1):

- the folder is OUTSIDE the repo (default ``~/hebloc-silver-ws``) and holds only the blind input of that chunk, the
  guideline, the protocol, the prompt, a minimal CLAUDE.md, ``.claude/settings.json`` (deny rules) and ``out/``;
- the session is started headless with ``--restricted`` (file tools confined to the folder, no shell, no web, user /
  project settings ignored), ``--strict-mcp-config`` (no MCP servers), ``--settings`` (the deny rules) and
  ``--permission-prompts none`` (anything that would prompt is denied);
- a CANARY preflight: the session must try to read a canary file in the repo and one in a sibling folder; both reads
  must be denied, and the canary token must never appear in the transcript's tool results or the outputs;
- afterwards the session transcript (``~/.claude/projects/*/<session>.jsonl``) is reduced to an ACCESS LOG (paths
  only) and checked: no successful access outside the workspace, no forbidden tool.

``finalize`` applies the deterministic rules, runs the QC (format, consistency, kappa between the FIRST-run passes A
and B, abstention), and FREEZES the job (SG2): hashes in ``FROZEN.json``; a frozen job cannot be rebuilt, rerun or
re-finalized. Failures follow the pre-registered recovery table (SG3); what recovery cannot fix is a STOP with
``QC_STOP.md`` and project-level options only (never human row labelling).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import random
import re
import secrets
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from hebloc.paths import ANNOTATION_DIR, DATA_DIR, ROOT
from hebloc.store.io import atomic_write_json, atomic_write_text, file_sha256, read_json

SILVER_VERSION = "silver-v1"
PROTOCOL_VERSION = "S56-silver-p1"
SILVER_DIR = DATA_DIR / "loc" / "silver"
JOBS_DIR = SILVER_DIR / "jobs"
FINAL_DIR = SILVER_DIR / "final"            # received, frozen SILVER files (Ori); test in its own folder
RECEIVED_DIR = SILVER_DIR / "received"
CANARY_DIR = SILVER_DIR / "canary"
SILVER_ANN = ANNOTATION_DIR / "silver"
PROMPTS_DIR = SILVER_ANN / "prompts"
FROZEN_PATH = SILVER_ANN / "FROZEN_SILVER.json"   # ids and hashes only (git): recorded BEFORE any read (SG2)
WORKED_PATH = SILVER_ANN / "worked_examples.csv"  # the guideline's 15 worked examples (texts already in the guideline)
ANCHOR_IDS_PATH = SILVER_ANN / "anchor_ids.csv"   # instance keys of the paper anchor, WITHOUT the paper's frames
PROTOCOL_PATH = ANNOTATION_DIR / "S56_SILVER_PROTOCOL.md"
GUIDELINE_PATH = ANNOTATION_DIR / "S56_GUIDELINE.md"
DEFAULT_MODEL = "opus"                            # D-061 (D-i): the same strongest model for every pass
CONFIDENCE = ("high", "medium", "low")
NOUN_TYPES = ("LOCATION", "LOCATUM", "ANIMATE", "UNCLEAR")
FRAMES = ("A", "B", "NON_LOCATIVE", "AMBIGUOUS")

# ---- pre-registered QC thresholds and recovery limits (D-061; SG3) ----
KAPPA_FRAME_MIN = 0.6
ABSTENTION_MAX = 0.30
QC_FORMAT_MAX = 0.05
MAX_TECH_ATTEMPTS = 2        # a missing / breached chunk is rerun once in a NEW workspace, then STOP
MAX_FORMAT_RERUNS = 1        # invalid rows: one rerun with the checker's message, then `abstained` (qc_format)
WORKED_ATTEMPTS = 2          # the worked-example compliance check: one rerun, then STOP
BOOTSTRAP = 1000

TASKS: dict[str, dict] = {
    "sentence": {"chunk": 25, "passes": ("A", "B"), "prompt": "sentence_pass.md", "guideline": True},
    "anchor": {"chunk": 25, "passes": ("A", "B"), "prompt": "sentence_pass.md", "guideline": True},
    "worked": {"chunk": 15, "passes": ("A",), "prompt": "sentence_pass.md", "guideline": True},
    "noun": {"chunk": 100, "passes": ("A", "B"), "prompt": "noun_pass.md", "guideline": False},
    "unit": {"chunk": 50, "passes": ("A", "B"), "prompt": "unit_pass.md", "guideline": False},
    "variant": {"chunk": 40, "passes": ("A", "B"), "prompt": "variant_pass.md", "guideline": False},
    "audit": {"chunk": 50, "passes": ("A",), "prompt": "audit_pass.md", "guideline": False},
}
SENTENCE_FIELDS = ("is_target_verb", "member", "locative", "frame", "do", "pps", "bare_np", "locatum", "location", "notes")
OUT_COLUMNS = {
    "sentence": ("item_id",) + SENTENCE_FIELDS + ("confidence", "evidence_rule", "abstain_reason"),
    "adjudicate": ("item_id", "choice", "confidence", "evidence_rule", "reason"),
    "noun": ("item_id", "type", "confidence", "evidence"),
    "unit": ("item_id", "decision", "base", "confidence", "evidence"),
    "variant": ("item_id", "decision", "entry", "voice", "confidence", "evidence"),
    "audit": ("item_id", "correct", "confidence", "evidence"),
}
BLIND_COLUMNS = {
    "sentence": ("item_id", "verb_key", "verb_entries", "target", "sentence", "words"),
    "noun": ("item_id", "upos", "n", "n_as_do", "n_pp_B", "n_pp_MIN", "n_other_pp", "n_verbs", "example_verbs"),
    "unit": ("item_id", "candidates", "n", "pres_share", "fin_share", "n_by_corpus", "examples"),
    "variant": ("item_id", "candidates", "n", "pres_share", "fin_share", "n_by_corpus", "examples"),
    "audit": ("item_id", "base", "n", "pres_share", "fin_share", "examples"),
}
CONTEXT_COLUMNS = ("context_before", "context_after")
#: the fields whose disagreement sends an item to context expansion / adjudication (SG3)
DECISION_FIELDS = ("is_target_verb", "member", "locative", "frame", "do", "bare_np", "locatum", "location")
ALLOWED_TOOLS = ("Read", "Write", "Edit", "Glob", "Grep", "TodoWrite")
DENIED_TOOLS = ("Bash", "PowerShell", "WebFetch", "WebSearch", "Agent", "Task", "NotebookEdit")


class SilverError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def task_kind(task: str) -> str:
    return "sentence" if task in ("sentence", "anchor", "worked") else task


# ============================================================================================ paths and jobs
def job_id(task: str, corpus: str | None = None, split: str | None = None, list_version: str | None = None) -> str:
    if task not in TASKS:
        raise SilverError(f"unknown task {task!r} (one of {sorted(TASKS)})")
    if task == "sentence":
        if not corpus or split not in ("dev", "validation", "test"):
            raise SilverError("a sentence job needs --corpus and --split dev|validation|test")
        return f"sentence-{corpus}-{split}"
    if task == "noun":
        if not corpus:
            raise SilverError("a noun job needs --corpus")
        if not list_version:
            raise SilverError("a noun job needs the list version (the manifest.json next to nouns_to_label.csv)")
        # D-062: the id carries the list version (noun-mikra-r2), so a job made from a corrected list never collides
        # with an earlier job, which is kept untouched
        return f"noun-{corpus}-{list_version.removeprefix('nouns-')}"
    if task == "anchor":
        return "anchor-mikra"
    return task


def job_dir(jid: str, jobs_dir: Path | None = None) -> Path:
    return Path(jobs_dir or JOBS_DIR) / jid


def default_ws_root() -> Path:
    return Path(os.environ.get("HEBLOC_SILVER_WS") or (Path.home() / "hebloc-silver-ws"))


def _outside_repo(p: Path) -> bool:
    try:
        Path(p).resolve().relative_to(ROOT.resolve())
        return False
    except ValueError:
        return True


def load_job(jid: str, jobs_dir: Path | None = None) -> dict:
    p = job_dir(jid, jobs_dir) / "items.json"
    if not p.exists():
        raise SilverError(f"no job {jid} (create it: hebloc loc silver create ...)")
    return read_json(p)


def is_frozen(jid: str, jobs_dir: Path | None = None) -> bool:
    return (job_dir(jid, jobs_dir) / "FROZEN.json").exists()


def duplicate_ids(items: list[dict]) -> list[str]:
    """Item ids that occur more than once (D-062: every job's item ids must be unique)."""
    seen: dict[str, int] = {}
    for x in items:
        seen[x["id"]] = seen.get(x["id"], 0) + 1
    return sorted(k for k, v in seen.items() if v > 1)


def _require_unique(jid: str, job: dict) -> None:
    dup = duplicate_ids(job["items"])
    if dup:
        raise SilverError(f"job {jid} has {len(dup)} duplicate item ids (made before D-062): it is kept on file, "
                          "never stepped, finalized, imported into or delivered. Make a new job from a corrected list")


def _require_open(jid: str, jobs_dir: Path | None) -> None:
    if is_frozen(jid, jobs_dir):
        raise SilverError(f"job {jid} is FROZEN (SG2): it is never rebuilt, rerun or revised")
    _require_unique(jid, load_job(jid, jobs_dir))


def _write_job(jid: str, doc: dict, jobs_dir: Path | None) -> dict:
    d = job_dir(jid, jobs_dir)
    p = d / "items.json"
    dup = duplicate_ids(doc["items"])
    if dup:
        raise SilverError(f"job {jid}: {len(dup)} item ids occur more than once (e.g. {dup[:3]}): refused (D-062; "
                          "a noun list must have one row per lemma: hebloc loc nouns list makes nouns-r2 lists)")
    doc["items_sha256"] = _sha(json.dumps([[x["id"], x["blind"]] for x in doc["items"]], ensure_ascii=False, sort_keys=True))
    if p.exists():
        old = read_json(p)
        if old.get("items_sha256") != doc["items_sha256"]:
            raise SilverError(f"job {jid} already exists with different items: refused (a job's items never change)")
        return old
    atomic_write_json(doc, p)
    return doc


# ============================================================================================ item builders
def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _write_csv_text(path: Path, header: tuple[str, ...] | list[str], rows: list[dict]) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(header), lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in header})
    atomic_write_text("\ufeff" + buf.getvalue(), path)


def verb_entries_text(verb_key: str, lex) -> str:
    """The entries of a gold ``verb_key`` in words, for ``is_target_verb`` and ``member`` (guideline §1)."""
    by_id = {e.id: e for e in lex.entries} if lex is not None else {}
    out = []
    for part in filter(None, (verb_key or "").split("|")):
        if part.startswith("~"):
            out.append(f"{part}: another verb that shares this form (the token may be that verb)")
        elif part in by_id:
            e = by_id[part]
            out.append(f"{part}: {e.citation} '{e.gloss}' ({e.template})")
        else:
            out.append(part)
    return " ; ".join(out)


def sentence_items(corpus: str, split: str, sample_dir: Path, lex) -> list[dict]:
    """Items of a frozen gold sample split (read from the LOCAL sheet; the blind part never holds the stratum, the
    place, the split or the agreement flag)."""
    import pyarrow.parquet as pq

    sample = {r["item_id"]: r for r in pq.read_table(Path(sample_dir) / "sample.parquet").to_pylist()}
    sheet = Path(sample_dir) / "sheets" / f"{split}.csv"
    if not sheet.exists():
        raise SilverError(f"no local sheet {sheet} (draw the sample: hebloc loc gold sample)")
    items = []
    for r in _read_csv(sheet):
        s = sample[r["item_id"]]
        items.append({"id": s["item_id"],
                      "blind": {"item_id": s["item_id"], "verb_key": s["verb_key"],
                                "verb_entries": verb_entries_text(s["verb_key"], lex), "target": r["target"],
                                "sentence": r["sentence"], "words": r["words"]},
                      "private": {"sample_id": s["sample_id"], "instance_key": s["instance_key"], "split": s["split"],
                                  "stratum": s["stratum"], "agreement": bool(s["agreement"]), "members": list(s["members"] or []),
                                  "sent_id": s["sent_id"], "doc_id": s["doc_id"], "corpus": corpus}})
    return sorted(items, key=lambda x: x["id"])


def worked_items(path: Path = WORKED_PATH) -> list[dict]:
    items = []
    for r in _read_csv(path):
        words = " ".join(f"{i}:{w}" for i, w in enumerate(r["sentence"].replace("[[", "").replace("]]", "").split()))
        items.append({"id": r["item_id"], "blind": {"item_id": r["item_id"], "verb_key": r["verb_key"],
                                                   "verb_entries": r.get("verb_entries", ""), "target": r["target"],
                                                   "sentence": r["sentence"], "words": words},
                      "private": {"expected_frame": r["expected_frame"], "members": [], "split": "worked"}})
    return items


def unit_sentences(con, source, corpus: str, keys: list[tuple[str, int, int]]) -> dict[tuple, dict]:
    """(sent_id, piece_idx, word_idx) -> marked sentence, words, target, doc_id (the gold sheets' format)."""
    import pyarrow as pa

    if not keys:
        return {}
    con.register("want_s", pa.table({"sent_id": [k[0] for k in keys], "piece_idx": [k[1] for k in keys]}))
    units = {r["sent_id"]: r for r in con.sql(
        f"SELECT u.sent_id, u.doc_id, u.text_norm FROM {source.units_sql(corpus, ('sent_id', 'doc_id', 'text_norm'))} u "
        "WHERE u.sent_id IN (SELECT sent_id FROM want_s)").to_arrow_table().to_pylist()}
    words: dict[tuple, list] = {}
    for run in source.runs(corpus):
        for r in con.sql(f"SELECT t.sent_id, t.piece_idx, t.word_idx, t.surface, t.char_start, t.char_end FROM {source.tokens_sql(run)} t "
                         "SEMI JOIN want_s w ON w.sent_id = t.sent_id AND w.piece_idx = t.piece_idx").to_arrow_table().to_pylist():
            words.setdefault((r["sent_id"], r["piece_idx"]), []).append(r)
    out = {}
    for k in keys:
        ws = sorted(words.get((k[0], k[1]), []), key=lambda r: r["word_idx"])
        t = next((r for r in ws if r["word_idx"] == k[2]), None)
        u = units.get(k[0])
        if t is None or u is None:
            continue
        text = u["text_norm"]
        out[k] = {"sentence": text[:t["char_start"]] + "[[" + text[t["char_start"]:t["char_end"]] + "]]" + text[t["char_end"]:],
                  "words": " ".join(f"{r['word_idx']}:{r['surface']}" for r in ws), "target": t["surface"], "doc_id": u["doc_id"]}
    return out


def _parse_key(instance_key: str) -> tuple[str, int, int]:
    sid, p, w = instance_key.split("|")
    return sid, int(p), int(w)


def anchor_items(source, lex, path: Path = ANCHOR_IDS_PATH) -> list[dict]:
    """The paper-example anchor (Mikra): instance keys and entry ids only; the paper's frame is NOT here."""
    from hebloc.loc.source import connect

    rows = _read_csv(path)
    keys = [_parse_key(r["instance_key"]) for r in rows]
    texts = unit_sentences(connect(), source, "mikra", keys)
    items = []
    for r, k in zip(rows, keys):
        t = texts.get(k)
        if t is None:
            raise SilverError(f"anchor instance {r['instance_key']} not found in the Mikra parse")
        items.append({"id": r["anchor_id"],
                      "blind": {"item_id": r["anchor_id"], "verb_key": r["entry_id"],
                                "verb_entries": verb_entries_text(r["entry_id"], lex), "target": t["target"],
                                "sentence": t["sentence"], "words": t["words"]},
                      "private": {"instance_key": r["instance_key"], "members": [r["entry_id"]], "sent_id": k[0],
                                  "doc_id": t["doc_id"], "corpus": "mikra", "split": "anchor"}})
    return items


def write_anchor_ids(paper_examples: Path, out: Path = ANCHOR_IDS_PATH, worked: Path = WORKED_PATH) -> dict:
    """Ori's side: the anchor ids from the paper-example dev set (``loc gold paper``): single-token items that are
    NOT frozen validation/test tokens, minus the guideline's worked examples. No frame, no reference."""
    rows = _read_csv(paper_examples)
    worked_refs = {r.get("ref", "") for r in _read_csv(worked)} if Path(worked).exists() else set()
    keep, seen = [], set()
    for r in rows:
        if r.get("status") != "dev" or not r.get("instance_key") or r.get("ref") in worked_refs:
            continue
        if r["instance_key"] in seen:
            continue
        seen.add(r["instance_key"])
        keep.append(r)
    keep.sort(key=lambda r: _sha("S56-silver:anchor:" + r["instance_key"]))
    out_rows = [{"anchor_id": f"AN{i + 1:03d}", "instance_key": r["instance_key"], "entry_id": r["entry_id"]} for i, r in enumerate(keep)]
    _write_csv_text(out, ("anchor_id", "instance_key", "entry_id"), out_rows)
    return {"anchor_items": len(out_rows), "excluded_worked_refs": len(worked_refs), "out": str(out)}


def noun_items(list_csv: Path) -> list[dict]:
    items = []
    for r in _read_csv(list_csv):
        b = {"item_id": r["lemma"], **{c: r.get(c, "") for c in BLIND_COLUMNS["noun"][1:]}}
        items.append({"id": r["lemma"], "blind": b, "private": {"corpus_source": r.get("corpus_source", "")}})
    return items


def _examples_by_lemma(examples_csv: Path | None) -> dict[str, str]:
    if not examples_csv or not Path(examples_csv).exists():
        return {}
    by: dict[str, list[str]] = {}
    for r in _read_csv(examples_csv):
        by.setdefault(r["lemma"], []).append(f"[{r.get('corpus', '')}] {r.get('target', '')}: {r.get('sentence', '')}")
    return {k: " ||| ".join(v[:3]) for k, v in by.items()}


def unit_items(sheet: Path, examples_csv: Path | None, kind: str) -> list[dict]:
    """Unit-link rows (``unit_review.csv``), paper variants (``paper_variants.csv``) or the 100-link audit
    (``audit.csv``; its ``rule`` column is NOT shown, so the audit pass never sees the P2 rules)."""
    ex = _examples_by_lemma(examples_csv)
    items = []
    for r in _read_csv(sheet):
        b = {"item_id": r["lemma"], **{c: r.get(c, "") for c in BLIND_COLUMNS[kind][1:] if c != "examples"},
             "examples": ex.get(r["lemma"], "")}
        items.append({"id": r["lemma"], "blind": b, "private": {"base": r.get("base", ""), "rule": r.get("rule", "")}})
    return items


def create_job(task: str, corpus: str | None = None, split: str | None = None, *, lex=None, source=None,
               sample_dir: Path | None = None, list_csv: Path | None = None, sheet: Path | None = None,
               examples_csv: Path | None = None, jobs_dir: Path | None = None) -> dict:
    list_version = None
    if task == "noun":
        if list_csv is None:
            raise SilverError("a noun job needs --list <nouns_to_label.csv>")
        man = Path(list_csv).parent / "manifest.json"
        if not man.exists():
            raise SilverError(f"{man} not found: a noun job is made from a list folder of hebloc loc nouns list")
        list_version = read_json(man).get("list_version")
    jid = job_id(task, corpus, split, list_version)
    if task == "sentence":
        if sample_dir is None:
            raise SilverError("a sentence job needs --sample <frozen sample folder>")
        items = sentence_items(corpus, split, sample_dir, lex)
        inputs = {"sample.parquet": file_sha256(Path(sample_dir) / "sample.parquet")}
    elif task == "worked":
        items, inputs = worked_items(WORKED_PATH), {"worked_examples.csv": file_sha256(WORKED_PATH)}
    elif task == "anchor":
        items, inputs = anchor_items(source, lex, ANCHOR_IDS_PATH), {"anchor_ids.csv": file_sha256(ANCHOR_IDS_PATH)}
    elif task == "noun":
        items, inputs = noun_items(list_csv), {"list": file_sha256(Path(list_csv)), "list_version": list_version}
    else:
        if sheet is None:
            raise SilverError(f"a {task} job needs --sheet (unit_review.csv / paper_variants.csv / audit.csv)")
        items, inputs = unit_items(sheet, examples_csv, task), {"sheet": file_sha256(Path(sheet))}
    if not items:
        raise SilverError(f"job {jid}: no items")
    doc = {"job_id": jid, "task": task, "corpus": corpus, "split": split, "silver_version": SILVER_VERSION,
           "protocol_version": PROTOCOL_VERSION, "created": _now(), "inputs": inputs, "items": items}
    d = _write_job(jid, doc, jobs_dir)
    return {"job_id": jid, "items": len(d["items"]), "dir": str(job_dir(jid, jobs_dir))}


# ============================================================================================ context (SG3)
def add_context(job: dict, item_ids: list[str], source) -> dict[str, dict]:
    """The previous and next unit of the same document for each item (context expansion; blind)."""
    from hebloc.loc.source import connect
    import pyarrow as pa

    want = [x for x in job["items"] if x["id"] in set(item_ids)]
    if job["task"] == "worked" or not want or source is None:
        return {x["id"]: {"context_before": "", "context_after": ""} for x in want}
    corpus = want[0]["private"]["corpus"]
    con = connect()
    docs = sorted({x["private"]["doc_id"] for x in want})
    con.register("want_d", pa.table({"doc_id": docs}))
    rows = con.sql(f"SELECT sent_id, doc_id, text_norm FROM {source.units_sql(corpus, ('sent_id', 'doc_id', 'text_norm'))} "
                   "WHERE doc_id IN (SELECT doc_id FROM want_d)").to_arrow_table().to_pylist()

    def order(sid: str) -> tuple:
        parts = sid.split(":")
        return tuple(int(p) if p.isdigit() else p for p in parts[2:])

    by_doc: dict[str, list] = {}
    for r in rows:
        by_doc.setdefault(r["doc_id"], []).append(r)
    pos = {}
    for d, rs in by_doc.items():
        rs.sort(key=lambda r: order(r["sent_id"]))
        for i, r in enumerate(rs):
            pos[r["sent_id"]] = (d, i)
    out = {}
    for x in want:
        d, i = pos.get(x["private"]["sent_id"], (None, None))
        rs = by_doc.get(d, [])
        out[x["id"]] = {"context_before": rs[i - 1]["text_norm"] if d is not None and i > 0 else "",
                        "context_after": rs[i + 1]["text_norm"] if d is not None and i + 1 < len(rs) else ""}
    return out


# ============================================================================================ workspaces (SG1)
def _rule_path(p: Path) -> str:
    """A Claude Code permission-rule path: ``//c/Users/...`` (absolute) for ``C:\\Users\\...``."""
    s = Path(p).resolve().as_posix()
    m = re.match(r"^([A-Za-z]):/(.*)$", s)
    return f"//{m.group(1).lower()}/{m.group(2)}" if m else "/" + s


def workspace_settings(repo: Path = ROOT, projects_dir: Path | None = None) -> dict:
    deny = list(DENIED_TOOLS)
    # Read rules also cover Glob and Grep; Edit rules cover every file-writing tool
    for p in (repo, Path(projects_dir or Path.home() / ".claude" / "projects"), Path.home() / ".claude"):
        for tool in ("Read", "Edit"):
            deny.append(f"{tool}({_rule_path(p)}/**)")
    return {"permissions": {"defaultMode": "acceptEdits", "deny": deny}, "enableAllProjectMcpServers": False}


def _order(jid: str, label: str, ids: list[str]) -> list[str]:
    return sorted(ids, key=lambda i: _sha(f"S56-silver:{jid}:{label}:{i}"))


def _prompt(task: str, kind: str, **fill) -> str:
    name = "adjudicate.md" if kind == "adjudicate" else TASKS[task]["prompt"]
    text = (PROMPTS_DIR / name).read_text(encoding="utf-8")
    for k, v in fill.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


WS_CLAUDE_MD = """# SILVER annotation workspace (S56-v1, D-061)

You are an AI annotator producing SILVER labels. Work ONLY with the files in this folder.
Read `PROMPT.md` and follow it exactly. Do not look for, open or ask for any other file, tool, code, prediction,
answer key or earlier label: none of them belongs to this task.
"""


def build_workspace(job: dict, label: str, item_ids: list[str], *, attempt: int, chunk: int, kind: str = "label",
                    context: dict | None = None, answers: dict | None = None, message: str = "",
                    root: Path | None = None, jobs_dir: Path | None = None, projects_dir: Path | None = None) -> Path:
    """One isolated workspace (SG1) for one chunk of one pass."""
    jid, task = job["job_id"], job["task"]
    _require_open(jid, jobs_dir)
    root = Path(root or default_ws_root())
    if not _outside_repo(root):
        raise SilverError(f"the workspace root {root} is inside the repo: refused (SG1)")
    name = f"{jid}-{label}-a{attempt}-c{chunk:02d}-{secrets.token_hex(4)}"
    ws = root / name
    (ws / "out").mkdir(parents=True)
    (ws / ".claude").mkdir()
    by_id = {x["id"]: x for x in job["items"]}
    tk = task_kind(task)
    cols = list(BLIND_COLUMNS[tk])
    rows = []
    for i in _order(jid, label, item_ids):
        r = dict(by_id[i]["blind"])
        if context is not None:
            r.update(context.get(i, {"context_before": "", "context_after": ""}))
        if answers is not None:
            r.update(answers[i])
        rows.append(r)
    if context is not None:
        cols += list(CONTEXT_COLUMNS)
    if answers is not None:
        cols += [c for c in next(iter(answers.values())) if c not in cols]
    _write_csv_text(ws / "input.csv", cols, rows)
    out_cols = OUT_COLUMNS["adjudicate" if kind == "adjudicate" else tk]
    token = "CANARY-" + secrets.token_hex(8)
    c1 = Path(CANARY_DIR) / f"{name}.txt"
    c2 = root / "_canary" / name / "canary.txt"
    atomic_write_text(token + "\n", c1)
    atomic_write_text(token + "\n", c2)
    files = {"input.csv": ws / "input.csv"}
    if TASKS[task]["guideline"] or kind == "adjudicate":
        shutil.copyfile(GUIDELINE_PATH, ws / "S56_GUIDELINE.md")
        files["S56_GUIDELINE.md"] = ws / "S56_GUIDELINE.md"
    shutil.copyfile(PROTOCOL_PATH, ws / "S56_SILVER_PROTOCOL.md")
    atomic_write_text(_prompt(task, kind, N=len(rows), OUT_COLUMNS=",".join(out_cols), CANARY_1=c1.resolve(),
                              CANARY_2=c2.resolve(), MESSAGE=message or "(none)", CONTEXT="yes" if context is not None else "no"),
                      ws / "PROMPT.md")
    atomic_write_text(WS_CLAUDE_MD, ws / "CLAUDE.md")
    atomic_write_json(workspace_settings(projects_dir=projects_dir), ws / ".claude" / "settings.json")
    meta = {"workspace": name, "job_id": jid, "task": task, "pass": label, "kind": kind, "attempt": attempt, "chunk": chunk,
            "items": [r["item_id"] for r in rows], "context": context is not None, "created": _now(),
            "canary": {"repo": str(c1.resolve()), "sibling": str(c2.resolve()), "token_sha256": _sha(token)},
            "protocol_sha256": file_sha256(PROTOCOL_PATH), "prompt_sha256": file_sha256(ws / "PROMPT.md"),
            "input_sha256": file_sha256(ws / "input.csv"), "out_columns": list(out_cols)}
    atomic_write_json(meta, ws / "WORKSPACE.json")
    # the token itself is kept only in the job folder (never in the workspace metadata)
    atomic_write_json({"token": token}, job_dir(jid, jobs_dir) / "canary" / f"{name}.json")
    return ws


def claude_command(ws: Path, *, model: str = DEFAULT_MODEL, claude: list[str] | None = None) -> list[str]:
    """The headless, restricted launch of one workspace session (no API key: the user's Claude Code login)."""
    base = list(claude or [shutil.which("claude") or "claude"])
    return base + ["-p", "Read CLAUDE.md and PROMPT.md in this folder and do exactly what PROMPT.md says.",
                   "--restricted", "--strict-mcp-config", "--settings", str(Path(ws) / ".claude" / "settings.json"),
                   "--permission-mode", "acceptEdits", "--permission-prompts", "none", "--model", model,
                   "--output-format", "json", "--disallowedTools", *DENIED_TOOLS]


def run_workspace(ws: Path, *, model: str = DEFAULT_MODEL, claude: list[str] | None = None, timeout: int = 5400) -> dict:
    cmd = claude_command(ws, model=model, claude=claude)
    t0 = datetime.now(timezone.utc)
    try:
        p = subprocess.run(cmd, cwd=str(ws), capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, stdin=subprocess.DEVNULL)
        out, rc = p.stdout, p.returncode
    except subprocess.TimeoutExpired as e:
        out, rc = (e.stdout or "") if isinstance(e.stdout, str) else "", -9
    info = {"returncode": rc, "started": t0.isoformat(timespec="seconds"), "ended": _now(), "model": model}
    try:
        j = json.loads(out.strip().splitlines()[-1]) if out.strip() else {}
    except (json.JSONDecodeError, IndexError):
        j = {}
    info.update({"session_id": j.get("session_id"), "is_error": j.get("is_error"), "num_turns": j.get("num_turns"),
                 "duration_ms": j.get("duration_ms")})
    atomic_write_json(info, Path(ws) / "RUN.json")
    return info


# ============================================================================================ access log (SG1)
def find_transcript(session_id: str, projects_dir: Path | None = None) -> Path | None:
    if not session_id:
        return None
    base = Path(projects_dir or Path.home() / ".claude" / "projects")
    hits = sorted(base.glob(f"*/{session_id}.jsonl"))
    return hits[0] if hits else None


def _inside(p: Path, ws: Path) -> bool:
    try:
        p.resolve().relative_to(ws.resolve())
        return True
    except ValueError:
        return False


def access_log(transcript: Path, ws: Path, canary: dict, token: str) -> dict:
    """Paths only (no text): every tool call of the session, the canary preflight, and the violations."""
    ws = Path(ws)
    calls, results = {}, {}
    for line in Path(transcript).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = e.get("message") or {}
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_use":
                calls[c.get("id")] = {"tool": c.get("name"), "input": c.get("input") or {}}
            elif c.get("type") == "tool_result":
                txt = c.get("content")
                if isinstance(txt, list):
                    txt = " ".join(str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in txt)
                results[c.get("tool_use_id")] = {"is_error": bool(c.get("is_error")), "has_token": token in str(txt or "")}
    log, violations = [], []
    canary_paths = {Path(canary["repo"]).resolve(): "repo", Path(canary["sibling"]).resolve(): "sibling"}
    pre = {"repo": {"attempted": False, "denied": None}, "sibling": {"attempted": False, "denied": None}}
    for cid, c in calls.items():
        res = results.get(cid, {"is_error": True, "has_token": False})
        inp = c["input"]
        raw = inp.get("file_path") or inp.get("path") or inp.get("notebook_path")
        p = None
        if raw:
            p = Path(raw) if Path(raw).is_absolute() else ws / raw
        inside = p is None or _inside(p, ws)
        entry = {"tool": c["tool"], "path": (str(p.resolve().relative_to(ws.resolve())) if p is not None and inside else str(p) if p else ""),
                 "inside": inside, "error": res["is_error"]}
        log.append(entry)
        if res["has_token"]:
            violations.append(f"canary token in a tool result ({c['tool']} {entry['path']})")
        if p is not None and p.resolve() in canary_paths:
            k = canary_paths[p.resolve()]
            pre[k]["attempted"] = True
            pre[k]["denied"] = res["is_error"] if pre[k]["denied"] is None else (pre[k]["denied"] and res["is_error"])
            if not res["is_error"]:
                violations.append(f"canary {k} was READ (isolation breach)")
            continue
        if not res["is_error"]:
            if c["tool"] not in ALLOWED_TOOLS:
                violations.append(f"forbidden tool used: {c['tool']}")
            elif not inside:
                violations.append(f"access outside the workspace: {c['tool']} {p}")
    preflight_ok = all(v["attempted"] and v["denied"] for v in pre.values())
    return {"ok": not violations and preflight_ok, "preflight": pre, "preflight_ok": preflight_ok,
            "violations": violations, "calls": log, "transcript_sha256": file_sha256(Path(transcript))}


# ============================================================================================ collecting labels
def _norm_pps(s: str) -> str:
    parts = []
    for pp in filter(None, (s or "").split(";")):
        i, _, prep = pp.strip().partition(":")
        parts.append(f"{i.strip()}:{prep.strip()}")
    return "; ".join(sorted(set(parts)))


def _clean(r: dict, cols: tuple[str, ...]) -> dict:
    v = {c: (r.get(c) or "").strip() for c in cols}
    if "pps" in v:
        v["pps"] = _norm_pps(v["pps"])
    if "confidence" in v:
        v["confidence"] = v["confidence"].lower()
    return v


def consistency_problems(v: dict) -> list[str]:
    """The internal-consistency rules of the guideline (§2, §3.5, §4): a failure is a QC_FORMAT row."""
    p = []
    if v["is_target_verb"] == "N" and any(v[c] for c in DECISION_FIELDS[1:] if c != "member"):
        p.append("is_target_verb N but other fields are filled")
    if v["is_target_verb"] == "Y":
        if v["frame"] == "NON_LOCATIVE" and v["locative"] != "N":
            p.append("frame NON_LOCATIVE needs locative N")
        concrete = v["do"] not in ("", "none")
        if v["frame"] == "A" and concrete and v["locatum"] and v["locatum"] != v["do"]:
            p.append("frame A: the direct object must be the locatum")
        if v["frame"] == "B" and concrete and v["location"] and v["location"] != v["do"]:
            p.append("frame B: the direct object must be the location")
        if v["locatum"] and v["locatum"] == v["location"] and v["locatum"] not in ("elided",):
            p.append("locatum and location are the same argument")
        pp_idx = {pp.partition(":")[0] for pp in filter(None, v["pps"].split("; "))}
        if v["do"].isdigit() and v["do"] in pp_idx:
            p.append("the direct object is also listed as a PP (partitive: put it in do only)")
    return p


def validate(task: str, kind: str, v: dict, item: dict) -> list[str]:
    from hebloc.loc.gold import row_problems

    tk = "adjudicate" if kind == "adjudicate" else task_kind(task)
    probs = []
    if "confidence" in v and v["confidence"] not in CONFIDENCE:
        probs.append("confidence must be high, medium or low")
    if tk == "sentence":
        n_words = len((item["blind"].get("words") or "").split())
        probs += row_problems(v, list(item["private"].get("members") or []), n_words)
        if not probs:
            probs += consistency_problems(v)
        abst = v["is_target_verb"] == "Y" and (v["locative"] == "?" or v["frame"] == "AMBIGUOUS")
        if abst and not v["abstain_reason"]:
            probs.append("an abstention (? / AMBIGUOUS) needs abstain_reason")
    elif tk == "adjudicate":
        if v["choice"] not in ("1", "2", "abstain"):
            probs.append("choice must be 1, 2 or abstain")
    elif tk == "noun":
        if v["type"] not in NOUN_TYPES:
            probs.append(f"type must be one of {NOUN_TYPES}")
    elif tk == "unit":
        if v["decision"] not in ("accept", "reject"):
            probs.append("decision must be accept or reject")
        cands = re.findall(r"(?:^|; )(\S+) \(", item["blind"].get("candidates") or "")
        if v["decision"] == "accept" and v["base"] not in cands:
            probs.append(f"accept must name one of the candidate bases {cands}")
    elif tk == "variant":
        if v["decision"] not in ("dicta_lemma", "shared_lemma", "exclude"):
            probs.append("decision must be dicta_lemma, shared_lemma or exclude")
    elif tk == "audit":
        if v["correct"] not in ("Y", "N"):
            probs.append("correct must be Y or N")
    return [x.strip() for x in probs]


def collect(ws: Path, *, jobs_dir: Path | None = None, projects_dir: Path | None = None) -> dict:
    """Read a finished workspace into the job: labels (validated), the access log, the canary check. A breach
    discards the chunk's labels (kept on file, flagged)."""
    ws = Path(ws)
    meta = read_json(ws / "WORKSPACE.json")
    run = read_json(ws / "RUN.json") if (ws / "RUN.json").exists() else {}
    jid, label = meta["job_id"], meta["pass"]
    job = load_job(jid, jobs_dir)
    by_id = {x["id"]: x for x in job["items"]}
    token = read_json(job_dir(jid, jobs_dir) / "canary" / f"{meta['workspace']}.json")["token"]
    dest = job_dir(jid, jobs_dir) / "passes" / label / f"a{meta['attempt']}" / f"c{meta['chunk']:02d}"
    dest.mkdir(parents=True, exist_ok=True)
    tr = find_transcript(run.get("session_id"), projects_dir)
    acc = access_log(tr, ws, meta["canary"], token) if tr else {"ok": False, "preflight_ok": False,
                                                                  "violations": ["no session transcript found"], "calls": []}
    outs = sorted((ws / "out").glob("*.csv"))
    leaked = any(token in p.read_text(encoding="utf-8", errors="replace") for p in (ws / "out").glob("*") if p.is_file())
    if leaked:
        acc["ok"] = False
        acc["violations"].append("canary token found in the outputs")
    rows, probs = [], {}
    cols = tuple(meta["out_columns"])
    for p in outs:
        for r in _read_csv(p):
            v = _clean(r, cols)
            if v["item_id"] not in meta["items"]:
                continue
            pr = validate(job["task"], meta["kind"], v, by_id[v["item_id"]])
            rows.append({**v, "_valid": not pr})
            if pr:
                probs[v["item_id"]] = pr
    seen = {}
    for r in rows:
        seen[r["item_id"]] = r                   # the last row of an item wins within one chunk
    status = "breach" if not acc["ok"] else "ok"
    atomic_write_json({**{k: v for k, v in acc.items()}, "workspace": meta["workspace"], "run": run, "status": status},
                      dest / "access.json")
    _write_csv_text(dest / "labels.csv", list(cols) + ["_valid"], list(seen.values()))
    atomic_write_json({"problems": probs}, dest / "problems.json")
    atomic_write_json(meta, dest / "WORKSPACE.json")
    missing = [i for i in meta["items"] if i not in seen]
    return {"workspace": meta["workspace"], "status": status, "labels": len(seen), "invalid": len(probs),
            "missing": len(missing), "violations": acc["violations"], "preflight_ok": acc.get("preflight_ok")}


# ============================================================================================ pass state
def pass_state(jid: str, label: str, jobs_dir: Path | None = None) -> dict:
    """The current labels of a pass: per item the latest VALID row from a non-breached chunk (all attempts kept)."""
    d = job_dir(jid, jobs_dir) / "passes" / label
    plan = read_json(d / "PLAN.json") if (d / "PLAN.json").exists() else None
    best: dict[str, dict] = {}
    invalid: dict[str, dict] = {}
    tried: dict[str, int] = {}
    format_reruns: dict[str, int] = {}
    breaches = 0
    for ad in sorted(d.glob("a*"), key=lambda p: int(p.name[1:])):
        for cd in sorted(ad.glob("c*")):
            acc = read_json(cd / "access.json")
            meta = read_json(cd / "WORKSPACE.json")
            for i in meta["items"]:
                tried[i] = tried.get(i, 0) + 1
            if meta.get("format_rerun"):
                for i in meta["items"]:
                    format_reruns[i] = format_reruns.get(i, 0) + 1
            if acc.get("status") == "breach":
                breaches += 1
                continue
            for r in _read_csv(cd / "labels.csv"):
                if r.get("_valid") == "True":
                    best[r["item_id"]] = r
                    invalid.pop(r["item_id"], None)
                elif r["item_id"] not in best:
                    invalid[r["item_id"]] = r
    items = plan["items"] if plan else []
    missing = [i for i in items if i not in best and i not in invalid]
    return {"plan": plan, "labels": best, "invalid": invalid, "missing": missing, "tried": tried,
            "format_reruns": format_reruns, "breaches": breaches}


def _plan_pass(jid: str, label: str, items: list[str], kind: str, context: bool, jobs_dir: Path | None) -> dict:
    d = job_dir(jid, jobs_dir) / "passes" / label
    p = d / "PLAN.json"
    if p.exists():
        return read_json(p)
    plan = {"pass": label, "items": sorted(items), "kind": kind, "context": context, "created": _now()}
    atomic_write_json(plan, p)
    return plan


def import_pass(jid: str, label: str, from_csv: Path, *, type_column: str = "proposed_type",
                confidence_column: str = "confidence", evidence_column: str = "note", jobs_dir: Path | None = None) -> dict:
    """Import an EARLIER AI pass made before this protocol (D-061 D-f: Efrat's Modern noun proposals as pass A).
    Its provenance is recorded; the other pass never sees it (it is never put in a workspace)."""
    _require_open(jid, jobs_dir)
    job = load_job(jid, jobs_dir)
    if job["task"] != "noun":
        raise SilverError("import-pass is defined for noun jobs only (D-061 D-f)")
    if pass_state(jid, label, jobs_dir)["plan"]:
        raise SilverError(f"pass {label} of {jid} already exists: refused")
    by_id = {x["id"]: x for x in job["items"]}
    rows = _read_csv(from_csv)
    if rows and confidence_column not in rows[0]:
        raise SilverError(f"{from_csv} has no {confidence_column!r} column (give --confidence-column)")
    out, probs = [], {}
    # D-062: proposals made on a nouns-r1 list can hold two rows for one lemma (NOUN and PROPN), each typed on part of
    # the evidence. Such a lemma is NOT imported: it stays missing, so the normal step labels it in an isolated pass A
    # with the merged evidence (never resolved by row order)
    n_rows: dict[str, int] = {}
    for r in rows:
        k = (r.get("lemma") or "").strip()
        n_rows[k] = n_rows.get(k, 0) + 1
    dropped = sorted(k for k, v in n_rows.items() if v > 1 and k in by_id)
    for r in rows:
        i = (r.get("lemma") or "").strip()
        if i not in by_id or n_rows[i] > 1:
            continue
        v = {"item_id": i, "type": (r.get(type_column) or "").strip(), "confidence": (r.get(confidence_column) or "").strip().lower(),
             "evidence": (r.get(evidence_column) or "").strip()[:200]}
        pr = validate("noun", "label", v, by_id[i])
        out.append({**v, "_valid": not pr})
        if pr:
            probs[i] = pr
    d = job_dir(jid, jobs_dir) / "passes" / label
    _plan_pass(jid, label, list(by_id), "label", False, jobs_dir)
    cd = d / "a0" / "c00"
    _write_csv_text(cd / "labels.csv", list(OUT_COLUMNS["noun"]) + ["_valid"], out)
    atomic_write_json({"problems": probs}, cd / "problems.json")
    atomic_write_json({"status": "ok", "imported": True, "source_file": str(from_csv), "source_sha256": file_sha256(Path(from_csv)),
                       "note": "made before the silver protocol (D-061 D-f); isolation not applicable"}, cd / "access.json")
    atomic_write_json({"workspace": "imported", "job_id": jid, "pass": label, "kind": "label", "attempt": 0, "chunk": 0,
                       "items": [r["item_id"] for r in out], "imported": True, "dropped_duplicate": dropped},
                      cd / "WORKSPACE.json")
    return {"imported": len(out), "invalid": len(probs), "missing": len(by_id) - len(out), "dropped_duplicate": len(dropped)}


def status(jid: str, jobs_dir: Path | None = None) -> dict:
    """Counts only (no labels): passes, labels, invalid, missing, breaches; frozen; STOP file."""
    job = load_job(jid, jobs_dir)
    d = job_dir(jid, jobs_dir)
    passes = {}
    for pd in sorted((d / "passes").glob("*")) if (d / "passes").exists() else []:
        if not (pd / "PLAN.json").exists():
            continue
        st = pass_state(jid, pd.name, jobs_dir)
        passes[pd.name] = {"planned": len(st["plan"]["items"]), "labelled": len(st["labels"]), "invalid": len(st["invalid"]),
                           "missing": len(st["missing"]), "breaches": st["breaches"]}
    return {"job_id": jid, "task": job["task"], "items": len(job["items"]), "passes": passes, "frozen": is_frozen(jid, jobs_dir),
            "stop": (d / "QC_STOP.md").exists()}


# ============================================================================================ decisions
CONF_RANK = {"high": 2, "medium": 1, "low": 0}


def _min_conf(*cs: str) -> str:
    return min(cs, key=lambda c: CONF_RANK.get(c, 0)) if cs else ""


def same_decision(a: dict, b: dict) -> bool:
    return all((a.get(f) or "") == (b.get(f) or "") for f in DECISION_FIELDS)


def is_abstention(r: dict) -> bool:
    return r.get("silver_status") == "abstained" or (
        r.get("is_target_verb") == "Y" and (r.get("locative") == "?" or r.get("frame") == "AMBIGUOUS"))


def frame_cat(r: dict) -> str:
    if r.get("is_target_verb") != "Y":
        return "NOT_TARGET"
    return "NON_LOCATIVE" if r.get("locative") == "N" else (r.get("frame") or "AMBIGUOUS")


def kappa(a: list[str], b: list[str]) -> float | None:
    if not a or len(a) != len(b):
        return None
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    if po == 1:
        return 1.0
    cats = sorted(set(a) | set(b))
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return None if pe == 1 else (po - pe) / (1 - pe)


def kappa_ci(a: list[str], b: list[str], n_boot: int = BOOTSTRAP, seed: int = 0) -> dict:
    k = kappa(a, b)
    if k is None:
        return {"kappa": None, "ci95": None, "n": len(a)}
    rng = random.Random(seed)
    n = len(a)
    ks = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        x = kappa([a[i] for i in idx], [b[i] for i in idx])
        if x is not None:
            ks.append(x)
    ks.sort()
    ci = (round(ks[int(0.025 * len(ks))], 4), round(ks[min(len(ks) - 1, int(0.975 * len(ks)))], 4)) if ks else None
    return {"kappa": round(k, 4), "ci95": ci, "n": n}


def _pair_answers(jid: str, ids: list[str], a: dict, b: dict) -> dict[str, dict]:
    """Adjudication input: the two answers in an order fixed by hash (never 'pass A' / 'pass B')."""
    out = {}
    fields = SENTENCE_FIELDS + ("confidence", "evidence_rule", "abstain_reason")
    for i in ids:
        first, second = (a[i], b[i]) if int(_sha(f"S56-silver:{jid}:C:{i}")[:2], 16) % 2 == 0 else (b[i], a[i])
        row = {}
        for k, r in (("answer_1", first), ("answer_2", second)):
            for f in fields:
                row[f"{k}_{f}"] = r.get(f, "")
        out[i] = row
    return out


def _which(jid: str, i: str, choice: str) -> int:
    """Maps an adjudication choice back to 0 (the first pass given) or 1."""
    flip = int(_sha(f"S56-silver:{jid}:C:{i}")[:2], 16) % 2 != 0
    k = 0 if choice == "1" else 1
    return 1 - k if flip else k


# ============================================================================================ the state machine
def _run_pass(job: dict, label: str, items: list[str], *, kind: str = "label", context_source=None, pair=None,
              run: bool, model: str, claude: list[str] | None, root: Path | None, jobs_dir: Path | None,
              projects_dir: Path | None) -> dict:
    """Bring one pass to completion (SG3 technical / format recovery). Returns {"done": bool, "stop": str|None, ...}."""
    jid, task = job["job_id"], job["task"]
    plan = _plan_pass(jid, label, items, kind, context_source is not None, jobs_dir)
    st = pass_state(jid, label, jobs_dir)
    todo_missing = list(st["missing"])
    todo_invalid = [i for i in st["invalid"] if st["format_reruns"].get(i, 0) < MAX_FORMAT_RERUNS]
    if not todo_missing and not todo_invalid:
        return {"done": True, "stop": None, "state": st}
    if todo_missing:
        over = [i for i in todo_missing if st["tried"].get(i, 0) >= MAX_TECH_ATTEMPTS]
        if over:
            return {"done": False, "stop": f"pass {label}: {len(over)} items still have no usable labels after "
                                           f"{MAX_TECH_ATTEMPTS} isolated attempts (technical failure or breach)", "state": st}
        batch, msg, frerun = todo_missing, "", False
    else:
        batch, frerun = todo_invalid, True
        probs = {}
        d = job_dir(jid, jobs_dir) / "passes" / label
        for pj in d.glob("a*/c*/problems.json"):
            probs.update(read_json(pj)["problems"])
        msg = "Your previous answers for these items failed the format/consistency check: " + " | ".join(
            f"{i}: {'; '.join(probs.get(i, []))}" for i in batch)
    attempt = 1 + max([int(p.name[1:]) for p in (job_dir(jid, jobs_dir) / "passes" / label).glob("a*")] or [0])
    ctx = add_context(job, batch, context_source) if context_source is not None else None
    ans = None
    if pair is not None:
        ans = _pair_answers(jid, batch, pair[0], pair[1])
    size = TASKS[task]["chunk"]
    wss = []
    for k in range(0, len(batch), size):
        chunk_ids = batch[k:k + size]
        ws = build_workspace(job, label, chunk_ids, attempt=attempt, chunk=k // size, kind=kind,
                             context={i: ctx[i] for i in chunk_ids} if ctx else None,
                             answers={i: ans[i] for i in chunk_ids} if ans else None, message=msg, root=root,
                             jobs_dir=jobs_dir, projects_dir=projects_dir)
        if frerun:
            m = read_json(ws / "WORKSPACE.json")
            m["format_rerun"] = True
            atomic_write_json(m, ws / "WORKSPACE.json")
        wss.append(ws)
    if not run:
        return {"done": False, "stop": None, "built": [str(w) for w in wss], "state": st,
                "launch": [claude_command(w, model=model, claude=claude) for w in wss]}
    results = []
    for ws in wss:
        run_workspace(ws, model=model, claude=claude)
        results.append(collect(ws, jobs_dir=jobs_dir, projects_dir=projects_dir))
    return {"done": False, "stop": None, "ran": results, "state": pass_state(jid, label, jobs_dir)}


def _sentence_assemble(job: dict, st: dict[str, dict]) -> tuple[dict, dict]:
    """The final rows and statuses from the pass states (deterministic; SG3 table)."""
    jid = job["job_id"]
    A, B = st["A"]["labels"], st["B"]["labels"]
    final, status = {}, {}
    for x in job["items"]:
        i = x["id"]
        a, b = A.get(i), B.get(i)
        if a is None or b is None:
            r = a or b
            final[i] = {**(r or {}), "abstain_reason": "qc_format"} if r else {"item_id": i, "abstain_reason": "qc_format"}
            status[i] = "abstained"
            continue
        if same_decision(a, b):
            final[i] = {**a, "pps": "; ".join(sorted(set(filter(None, a["pps"].split("; "))) & set(filter(None, b["pps"].split("; "))))),
                        "confidence": _min_conf(a["confidence"], b["confidence"])}
            status[i] = "agreed"
            continue
        a2, b2 = st.get("A2", {}).get("labels", {}).get(i), st.get("B2", {}).get("labels", {}).get(i)
        if a2 is not None and b2 is not None and same_decision(a2, b2):
            final[i] = {**a2, "confidence": _min_conf(a2["confidence"], b2["confidence"])}
            status[i] = "agreed_ctx"
            continue
        c = st.get("C", {}).get("labels", {}).get(i)
        if c is not None and c["choice"] in ("1", "2") and a2 is not None and b2 is not None:
            final[i] = {**(a2, b2)[_which(jid, i, c["choice"])], "confidence": c["confidence"]}
            status[i] = "adjudicated"
            continue
        same_t = a["is_target_verb"] if a["is_target_verb"] == b["is_target_verb"] else "?"
        final[i] = {"item_id": i, "is_target_verb": same_t, "locative": "?" if same_t == "Y" else "",
                    "frame": "AMBIGUOUS" if same_t == "Y" else "", "abstain_reason": (c or {}).get("reason") or "passes disagree"}
        status[i] = "abstained"
    a3s, b3s = st.get("A3", {}).get("labels", {}), st.get("B3", {}).get("labels", {})
    for i in list(final):
        if status[i] == "agreed" and is_abstention(final[i]) and i in a3s and i in b3s:
            a3, b3 = a3s[i], b3s[i]
            if same_decision(a3, b3) and not is_abstention(a3):
                final[i] = {**a3, "confidence": _min_conf(a3["confidence"], b3["confidence"])}
                status[i] = "agreed_ctx"
    return final, status


def _sentence_qc(job: dict, st: dict, final: dict, status: dict) -> dict:
    A, B = st["A"]["labels"], st["B"]["labels"]
    both = sorted(set(A) & set(B))
    agree_items = [i for i in both if next(x for x in job["items"] if x["id"] == i)["private"].get("agreement")]

    def kap(ids, f):
        return kappa_ci([f(A[i]) for i in ids], [f(B[i]) for i in ids])

    fields = {"is_target_verb": lambda r: r["is_target_verb"], "locative": lambda r: r.get("locative", ""), "frame": frame_cat}
    n = len(job["items"])
    abst = [i for i in final if is_abstention({**final[i], "silver_status": status[i]})]
    qc_format = [i for i in final if (final[i].get("abstain_reason") == "qc_format")]
    by_status = {}
    for s in status.values():
        by_status[s] = by_status.get(s, 0) + 1
    qc = {"n_items": n, "first_run_pairs": len(both),
          "kappa_first_run": {k: kap(both, f) for k, f in fields.items()},
          "kappa_agreement_items": {k: kap(agree_items, f) for k, f in fields.items()} if agree_items else None,
          "status": by_status, "abstained": len(abst), "abstention_share": round(len(abst) / n, 4) if n else None,
          "qc_format": len(qc_format), "qc_format_share": round(len(qc_format) / n, 4) if n else None,
          "breaches": {k: v["breaches"] for k, v in st.items()},
          "thresholds": {"kappa_frame_min": KAPPA_FRAME_MIN, "abstention_max": ABSTENTION_MAX, "qc_format_max": QC_FORMAT_MAX}}
    stops = []
    kf = qc["kappa_first_run"]["frame"]["kappa"]
    if kf is not None and kf < KAPPA_FRAME_MIN:
        stops.append(f"T4: frame kappa between the first-run passes {kf} < {KAPPA_FRAME_MIN}")
    if qc["qc_format_share"] and qc["qc_format_share"] > QC_FORMAT_MAX:
        stops.append(f"T5: {qc['qc_format_share']:.1%} of the items failed the format/consistency check (> {QC_FORMAT_MAX:.0%})")
    if qc["abstention_share"] and qc["abstention_share"] > ABSTENTION_MAX:
        stops.append(f"abstention {qc['abstention_share']:.1%} > {ABSTENTION_MAX:.0%} after the context recovery")
    qc["stops"] = stops
    return qc


def step(jid: str, *, source=None, run: bool = True, model: str = DEFAULT_MODEL, claude: list[str] | None = None,
         root: Path | None = None, jobs_dir: Path | None = None, projects_dir: Path | None = None) -> dict:
    """Do the NEXT automatic step of a job (build and run one pass, or finalize). Call it until it returns
    ``finalized`` or ``STOP``. Every decision follows the pre-registered table (SG3)."""
    _require_open(jid, jobs_dir)
    job = load_job(jid, jobs_dir)
    task = job["task"]
    ids = [x["id"] for x in job["items"]]
    kw = dict(run=run, model=model, claude=claude, root=root, jobs_dir=jobs_dir, projects_dir=projects_dir)

    def go(label, items, **k):
        r = _run_pass(job, label, items, **kw, **k)
        if r["stop"]:
            return {"action": "STOP", "reason": r["stop"], **_stop(job, [r["stop"]], jobs_dir)}
        if not r["done"]:
            return {"action": f"pass {label}", **{k2: v for k2, v in r.items() if k2 != "state"}}
        return None

    if task == "worked":
        res = go("A", ids)
        if res:
            return res
        st = pass_state(jid, "A", jobs_dir)
        exp = {x["id"]: x["private"]["expected_frame"] for x in job["items"]}
        wrong = [i for i in ids if frame_cat(st["labels"].get(i, {})) != exp[i]]
        if wrong:
            d = job_dir(jid, jobs_dir) / "passes"
            n_att = 1 + len(list(d.glob("A-attempt*")))
            if n_att < WORKED_ATTEMPTS:
                # one fresh rerun of ALL items in new workspaces (the failed attempt is kept on file, renamed)
                (d / "A").rename(d / f"A-attempt{n_att}")
                return {"action": "rerun worked examples", "wrong": len(wrong)}
            return {"action": "STOP", **_stop(job, [f"T3: worked examples {len(ids) - len(wrong)}/{len(ids)} after "
                                                    f"{WORKED_ATTEMPTS} attempts"], jobs_dir)}
        return finalize(jid, jobs_dir=jobs_dir)

    for label in TASKS[task]["passes"]:
        res = go(label, ids)
        if res:
            return res
    if task_kind(task) != "sentence":
        return finalize(jid, jobs_dir=jobs_dir)
    A, B = pass_state(jid, "A", jobs_dir)["labels"], pass_state(jid, "B", jobs_dir)["labels"]
    dis = [i for i in ids if i in A and i in B and not same_decision(A[i], B[i])]
    if dis:
        for label in ("A2", "B2"):
            res = go(label, dis, context_source=source)
            if res:
                return res
        A2, B2 = pass_state(jid, "A2", jobs_dir)["labels"], pass_state(jid, "B2", jobs_dir)["labels"]
        rest = [i for i in dis if i in A2 and i in B2 and not same_decision(A2[i], B2[i])]
        if rest:
            res = go("C", rest, kind="adjudicate", context_source=source, pair=(A2, B2))
            if res:
                return res
    st = {lb: pass_state(jid, lb, jobs_dir) for lb in ("A", "B", "A2", "B2", "C", "A3", "B3")}
    final, status = _sentence_assemble(job, st)
    abst = [i for i in final if is_abstention({**final[i], "silver_status": status[i]})]
    # abstention recovery (SG3): once triggered (> 30%), the context passes A3 / B3 run on every item both first-run
    # passes abstained on; their plan is fixed at the first trigger, so later calls only complete them
    if (ids and len(abst) / len(ids) > ABSTENTION_MAX) or st["A3"]["plan"]:
        eligible = [i for i in abst if status[i] == "agreed"]
        if eligible or st["A3"]["plan"]:
            for label in ("A3", "B3"):
                res = go(label, eligible, context_source=source)
                if res:
                    return res
    return finalize(jid, jobs_dir=jobs_dir)


# ============================================================================================ finalize + freeze (SG2)
def _stop(job: dict, reasons: list[str], jobs_dir: Path | None, qc: dict | None = None) -> dict:
    d = job_dir(job["job_id"], jobs_dir)
    lines = [f"# QC STOP: {job['job_id']}", "", f"When: {_now()}", "", "## Why", *[f"- {r}" for r in reasons]]
    if qc:
        lines += ["", "## QC numbers", "```json", json.dumps({k: v for k, v in qc.items() if k != "stops"}, indent=2,
                                                            ensure_ascii=False), "```"]
    lines += ["", "## Project-level options (Ori decides; never human row labelling)",
              "1. Accept the split with its reliability stated (`loc silver finalize --accept-stop <decision id>`).",
              "2. Restrict the primary analysis to `agreed` items (recorded in the decision; the file is unchanged).",
              "3. A protocol revision: only for splits not yet annotated, and dev only if no dev silver has been read.",
              "4. Drop the split from the primary result (reported).", "",
              "Nothing proceeds until Ori decides. Every pass and attempt stays on file."]
    atomic_write_text("\n".join(lines) + "\n", d / "QC_STOP.md")
    return {"stop_file": str(d / "QC_STOP.md"), "reasons": reasons}


def _freeze(jid: str, files: list[Path], qc: dict, jobs_dir: Path | None, accept_stop: str | None) -> dict:
    d = job_dir(jid, jobs_dir)
    from hebloc.loc.manifest import git_state

    rec = {"job_id": jid, "frozen_at": _now(), "silver_version": SILVER_VERSION, "protocol_version": PROTOCOL_VERSION,
           "protocol_sha256": file_sha256(PROTOCOL_PATH), "guideline_sha256": file_sha256(GUIDELINE_PATH),
           "prompts_sha256": {p.name: file_sha256(p) for p in sorted(PROMPTS_DIR.glob("*.md"))},
           "git": git_state(), "files": {str(p.relative_to(d)).replace("\\", "/"): file_sha256(p) for p in files},
           "qc_sha256": file_sha256(d / "qc.json"), "accepted_stop": accept_stop}
    atomic_write_json(rec, d / "FROZEN.json")
    return rec


def finalize(jid: str, *, jobs_dir: Path | None = None, accept_stop: str | None = None) -> dict:
    _require_open(jid, jobs_dir)
    job = load_job(jid, jobs_dir)
    task, d = job["task"], job_dir(jid, jobs_dir)
    fin = d / "final"
    qc_id = None
    if task_kind(task) == "sentence":
        st = {lb: pass_state(jid, lb, jobs_dir) for lb in ("A", "B", "A2", "B2", "C", "A3", "B3")}
        if task == "worked":
            lab = st["A"]["labels"]
            exp = {x["id"]: x["private"]["expected_frame"] for x in job["items"]}
            ok = sum(1 for i in exp if frame_cat(lab.get(i, {})) == exp[i])
            qc = {"worked_examples": f"{ok}/{len(exp)}", "ok": ok == len(exp), "stops": [] if ok == len(exp) else ["T3"],
                  "note": "a COMPLIANCE check (the answers are in the guideline), not a validity check"}
            final, status = {i: lab.get(i, {}) for i in exp}, {i: "single_pass" for i in exp}
        else:
            final, status = _sentence_assemble(job, st)
            qc = _sentence_qc(job, st, final, status)
        rows = []
        for x in job["items"]:
            i, pv = x["id"], x["private"]
            r = final[i]
            rows.append({"sample_id": pv.get("sample_id", ""), "item_id": i, "instance_key": pv.get("instance_key", ""),
                         "split": pv.get("split", ""), "stratum": pv.get("stratum", ""), "agreement": pv.get("agreement", ""),
                         "annotator": "claude_code", "label_source": "ai", "silver_version": SILVER_VERSION,
                         "protocol_version": PROTOCOL_VERSION, "guideline_version": "S56-v1-g1",
                         **{c: r.get(c, "") for c in SENTENCE_FIELDS if c != "notes"}, "has_notes": bool(r.get("notes")),
                         "silver_status": status[i], "confidence": r.get("confidence", ""),
                         "evidence_rule": r.get("evidence_rule", ""), "abstain_reason": r.get("abstain_reason", "")})
        name = f"{job['corpus']}_{job['split']}_silver.csv" if task == "sentence" else f"{jid}_silver.csv"
        cols = list(rows[0])
        _write_csv_text(fin / name, cols, rows)
        out_files = [fin / name]
    else:
        st = {lb: pass_state(jid, lb, jobs_dir) for lb in TASKS[task]["passes"]}
        out_files, qc = _finalize_lemma_task(job, st, fin)
    qc["job_id"] = jid
    atomic_write_json(qc, d / "qc.json")
    if qc.get("stops") and not accept_stop:
        return {"action": "STOP", **_stop(job, qc["stops"], jobs_dir, qc), "qc": qc}
    rec = _freeze(jid, out_files, qc, jobs_dir, accept_stop)
    return {"action": "finalized", "job_id": jid, "files": rec["files"], "qc": qc}


def _finalize_lemma_task(job: dict, st: dict, fin: Path) -> tuple[list[Path], dict]:
    jid, task = job["job_id"], job["task"]
    ids = [x["id"] for x in job["items"]]
    A = st["A"]["labels"]
    B = st.get("B", {}).get("labels", {})
    qc_id = f"{jid}-{_sha(json.dumps([A, B], sort_keys=True, ensure_ascii=False))[:12]}"
    rows = []
    if task == "noun":
        for x in job["items"]:
            i = x["id"]
            a, b = A.get(i), B.get(i)
            agree = a and b and a["type"] == b["type"] and "low" not in (a["confidence"], b["confidence"])
            t = a["type"] if agree else "UNCLEAR"
            rows.append({"lemma": i, "type": t, "corpus_source": x["private"].get("corpus_source") or job["corpus"],
                         "proposed_by": "claude_code", "reviewed_by": f"auto-qc:{qc_id}", "review_mode": "automated",
                         "silver_status": "agreed" if agree else "abstained",
                         "note": f"A={(a or {}).get('type', '-')}/{(a or {}).get('confidence', '-')}; "
                                 f"B={(b or {}).get('type', '-')}/{(b or {}).get('confidence', '-')}"})
        both = [i for i in ids if i in A and i in B]
        qc = {"kappa_type": kappa_ci([A[i]["type"] for i in both], [B[i]["type"] for i in both]),
              "types": {t: sum(1 for r in rows if r["type"] == t) for t in NOUN_TYPES},
              "abstained_unclear": sum(1 for r in rows if r["silver_status"] == "abstained")}
        name = f"noun_types_{job['corpus']}.csv"
    elif task == "unit":
        for x in job["items"]:
            i = x["id"]
            a, b = A.get(i), B.get(i)
            agree = (a and b and a["decision"] == b["decision"] == "accept" and a["base"] == b["base"]
                     and "low" not in (a["confidence"], b["confidence"]))
            rows.append({"lemma": i, "decision": "accept" if agree else "reject", "base": a["base"] if agree else "",
                         "proposed_by": "claude_code", "reviewed_by": f"auto-qc:{qc_id}", "review_mode": "automated",
                         "silver_status": "agreed" if (a and b and a["decision"] == b["decision"]) else "abstained",
                         "note": f"A={(a or {}).get('decision', '-')}:{(a or {}).get('base', '')}/{(a or {}).get('confidence', '-')}; "
                                 f"B={(b or {}).get('decision', '-')}:{(b or {}).get('base', '')}/{(b or {}).get('confidence', '-')}"})
        both = [i for i in ids if i in A and i in B]
        qc = {"kappa_decision": kappa_ci([A[i]["decision"] for i in both], [B[i]["decision"] for i in both]),
              "accepted": sum(1 for r in rows if r["decision"] == "accept"), "rejected_or_no_link": sum(1 for r in rows if r["decision"] == "reject"),
              "rule": "a link only when both passes accept the same base and neither has low confidence (D-061 D-j)"}
        name = "unit_review_automated.csv"
    elif task == "variant":
        for x in job["items"]:
            i = x["id"]
            a, b = A.get(i, {}), B.get(i, {})
            agree = a and b and (a.get("decision"), a.get("entry")) == (b.get("decision"), b.get("entry"))
            rows.append({"lemma": i, "decision_a": a.get("decision", ""), "entry_a": a.get("entry", ""), "voice_a": a.get("voice", ""),
                         "decision_b": b.get("decision", ""), "entry_b": b.get("entry", ""), "voice_b": b.get("voice", ""),
                         "agree": bool(agree), "suggestion": f"{a.get('decision')}:{a.get('entry')}" if agree else "undecided",
                         "label_source": "ai", "use": "evidence for Phase C I-1 only (lexicon-v2 is Ori's decision)"})
        qc = {"agree": sum(1 for r in rows if r["agree"]), "n": len(rows)}
        name = "paper_variants_evidence.csv"
    else:   # audit
        for x in job["items"]:
            i = x["id"]
            a = A.get(i, {})
            rows.append({"lemma": i, "correct": a.get("correct", ""), "reviewed_by": f"auto-qc:{qc_id}",
                         "review_mode": "automated", "confidence": a.get("confidence", ""), "note": "AI audit (silver), not validation"})
        qc = {"correct": sum(1 for r in rows if r["correct"] == "Y"), "n": len(rows),
              "missing": sum(1 for r in rows if not r["correct"])}
        name = "audit_automated.csv"
    qc.update({"qc_id": qc_id, "n_items": len(ids), "stops": [], "label_source": "ai"})
    missing = [i for i in ids if i not in A or (TASKS[task]["passes"] == ("A", "B") and i not in B)]
    qc["no_valid_label"] = len(missing)
    _write_csv_text(fin / name, list(rows[0]), rows)
    qc["final_sha256"] = file_sha256(fin / name)
    return [fin / name], qc


# ============================================================================================ delivery / receipt
def deliver(job_ids: list[str], outbox: Path, *, who: str, jobs_dir: Path | None = None) -> dict:
    """Copy FROZEN jobs (final file, pass label files, QC, access logs: no input texts) to an outbox, with
    ``DELIVERY.json`` (sha256 of every file)."""
    from hebloc.loc.manifest import git_state

    outbox = Path(outbox)
    files = {}
    for jid in job_ids:
        if not is_frozen(jid, jobs_dir):
            raise SilverError(f"job {jid} is not frozen: only frozen jobs are delivered (SG2)")
        _require_unique(jid, load_job(jid, jobs_dir))
        d = job_dir(jid, jobs_dir)
        dest = outbox / "silver" / jid
        for p in sorted(d.rglob("*")):
            rel = p.relative_to(d)
            if not p.is_file() or rel.parts[0] in ("canary",) or p.name in ("items.json",):
                continue
            q = dest / rel
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, q)
            files[str(q.relative_to(outbox)).replace("\\", "/")] = file_sha256(q)
    doc = {"who": who, "when": _now(), "git": git_state(), "jobs": job_ids, "files": files, "label_source": "ai"}
    atomic_write_json(doc, outbox / "DELIVERY.json")
    return {"jobs": job_ids, "files": len(files), "outbox": str(outbox)}


def receive(delivery: Path, *, frozen_path: Path = FROZEN_PATH, final_dir: Path = FINAL_DIR,
            received_dir: Path = RECEIVED_DIR) -> dict:
    """Ori's side: verify a delivery by hash ONLY (no content is printed or read for development), store it, and
    record its hashes in ``annotation/silver/FROZEN_SILVER.json`` BEFORE any read (SG2)."""
    delivery = Path(delivery)
    doc = read_json(delivery / "DELIVERY.json")
    probs = [f for f, h in doc["files"].items() if not (delivery / f).exists() or file_sha256(delivery / f) != h]
    if probs:
        raise SilverError(f"delivery hash mismatch: {probs[:5]}")
    frozen = read_json(frozen_path) if Path(frozen_path).exists() else {"meta": {"rule": "SG2: recorded before any read; never revised"}, "jobs": {}}
    out = {}
    for jid in doc["jobs"]:
        src = delivery / "silver" / jid
        fz = read_json(src / "FROZEN.json")
        for rel, h in fz["files"].items():
            if file_sha256(src / rel) != h:
                raise SilverError(f"{jid}: {rel} does not match its FROZEN.json")
        if jid in frozen["jobs"] and frozen["jobs"][jid]["files"] != fz["files"]:
            raise SilverError(f"{jid} was already received with different hashes: refused (silver is never revised)")
        dst = Path(received_dir) / jid
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        placed = {}
        for rel in fz["files"]:
            name = Path(rel).name
            if jid.startswith("sentence-"):
                split = jid.split("-")[-1]
                target = Path(final_dir) / split / name
            else:
                target = Path(final_dir) / "other" / jid / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src / rel, target)
            placed[name] = file_sha256(target)
        frozen["jobs"][jid] = {"files": fz["files"], "placed": placed, "frozen_at": fz["frozen_at"],
                               "received_at": _now(), "delivery_sha256": file_sha256(delivery / "DELIVERY.json"),
                               "protocol_sha256": fz["protocol_sha256"], "accepted_stop": fz.get("accepted_stop")}
        out[jid] = {"files": len(fz["files"])}
    atomic_write_json(frozen, frozen_path)
    return {"received": out, "frozen_record": str(frozen_path)}


def frozen_file_ok(path: Path, frozen_path: Path = FROZEN_PATH) -> tuple[bool, str]:
    """Is ``path`` a received SILVER file whose hash is recorded in FROZEN_SILVER.json?"""
    if not Path(frozen_path).exists():
        return False, "no FROZEN_SILVER.json"
    frozen = read_json(frozen_path)
    h = file_sha256(path)
    for jid, rec in frozen.get("jobs", {}).items():
        if rec.get("placed", {}).get(Path(path).name) == h:
            return True, jid
    return False, f"{Path(path).name}: hash not recorded in FROZEN_SILVER.json (SG2)"


def check_automated(reviewed_csv: Path, job_folder: Path) -> tuple[str | None, list[str]]:
    """For ``--automated`` merges (nouns, unit links, the audit): the CSV must be the frozen final file of a SILVER job
    (its sha256 is in the job's FROZEN.json) and every row must carry ``reviewed_by = auto-qc:<qc_id>``."""
    job_folder = Path(job_folder)
    probs = []
    if not (job_folder / "FROZEN.json").exists() or not (job_folder / "qc.json").exists():
        return None, [f"{job_folder}: not a frozen SILVER job folder (FROZEN.json + qc.json)"]
    fz, qc = read_json(job_folder / "FROZEN.json"), read_json(job_folder / "qc.json")
    if file_sha256(Path(reviewed_csv)) not in set(fz["files"].values()):
        probs.append(f"{reviewed_csv} is not the frozen final file of {fz['job_id']} (hash differs): refused (SG2)")
    if qc.get("stops") and not fz.get("accepted_stop"):
        probs.append(f"{fz['job_id']} has unresolved QC STOPs")
    qc_id = qc.get("qc_id")
    lem: dict[str, int] = {}
    for r in _read_csv(reviewed_csv):
        lem[r.get("lemma")] = lem.get(r.get("lemma"), 0) + 1
    dup = sorted(k for k, v in lem.items() if v > 1)
    if dup:
        probs.append(f"{fz['job_id']}: {len(dup)} lemmas occur in more than one row (a job made before D-062): never "
                     "merged")
    for i, r in enumerate(_read_csv(reviewed_csv), 2):
        if (r.get("reviewed_by") or "").strip() != f"auto-qc:{qc_id}" or (r.get("review_mode") or "").strip() != "automated":
            probs.append(f"line {i}: reviewed_by must be auto-qc:{qc_id} with review_mode automated")
            break
    return qc_id, probs


# ============================================================================================ anchor agreement
def anchor_agreement(anchor_silver: Path, paper_key: Path, anchor_ids: Path = ANCHOR_IDS_PATH) -> dict:
    """Agreement of the frozen anchor SILVER with the paper's own frames (Mikra; an UPPER bound: the annotator model
    has read the paper). Reported with a Wilson 95% interval and by confidence; never used to tune the protocol."""
    from hebloc.stats.accuracy import wilson

    ids = {r["anchor_id"]: r["instance_key"] for r in _read_csv(anchor_ids)}
    key = {}
    for r in _read_csv(paper_key):
        if r.get("status") == "dev" and r.get("instance_key"):
            key.setdefault(r["instance_key"], set()).add(r["frame"])
    ok, n, by_conf, abst = 0, 0, {}, 0
    for r in _read_csv(anchor_silver):
        ik = ids.get(r["item_id"])
        if ik not in key or len(key[ik]) != 1:
            continue
        if is_abstention(r):
            abst += 1
            continue
        n += 1
        hit = frame_cat(r) == next(iter(key[ik]))
        ok += hit
        c = by_conf.setdefault(r.get("confidence") or "-", [0, 0])
        c[0] += hit
        c[1] += 1
    p = ok / n if n else float("nan")
    return {"measure": "agreement of SILVER with the paper's own frames (upper bound; not validated accuracy)",
            "n": n, "agree": ok, "share": round(p, 4) if n else None, "wilson95": wilson(p, n) if n else None,
            "abstained": abst, "by_confidence": {k: {"agree": v[0], "n": v[1]} for k, v in by_conf.items()}}


# ============================================================================================ isolation self-test
def isolation_test(*, root: Path | None = None, model: str = "haiku", claude: list[str] | None = None,
                   jobs_dir: Path | None = None, projects_dir: Path | None = None) -> dict:
    """SG1 check on this computer: a dummy workspace (synthetic text, no corpus) whose session must be DENIED both
    canary reads. Run before the first real pass on each computer."""
    jid = "isolation-test"
    d = job_dir(jid, jobs_dir)
    doc = {"job_id": jid, "task": "audit", "corpus": None, "split": None, "created": _now(), "inputs": {},
           "items": [{"id": "test-lemma", "blind": {"item_id": "test-lemma", "base": "test-base", "n": "1",
                                                     "pres_share": "1", "fin_share": "0", "examples": "a synthetic example"},
                      "private": {}}]}
    atomic_write_json({**doc, "items_sha256": "test"}, d / "items.json")
    ws = build_workspace(doc, "T", ["test-lemma"], attempt=1 + len(list((d / "passes" / "T").glob("a*"))), chunk=0,
                         root=root, jobs_dir=jobs_dir, projects_dir=projects_dir)
    info = run_workspace(ws, model=model, claude=claude, timeout=900)
    r = collect(ws, jobs_dir=jobs_dir, projects_dir=projects_dir)
    meta = read_json(ws / "WORKSPACE.json")
    acc = read_json(d / "passes" / "T" / f"a{meta['attempt']}" / "c00" / "access.json")
    return {"ok": r["status"] == "ok" and bool(r["preflight_ok"]), "workspace": str(ws), "run": info,
            "preflight": acc.get("preflight"), "violations": acc.get("violations"),
            "calls": [{k: c[k] for k in ("tool", "inside", "error")} for c in acc.get("calls", [])]}
