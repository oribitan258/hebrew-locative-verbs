"""Standalone analysis package (D-051): every registered parse result + sentences + catalog + official §4
statistics + tools, for independent exploration WITHOUT Dicta and without the main project.

Layout of the package (``hebloc-analysis-pack/``)::

    CLAUDE.md README.md ASSIGNMENT.md RESEARCH_IDEAS.md pyproject.toml uv.lock MANIFEST.json VERIFICATION.json
    hebpack/                 tools (DuckDB views, verbatim official statistics code, self-test, verify, charts)
    data/tokens/<corpus>/<run_id>.parquet     every Dicta word, ALL token columns + corpus_id, doc_id, shard
    data/pieces/<corpus>/<run_id>.parquet     parser pieces + Dicta piece status (no raw JSON)
    data/run_units/<corpus>/<run_id>.parquet  the run's units (sent_id, text_sha1, shard), incl. empty units
    data/sentences/<corpus>/part-*.parquet    the M2 units, byte-identical copies (text, provenance, tags)
    data/documents.parquet                    the catalog, byte-identical copy
    official/                                 final statistics (Parquet + unit_metrics), CSV, figures, accuracy, report
    docs/                                     project documentation copies
    analyses/                                 empty: the recipient's own work

Each tokens/pieces/run_units file has one Parquet row group per original shard (all pieces of a unit are in one
shard), so the package's self-test runs the official ``hebloc.stats`` code on exactly the official batches.

Lossless by construction and by check (``VERIFICATION.json``): per run, row counts and an order-independent content
hash over every source column equal the source; every unit's ``sha1(text_norm)`` equals the parser input's
``text_sha1``; a sample of Dicta's raw JSON is re-derived and every raw field found in the tokens or derivable.
"""

from __future__ import annotations

import hashlib
import json
import random
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from hebloc.paths import CATALOG_DIR, CORPORA, DATA_DIR, DOCS_DIR, RESULTS_DIR, STATS_DIR, UNITS_DIR
from hebloc.store.io import atomic_write_json, file_sha256, sql_list, sql_str

PACK_NAME = "hebloc-analysis-pack"
PACK_VERSION = "1"
SHARE_DIR = DATA_DIR / "share"
TEMPLATES = Path(__file__).parent / "pack_templates"
STATS_CODE = Path(__file__).parent / "stats"
VENDORED = ("metrics.py", "tables.py")              # copied byte-for-byte into hebpack/_official/
PIECE_STATUS_COLS = ["status", "compute_mst", "error"]
DOC_FILES = ("SECTIONS_2-4.md", "stats_analysis.md", "m6_design.md", "corpus_report.md", "data_dictionary.md",
             "m2_preprocessing.md", "pilot_report.md", "decisions.md")


class PackRefusal(RuntimeError):
    pass


# ----------------------------------------------------------------------------------------- inputs

def final_stats_dir(rs) -> Path:
    """The newest ``data/stats/final-*`` folder computed from exactly these registered runs, verified."""
    from hebloc.stats.compute import verify

    for d in sorted(STATS_DIR.glob("final-*"), reverse=True):
        if d.name.endswith(".partial") or not (d / "manifest.json").exists():
            continue
        man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        if man.get("status") == "final" and man.get("runs") == rs.refs():
            probs = verify(d)
            if probs:
                raise PackRefusal(f"{d.name} fails stats verify: {probs[:3]}")
            return d
    raise PackRefusal("no verified final statistics for the registered runs (run: hebloc stats run --registered)")


def registered_runset():
    from hebloc.stats import runset as R

    try:
        rs = R.check(R.from_registry())
    except R.RunSetRefusal as e:
        raise PackRefusal(str(e)) from e
    if rs.status() != "final":
        raise PackRefusal("the registry does not cover all five corpora completely (status is not final)")
    return rs


# ----------------------------------------------------------------------------------------- export

def _with_ids(t: pa.Table, corpus: str, shard: str) -> pa.Table:
    parts = pc.split_pattern(t["sent_id"], ":")
    n = t.num_rows
    return (t.append_column("corpus_id", pa.array([corpus] * n, pa.string()))
             .append_column("doc_id", pc.list_element(parts, 1))
             .append_column("shard", pa.array([shard] * n, pa.string())))


def _pieces_with_status(run, shard: str) -> pa.Table:
    pieces = pq.read_table(run.part_file("pieces", shard))
    raw = pq.read_table(run.part_file("dicta_raw", shard), columns=["sent_id", "piece_idx"] + PIECE_STATUS_COLS)
    if pieces.num_rows != raw.num_rows:
        raise PackRefusal(f"{run.ref} {shard}: {pieces.num_rows} pieces but {raw.num_rows} raw rows")
    j = pieces.join(raw, keys=["sent_id", "piece_idx"], join_type="left outer")
    j = j.sort_by([("sent_id", "ascending"), ("piece_idx", "ascending")])
    if j.num_rows != pieces.num_rows or j["status"].null_count:
        raise PackRefusal(f"{run.ref} {shard}: pieces and raw output do not match one-to-one")
    return j


def _write_run(run, corpus: str, out: Path, progress: bool) -> dict:
    """tokens / pieces / run_units of one run, one row group per shard. Returns row counts."""
    writers: dict[str, pq.ParquetWriter] = {}
    counts = {"tokens": 0, "pieces": 0, "run_units": 0, "shards": 0}
    shards = run.shards()
    it = shards
    if progress:
        from tqdm import tqdm

        it = tqdm(shards, desc=f"export {run.ref}", unit="shard")
    try:
        for s in it:
            tok = run.path / "tokens" / f"{s}.parquet"
            if not tok.exists():
                raise PackRefusal(f"{run.ref}: tokens missing for {s} (run: hebloc tokens {run.ref})")
            tables = {
                "tokens": _with_ids(pq.read_table(tok), corpus, s),
                "pieces": _with_ids(_pieces_with_status(run, s), corpus, s),
                "run_units": _with_ids(pq.read_table(run.part_file("inputs", s), columns=["sent_id", "text_sha1"]),
                                       corpus, s),
            }
            for part, t in tables.items():
                if t.num_rows == 0:
                    continue
                if part not in writers:
                    path = out / "data" / part / corpus / f"{run.run_id}.parquet"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    writers[part] = pq.ParquetWriter(path, t.schema, compression="zstd")
                writers[part].write_table(t, row_group_size=max(t.num_rows, 1))
                counts[part] += t.num_rows
            counts["shards"] += 1
    finally:
        for w in writers.values():
            w.close()
    return counts


def _copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, dirs_exist_ok=False)


def _copy_official(stats_dir: Path, out: Path) -> None:
    off = out / "official"
    _copy_tree(stats_dir, off / "stats_tables" / stats_dir.name)
    _copy_tree(RESULTS_DIR / "stats", off / "results")
    report = (DOCS_DIR / "stats_report.md").read_text(encoding="utf-8")
    report = report.replace("../results/stats/figures/", "results/figures/").replace("`results/stats/", "`official/results/")
    (off / "stats_report.md").write_text(report, encoding="utf-8", newline="\n")


def _copy_templates(out: Path, facts: dict) -> None:
    for src in sorted(TEMPLATES.rglob("*")):
        if src.is_dir() or "__pycache__" in src.parts:
            continue
        dst = out / src.relative_to(TEMPLATES)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix in (".md", ".toml", ".py"):
            text = src.read_text(encoding="utf-8")
            for k, v in facts.items():
                text = text.replace("{{" + k + "}}", str(v))
            dst.write_text(text, encoding="utf-8", newline="\n")
        else:
            shutil.copy2(src, dst)
    vend = out / "hebpack" / "_official"
    vend.mkdir(parents=True, exist_ok=True)
    for name in VENDORED:
        shutil.copy2(STATS_CODE / name, vend / name)


# ----------------------------------------------------------------------------------------- verification

def _hash_sql(files: list[Path], cols: list[str], where: str = "TRUE") -> str:
    expr = "hash(" + ", ".join(f'"{c}"' for c in cols) + ")"
    return (f"SELECT count(*), sum({expr}::HUGEINT)::VARCHAR, bit_xor({expr})::VARCHAR "
            f"FROM read_parquet({sql_list(files)}, union_by_name=true) WHERE {where}")


def verify_run_lossless(con, run, corpus: str, out: Path) -> dict:
    """Source shard files vs package file: count + content hashes over ALL source columns."""
    rep = {}
    for part, src_part in (("tokens", "tokens"), ("pieces", "pieces"), ("run_units", "inputs")):
        if part == "tokens":
            src = [run.path / "tokens" / f"{s}.parquet" for s in run.shards()]
        else:
            src = run.part_files(src_part)
        cols = pq.read_schema(src[0]).names
        if part == "run_units":
            cols = ["sent_id", "text_sha1"]
        pkg = out / "data" / part / corpus / f"{run.run_id}.parquet"
        a = con.execute(_hash_sql(src, cols)).fetchone()
        b = con.execute(_hash_sql([pkg], cols)).fetchone() if pkg.exists() else (0, None, None)
        if part == "pieces":       # status columns come from dicta_raw: check them against it too
            raw = run.part_files("dicta_raw")
            rc = ["sent_id", "piece_idx"] + PIECE_STATUS_COLS
            ra, rb = con.execute(_hash_sql(raw, rc)).fetchone(), con.execute(_hash_sql([pkg], rc)).fetchone()
            rep["piece_status"] = {"rows": ra[0], "equal": tuple(ra) == tuple(rb)}
        rep[part] = {"rows": a[0], "equal": tuple(a) == tuple(b)}
    return rep


def verify_text(con, out: Path) -> dict:
    """Every unit of every run: sha1(text_norm of the shipped sentence) == the parser input's text_sha1."""
    rep = {}
    for corpus in CORPORA:
        r = con.execute(f"""
            SELECT count(*), count(*) FILTER (WHERE s.sent_id IS NULL),
                   count(*) FILTER (WHERE sha1(s.text_norm) IS DISTINCT FROM u.text_sha1)
            FROM read_parquet({sql_str((out / 'data/run_units' / corpus).as_posix() + '/*.parquet')}) u
            LEFT JOIN read_parquet({sql_str((out / 'data/sentences' / corpus).as_posix() + '/*.parquet')}) s USING (sent_id)
        """).fetchone()
        n_sent = con.execute(f"SELECT count(*) FROM read_parquet("
                             f"{sql_str((out / 'data/sentences' / corpus).as_posix() + '/*.parquet')})").fetchone()[0]
        rep[corpus] = {"run_units": r[0], "sentences": n_sent, "missing_sentence": r[1], "text_mismatch": r[2],
                       "ok": r[1] == 0 and r[2] == 0 and r[0] == n_sent}
    return rep


def _bio_spans(tags: list[str]) -> list[tuple[int, int, str]]:
    spans, start, label = [], None, None
    for i, t in enumerate(tags + ["O"]):
        if start is not None and (t == "O" or t.startswith("B-") or t[2:] != label):
            spans.append((start, i - 1, label))
            start = None
        if t.startswith("B-") or (t.startswith("I-") and start is None):
            start, label = i, t[2:]
    return spans


def _same_int(a, b) -> bool:
    import math

    a = None if a is None or (isinstance(a, float) and math.isnan(a)) else int(a)
    return a == (None if b is None else int(b))


def verify_raw_coverage(rs, n_shards_per_corpus: int = 3, seed: int = 7) -> dict:
    """Re-derive a sample of Dicta's raw JSON (all of Mikra + random shards per corpus) and check that every
    raw field is in the tokens or derivable from them."""
    from hebloc.parse.tokens import _feats

    rng = random.Random(seed)
    rep = {}
    for corpus, runs in rs.runs.items():
        pairs = [(r, s) for r in runs for s in r.shards()]
        sample = pairs if corpus == "mikra" else rng.sample(pairs, min(n_shards_per_corpus, len(pairs)))
        c = {"pieces": 0, "tokens": 0, "seg_over_2": 0, "field_mismatch": 0, "dep_head_mismatch": 0,
             "root_mismatch": 0, "entities": 0, "entities_not_from_bio": 0, "raw_keys": set(), "token_keys": set()}
        for run, s in sample:
            raw = pq.read_table(run.part_file("dicta_raw", s), columns=["sent_id", "piece_idx", "raw_json"]).to_pylist()
            groups: dict[tuple, list[dict]] = {}            # plain Python values (pandas turns nulls into NaN)
            for row in pq.read_table(run.path / "tokens" / f"{s}.parquet").to_pylist():
                groups.setdefault((row["sent_id"], row["piece_idx"]), []).append(row)
            for g in groups.values():
                g.sort(key=lambda x: x["word_idx"])
            for r in raw:
                if not r["raw_json"]:
                    continue
                j = json.loads(r["raw_json"])
                c["raw_keys"] |= set(j)
                g = groups.get((r["sent_id"], r["piece_idx"]))
                toks = j["tokens"]
                c["pieces"] += 1
                c["tokens"] += len(toks)
                if g is None or len(g) != len(toks):
                    c["field_mismatch"] += len(toks)
                    continue
                rows = g
                for t, row in zip(toks, rows):
                    c["token_keys"] |= set(t)
                    seg = t.get("seg") or [t["token"]]
                    m, syn = t.get("morph") or {}, t.get("syntax") or {}
                    if len(seg) > 2:
                        c["seg_over_2"] += 1
                    ok = (row["form"] == t["token"] and row["host"] == seg[-1]
                          and (row["prefix"] or None) == (seg[0] if len(seg) > 1 else None)
                          and row["lemma"] == t.get("lex") and row["upos"] == m.get("pos")
                          and (row["feats"] or None) == _feats(m.get("feats"))
                          and list(row["prefix_upos"]) == list(m.get("prefixes") or [])
                          and (row["suffix"] or None) == (m.get("suffix") or None)
                          and (row["suffix_feats"] or None) == _feats(m.get("suffix_feats"))
                          and _same_int(row["head"], syn.get("dep_head_idx"))
                          and row["deprel"] == syn.get("dep_func") and row["ner"] == t.get("ner"))
                    c["field_mismatch"] += not ok
                    h = syn.get("dep_head_idx")
                    if h is not None and h >= 0 and syn.get("dep_head") != toks[h]["token"]:
                        c["dep_head_mismatch"] += 1
                roots = [i for i, t in enumerate(toks) if (t.get("syntax") or {}).get("dep_head_idx", 0) < 0]
                if j.get("root_idx") is not None and j["root_idx"] not in roots and roots:
                    c["root_mismatch"] += 1
                bio = set(_bio_spans([row["ner"] or "O" for row in rows]))
                for e in j.get("ner_entities") or []:
                    c["entities"] += 1
                    c["entities_not_from_bio"] += (e["token_start"], e["token_end"], e["label"]) not in bio
        c["raw_keys"], c["token_keys"] = sorted(c["raw_keys"]), sorted(c["token_keys"])
        c["shards_checked"] = len(sample)
        rep[corpus] = c
    return rep


# ----------------------------------------------------------------------------------------- manifest + zip

def write_manifest(out: Path, meta: dict) -> dict:
    files = {}
    for f, rel in _shipped(out):
        if rel.as_posix() != "MANIFEST.json":
            files[rel.as_posix()] = {"bytes": f.stat().st_size, "sha256": file_sha256(f)}
    man = {**meta, "files": files, "total_bytes": sum(v["bytes"] for v in files.values())}
    atomic_write_json(man, out / "MANIFEST.json")
    return man


PACKAGE_EXCLUDE = (".venv", "__pycache__", "_selftest", "_status.json", "to-ori")   # never shipped: local env, caches, workspace state


def _shipped(folder: Path):
    for f in sorted(folder.rglob("*")):
        rel = f.relative_to(folder)
        if f.is_file() and not any(p in PACKAGE_EXCLUDE for p in rel.parts):
            yield f, rel


def make_zip(folder: Path) -> Path:
    """Files at the zip ROOT (no top folder): Windows 'Extract All' creates ONE folder named after the zip, with
    CLAUDE.md directly inside, which is the folder to open in VS Code."""
    z = folder.with_suffix(".zip")
    if z.exists():
        raise PackRefusal(f"{z} already exists")
    tmp = z.with_name(z.name + ".partial")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        for f, rel in _shipped(folder):
            zf.write(f, rel.as_posix())
    with zipfile.ZipFile(tmp) as zf:
        if zf.testzip() is not None:
            raise PackRefusal(f"{tmp}: zip test failed")
    tmp.replace(z)
    Path(str(z) + ".sha256").write_text(f"{file_sha256(z)}  {z.name}\n", encoding="utf-8", newline="\n")
    return z


# ----------------------------------------------------------------------------------------- build

def build(out: Path | None = None, *, zip_it: bool = True, progress: bool = True, raw_sample_shards: int = 3) -> dict:
    from hebloc.inventory import _git_commit

    rs = registered_runset()
    stats_dir = final_stats_dir(rs)
    out = Path(out) if out else SHARE_DIR / PACK_NAME
    if out.exists():
        raise PackRefusal(f"{out} already exists: nothing overwritten")
    work = out.with_name(out.name + ".partial")
    if work.exists():
        shutil.rmtree(work)          # our own unfinished attempt
    work.mkdir(parents=True)

    counts: dict[str, dict] = {}
    for corpus, runs in rs.runs.items():
        for run in runs:
            counts[run.ref] = _write_run(run, corpus, work, progress)
    for corpus in CORPORA:
        _copy_tree(UNITS_DIR / corpus, work / "data" / "sentences" / corpus)
    shutil.copy2(CATALOG_DIR / "documents.parquet", work / "data" / "documents.parquet")
    shutil.copy2(CATALOG_DIR / "documents.manifest.json", work / "data" / "documents.manifest.json")
    _copy_official(stats_dir, work)
    (work / "docs").mkdir()
    for name in DOC_FILES:
        shutil.copy2(DOCS_DIR / name, work / "docs" / name)

    totals = {k: sum(c[k] for c in counts.values()) for k in ("tokens", "pieces", "run_units")}
    facts = {"STATS_ID": stats_dir.name, "BUILT": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
             "TOKENS": f"{totals['tokens']:,}", "UNITS": f"{totals['run_units']:,}", "PIECES": f"{totals['pieces']:,}",
             "RUNS": len(counts), "PACK_VERSION": PACK_VERSION}
    _copy_templates(work, facts)
    (work / "analyses").mkdir(exist_ok=True)

    # ---- verification (before publishing)
    con = duckdb.connect()
    lossless = {ref: verify_run_lossless(con, run, corpus, work)
                for corpus, runs in rs.runs.items() for run in runs for ref in [run.ref]}
    text = verify_text(con, work)
    raw = verify_raw_coverage(rs, raw_sample_shards)
    vend = {n: file_sha256(STATS_CODE / n) == file_sha256(work / "hebpack" / "_official" / n) for n in VENDORED}
    problems = [f"{ref} {part}" for ref, r in lossless.items() for part, v in r.items() if not v["equal"]]
    problems += [f"text {c}" for c, v in text.items() if not v["ok"]]
    problems += [f"raw {c}: {k}={v[k]}" for c, v in raw.items()
                 for k in ("seg_over_2", "field_mismatch", "dep_head_mismatch", "root_mismatch") if v[k]]
    problems += [f"vendored {n}" for n, ok in vend.items() if not ok]
    verification = {"lossless_runs": lossless, "text_sha1": text, "raw_coverage": raw, "vendored_code_identical": vend,
                    "totals": totals, "problems": problems, "ok": not problems}
    atomic_write_json(verification, work / "VERIFICATION.json")
    if problems:
        raise PackRefusal("verification failed; nothing published (partial package kept in "
                          f"{work}):\n  " + "\n  ".join(problems[:20]))

    meta = {"package": PACK_NAME, "pack_version": PACK_VERSION, "created_utc": datetime.now(timezone.utc).isoformat(
        timespec="seconds"), "code_commit": _git_commit(), "stats_id": stats_dir.name, "registry": rs.refs(),
        "totals": totals, "per_run": counts, "facts": facts, "template_files": template_files(),
        "vendored_code_sha256": {n: file_sha256(STATS_CODE / n) for n in VENDORED}}
    man = write_manifest(work, meta)
    work.replace(out)
    res = {"path": str(out), "total_bytes": man["total_bytes"], "files": len(man["files"]), "totals": totals,
           "verification_ok": True}
    if zip_it:
        z = make_zip(out)
        res["zip"] = str(z)
        res["zip_bytes"] = z.stat().st_size
    return res


def template_files() -> list[str]:
    """Package paths that come from the templates (+ the vendored official code)."""
    rel = [p.relative_to(TEMPLATES).as_posix() for p in sorted(TEMPLATES.rglob("*"))
           if p.is_file() and "__pycache__" not in p.parts]
    return rel + [f"hebpack/_official/{n}" for n in VENDORED]


def refresh(out: Path | None = None, *, zip_it: bool = True) -> dict:
    """Update ONLY the template files (docs, CLAUDE.md, hebpack tools) of a built, verified package, re-write
    MANIFEST.json and re-make the zip. The data, official results and VERIFICATION.json are untouched: every
    non-template file must be byte-identical before and after (checked)."""
    from hebloc.inventory import _git_commit

    out = Path(out) if out else SHARE_DIR / PACK_NAME
    probs = verify_package(out)
    if probs:
        raise PackRefusal(f"{out} does not match its MANIFEST.json; rebuild instead: {probs[:5]}")
    old = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    tmpl = set(template_files())
    stale = set(old.get("template_files") or []) - tmpl
    data_before = {k: v["sha256"] for k, v in old["files"].items() if k not in tmpl | stale}
    facts = old.get("facts") or {
        "STATS_ID": old["stats_id"], "BUILT": old["created_utc"][:10], "PACK_VERSION": old["pack_version"],
        "TOKENS": f"{old['totals']['tokens']:,}", "UNITS": f"{old['totals']['run_units']:,}",
        "PIECES": f"{old['totals']['pieces']:,}", "RUNS": len(old["per_run"])}
    for rel in stale:
        (out / rel).unlink(missing_ok=True)
    _copy_templates(out, facts)
    meta = {k: v for k, v in old.items() if k not in ("files", "total_bytes")}
    meta.update({"facts": facts, "template_files": sorted(tmpl), "refreshed_utc": datetime.now(timezone.utc).isoformat(
        timespec="seconds"), "refresh_code_commit": _git_commit()})
    man = write_manifest(out, meta)
    data_after = {k: v["sha256"] for k, v in man["files"].items() if k not in tmpl}
    if data_after != data_before:
        changed = sorted(set(data_after.items()) ^ set(data_before.items()))[:5]
        raise PackRefusal(f"non-template files changed during refresh (must never happen): {changed}")
    res = {"path": str(out), "files": len(man["files"]), "total_bytes": man["total_bytes"],
           "template_files": len(tmpl), "data_files_unchanged": len(data_after)}
    if zip_it:
        z = out.with_suffix(".zip")
        for f in (z, Path(str(z) + ".sha256")):
            f.unlink(missing_ok=True)        # our own previous zip of this package (re-made below)
        z = make_zip(out)
        res.update({"zip": str(z), "zip_bytes": z.stat().st_size})
    return res


def verify_package(folder: Path) -> list[str]:
    """Re-hash a built package against its MANIFEST.json (same check as the package's own hebpack.verify)."""
    folder = Path(folder)
    man = json.loads((folder / "MANIFEST.json").read_text(encoding="utf-8"))
    probs = []
    for rel, meta in man["files"].items():
        f = folder / rel
        if not f.exists():
            probs.append(f"missing {rel}")
        elif f.stat().st_size != meta["bytes"] or file_sha256(f) != meta["sha256"]:
            probs.append(f"changed {rel}")
    return probs


def sha1_text(s: str) -> str:          # the parser-input convention (inputs.text_sha1)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()
