"""Phase C id-list draws for the new SILVER jobs (D-065; annotation/silver/r2/PROTOCOL_R2.md). Ids only, never labels.

Every draw is deterministic (salted sha256 order), depends only on its inputs (never on the data source, so Ori and
Efrat draw the same ids from the repo or the package) and writes ``data/loc/draws/<kind>/<corpus>/<draw id>/`` with
``ids.csv`` (``item_id``, ``instance_key`` or ``lemma``, the verb key shown to the annotator, the stratum) and
``manifest.json`` (``items_sha256`` = the fingerprint a second draw must match). The SILVER jobs are built from
``ids.csv`` by ``hebloc loc silver create --task instances|template``.

- ``screen``  (I-3, D-059 addendum): per affected key, 15 instances from OUTSIDE every sample (no sentence that holds a
  frozen or registered supplement item, an anchor item, a paper-example verse or an R1 sense-screen reading). Drawn
  only at G3, with Ori's decision id. Decision at C1: the key's I-3 change is applied when <= 3 of the 15 are the verb.
- ``review``  (§6 candidate review, EFRAT §5.9(2)): non-lexicon units that are swap-test candidates, have both A and B
  outcomes, or both DO+PP[B] and DO+PP[MIN] signatures; the 100 most frequent; per unit <= 5 instances of each pool
  (outcome A / outcome B, or the two signatures when the unit has no A/B outcome).
- ``template`` (§6 template proxy, EFRAT §5.9(3)): 200 lemmas with >= 20 tokens, by proxy value (proportional, at
  least 20 per value when available).
- ``audit``   (class / identity audit, EFRAT §5.5, §5.6): every PRIMARY verb whose class differs from the paper, or
  whose identity verdict is COUNTEREXAMPLE: its ``deciding_ids`` and ``identity_ids``. The pipeline's outcomes are
  written to a SEPARATE local key file (``audit_key.csv``) that is never sent to the annotator.
"""

from __future__ import annotations

import csv
import hashlib
from collections import defaultdict
from pathlib import Path

import pyarrow as pa

from hebloc.loc import METHODOLOGY
from hebloc.loc import gold as G
from hebloc.loc import identify as ID
from hebloc.loc.lexicon import Lexicon
from hebloc.loc.manifest import write_csv, write_manifest
from hebloc.loc.resolve import _lst, _parts
from hebloc.loc.source import Source, connect
from hebloc.paths import DATA_DIR
from hebloc.store.io import read_json

DRAWS_VERSION = "draws-c0"
DRAWS_DIR = DATA_DIR / "loc" / "draws"
QUALITY_DIR = DATA_DIR / "loc" / "review" / "quality"
# ---- pre-registered sizes (D-065; Ori, 2026-11-22) ----
SCREEN_PER_KEY = 15                 # D-059 addendum (I-3); decision: dropped when <= SCREEN_MAX_VERB are the verb
SCREEN_MAX_VERB = 3
REVIEW_MAX_CANDIDATES = 100
REVIEW_PER_POOL = 5
TEMPLATE_SIZE = 200
TEMPLATE_MIN_TOKENS = 20
TEMPLATE_MIN_PER_VALUE = 20
AUDIT_PRIMARY = "level = 'unit' AND view = 'full' AND scope = 'all' AND k = 1"
PREFIX = {"screen": "SC", "review": "RV", "template": "TP", "audit": "AU"}
IDS_COLUMNS = ("item_id", "instance_key", "verb_key", "stratum")


class DrawError(Exception):
    pass


def salt(kind: str, corpus: str) -> str:
    return f"{METHODOLOGY}:{corpus}:{kind}:"


def _h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def items_fingerprint(rows: list[dict], key: str = "instance_key") -> str:
    return _h("\n".join(sorted(f"{r['item_id']}|{r[key]}|{r.get('verb_key', '')}|{r.get('stratum', '')}" for r in rows)))


def _number(kind: str, corpus: str, rows: list[dict], key: str) -> list[dict]:
    """Item ids in hash order (``SCMI0001`` …): the order is fixed by the salt, never by the data source."""
    rows = sorted(rows, key=lambda r: _h(salt(kind, corpus) + "id:" + r[key]))
    for i, r in enumerate(rows, 1):
        r["item_id"] = f"{PREFIX[kind]}{corpus[:2].upper()}{i:04d}"
    return rows


def _write(kind: str, corpus: str, did: str, rows: list[dict], columns: tuple[str, ...], *, git: dict, source: dict | None,
           extra: dict, out_root: Path, key: str = "instance_key", private: list[dict] | None = None) -> dict:
    out = Path(out_root) / kind / corpus / did
    if (out / "manifest.json").exists():
        raise DrawError(f"{out} already exists (a draw is made once; it is identical by design)")
    out.mkdir(parents=True, exist_ok=True)
    write_csv(pa.Table.from_pylist([{c: r.get(c) for c in columns} for r in rows]) if rows else pa.table({c: [] for c in columns}),
              out / "ids.csv")
    if private is not None:
        write_csv(pa.Table.from_pylist(private) if private else pa.table({"item_id": []}), out / f"{kind}_key.csv")
    return write_manifest(out, what=f"Phase C draw: {kind} ids (no labels)", git=git, source=source,
                          extra={"kind": kind, "corpus": corpus, "draw_id": did, "draws_version": DRAWS_VERSION,
                                 "salt": salt(kind, corpus), "n_items": len(rows),
                                 "items_sha256": items_fingerprint(rows, key), **extra})


def read_ids(folder: Path) -> tuple[list[dict], dict]:
    folder = Path(folder)
    man = read_json(folder / "manifest.json")
    with open(folder / "ids.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, man


# ============================================================================================ I-3 sense screen
def _sample_sent_ids(corpus: str, gold_dir: Path) -> set[str]:
    import pyarrow.parquet as pq

    out: set[str] = set()
    sids = [G.FROZEN_SAMPLES.get(corpus, {}).get("sample_id")] + list(G.FROZEN_SUPPLEMENTS.get(corpus, {}))
    for sid in filter(None, sids):
        f = Path(gold_dir) / corpus / sid / "sample.parquet"
        if not f.exists():
            raise DrawError(f"{f} not found: the screen must exclude every sample (draw / receive it first)")
        out |= set(pq.read_table(f, columns=["sent_id"]).column("sent_id").to_pylist())
    return out


def screen(corpus: str, source: Source, r1: Lexicon, affected: dict[str, set[str]], *, approval: str | None, git: dict,
           candidate_sha256: str, anchor_ids: Path | None = None, gold_dir: Path = G.GOLD_DIR,
           quality_dir: Path = QUALITY_DIR, out_root: Path = DRAWS_DIR, per_key: int = SCREEN_PER_KEY,
           progress: bool = True) -> dict:
    """The I-3 sense screen: ``affected`` = entry id -> the hosts whose zone I-3 changes (from the I-3 candidate's
    ``changes.csv``). Population: R1-identified full-view tokens of that entry on those hosts, in no excluded sentence.
    ``per_key`` per entry by hash. Refused without Ori's decision id."""
    if not approval:
        raise DrawError("the I-3 sense screen is drawn only with Ori's approval and a decision: --approval D-0xx (G3)")
    s = salt("screen", corpus)
    did = f"{corpus}-screen-" + _h(f"{corpus}|{r1.sha256}|{candidate_sha256}|{per_key}|{s}|{DRAWS_VERSION}")[:10]
    excl = _sample_sent_ids(corpus, gold_dir)
    if anchor_ids is not None and Path(anchor_ids).exists() and corpus == "mikra":
        with open(anchor_ids, encoding="utf-8-sig", newline="") as f:
            excl |= {r["instance_key"].split("|")[0] for r in csv.DictReader(f)}
    excl_refs: set[str] = {r["he"] for e in r1.entries for r in e.paper_refs if r.get("he")} if corpus == "mikra" else set()
    rq = Path(quality_dir) / f"sense_screen_{corpus}.csv"
    if rq.exists():
        with open(rq, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                (excl_refs if corpus == "mikra" else excl).add(row["ref"])
    con = connect()
    con.register("aff_in", pa.table({"entry": [e for e, hs in sorted(affected.items()) for _ in sorted(hs)],
                                     "host": [h for _, hs in sorted(affected.items()) for h in sorted(hs)]}))
    con.execute("CREATE OR REPLACE TEMP TABLE aff AS SELECT * FROM aff_in")
    con.register("ex_s", pa.table({"sent_id": sorted(excl)}, schema=pa.schema([("sent_id", pa.string())])))
    con.register("ex_r", pa.table({"ref": sorted(excl_refs)}, schema=pa.schema([("ref", pa.string())])))
    con.execute(f"""CREATE OR REPLACE TEMP TABLE units AS SELECT sent_id, ref FROM {source.units_sql(corpus, ('sent_id', 'ref', 'in_full_view'))}
                    WHERE in_full_view AND sent_id NOT IN (SELECT sent_id FROM ex_s) AND coalesce(ref, '') NOT IN (SELECT ref FROM ex_r)""")
    ID.register(con, r1)
    parts = []
    pop: dict[str, int] = defaultdict(int)
    for run in source.runs(corpus):
        if progress:
            print(f"  screen {corpus}: {run.run_id}", flush=True)
        con.execute(f"CREATE OR REPLACE TEMP TABLE tok AS SELECT t.* FROM {source.tokens_sql(run, G.TREE_COLUMNS)} t "
                    "JOIN units u USING (sent_id)")
        con.execute(f"CREATE OR REPLACE TEMP TABLE idn AS {ID.identify_sql('tok')}")
        con.execute(f"""CREATE OR REPLACE TEMP TABLE p AS
            SELECT a.entry, i.verb_key, i.sent_id || '|' || i.piece_idx || '|' || i.word_idx AS instance_key,
                   sha256('{s}' || i.sent_id || '|' || i.piece_idx || '|' || i.word_idx) AS h
            FROM idn i JOIN tok t USING (sent_id, piece_idx, word_idx) JOIN aff a ON list_contains(i.members, a.entry) AND t.host = a.host""")
        for e, n in con.sql("SELECT entry, count(*) FROM p GROUP BY 1").fetchall():
            pop[e] += n
        parts.append(con.sql(f"SELECT * FROM (SELECT *, row_number() OVER (PARTITION BY entry ORDER BY h) AS r FROM p) WHERE r <= {per_key}")
                     .to_arrow_table().drop(["r"]))
    allp = pa.concat_tables(parts) if parts else pa.table({"entry": [], "verb_key": [], "instance_key": [], "h": []})
    con.register("allp", allp)
    rows = con.sql(f"""SELECT entry AS stratum, verb_key, instance_key FROM
                       (SELECT *, row_number() OVER (PARTITION BY entry ORDER BY h) AS r FROM allp) WHERE r <= {per_key}
                       ORDER BY stratum, instance_key""").to_arrow_table().to_pylist()
    rows = _number("screen", corpus, rows, "instance_key")
    short = {e: per_key - sum(1 for r in rows if r["stratum"] == e) for e in affected if sum(1 for r in rows if r["stratum"] == e) < per_key}
    return _write("screen", corpus, did, rows, IDS_COLUMNS, git=git, source=source.describe(corpus), out_root=out_root,
                  extra={"approval": approval, "per_key": per_key, "decision_rule": f"<= {SCREEN_MAX_VERB} of {per_key} are the verb -> the key's I-3 change applies",
                         "r1_lexicon_sha256": r1.sha256, "candidate_lexicon_sha256": candidate_sha256,
                         "affected": {e: sorted(hs) for e, hs in sorted(affected.items())}, "population_by_key": dict(pop),
                         "shortfall": short, "excluded_sentences": len(excl), "excluded_refs": len(excl_refs)})


def affected_from_changes(changes_csv: Path) -> dict[str, set[str]]:
    """entry -> hosts whose zone the I-3 candidate changes (removed or zone_changed; additions are not screened)."""
    out: dict[str, set[str]] = defaultdict(set)
    with open(changes_csv, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("change") in ("removed", "zone_changed"):
                out[r["entry"]].add(r["host"])
    return dict(out)


# ============================================================================================ §6 candidate review
def review(extract_folder: Path, variant: str, *, git: dict, out_root: Path = DRAWS_DIR,
           max_candidates: int = REVIEW_MAX_CANDIDATES, per_pool: int = REVIEW_PER_POOL) -> dict:
    """EFRAT §5.9(2): the candidate-review ids of one all-verbs extraction (unit level, full view, scope all)."""
    folder = Path(extract_folder)
    xman = read_json(folder / "manifest.json")
    corpus = xman["corpus"]
    cdir, rdir = folder / f"classes-{variant}", folder / f"roles-{variant}"
    if not (cdir / "manifest.json").exists():
        raise DrawError(f"no classes-{variant} in {folder} (run: hebloc loc classify)")
    s = salt("review", corpus)
    con = connect()
    con.execute(f"CREATE OR REPLACE TEMP VIEW inst AS SELECT * FROM read_parquet({_lst(_parts(folder, 'instances'))})")
    con.execute(f"CREATE OR REPLACE TEMP VIEW roles AS SELECT * FROM read_parquet({_lst(_parts(rdir, 'roles'))})")
    for t in ("verb_classes", "verb_signatures", "swap_candidates", "verb_profiles"):
        con.execute(f"CREATE OR REPLACE TEMP VIEW {t} AS SELECT * FROM read_parquet('{(cdir / f'{t}.parquet').as_posix()}')")
    cands = con.sql(f"""
        WITH sw AS (SELECT DISTINCT verb_key FROM swap_candidates WHERE level = 'unit' AND view = 'full'),
             ab AS (SELECT DISTINCT verb_key FROM verb_classes WHERE level = 'unit' AND view = 'full' AND scope = 'all' AND k = 1
                    AND n_a > 0 AND n_b > 0),
             sg AS (SELECT verb_key FROM verb_signatures WHERE level = 'unit' AND view = 'full' GROUP BY verb_key
                    HAVING bool_or(contains(signature, '+DO') AND contains(signature, '+PP[B]'))
                       AND bool_or(contains(signature, '+DO') AND contains(signature, '+PP[MIN]'))),
             u AS (SELECT verb_key, 'swap' AS src FROM sw UNION ALL SELECT verb_key, 'a_and_b' FROM ab
                   UNION ALL SELECT verb_key, 'signatures' FROM sg)
        SELECT u.verb_key, list_sort(list_distinct(list(u.src))) AS sources, any_value(p.n_tokens) AS n_tokens
        FROM u JOIN verb_profiles p ON p.verb_key = u.verb_key AND p.level = 'unit' AND p.view = 'full'
        WHERE NOT coalesce(p.in_lexicon, false)
        GROUP BY u.verb_key ORDER BY n_tokens DESC, u.verb_key LIMIT {int(max_candidates)}""").to_arrow_table()
    con.register("cand", cands)
    rows = con.sql(f"""
        WITH j AS (SELECT i.instance_id, i.unit_id, i.verb_key, i.signature, r.outcome,
                          sha256('{s}' || i.instance_id) AS h
                   FROM inst i JOIN roles r USING (instance_id) JOIN cand c ON c.verb_key = i.unit_id WHERE i.in_full_view),
             hasab AS (SELECT unit_id, bool_or(outcome IN ('A', 'B')) AS ab FROM j GROUP BY 1),
             pooled AS (SELECT j.*, CASE WHEN hasab.ab THEN (CASE WHEN outcome = 'A' THEN 'A' WHEN outcome = 'B' THEN 'B' END)
                                         ELSE (CASE WHEN contains(signature, '+DO') AND contains(signature, '+PP[B]') THEN 'DO+PP[B]'
                                                    WHEN contains(signature, '+DO') AND contains(signature, '+PP[MIN]') THEN 'DO+PP[MIN]' END) END AS pool
                        FROM j JOIN hasab USING (unit_id))
        SELECT instance_id AS instance_key, verb_key, unit_id || '/' || pool AS stratum FROM
          (SELECT *, row_number() OVER (PARTITION BY unit_id, pool ORDER BY h) AS r FROM pooled WHERE pool IS NOT NULL)
        WHERE r <= {int(per_pool)} ORDER BY stratum, instance_key""").to_arrow_table().to_pylist()
    rows = _number("review", corpus, rows, "instance_key")
    did = f"{corpus}-review-" + _h(f"{xman.get('output_id')}|{variant}|{max_candidates}|{per_pool}|{s}|{DRAWS_VERSION}")[:10]
    return _write("review", corpus, did, rows, IDS_COLUMNS, git=git, out_root=out_root,
                  source={"extract": xman.get("output_id"), "variant": variant},
                  extra={"max_candidates": max_candidates, "per_pool": per_pool, "n_candidates": cands.num_rows,
                         "candidates": [{"unit": r["verb_key"], "sources": r["sources"], "n_tokens": r["n_tokens"]}
                                        for r in cands.to_pylist()]})


# ============================================================================================ §6 template proxy
def template(extract_folder: Path, *, git: dict, out_root: Path = DRAWS_DIR, size: int = TEMPLATE_SIZE,
             min_tokens: int = TEMPLATE_MIN_TOKENS, min_per_value: int = TEMPLATE_MIN_PER_VALUE) -> dict:
    """EFRAT §5.9(3): a lemma sample of an all-verbs extraction, by the lemma's template proxy (its most frequent
    ``template_proxy``). Each item shows the lemma and its 5 most frequent forms (no sentence)."""
    folder = Path(extract_folder)
    xman = read_json(folder / "manifest.json")
    corpus = xman["corpus"]
    s = salt("template", corpus)
    con = connect()
    con.execute(f"CREATE OR REPLACE TEMP VIEW inst AS SELECT * FROM read_parquet({_lst(_parts(folder, 'instances'))})")
    lem = con.sql(f"""
        WITH x AS (SELECT lemma, template_proxy, form FROM inst WHERE in_full_view AND lemma IS NOT NULL AND lemma <> '[BLANK]'
                   AND NOT starts_with(lemma, '##')),
             n AS (SELECT lemma, count(*) AS n FROM x GROUP BY 1 HAVING count(*) >= {int(min_tokens)}),
             tp AS (SELECT lemma, arg_max(template_proxy, c) AS proxy FROM (SELECT lemma, template_proxy, count(*) AS c FROM x GROUP BY ALL) GROUP BY 1),
             fc AS (SELECT lemma, form, count(*) AS c FROM x GROUP BY lemma, form),
             fr AS (SELECT *, row_number() OVER (PARTITION BY lemma ORDER BY c DESC, form) AS r FROM fc),
             fm AS (SELECT lemma, string_agg(form || ' (' || c || ')', '; ' ORDER BY c DESC, form) AS forms
                    FROM fr WHERE r <= 5 GROUP BY 1)
        SELECT n.lemma, n.n, tp.proxy, fm.forms, sha256('{s}' || n.lemma) AS h FROM n JOIN tp USING (lemma) JOIN fm USING (lemma)""").to_arrow_table().to_pylist()
    by: dict[str, list[dict]] = defaultdict(list)
    for r in lem:
        by[r["proxy"]].append(r)
    for v in by.values():
        v.sort(key=lambda r: r["h"])
    alloc = {v: min(min_per_value, len(rs)) for v, rs in by.items()}
    # the rest proportionally to the population (largest remainders); slots a value cannot fill go to the others
    while True:
        rest = size - sum(alloc.values())
        open_ = {v: len(rs) for v, rs in by.items() if len(rs) > alloc[v]}
        total = sum(open_.values())
        if rest <= 0 or not total:
            break
        extra = {v: (rest * n) // total for v, n in open_.items()}
        for v in sorted(open_, key=lambda v: (-((rest * open_[v]) % total), v))[: rest - sum(extra.values())]:
            extra[v] += 1
        for v in open_:
            alloc[v] = min(len(by[v]), alloc[v] + extra[v])
    rows = [{"lemma": r["lemma"], "verb_key": r["forms"], "stratum": v, "n": r["n"]} for v, rs in sorted(by.items()) for r in rs[: alloc[v]]]
    rows = _number("template", corpus, rows, "lemma")
    did = f"{corpus}-template-" + _h(f"{xman.get('output_id')}|{size}|{min_tokens}|{min_per_value}|{s}|{DRAWS_VERSION}")[:10]
    return _write("template", corpus, did, rows, ("item_id", "lemma", "verb_key", "stratum", "n"), git=git, out_root=out_root,
                  key="lemma", source={"extract": xman.get("output_id")},
                  extra={"size": size, "min_tokens": min_tokens, "min_per_value": min_per_value,
                         "population_by_value": {v: len(rs) for v, rs in sorted(by.items())}, "allocation": alloc,
                         "note": "verb_key column = the lemma's 5 most frequent forms (shown to the annotator); stratum = the proxy (NOT shown)"})


# ============================================================================================ class / identity audit
def audit(extract_folder: Path, variant: str, *, git: dict, out_root: Path = DRAWS_DIR) -> dict:
    """EFRAT §5.5, §5.6: the deciding instances of every PRIMARY verb whose class differs from the paper (or is not
    A / A/B / B for a paper verb) or whose identity verdict is COUNTEREXAMPLE. ``ids.csv`` carries no outcome; the
    pipeline outcome of each id is in the local ``audit_key.csv`` (Ori's side, never sent)."""
    folder = Path(extract_folder)
    xman = read_json(folder / "manifest.json")
    corpus = xman["corpus"]
    cdir = folder / f"classes-{variant}"
    if not (cdir / "manifest.json").exists():
        raise DrawError(f"no classes-{variant} in {folder} (run: hebloc loc classify)")
    con = connect()
    vc = con.sql(f"""SELECT verb_key, class, paper_class, identity_verdict, deciding_ids, identity_ids
                     FROM read_parquet('{(cdir / 'verb_classes.parquet').as_posix()}')
                     WHERE {AUDIT_PRIMARY} AND paper_comparable
                       AND (agrees_with_paper IS DISTINCT FROM true OR identity_verdict = 'COUNTEREXAMPLE')
                     ORDER BY verb_key""").to_arrow_table().to_pylist()
    seen: dict[str, dict] = {}
    key_rows = []
    for v in vc:
        why = "class" if v["class"] != v["paper_class"] else "identity"
        for which, ids in (("class", v["deciding_ids"] or []), ("identity", v["identity_ids"] or [])):
            if which == "identity" and v["identity_verdict"] != "COUNTEREXAMPLE":
                continue
            if which == "class" and why != "class":
                continue
            for x in ids:
                outcome, _, iid = x.partition(":")
                key_rows.append({"instance_key": iid, "verb_key": v["verb_key"], "audit": which, "pipeline_outcome": outcome,
                                 "class": v["class"], "paper_class": v["paper_class"], "identity_verdict": v["identity_verdict"]})
                seen.setdefault(iid, {"instance_key": iid, "verb_key": v["verb_key"], "stratum": which})
    rows = _number("audit", corpus, list(seen.values()), "instance_key")
    item_of = {r["instance_key"]: r["item_id"] for r in rows}
    for k in key_rows:
        k["item_id"] = item_of[k["instance_key"]]
    s = salt("audit", corpus)
    did = f"{corpus}-audit-" + _h(f"{xman.get('output_id')}|{variant}|{s}|{DRAWS_VERSION}")[:10]
    return _write("audit", corpus, did, rows, IDS_COLUMNS, git=git, out_root=out_root, private=sorted(key_rows, key=lambda r: (r["item_id"], r["audit"])),
                  source={"extract": xman.get("output_id"), "variant": variant},
                  extra={"n_verbs": len(vc), "primary": AUDIT_PRIMARY,
                         "local_only": ["audit_key.csv (pipeline outcomes: Ori's side, never sent to the annotator)"]})
