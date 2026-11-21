"""§5.7 tables of one corpus x resolver variant (S56-v1 §5.7; D-059 sensitivity views). PROVISIONAL until R2.

Written to ``<extract folder>/report-<variant>/`` (local data: CSV with a UTF-8 BOM + ``report.md``):
- ``coverage.csv``: VERB tokens by view; lexicon tokens by match method and key kind; unit-link status;
  function_use share; unlemmatized tokens; AUX tokens outside the scope (from the tense-aware inventory);
- ``signatures.csv``: signature distribution per paper class (lexicon tokens);
- ``outcomes.csv``: outcome shares per paper class with Wilson 95% intervals (UNDETERMINED included);
- ``class_vs_paper.csv`` + ``class_vs_paper_metrics.csv``: confusion matrix and accuracy / P / R / F1 per class
  (unit level, full view, scope all, k = 1; comparable keys only, combined keys whose members share one class);
- ``identity.csv``: every A/B paper verb with its verdict (strict and על-as-ב), family and putting/removal;
- ``table1_check.csv``: Table 1 verbs should be A or A/B, never B (§3.2.1);
- ``sensitivity.csv``: what changes with the unit level vs the raw lemma, without function_use tokens, without
  partitive evidence, and at k = 2 and 3.
Every number traces back to instance ids (``verb_classes.deciding_ids``) and so to ``sent_id`` and ``ref``.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa

from hebloc.loc.lexicon import Lexicon
from hebloc.loc.manifest import write_csv, write_manifest
from hebloc.loc.resolve import _lst, _parts, resolver_id
from hebloc.loc.source import connect
from hebloc.loc.units import INVENTORY_T_DIR
from hebloc.stats.accuracy import wilson
from hebloc.store.io import atomic_write_text, file_sha256, read_json

REPORT_VERSION = "report-r2.0"
PRIMARY = "level = 'unit' AND view = 'full' AND scope = 'all' AND k = 1"


class ReportError(Exception):
    pass


def _rows(con, sql: str) -> list[dict]:
    return con.sql(sql).to_arrow_table().to_pylist()


def report(extract_folder: Path, variant: str, lex: Lexicon, *, git: dict, inventory_t_dir: Path = INVENTORY_T_DIR) -> dict:
    folder = Path(extract_folder)
    xman = read_json(folder / "manifest.json")
    cdir, rdir = folder / f"classes-{variant}", folder / f"roles-{variant}"
    if not (cdir / "manifest.json").exists():
        raise ReportError(f"no classes for {variant} in {folder} (run: hebloc loc classify)")
    out = folder / f"report-{variant}"
    corpus = xman["corpus"]
    con = connect()
    con.execute(f"CREATE OR REPLACE TEMP VIEW inst AS SELECT * FROM read_parquet({_lst(_parts(folder, 'instances'))})")
    con.execute(f"CREATE OR REPLACE TEMP VIEW roles AS SELECT * FROM read_parquet({_lst(_parts(rdir, 'roles'))})")
    con.execute(f"CREATE OR REPLACE TEMP VIEW vc AS SELECT * FROM read_parquet('{(cdir / 'verb_classes.parquet').as_posix()}')")
    tables: dict[str, list[dict]] = {}

    # coverage -------------------------------------------------------------------------------------------
    cov = []
    for view, col in (("full", "in_full_view"), ("curated", "in_curated_view")):
        tot = con.sql(f"SELECT count(*) FROM inst WHERE {col}").fetchall()[0][0]
        for what, sql in (("verb_tokens", "TRUE"), ("in_lexicon", "in_lexicon"),
                          ("lexicon_match_lemma", "in_lexicon AND match_method = 'lemma'"),
                          ("lexicon_match_form", "in_lexicon AND match_method = 'form'"),
                          ("lexicon_match_both", "in_lexicon AND match_method = 'both'"),
                          ("lexicon_key_single", "in_lexicon AND NOT contains(verb_key, '|')"),
                          ("lexicon_key_combined", "in_lexicon AND contains(verb_key, '|') AND NOT contains(verb_key, '~')"),
                          ("lexicon_key_with_tilde", "in_lexicon AND contains(verb_key, '~')"),
                          ("unlemmatized", "link_status = 'unlemmatized'"),
                          ("unit_link_auto", "link_status = 'auto'"), ("unit_link_reviewed", "link_status = 'reviewed'"),
                          ("unit_link_auto_inactive", "link_status = 'auto_inactive'"),
                          ("function_class_tagged", "function_class IS NOT NULL"), ("function_use", "function_use"),
                          ("tree_invalid", "list_contains(flags, 'tree_invalid')"), ("multi_piece", "list_contains(flags, 'multi_piece')")):
            n = con.sql(f"SELECT count(*) FROM inst WHERE {col} AND ({sql})").fetchall()[0][0]
            cov.append({"view": view, "what": what, "n": n, "share_of_view": round(n / tot, 4) if tot else None})
    aux = Path(inventory_t_dir) / f"{corpus}_aux.parquet"
    if aux.exists():
        a = con.sql(f"SELECT sum(n), sum(n) FILTER (WHERE has_do), sum(n) FILTER (WHERE has_do AND has_bm_pp) "
                    f"FROM read_parquet('{aux.as_posix()}')").fetchall()[0]
        cov += [{"view": "all_units", "what": "aux_tokens_outside_scope", "n": a[0], "share_of_view": None},
                {"view": "all_units", "what": "aux_with_object", "n": a[1], "share_of_view": None},
                {"view": "all_units", "what": "aux_with_object_and_b_min_pp", "n": a[2], "share_of_view": None}]
    tables["coverage"] = cov

    # signatures and outcomes per paper class ---------------------------------------------------------------
    tables["signatures"] = _rows(con, """SELECT coalesce(paper_class, 'non_lexicon') AS paper_class, signature, count(*) AS n
        FROM inst WHERE in_full_view GROUP BY ALL ORDER BY paper_class, n DESC, signature""")
    oc = _rows(con, """SELECT coalesce(i.paper_class, 'non_lexicon') AS paper_class, r.outcome, count(*) AS n
        FROM inst i JOIN roles r USING (instance_id) WHERE i.in_full_view GROUP BY ALL ORDER BY 1, 2""")
    tot = {}
    for r in oc:
        tot[r["paper_class"]] = tot.get(r["paper_class"], 0) + r["n"]
    for r in oc:
        p = r["n"] / tot[r["paper_class"]]
        lo, hi = wilson(p, tot[r["paper_class"]])
        r.update({"total": tot[r["paper_class"]], "share": round(p, 4), "ci95_low": lo, "ci95_high": hi})
    tables["outcomes"] = oc

    # class vs paper ---------------------------------------------------------------------------------------
    tables["class_vs_paper"] = _rows(con, f"""SELECT paper_class, class, count(*) AS n FROM vc WHERE {PRIMARY} AND paper_comparable
        GROUP BY ALL ORDER BY 1, 2""")
    met = []
    comp = _rows(con, f"SELECT paper_class, class FROM vc WHERE {PRIMARY} AND paper_comparable")
    n_all = len(comp)
    acc = sum(1 for r in comp if r["paper_class"] == r["class"]) / n_all if n_all else None
    for c in ("A", "A/B", "B"):
        tp = sum(1 for r in comp if r["paper_class"] == c and r["class"] == c)
        fp = sum(1 for r in comp if r["paper_class"] != c and r["class"] == c)
        fn = sum(1 for r in comp if r["paper_class"] == c and r["class"] != c)
        prec = tp / (tp + fp) if tp + fp else None
        rec = tp / (tp + fn) if tp + fn else None
        f1 = 2 * prec * rec / (prec + rec) if prec and rec else None
        met.append({"class": c, "support": tp + fn, "predicted": tp + fp, "precision": prec, "recall": rec, "f1": f1})
    met.append({"class": "accuracy", "support": n_all, "predicted": None, "precision": acc, "recall": None, "f1": None})
    tables["class_vs_paper_metrics"] = met

    # identity ---------------------------------------------------------------------------------------------
    tables["identity"] = _rows(con, f"""SELECT verb_key, paper_class, n_a, n_b, identity_verdict, identity_family,
        identity_verdict_al_as_b, identity_family_al_as_b, putting_removal, fn8_min_both_forms_both_frames,
        array_to_string(families_frame_a, '|') AS families_frame_a, array_to_string(families_frame_b, '|') AS families_frame_b,
        array_to_string(identity_ids, '; ') AS identity_ids
        FROM vc WHERE {PRIMARY} AND in_lexicon AND class = 'A/B' ORDER BY verb_key""")

    # Table 1 check ----------------------------------------------------------------------------------------
    t1 = sorted({e.id for e in lex.entries for r in e.paper_refs if str(r.get("where", "")).startswith("Table 1")})
    con.register("t1", pa.table({"entry_id": t1}))
    tables["table1_check"] = _rows(con, f"""SELECT t1.entry_id, v.verb_key, v.class, v.class = 'B' AS violates_table1
        FROM t1 LEFT JOIN (SELECT * FROM vc WHERE {PRIMARY}) v ON list_contains(string_split(v.verb_key, '|'), t1.entry_id)
        ORDER BY 1, 2""")

    # sensitivity -------------------------------------------------------------------------------------------
    sens = []
    for name, a, b in (("unit_vs_lemma", "level = 'unit'", "level = 'lemma'"),):
        n = con.sql(f"""SELECT count(*) FROM (SELECT verb_key, class FROM vc WHERE {a} AND view = 'full' AND scope = 'all' AND k = 1) x
                       JOIN (SELECT verb_key, class FROM vc WHERE {b} AND view = 'full' AND scope = 'all' AND k = 1) y USING (verb_key)
                       WHERE x.class <> y.class""").fetchall()[0][0]
        sens.append({"comparison": name, "keys_with_a_different_class": n,
                     "note": "keys present at both levels (lexicon keys and unlinked lemmas); linked lemmas merge into their unit"})
    n_units = con.sql(f"SELECT count(*) FROM vc WHERE {PRIMARY}").fetchall()[0][0]
    n_lem = con.sql("SELECT count(*) FROM vc WHERE level = 'lemma' AND view = 'full' AND scope = 'all' AND k = 1").fetchall()[0][0]
    sens.append({"comparison": "number_of_keys_unit_vs_lemma", "keys_with_a_different_class": None, "note": f"units {n_units}; lemmas {n_lem}"})
    for name, cond in (("no_function_use", "scope = 'no_function_use' AND k = 1"), ("k2", "scope = 'all' AND k = 2"),
                       ("k3", "scope = 'all' AND k = 3")):
        n = con.sql(f"""SELECT count(*) FROM (SELECT verb_key, class FROM vc WHERE {PRIMARY}) x
                       JOIN (SELECT verb_key, class FROM vc WHERE level = 'unit' AND view = 'full' AND {cond}) y USING (verb_key)
                       WHERE x.class <> y.class""").fetchall()[0][0]
        sens.append({"comparison": f"primary_vs_{name}", "keys_with_a_different_class": n, "note": ""})
    n = con.sql(f"SELECT count(*) FROM vc WHERE {PRIMARY} AND class <> class_without_partitive").fetchall()[0][0]
    sens.append({"comparison": "primary_vs_without_partitive", "keys_with_a_different_class": n,
                 "note": "Frame A evidence from the partitive rule (fn 24, 27) removed (D-059 P7)"})
    tables["sensitivity"] = sens

    for name, rows in tables.items():
        t = pa.Table.from_pylist(rows) if rows else pa.table({"empty": pa.array([], pa.string())})
        write_csv(t, out / f"{name}.csv")
    md = _markdown(corpus, variant, xman, tables)
    atomic_write_text(md, out / "report.md")
    return write_manifest(out, what=f"§5.7 tables, PROVISIONAL ({resolver_id(variant)})", git=git,
                          source={"extract": xman.get("output_id"), "classes_manifest_sha256": file_sha256(cdir / "manifest.json")},
                          extra={"report_version": REPORT_VERSION, "corpus": corpus, "variant": variant,
                                 "tables": {k: len(v) for k, v in tables.items()}, "status": "PROVISIONAL (Phase B; not validated)"})


def _markdown(corpus: str, variant: str, xman: dict, t: dict) -> str:
    cov = {(r["view"], r["what"]): r for r in t["coverage"]}
    full = lambda w: cov.get(("full", w), {}).get("n")  # noqa: E731
    lines = [f"# {corpus}: §5.7 tables, resolver {resolver_id(variant)} (PROVISIONAL)", "",
             f"Extraction `{xman.get('output_id')}` ({xman.get('mode')}); units {xman.get('units', {}).get('audit')} "
             f"(auto links in force: {xman.get('units', {}).get('auto_links_in_force')}); function list "
             f"{xman.get('functions', {}).get('status')}.", "",
             "**Not a result.** Phase B demonstration: the noun types, the identification candidates and the resolver are "
             "not validated yet (Phase C).", "",
             "## Coverage (full view)", "",
             f"- VERB tokens: {full('verb_tokens')}; in the lexicon: {full('in_lexicon')} "
             f"(lemma {full('lexicon_match_lemma')}, form {full('lexicon_match_form')}, both {full('lexicon_match_both')})",
             f"- unlemmatized: {full('unlemmatized')}; function_use tokens: {full('function_use')}",
             f"- unit links in force: auto {full('unit_link_auto')}, reviewed {full('unit_link_reviewed')}; "
             f"inactive auto links (audit pending): {full('unit_link_auto_inactive')}", "",
             "## Class vs. the paper (unit level, full view, k = 1, comparable keys)", "", "| paper | ours | n |", "|---|---|---|"]
    lines += [f"| {r['paper_class']} | {r['class']} | {r['n']} |" for r in t["class_vs_paper"]]
    lines += ["", "| class | support | precision | recall | F1 |", "|---|---|---|---|---|"]
    fmt = lambda x: "" if x is None else f"{x:.3f}"  # noqa: E731
    lines += [f"| {r['class']} | {r['support']} | {fmt(r['precision'])} | {fmt(r['recall'])} | {fmt(r['f1'])} |"
              for r in t["class_vs_paper_metrics"]]
    from collections import Counter

    ver = Counter(r["identity_verdict"] for r in t["identity"])
    lines += ["", "## Identity (A/B paper verbs)", "", f"- strict: {dict(ver)}",
              f"- Table 1 violations (class B): {sum(1 for r in t['table1_check'] if r['violates_table1'])}", "",
              "## Sensitivity", ""]
    lines += [f"- {r['comparison']}: {r['keys_with_a_different_class']} {r['note']}" for r in t["sensitivity"]]
    return "\n".join(lines) + "\n"
