"""SILVER annotation (D-061; annotation/S56_SILVER_PROTOCOL.md): isolated workspaces (SG1), freeze and hashes (SG2),
the pre-registered recovery (SG3), the deterministic decisions, and that silver is never presented as human gold.

A FAKE `claude` executable stands in for the model: it writes labels and a session transcript in the real format,
so the whole pipeline runs without any model call."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hebloc.loc import gold as G
from hebloc.loc import nouns as N
from hebloc.loc import score as S
from hebloc.loc import silver as SV
from hebloc.paths import ROOT

FAKE = r'''
import csv, json, os, sys, uuid
from pathlib import Path
ws = Path.cwd()
meta = json.loads((ws / "WORKSPACE.json").read_text(encoding="utf-8"))
mode = os.environ.get("FAKE_MODE", "agree")
proj = Path(os.environ["FAKE_PROJECTS"]) / "proj"
proj.mkdir(parents=True, exist_ok=True)
sid = uuid.uuid4().hex
ev = []
def call(i, name, path, err, content=""):
    ev.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": i, "name": name, "input": {"file_path": path}}]}})
    ev.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": i, "is_error": err, "content": content}]}})
if mode == "limit":     # D-063: the client refuses the launch (usage limit) before any tool call
    with open(proj / f"{sid}.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "user", "message": {"role": "user", "content": "Read CLAUDE.md"}}) + "\n")
        f.write(json.dumps({"type": "assistant", "isApiErrorMessage": True, "error": "rate_limit",
                            "message": {"model": "<synthetic>", "role": "assistant",
                                        "content": [{"type": "text", "text": "You've hit your session limit"}]}}) + "\n")
    print(json.dumps({"session_id": sid, "is_error": True, "num_turns": 1}))
    sys.exit(1)
c1, c2 = meta["canary"]["repo"], meta["canary"]["sibling"]
if mode == "breach":
    call("t1", "Read", c1, False, Path(c1).read_text())
else:
    call("t1", "Read", c1, True, "denied")
call("t2", "Read", c2, True, "denied")
call("t3", "Read", str(ws / "input.csv"), False, "ok")
if mode == "outside":
    call("t9", "Read", os.environ["FAKE_OUTSIDE"], False, "secret")
rows = list(csv.DictReader(open(ws / "input.csv", encoding="utf-8-sig")))
label, out = meta["pass"], []
for r in rows:
    i = r["item_id"]
    if meta["kind"] == "adjudicate":
        out.append({"item_id": i, "choice": "1", "confidence": "high", "evidence_rule": "3.5", "reason": "x"})
    elif meta["task"] in ("sentence", "anchor", "worked", "instances"):
        if mode == "invalid":
            out.append({"item_id": i, "is_target_verb": "X", "confidence": "high"})
            continue
        frame, loc, why = os.environ.get("FAKE_FRAME", "A"), "Y", ""
        if mode in ("disagree", "kappa") and label == "B":
            frame = "B"
        if mode == "disagree" and label == "B2":
            frame = "B"
        if mode == "abstain" and label in ("A", "B"):
            frame, loc, why = "AMBIGUOUS", "?", "unclear"
        out.append({"item_id": i, "is_target_verb": "Y", "locative": loc, "frame": frame, "confidence": "high",
                    "evidence_rule": "3.5", "abstain_reason": why})
    elif meta["task"] == "noun":
        t = "LOCATUM" if (mode == "disagree" and label == "B" and i.endswith("2")) else "LOCATION"
        out.append({"item_id": i, "type": t, "confidence": "high", "evidence": "x"})
    elif meta["task"] == "unit":
        base = r["candidates"].split(" (")[0]
        dec = "reject" if (mode == "disagree" and label == "B" and i.endswith("2")) else "accept"
        out.append({"item_id": i, "decision": dec, "base": base if dec == "accept" else "", "confidence": "high", "evidence": "x"})
    elif meta["task"] == "audit":
        out.append({"item_id": i, "correct": "Y", "confidence": "high", "evidence": "x"})
    elif meta["task"] == "template":
        t = "Intensive" if (mode == "disagree" and label == "B") else "Causative"
        out.append({"item_id": i, "template": t, "confidence": "high", "evidence": "x"})
(ws / "out").mkdir(exist_ok=True)
with open(ws / "out" / "labels.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=meta["out_columns"], extrasaction="ignore")
    w.writeheader()
    w.writerows(out)
call("t4", "Write", str(ws / "out" / "labels.csv"), False, "ok")
with open(proj / f"{sid}.jsonl", "w", encoding="utf-8") as f:
    for e in ev:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
print(json.dumps({"session_id": sid, "is_error": False, "num_turns": 4}))
'''


@pytest.fixture()
def sw(tmp_path, monkeypatch):
    """A synthetic frozen sample (4 items, one agreement item) and a fake `claude`."""
    fake = tmp_path / "fake_claude.py"
    fake.write_text(FAKE, encoding="utf-8")
    monkeypatch.setenv("FAKE_PROJECTS", str(tmp_path / "projects"))
    monkeypatch.setattr(SV, "CANARY_DIR", tmp_path / "repo_data" / "canary")
    sdir = tmp_path / "sample"
    (sdir / "sheets").mkdir(parents=True)
    items = [{"sample_id": "mikra-test", "item_id": f"MI000{k}", "instance_key": f"mikra:d0:{k}:0|0|1", "split": "dev",
              "stratum": "B", "agreement": k == 1, "members": ["מלא.I"], "verb_key": "מלא.I", "sent_id": f"mikra:d0:{k}:0",
              "doc_id": "d0"} for k in range(1, 5)]
    pq.write_table(pa.Table.from_pylist(items), sdir / "sample.parquet")
    with open(sdir / "sheets" / "dev.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item_id", "split", "agreement", "stratum", "where", "verb_key", "target", "sentence", "words"]
                   + list(G.ANNOTATION_COLUMNS))
        for x in items:
            w.writerow([x["item_id"], "dev", "Y" if x["agreement"] else "", "B", "Genesis 1:1", "מלא.I", "מילא",
                        "דני [[מילא]] את הכד במים", "0:דני 1:מילא 2:את 3:הכד 4:במים"] + [""] * len(G.ANNOTATION_COLUMNS))
    jobs = tmp_path / "jobs"
    kw = dict(jobs_dir=jobs, root=tmp_path / "ws", projects_dir=tmp_path / "projects",
              claude=[sys.executable, str(fake)])
    return {"tmp": tmp_path, "sdir": sdir, "jobs": jobs, "kw": kw}


def _create(w, corpus="mikra", split="dev"):
    return SV.create_job("sentence", corpus, split, sample_dir=w["sdir"], jobs_dir=w["jobs"])


def _run(w, jid, limit=20):
    r = None
    for _ in range(limit):
        r = SV.step(jid, **w["kw"])
        if r["action"] in ("finalized", "STOP"):
            return r
    raise AssertionError(f"no end after {limit} steps: {r}")


# ============================================================================================ SG1 isolation
def test_blind_workspace_holds_only_the_allowed_files(sw):
    jid = _create(sw)["job_id"]
    job = SV.load_job(jid, sw["jobs"])
    ws = SV.build_workspace(job, "A", [x["id"] for x in job["items"]], attempt=1, chunk=0, root=sw["tmp"] / "ws",
                            jobs_dir=sw["jobs"])
    files = sorted(str(p.relative_to(ws)).replace("\\", "/") for p in ws.rglob("*") if p.is_file())
    assert files == [".claude/settings.json", "CLAUDE.md", "PROMPT.md", "S56_GUIDELINE.md", "S56_SILVER_PROTOCOL.md",
                     "WORKSPACE.json", "input.csv"]
    header = (ws / "input.csv").read_text(encoding="utf-8-sig").splitlines()[0]
    assert header == "item_id,verb_key,verb_entries,target,sentence,words"
    for hidden in ("stratum", "where", "split", "agreement", "Genesis", "instance_key", "sample_id"):
        assert hidden not in (ws / "input.csv").read_text(encoding="utf-8-sig")
    meta = json.loads((ws / "WORKSPACE.json").read_text(encoding="utf-8"))
    assert "token" not in json.dumps(meta).lower().replace("token_sha256", "")       # the canary token is never in the workspace
    deny = json.loads((ws / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]
    assert {"Bash", "WebFetch", "WebSearch", "Agent"} <= set(deny)
    assert f"Read({SV._rule_path(ROOT)}/**)" in deny and f"Edit({SV._rule_path(ROOT)}/**)" in deny
    assert not any(x.startswith("Write(") for x in deny)
    cmd = SV.claude_command(ws, claude=["claude"])
    assert {"--restricted", "--strict-mcp-config", "--settings", "--permission-prompts"} <= set(cmd)
    assert cmd[cmd.index("--permission-prompts") + 1] == "none"


def test_workspace_root_inside_the_repo_is_refused(sw):
    jid = _create(sw)["job_id"]
    job = SV.load_job(jid, sw["jobs"])
    with pytest.raises(SV.SilverError):
        SV.build_workspace(job, "A", ["MI0001"], attempt=1, chunk=0, root=ROOT / "data" / "ws", jobs_dir=sw["jobs"])


def test_access_log_flags_outside_reads_and_canary_reads(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    c1, c2 = tmp_path / "c1.txt", tmp_path / "c2.txt"
    tr = tmp_path / "t.jsonl"

    def write(events):
        tr.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")

    def call(i, path, err, content=""):
        return [{"message": {"content": [{"type": "tool_use", "id": i, "name": "Read", "input": {"file_path": str(path)}}]}},
                {"message": {"content": [{"type": "tool_result", "tool_use_id": i, "is_error": err, "content": content}]}}]

    write(call("a", c1, True) + call("b", c2, True) + call("c", ws / "input.csv", False))
    ok = SV.access_log(tr, ws, {"repo": str(c1), "sibling": str(c2)}, "CANARY-x")
    assert ok["ok"] and ok["preflight_ok"]
    write(call("a", c1, True) + call("b", c2, True) + call("c", tmp_path / "secret.txt", False))
    bad = SV.access_log(tr, ws, {"repo": str(c1), "sibling": str(c2)}, "CANARY-x")
    assert not bad["ok"] and "outside the workspace" in bad["violations"][0]
    write(call("a", c1, False, "CANARY-x") + call("b", c2, True))
    br = SV.access_log(tr, ws, {"repo": str(c1), "sibling": str(c2)}, "CANARY-x")
    assert not br["ok"] and any("READ" in v for v in br["violations"])
    write(call("c", ws / "input.csv", False))
    assert not SV.access_log(tr, ws, {"repo": str(c1), "sibling": str(c2)}, "CANARY-x")["preflight_ok"]


def test_a_breach_discards_the_chunk_reruns_once_then_stops(sw, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "breach")
    jid = _create(sw)["job_id"]
    r = _run(sw, jid)
    assert r["action"] == "STOP" and "isolated attempts" in r["reason"]
    st = SV.pass_state(jid, "A", sw["jobs"])
    assert st["breaches"] == 2 and not st["labels"]                     # both breached chunks kept, none used
    stop = (sw["jobs"] / jid / "QC_STOP.md").read_text(encoding="utf-8")
    assert "never human row labelling" in stop
    assert not SV.is_frozen(jid, sw["jobs"])


def test_a_usage_limit_refusal_is_an_outage_not_an_attempt(sw, monkeypatch):
    """D-063: a launch refused by the client (usage limit, no tool call) is kept on file as an outage, is not an
    attempt, launches nothing more in that step, and never leads to a STOP; the job then completes normally."""
    monkeypatch.setitem(SV.TASKS["sentence"], "chunk", 1)              # 4 chunks: only the first may be launched
    monkeypatch.setenv("FAKE_MODE", "limit")
    jid = _create(sw)["job_id"]
    for _ in range(3):
        r = SV.step(jid, **sw["kw"])
        assert r["action"] == "WAIT" and "session limit" in r["reason"] and len(r["ran"]) == 1
        assert r["ran"][0]["status"] == "outage"
    st = SV.pass_state(jid, "A", sw["jobs"])
    assert st["outages"] == 3 and st["breaches"] == 0 and not st["tried"] and not st["labels"]
    assert not (sw["jobs"] / jid / "QC_STOP.md").exists()
    assert SV.status(jid, sw["jobs"])["passes"]["A"]["outages"] == 3
    monkeypatch.setenv("FAKE_MODE", "agree")
    assert _run(sw, jid)["action"] == "finalized"


def _as_recorded_before_d063(jobs: Path, jid: str) -> int:
    """Rewrite outage chunks the way the pre-D-063 code filed them (status breach, no outage field)."""
    n = 0
    for p in (jobs / jid / "passes").glob("*/a*/c*/access.json"):
        acc = json.loads(p.read_text(encoding="utf-8"))
        if acc.get("status") == "outage":
            acc.pop("outage")
            acc["status"] = "breach"
            p.write_text(json.dumps(acc), encoding="utf-8")
            n += 1
    return n


def test_reclassify_outages_supersedes_a_stop_caused_only_by_refusals(sw, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "limit")
    jid = _create(sw)["job_id"]
    SV.step(jid, **sw["kw"])
    SV.step(jid, **sw["kw"])
    assert _as_recorded_before_d063(sw["jobs"], jid) == 2
    r = SV.step(jid, **sw["kw"])                                         # the old classification: 2 "attempts" -> STOP
    assert r["action"] == "STOP" and (sw["jobs"] / jid / "QC_STOP.md").exists()
    rc = SV.reclassify_outages(jid, jobs_dir=sw["jobs"], projects_dir=sw["tmp"] / "projects")
    assert rc["outages"] == 2 and not rc["items_over_limit"] and rc["stop_superseded"]
    assert not (sw["jobs"] / jid / "QC_STOP.md").exists()
    assert "D-063" in Path(rc["stop_superseded"]).read_text(encoding="utf-8")
    assert len(list((sw["jobs"] / jid / "passes").glob("A/a*/c*/OUTAGE.json"))) == 2
    assert SV.reclassify_outages(jid, jobs_dir=sw["jobs"], projects_dir=sw["tmp"] / "projects")["outages"] == 0
    monkeypatch.setenv("FAKE_MODE", "agree")
    assert _run(sw, jid)["action"] == "finalized"


def test_reclassify_outages_never_turns_a_breach_into_an_outage(sw, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "breach")
    jid = _create(sw)["job_id"]
    assert _run(sw, jid)["action"] == "STOP"
    rc = SV.reclassify_outages(jid, jobs_dir=sw["jobs"], projects_dir=sw["tmp"] / "projects")
    assert rc["outages"] == 0 and rc["items_over_limit"] and not rc["stop_superseded"]
    assert (sw["jobs"] / jid / "QC_STOP.md").exists()


def test_reclassify_outages_refuses_a_changed_transcript_and_skips_a_missing_one(sw, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "limit")
    jid = _create(sw)["job_id"]
    SV.step(jid, **sw["kw"])
    _as_recorded_before_d063(sw["jobs"], jid)
    acc_p = next((sw["jobs"] / jid / "passes").glob("A/a*/c*/access.json"))
    sid = json.loads(acc_p.read_text(encoding="utf-8"))["run"]["session_id"]
    tr = sw["tmp"] / "projects" / "proj" / f"{sid}.jsonl"
    tr.write_text(tr.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(SV.SilverError):
        SV.reclassify_outages(jid, jobs_dir=sw["jobs"], projects_dir=sw["tmp"] / "projects")
    tr.unlink()
    rc = SV.reclassify_outages(jid, jobs_dir=sw["jobs"], projects_dir=sw["tmp"] / "projects")
    assert rc["outages"] == 0 and rc["skipped"][0]["why"] == "no transcript"


def test_outage_reason_needs_a_synthetic_rate_limit_and_no_tool_call(tmp_path):
    t = tmp_path / "t.jsonl"
    syn = {"type": "assistant", "isApiErrorMessage": True, "error": "rate_limit",
           "message": {"model": "<synthetic>", "content": [{"type": "text", "text": "limit"}]}}
    t.write_text(json.dumps(syn), encoding="utf-8")
    assert SV.outage_reason(t) == "limit"
    t.write_text(json.dumps({**syn, "error": "authentication_failed"}), encoding="utf-8")
    assert SV.outage_reason(t) is None
    tool = {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "x", "name": "Read", "input": {}}]}}
    t.write_text(json.dumps(tool) + "\n" + json.dumps(syn), encoding="utf-8")
    assert SV.outage_reason(t) is None
    t.write_text(json.dumps({"type": "user", "message": {"content": "hi"}}), encoding="utf-8")
    assert SV.outage_reason(t) is None
    assert SV.outage_reason(None) is None


def test_reads_outside_the_workspace_are_a_breach(sw, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_MODE", "outside")
    monkeypatch.setenv("FAKE_OUTSIDE", str(tmp_path / "resolve.py"))
    jid = _create(sw)["job_id"]
    assert _run(sw, jid)["action"] == "STOP"


# ============================================================================================ decisions + SG3
def test_agreement_path_finalizes_and_freezes(sw):
    jid = _create(sw)["job_id"]
    r = _run(sw, jid)
    assert r["action"] == "finalized"
    final = sw["jobs"] / jid / "final" / "mikra_dev_silver.csv"
    rows = list(csv.DictReader(open(final, encoding="utf-8-sig")))
    assert {x["label_source"] for x in rows} == {"ai"} and {x["silver_status"] for x in rows} == {"agreed"}
    assert {x["annotator"] for x in rows} == {"claude_code"}
    qc = json.loads((sw["jobs"] / jid / "qc.json").read_text(encoding="utf-8"))
    assert qc["kappa_first_run"]["frame"]["kappa"] == 1.0 and qc["kappa_agreement_items"]["frame"]["n"] == 1
    assert SV.is_frozen(jid, sw["jobs"])
    with pytest.raises(SV.SilverError):
        SV.step(jid, **sw["kw"])                                        # frozen: never rerun (SG2)
    with pytest.raises(SV.SilverError):
        SV.finalize(jid, jobs_dir=sw["jobs"])                           # frozen: never re-finalized


def test_disagreement_goes_to_context_then_adjudication(sw, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "disagree")
    monkeypatch.setattr(SV, "KAPPA_FRAME_MIN", -1.0)     # this test is about the path, not the T4 threshold
    jid = _create(sw)["job_id"]
    r = _run(sw, jid)
    assert r["action"] == "finalized"
    st = {lb: SV.pass_state(jid, lb, sw["jobs"]) for lb in ("A2", "B2", "C")}
    assert all(len(s["labels"]) == 4 for s in st.values())
    rows = list(csv.DictReader(open(sw["jobs"] / jid / "final" / "mikra_dev_silver.csv", encoding="utf-8-sig")))
    assert {x["silver_status"] for x in rows} == {"adjudicated"}
    # the adjudicator never sees which answer came from which pass: choice 1 maps by the fixed hash order
    assert {x["frame"] for x in rows} <= {"A", "B"}


def test_low_frame_kappa_is_a_stop_and_not_rerun(sw, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "kappa")
    jid = _create(sw)["job_id"]
    r = _run(sw, jid)
    assert r["action"] == "STOP" and any("T4" in s for s in r["reasons"])
    qc = json.loads((sw["jobs"] / jid / "qc.json").read_text(encoding="utf-8"))
    assert qc["kappa_first_run"]["frame"]["kappa"] < SV.KAPPA_FRAME_MIN
    assert len(list((sw["jobs"] / jid / "passes" / "A").glob("a*"))) == 1     # no rerun to raise agreement
    acc = SV.finalize(jid, jobs_dir=sw["jobs"], accept_stop="D-0xx")             # Ori's project-level decision
    assert acc["action"] == "finalized" and SV.is_frozen(jid, sw["jobs"])


def test_invalid_rows_are_rerun_once_then_abstained_and_stop(sw, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "invalid")
    jid = _create(sw)["job_id"]
    r = _run(sw, jid)
    st = SV.pass_state(jid, "A", sw["jobs"])
    assert st["format_reruns"] and max(st["format_reruns"].values()) == 1
    assert r["action"] == "STOP" and any("T5" in s for s in r["reasons"])


def test_abstention_above_threshold_triggers_context_recovery(sw, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "abstain")
    jid = _create(sw)["job_id"]
    r = _run(sw, jid)
    assert r["action"] == "finalized"
    assert SV.pass_state(jid, "A3", sw["jobs"])["plan"] is not None
    rows = list(csv.DictReader(open(sw["jobs"] / jid / "final" / "mikra_dev_silver.csv", encoding="utf-8-sig")))
    assert {x["silver_status"] for x in rows} == {"agreed_ctx"}


def test_worked_examples_are_a_compliance_check(sw, monkeypatch, tmp_path):
    wp = tmp_path / "worked.csv"
    wp.write_text("item_id,ref,verb_key,verb_entries,target,sentence,expected_frame\n"
                  "W01,,,,מילא,דני [[מילא]] מים במיכל,A\nW02,,,,מילא,דני [[מילא]] מים בכד,A\n", encoding="utf-8")
    monkeypatch.setattr(SV, "WORKED_PATH", wp)
    jid = SV.create_job("worked", jobs_dir=sw["jobs"])["job_id"]
    assert _run(sw, jid)["action"] == "finalized"
    wp2 = tmp_path / "worked2.csv"
    wp2.write_text(wp.read_text(encoding="utf-8").replace(",A\n", ",B\n"), encoding="utf-8")
    monkeypatch.setattr(SV, "WORKED_PATH", wp2)
    jobs2 = tmp_path / "jobs2"
    jid2 = SV.create_job("worked", jobs_dir=jobs2)["job_id"]
    kw = {**sw["kw"], "jobs_dir": jobs2}
    r = None
    for _ in range(10):
        r = SV.step(jid2, **kw)
        if r["action"] == "STOP":
            break
    assert r["action"] == "STOP" and "T3" in r["reasons"][0]
    assert len(list((jobs2 / jid2 / "passes").glob("A-attempt*"))) == 1   # one fresh rerun, both attempts kept


def test_job_items_never_change(sw):
    _create(sw)
    _create(sw)                                                         # identical: fine
    with open(sw["sdir"] / "sheets" / "dev.csv", "a", encoding="utf-8") as f:
        pass
    items = pq.read_table(sw["sdir"] / "sample.parquet").to_pylist()
    items[0]["verb_key"] = "אחר.S"
    pq.write_table(pa.Table.from_pylist(items), sw["sdir"] / "sample.parquet")
    with pytest.raises(SV.SilverError):
        _create(sw)


# ============================================================================================ nouns / units / audit
NOUN_HEADER = ("lemma,upos,n,n_as_do,n_pp_B,n_pp_MIN,n_other_pp,n_verbs,example_verbs,corpus_source,proposed_type,"
               "proposed_by,type,reviewed_by,note\n")


def _list_manifest(folder: Path, version: str = "nouns-r2") -> None:
    (folder / "manifest.json").write_text(json.dumps({"list_version": version}), encoding="utf-8")


def _noun_list(tmp_path) -> Path:
    p = tmp_path / "nouns_to_label.csv"
    p.write_text(NOUN_HEADER + "בית1,NOUN,9,1,5,1,0,3,שם,mikra,,,,,\nבית2,NOUN,8,1,5,1,0,3,שם,mikra,,,,,\n",
                 encoding="utf-8")
    _list_manifest(tmp_path)
    return p


def test_noun_merge_rule_and_the_automated_merge(sw, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_MODE", "disagree")
    jid = SV.create_job("noun", "mikra", list_csv=_noun_list(tmp_path), jobs_dir=sw["jobs"])["job_id"]
    assert _run(sw, jid)["action"] == "finalized"
    final = sw["jobs"] / jid / "final" / "noun_types_mikra.csv"
    rows = {r["lemma"]: r for r in csv.DictReader(open(final, encoding="utf-8-sig"))}
    assert rows["בית1"]["type"] == "LOCATION" and rows["בית2"]["type"] == "UNCLEAR"     # disagreement -> UNCLEAR
    types = tmp_path / "noun_types.yaml"
    bad = N.merge(final, types)                                         # an auto-qc reviewer is not a human
    assert not bad["ok"]
    ok = N.merge(final, types, automated=sw["jobs"] / jid)
    assert ok["ok"] and N.load_types(types)["בית1"]["review_mode"] == "automated"
    # G1 (Ori): a cross-corpus type conflict becomes UNCLEAR with both types recorded; uncertainty is preserved
    monkeypatch.setenv("FAKE_MODE", "agree")
    lst2 = tmp_path / "modern_list.csv"
    lst2.write_text("lemma,upos,n,n_as_do,n_pp_B,n_pp_MIN,n_other_pp,n_verbs,example_verbs,corpus_source,proposed_type,"
                    "proposed_by,type,reviewed_by,note\nבית2,NOUN,8,1,5,1,0,3,שם,modern,,,,,\n", encoding="utf-8")
    jid2 = SV.create_job("noun", "modern", list_csv=lst2, jobs_dir=sw["jobs"])["job_id"]
    assert _run(sw, jid2)["action"] == "finalized"
    r2 = N.merge(sw["jobs"] / jid2 / "final" / "noun_types_modern.csv", types, automated=sw["jobs"] / jid2)
    assert r2["ok"] and r2["cross_corpus_conflicts_unclear"] == 1
    t = N.load_types(types)
    assert t["בית2"]["type"] == "UNCLEAR" and t["בית2"]["silver_status"] == "cross_corpus_conflict"
    assert "mikra=UNCLEAR" in t["בית2"]["note"] and "modern=LOCATION" in t["בית2"]["note"]
    assert t["בית1"]["type"] == "LOCATION"
    tampered = tmp_path / "t.csv"
    tampered.write_text(final.read_text(encoding="utf-8-sig").replace("LOCATION", "LOCATUM"), encoding="utf-8")
    assert not N.merge(tampered, tmp_path / "t.yaml", automated=sw["jobs"] / jid)["ok"]   # not the frozen file


def test_import_pass_reuses_earlier_noun_proposals_without_showing_them(sw, tmp_path):
    lst = _noun_list(tmp_path)
    jid = SV.create_job("noun", "modern", list_csv=lst, jobs_dir=sw["jobs"])["job_id"]
    prop = tmp_path / "proposals.csv"
    prop.write_text("lemma,proposed_type,confidence,note\nבית1,LOCATION,high,x\nבית2,LOCATION,low,y\n", encoding="utf-8")
    r = SV.import_pass(jid, "A", prop, jobs_dir=sw["jobs"])
    assert r == {"imported": 2, "invalid": 0, "missing": 0, "dropped_duplicate": 0}
    assert _run(sw, jid)["action"] == "finalized"
    for inp in (sw["tmp"] / "ws").glob(f"{jid}-B-*/input.csv"):
        assert "proposed_type" not in inp.read_text(encoding="utf-8-sig") and "LOCATION" not in inp.read_text(encoding="utf-8-sig")
    rows = {r["lemma"]: r for r in csv.DictReader(open(sw["jobs"] / jid / "final" / "noun_types_modern.csv", encoding="utf-8-sig"))}
    assert rows["בית2"]["type"] == "UNCLEAR"                            # low confidence in pass A -> abstention


# ------------------------------------------------------------------------------------------- D-062 unique item ids
def _tree_hashes(d: Path) -> dict[str, str]:
    from hebloc.store.io import file_sha256

    return {str(p.relative_to(d)): file_sha256(p) for p in sorted(d.rglob("*")) if p.is_file()}


def test_noun_job_ids_are_unique_and_carry_the_list_version(sw, tmp_path):
    r = SV.create_job("noun", "mikra", list_csv=_noun_list(tmp_path), jobs_dir=sw["jobs"])
    assert r["job_id"] == "noun-mikra-r2" and r["items"] == 2
    assert SV.load_job("noun-mikra-r2", sw["jobs"])["inputs"]["list_version"] == "nouns-r2"
    dup = tmp_path / "dup"
    dup.mkdir()
    (dup / "nouns_to_label.csv").write_text(NOUN_HEADER + "ארץ,NOUN,9,1,5,1,0,3,שם,modern,,,,,\n"
                                            "ארץ,PROPN,2,0,2,0,0,2,שם,modern,,,,,\n", encoding="utf-8")
    _list_manifest(dup, "nouns-r1")
    with pytest.raises(SV.SilverError, match="more than once"):         # a nouns-r1 list with a NOUN/PROPN pair
        SV.create_job("noun", "modern", list_csv=dup / "nouns_to_label.csv", jobs_dir=sw["jobs"])
    assert not (sw["jobs"] / "noun-modern-r1").exists()
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / "nouns_to_label.csv").write_text(NOUN_HEADER + "בית,NOUN,9,1,5,1,0,3,שם,mikra,,,,,\n", encoding="utf-8")
    with pytest.raises(SV.SilverError, match="manifest.json"):          # the list version is required
        SV.create_job("noun", "mikra", list_csv=bare / "nouns_to_label.csv", jobs_dir=sw["jobs"])
    sheet = tmp_path / "unit_review.csv"
    sheet.write_text("lemma,candidates,n,pres_share,fin_share,n_by_corpus\nרוצה,רצה (participle),60,0.9,0.1,modern=60\n"
                     "רוצה,רצה (participle),60,0.9,0.1,modern=60\n", encoding="utf-8")
    with pytest.raises(SV.SilverError, match="more than once"):         # the guard holds for every task
        SV.create_job("unit", sheet=sheet, jobs_dir=sw["jobs"])


def test_a_job_made_before_d062_is_kept_but_never_used(sw, tmp_path):
    """A job with duplicate item ids (made from a nouns-r1 list before the fix) stays on file byte-identical; status
    still reads it; nothing steps, finalizes, imports into, builds a workspace for, or delivers it."""
    d = sw["jobs"] / "noun-mikra"
    item = lambda lem, upos: {"id": lem, "blind": {"item_id": lem, "upos": upos}, "private": {"corpus_source": "mikra"}}
    (d / "passes" / "A").mkdir(parents=True)
    (d / "items.json").write_text(json.dumps({"job_id": "noun-mikra", "task": "noun", "corpus": "mikra", "split": None,
                                              "items": [item("ארץ", "NOUN"), item("ארץ", "PROPN"), item("יד", "NOUN")],
                                              "items_sha256": "legacy"}, ensure_ascii=False), encoding="utf-8")
    before = _tree_hashes(d)
    assert SV.status("noun-mikra", sw["jobs"])["items"] == 3
    for call in (lambda: SV.step("noun-mikra", **sw["kw"]),
                 lambda: SV.finalize("noun-mikra", jobs_dir=sw["jobs"]),
                 lambda: SV.import_pass("noun-mikra", "B", _noun_list(tmp_path), jobs_dir=sw["jobs"]),
                 lambda: SV.build_workspace(SV.load_job("noun-mikra", sw["jobs"]), "A", ["יד"], attempt=1, chunk=0,
                                            root=sw["tmp"] / "ws", jobs_dir=sw["jobs"], projects_dir=sw["tmp"] / "projects")):
        with pytest.raises(SV.SilverError, match="duplicate item ids"):
            call()
    (d / "FROZEN.json").write_text("{}", encoding="utf-8")              # even a frozen one is never delivered
    with pytest.raises(SV.SilverError, match="duplicate item ids"):
        SV.deliver(["noun-mikra"], tmp_path / "outbox", who="efrat", jobs_dir=sw["jobs"])
    (d / "FROZEN.json").unlink()
    assert _tree_hashes(d) == before
    assert not (tmp_path / "outbox").exists()


def test_import_pass_drops_lemmas_with_several_proposal_rows(sw, tmp_path):
    """Proposals made on a nouns-r1 list may type one lemma twice (NOUN and PROPN rows). That lemma is not imported:
    an isolated pass A labels it with the merged evidence."""
    jid = SV.create_job("noun", "modern", list_csv=_noun_list(tmp_path), jobs_dir=sw["jobs"])["job_id"]
    prop = tmp_path / "proposals.csv"
    prop.write_text("lemma,upos,proposed_type,confidence,note\nבית1,NOUN,LOCATION,high,x\nבית1,PROPN,ANIMATE,high,y\n"
                    "בית2,NOUN,LOCATION,high,z\n", encoding="utf-8")
    r = SV.import_pass(jid, "A", prop, jobs_dir=sw["jobs"])
    assert r == {"imported": 1, "invalid": 0, "missing": 1, "dropped_duplicate": 1}
    assert _run(sw, jid)["action"] == "finalized"
    a_inputs = [p.read_text(encoding="utf-8-sig") for p in (sw["tmp"] / "ws").glob(f"{jid}-A-*/input.csv")]
    assert len(a_inputs) == 1 and "בית1" in a_inputs[0] and "בית2" not in a_inputs[0]
    final = list(csv.DictReader(open(sw["jobs"] / jid / "final" / "noun_types_modern.csv", encoding="utf-8-sig")))
    assert sorted(x["lemma"] for x in final) == ["בית1", "בית2"]           # one row per lemma
    st = SV.status(jid, sw["jobs"])
    assert st["passes"]["A"]["labelled"] == 2 and st["passes"]["A"]["missing"] == 0


def test_repeated_lemma_rows_are_never_merged(sw, tmp_path):
    rev = tmp_path / "reviewed.csv"
    rev.write_text("lemma,type,proposed_by,reviewed_by,note,corpus_source\nארץ,LOCATION,human,ori,,mikra\n"
                   "ארץ,ANIMATE,human,ori,,mikra\n", encoding="utf-8")
    r = N.merge(rev, tmp_path / "noun_types.yaml")
    assert not r["ok"] and any("D-062" in p for p in r["problems"])
    assert not (tmp_path / "noun_types.yaml").exists()
    # check_automated: the final file of a (pre-fix) frozen job that lists a lemma twice is refused
    from hebloc.store.io import file_sha256

    job = tmp_path / "legacy-job"
    (job / "final").mkdir(parents=True)
    fin = job / "final" / "noun_types_modern.csv"
    fin.write_text("lemma,type,reviewed_by,review_mode\nארץ,LOCATION,auto-qc:q1,automated\nארץ,UNCLEAR,auto-qc:q1,automated\n",
                   encoding="utf-8")
    (job / "FROZEN.json").write_text(json.dumps({"job_id": "noun-modern", "files": {"final": file_sha256(fin)}}), encoding="utf-8")
    (job / "qc.json").write_text(json.dumps({"qc_id": "q1", "stops": []}), encoding="utf-8")
    _, probs = SV.check_automated(fin, job)
    assert any("more than one row" in p for p in probs)
    assert not N.merge(fin, tmp_path / "noun_types.yaml", automated=job)["ok"]


def test_unit_links_need_both_passes_to_accept_the_same_base(sw, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_MODE", "disagree")
    sheet = tmp_path / "unit_review.csv"
    sheet.write_text("lemma,candidates,n,pres_share,fin_share,n_by_corpus,planned_reviewer\n"
                     "רוצה1,רצה (participle, Simple, qal_part, n=50),60,0.9,0.1,modern=60,efrat\n"
                     "נשבע2,שבע (passive, Simple, nifal, n=50),60,0.1,0.9,modern=60,efrat\n", encoding="utf-8")
    jid = SV.create_job("unit", sheet=sheet, jobs_dir=sw["jobs"])["job_id"]
    assert _run(sw, jid)["action"] == "finalized"
    rows = {r["lemma"]: r for r in csv.DictReader(open(sw["jobs"] / jid / "final" / "unit_review_automated.csv", encoding="utf-8-sig"))}
    assert rows["רוצה1"]["decision"] == "accept" and rows["רוצה1"]["base"] == "רצה"
    assert rows["נשבע2"]["decision"] == "reject"                         # the passes disagree: no link (never merge)
    qc_id, probs = SV.check_automated(sw["jobs"] / jid / "final" / "unit_review_automated.csv", sw["jobs"] / jid)
    assert not probs and qc_id.startswith("unit-")


def test_audit_pass_never_sees_the_rule(sw, tmp_path):
    sheet = tmp_path / "audit.csv"
    sheet.write_text("lemma,base,rule,n,pres_share,fin_share,example_ids\nרואה,ראה,qal_participle,90,0.9,0.05,\n", encoding="utf-8")
    jid = SV.create_job("audit", sheet=sheet, jobs_dir=sw["jobs"])["job_id"]
    job = SV.load_job(jid, sw["jobs"])
    assert "rule" not in job["items"][0]["blind"]
    assert _run(sw, jid)["action"] == "finalized"


# ============================================================================================ SG2 delivery + scoring
def test_deliver_receive_record_hashes_and_score_guards(sw, tmp_path):
    jid = _create(sw)["job_id"]
    _run(sw, jid)
    out = tmp_path / "outbox"
    SV.deliver([jid], out, who="efrat", jobs_dir=sw["jobs"])
    d = json.loads((out / "DELIVERY.json").read_text(encoding="utf-8"))
    assert d["label_source"] == "ai" and not any("items.json" in f or "canary" in f for f in d["files"])
    frozen, final = tmp_path / "FROZEN_SILVER.json", tmp_path / "final"
    SV.receive(out, frozen_path=frozen, final_dir=final, received_dir=tmp_path / "received")
    rec = json.loads(frozen.read_text(encoding="utf-8"))
    assert jid in rec["jobs"] and rec["jobs"][jid]["placed"]
    rows = S.load_gold("mikra", "dev", gold_dir=final, frozen_path=frozen)
    assert len(rows) == 4 and {r["label_source"] for r in rows} == {"ai"}
    with pytest.raises(S.ScoreError):
        S.load_gold("mikra", "test", gold_dir=final, frozen_path=frozen)                 # test only with --final-test
    f = final / "dev" / "mikra_dev_silver.csv"
    f.write_text(f.read_text(encoding="utf-8-sig").replace("agreed", "adjudicated"), encoding="utf-8")
    with pytest.raises(S.ScoreError):
        S.load_gold("mikra", "dev", gold_dir=final, frozen_path=frozen)                  # revised silver is refused
    with pytest.raises(SV.SilverError):
        (out / "silver" / jid / "final" / "mikra_dev_silver.csv").write_text("x", encoding="utf-8")
        SV.receive(out, frozen_path=frozen, final_dir=final, received_dir=tmp_path / "received")


def test_silver_is_never_human_gold(sw, tmp_path):
    with pytest.raises(G.GoldError):
        G.check_sheet(sw["sdir"] / "sheets" / "dev.csv", sw["sdir"], "claude_code", tmp_path / "out")
    gd = tmp_path / "gold"
    gd.mkdir()
    (gd / "mikra_dev_x.csv").write_text("item_id,instance_key,annotator,label_source\nMI0001,k,x,ai\n", encoding="utf-8")
    with pytest.raises(S.ScoreError):
        S.load_gold("mikra", "dev", gold_dir=gd, label_source="human")


def test_frozen_samples_and_protocol_files_are_in_place():
    assert G.FROZEN_SAMPLES["mikra"]["sample_id"] == "mikra-r1b-1cd4ee9802"
    assert G.FROZEN_SAMPLES["modern"]["sample_id"] == "modern-r1b-5fbb5e22e7"
    for name in ("sentence_pass.md", "adjudicate.md", "noun_pass.md", "unit_pass.md", "variant_pass.md", "audit_pass.md"):
        text = (SV.PROMPTS_DIR / name).read_text(encoding="utf-8")
        assert "{{CANARY_1}}" in text and "{{OUT_COLUMNS}}" in text and "SILVER" in text
    rows = list(csv.DictReader(open(SV.WORKED_PATH, encoding="utf-8-sig")))
    assert len(rows) == 15 and {r["expected_frame"] for r in rows} <= {"A", "B", "NON_LOCATIVE"}
    assert SV.PROTOCOL_PATH.exists()


def test_kappa_ci_is_deterministic():
    a, b = ["A", "B", "A", "B", "A"] * 4, ["A", "B", "B", "B", "A"] * 4
    assert SV.kappa_ci(a, b) == SV.kappa_ci(a, b)
    assert SV.kappa(["A"] * 5, ["A"] * 5) == 1.0


# ============================================================================================ Phase C (C0, D-065)
def test_c0_leaves_the_frozen_sample_jobs_unchanged(sw):
    """D-065: the job id, the final file name and the FROZEN.json prompt record of a frozen-sample job are exactly as
    before C0 (the E5/E6 jobs run the older code and must stay comparable)."""
    jid = _create(sw)["job_id"]
    assert jid == "sentence-mikra-dev"
    assert _run(sw, jid)["action"] == "finalized"
    assert (sw["jobs"] / jid / "final" / "mikra_dev_silver.csv").exists()
    fz = json.loads((sw["jobs"] / jid / "FROZEN.json").read_text(encoding="utf-8"))
    assert sorted(fz["prompts_sha256"]) == sorted(["adjudicate.md", "audit_pass.md", "noun_pass.md", "sentence_pass.md",
                                                   "unit_pass.md", "variant_pass.md"])
    assert "protocol_r2_sha256" not in fz and "prompt_r2_sha256" not in fz


def _supplement_dir(w, sid="mikra-s1-0123456789", items_sha="FP"):
    d = w["tmp"] / "supp"
    (d / "sheets").mkdir(parents=True)
    items = [{"sample_id": sid, "item_id": f"MIS10{k:02d}", "instance_key": f"mikra:d0:{k + 10}:0|0|1", "split": "dev",
              "stratum": "I-1/B", "agreement": False, "members": ["מלא.I"], "verb_key": "מלא.I", "sent_id": f"mikra:d0:{k + 10}:0",
              "doc_id": "d0"} for k in range(1, 3)]
    pq.write_table(pa.Table.from_pylist(items), d / "sample.parquet")
    (d / "manifest.json").write_text(json.dumps({"sample_id": sid, "supplement_version": "gold-sup-c0", "items_sha256": items_sha}),
                                     encoding="utf-8")
    with open(d / "sheets" / "dev.csv", "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["item_id", "split", "agreement", "stratum", "where", "verb_key", "target", "sentence", "words"]
                    + list(G.ANNOTATION_COLUMNS))
        for x in items:
            wr.writerow([x["item_id"], "dev", "", "I-1/B", "Genesis 1:2", "מלא.I", "מילא", "דני [[מילא]] את הכד במים",
                         "0:דני 1:מילא 2:את 3:הכד 4:במים"] + [""] * len(G.ANNOTATION_COLUMNS))
    return d, sid


def test_supplement_jobs_never_collide_and_are_scored_as_a_second_stratum(sw, tmp_path, monkeypatch):
    d, sid = _supplement_dir(sw)
    with pytest.raises(SV.SilverError):                                    # not registered (G3): refused
        SV.create_job("sentence", "mikra", "dev", sample_dir=d, jobs_dir=sw["jobs"])
    monkeypatch.setattr(G, "FROZEN_SUPPLEMENTS", {"mikra": {sid: {"items_sha256": "OTHER"}}})
    with pytest.raises(SV.SilverError):                                    # registered with other items: refused
        SV.create_job("sentence", "mikra", "dev", sample_dir=d, jobs_dir=sw["jobs"])
    monkeypatch.setattr(G, "FROZEN_SUPPLEMENTS", {"mikra": {sid: {"items_sha256": "FP"}}})
    sj = SV.create_job("sentence", "mikra", "dev", sample_dir=d, jobs_dir=sw["jobs"])["job_id"]
    fj = _create(sw)["job_id"]
    assert sj == f"sentence-{sid}-dev" and fj == "sentence-mikra-dev"
    for j in (sj, fj):
        assert _run(sw, j)["action"] == "finalized"
    assert (sw["jobs"] / sj / "final" / f"{sid}_dev_silver.csv").exists()
    out, frozen, final = tmp_path / "outbox", tmp_path / "FROZEN_SILVER.json", tmp_path / "final"
    SV.deliver([fj, sj], out, who="efrat", jobs_dir=sw["jobs"])
    SV.receive(out, frozen_path=frozen, final_dir=final, received_dir=tmp_path / "received")
    assert sorted(p.name for p in (final / "dev").glob("*.csv")) == sorted(["mikra_dev_silver.csv", f"{sid}_dev_silver.csv"])
    rows = S.load_gold("mikra", "dev", gold_dir=final, frozen_path=frozen)
    assert len(rows) == 6 and {r["sample_id"] for r in rows} == {"mikra-test", sid}
    assert len(S.load_gold("mikra", "dev", gold_dir=final, frozen_path=frozen, include_supplements=False)) == 4
    placed = final / "dev" / "mikra_dev_silver.csv"
    placed.write_text("changed", encoding="utf-8")                        # a different file already placed
    with pytest.raises(SV.SilverError):
        SV.receive(out, frozen_path=frozen, final_dir=final, received_dir=tmp_path / "received")


def _draw_dir(tmp_path, kind, rows, corpus="mikra"):
    d = tmp_path / "draws" / kind / corpus / f"{corpus}-{kind}-x"
    d.mkdir(parents=True)
    cols = list(rows[0])
    with open(d / "ids.csv", "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=cols)
        wr.writeheader()
        wr.writerows(rows)
    (d / "manifest.json").write_text(json.dumps({"kind": kind, "corpus": corpus, "draw_id": d.name,
                                                 "items_sha256": "abcdef0123456789" + kind}), encoding="utf-8")
    return d


def test_instances_job_end_to_end_uses_the_pinned_sentence_prompt(sw, tmp_path, monkeypatch):
    rows = [{"item_id": f"SCMI000{k}", "instance_key": f"mikra:d0:{k}:0|0|1", "verb_key": "צרר.S|~form", "stratum": "צרר.S"}
            for k in range(1, 4)]
    d = _draw_dir(tmp_path, "screen", rows)

    def fake_sentences(con, source, corpus, keys):
        return {k: {"sentence": "הוא [[צריך]] ללכת", "words": "0:הוא 1:צריך 2:ללכת", "target": "צריך", "doc_id": "d0"} for k in keys}

    monkeypatch.setattr(SV, "unit_sentences", fake_sentences)
    with pytest.raises(SV.SilverError):                                    # the draw kind must match the purpose
        SV.create_job("instances", purpose="review", ids=d, source=object(), jobs_dir=sw["jobs"])
    r = SV.create_job("instances", purpose="screen", ids=d, source=object(), jobs_dir=sw["jobs"])
    jid = r["job_id"]
    assert jid.startswith("screen-mikra-")
    job = SV.load_job(jid, sw["jobs"])
    assert set(job["items"][0]["blind"]) == set(SV.BLIND_COLUMNS["sentence"])      # the stratum is never shown
    assert _run(sw, jid)["action"] == "finalized"
    fz = json.loads((sw["jobs"] / jid / "FROZEN.json").read_text(encoding="utf-8"))
    assert f"{jid}_silver.csv" in "".join(fz["files"]) and fz["protocol_r2_sha256"]
    ws = sorted((sw["tmp"] / "ws").glob(f"{jid}-A-*"))[0]
    assert (ws / "PROMPT.md").read_text(encoding="utf-8").startswith("# SILVER pass: annotate verb instances")


def test_template_job_end_to_end(sw, tmp_path):
    rows = [{"item_id": f"TPMO000{k}", "lemma": f"הכניס{k}", "verb_key": "הכניס (40); מכניס (20)", "stratum": "Causative", "n": "60"}
            for k in range(1, 4)]
    d = _draw_dir(tmp_path, "template", rows, corpus="modern")
    jid = SV.create_job("template", ids=d, jobs_dir=sw["jobs"])["job_id"]
    assert jid.startswith("template-modern-")
    job = SV.load_job(jid, sw["jobs"])
    assert "proxy" not in job["items"][0]["blind"] and "stratum" not in job["items"][0]["blind"]
    assert _run(sw, jid)["action"] == "finalized"
    out = list(csv.DictReader(open(sw["jobs"] / jid / "final" / "template_check.csv", encoding="utf-8-sig")))
    assert {r["template"] for r in out} == {"Causative"} and {r["label_source"] for r in out} == {"ai"}
    fz = json.loads((sw["jobs"] / jid / "FROZEN.json").read_text(encoding="utf-8"))
    assert list(fz["prompt_r2_sha256"]) == ["template_pass.md"]
    ws = sorted((sw["tmp"] / "ws").glob(f"{jid}-A-*"))[0]
    assert "binyan" in (ws / "PROMPT.md").read_text(encoding="utf-8")


def test_template_passes_that_disagree_give_unclear(sw, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "disagree")
    d = _draw_dir(tmp_path, "template", [{"item_id": "TPMO0001", "lemma": "שם", "verb_key": "שם (9)", "stratum": "Simple", "n": "9"}],
                  corpus="modern")
    jid = SV.create_job("template", ids=d, jobs_dir=sw["jobs"])["job_id"]
    assert _run(sw, jid)["action"] == "finalized"
    out = list(csv.DictReader(open(sw["jobs"] / jid / "final" / "template_check.csv", encoding="utf-8-sig")))
    assert out[0]["template"] == "unclear" and out[0]["silver_status"] == "abstained"


def test_pinned_prompts_unchanged_and_phase_c_files_separate():
    """D-065: the six pinned prompts stay alone in prompts/ (byte-identical to s56-r1.1); Phase C files are in r2/."""
    import subprocess

    assert sorted(p.name for p in SV.PROMPTS_DIR.glob("*")) == sorted(
        ["adjudicate.md", "audit_pass.md", "noun_pass.md", "sentence_pass.md", "unit_pass.md", "variant_pass.md"])
    assert sorted(p.name for p in SV.R2_DIR.glob("*")) == ["PROTOCOL_R2.md", "template_pass.md"]
    pinned = ["annotation/S56_SILVER_PROTOCOL.md", "annotation/S56_GUIDELINE.md", "annotation/silver/prompts/",
              "annotation/silver/worked_examples.csv", "annotation/silver/anchor_ids.csv"]
    tag = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "s56-r1.1^{commit}"], cwd=ROOT, capture_output=True)
    if tag.returncode != 0:
        pytest.skip("tag s56-r1.1 not available")
    r = subprocess.run(["git", "diff", "--quiet", "s56-r1.1", "--", *pinned], cwd=ROOT)
    assert r.returncode == 0, "a pinned protocol file differs from s56-r1.1"
