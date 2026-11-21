"""Verb classes, the identity test and the role-free swap test (S56-v1 §5.5–§5.7; I3; D-059).

Per corpus x view (full = primary, curated) x level (``unit`` = the D-059 verb unit, primary; ``lemma`` = Dicta's
raw lemma / ``verb_key``) x scope (``all`` = primary; ``no_function_use`` = the D-059 P6 sensitivity view that drops
only ``function_use`` tokens, never whole lemmas) x k (1 primary; 2, 3 sensitivity):

- CLASS (§5.5, fixed precedence): A/B (>= k A and >= k B) > A (>= k A, no B) > B (>= k B, no A) > NON_LOCATIVE (no
  A/B, and >= 1 positive NON_LOCATIVE instance, or >= 20 instances with an object and none A, B or AMBIGUOUS: the
  rule of three) > AMBIGUOUS (no A/B, no non-locative evidence, >= 1 AMBIGUOUS) > INSUFFICIENT_EVIDENCE. Never
  forced; every row carries its evidence counts, ``class_basis`` and ``deciding_ids``. ``class_without_partitive``
  is the D-059 P7 sensitivity (partitive Frame A removed).
- IDENTITY (§5.6, the paper's exact claim, only for A/B): the prepositional families marking the Location in FULL
  Frame A instances (DO + a Location PP) and the Locatum in FULL Frame B instances (DO + a Locatum PP).
  IDENTITY_ATTESTED (a shared family), COUNTEREXAMPLE (both sets non-empty, none shared), NOT_TESTABLE. Reported
  strictly and with על counted as ב in Frame A (fn 22). Partitive (fn 24, 27) and bare-NP (fn 13, 21) instances have
  no PP in that role, so they never decide identity; other PPs alongside are not counterexamples (fn 15). The
  residual family OTHER is compared by its exact preposition (``OTHER:עם`` is not ``OTHER:תחת``; D-060).
- The prepositions are read here only as OUTCOMES of instances whose roles were decided without them (rule zero).
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa

from hebloc.loc import METHODOLOGY
from hebloc.loc.lexicon import Lexicon
from hebloc.loc.manifest import write_csv, write_manifest
from hebloc.loc.resolve import _lst, _parts, _q, resolver_id
from hebloc.loc.source import connect
from hebloc.store.io import atomic_write_parquet, file_sha256, read_json

CLASSIFY_VERSION = "classify-r2.0"
CLASSES = ("A/B", "A", "B", "NON_LOCATIVE", "AMBIGUOUS", "INSUFFICIENT_EVIDENCE")
LEVELS = {"unit": "unit_id", "lemma": "verb_key"}
VIEWS = {"full": "in_full_view", "curated": "in_curated_view"}
SCOPES = {"all": "TRUE", "no_function_use": "NOT coalesce(function_use, false)"}
N_IDS = 5
ID_SALT = f"{METHODOLOGY}:classify:"


class ClassifyError(Exception):
    pass


def _class_sql(a: str, b: str, nl: str, amb: str, nobj: str, k: int, m: int) -> tuple[str, str]:
    cls = (f"CASE WHEN {a} >= {k} AND {b} >= {k} THEN 'A/B' WHEN {a} >= {k} AND {b} = 0 THEN 'A' "
           f"WHEN {b} >= {k} AND {a} = 0 THEN 'B' WHEN {a} = 0 AND {b} = 0 AND {nl} >= 1 THEN 'NON_LOCATIVE' "
           f"WHEN {a} = 0 AND {b} = 0 AND {amb} = 0 AND {nobj} >= {m} THEN 'NON_LOCATIVE' "
           f"WHEN {a} = 0 AND {b} = 0 AND {amb} >= 1 THEN 'AMBIGUOUS' ELSE 'INSUFFICIENT_EVIDENCE' END")
    basis = (f"CASE WHEN {a} >= {k} AND {b} >= {k} THEN 'A>=k&B>=k' WHEN {a} >= {k} AND {b} = 0 THEN 'A>=k,no_B' "
             f"WHEN {b} >= {k} AND {a} = 0 THEN 'B>=k,no_A' WHEN {a} = 0 AND {b} = 0 AND {nl} >= 1 THEN 'positive_nonlocative' "
             f"WHEN {a} = 0 AND {b} = 0 AND {amb} = 0 AND {nobj} >= {m} THEN 'rule_of_three' "
             f"WHEN {a} = 0 AND {b} = 0 AND {amb} >= 1 THEN 'ambiguous_only' "
             f"WHEN {a} > 0 OR {b} > 0 THEN 'frames_below_k' ELSE 'insufficient' END")
    return cls, basis


def _identity_sql(fa: str, fb: str) -> str:
    return (f"CASE WHEN len(list_intersect({fa}, {fb})) > 0 THEN 'IDENTITY_ATTESTED' "
            f"WHEN len({fa}) > 0 AND len({fb}) > 0 THEN 'COUNTEREXAMPLE' ELSE 'NOT_TESTABLE' END")


def _ids(cond: str) -> str:
    return (f"(list(instance_id ORDER BY sha256('{ID_SALT}' || instance_id)) FILTER (WHERE {cond}))")


def classify(extract_folder: Path, variant: str, lex: Lexicon, cfg: dict, *, git: dict, progress: bool = True) -> dict:
    folder = Path(extract_folder)
    xman = read_json(folder / "manifest.json")
    rfolder = folder / f"roles-{variant}"
    if not (rfolder / "manifest.json").exists():
        raise ClassifyError(f"no roles for {variant} in {folder} (run: hebloc loc resolve)")
    out = folder / f"classes-{variant}"
    if (out / "manifest.json").exists():
        raise ClassifyError(f"{out} already exists")
    ks = [int(k) for k in cfg["classes"]["k"]]
    m = int(cfg["classes"]["nonlocative_min_examined"])
    con = connect()
    con.execute(f"CREATE OR REPLACE TEMP VIEW inst AS SELECT * FROM read_parquet({_lst(_parts(folder, 'instances'))})")
    con.execute(f"CREATE OR REPLACE TEMP VIEW args AS SELECT * FROM read_parquet({_lst(_parts(folder, 'arguments'))})")
    con.execute(f"CREATE OR REPLACE TEMP VIEW roles AS SELECT * FROM read_parquet({_lst(_parts(rfolder, 'roles'))})")
    con.execute("""CREATE OR REPLACE TEMP TABLE j AS
        SELECT i.instance_id, i.unit_id, i.verb_key, i.in_lexicon, i.paper_class, i.in_full_view, i.in_curated_view,
               i.function_class, i.function_use, i.has_do, i.signature, r.outcome, r.reason, r.locatum_arg_idx, r.location_arg_idx
        FROM inst i JOIN roles r USING (instance_id)""")
    # the PP in the deciding role of a FULL frame instance: the Location in A, the Locatum in B
    # identity compares families; the residual OTHER bucket is compared by its exact preposition (עם is not תחת)
    con.execute("""CREATE OR REPLACE TEMP TABLE rp AS
        SELECT j.instance_id, j.outcome, CASE WHEN a.p_family = 'OTHER' THEN 'OTHER:' || a.p_exact ELSE a.p_family END AS p_family,
               a.p_exact
        FROM j JOIN args a ON a.instance_id = j.instance_id
             AND a.arg_idx = CASE WHEN j.outcome = 'A' THEN j.location_arg_idx WHEN j.outcome = 'B' THEN j.locatum_arg_idx END
        WHERE j.outcome IN ('A', 'B') AND a.slot = 'PP'""")
    tabs: dict[str, list[pa.Table]] = {"verb_classes": [], "verb_profiles": [], "verb_signatures": [], "verb_preps": [],
                                       "swap_candidates": []}
    for level, kcol in LEVELS.items():
        for view, vcol in VIEWS.items():
            for scope, scond in SCOPES.items():
                if progress:
                    print(f"  classify {variant}: {level} / {view} / {scope}", flush=True)
                where = f"{vcol} AND {scond}"
                prof = con.sql(f"""
                    WITH s AS (SELECT {kcol} AS key, * FROM j WHERE {where}),
                    fam AS (SELECT {kcol} AS key, list_distinct(list(rp.p_family) FILTER (WHERE rp.outcome = 'A')) AS fa,
                                   list_distinct(list(rp.p_family) FILTER (WHERE rp.outcome = 'B')) AS fb,
                                   count(*) FILTER (WHERE rp.outcome = 'A' AND rp.p_exact = 'מן') AS a_min_full,
                                   count(*) FILTER (WHERE rp.outcome = 'A' AND rp.p_exact = 'מ') AS a_min_prefix,
                                   count(*) FILTER (WHERE rp.outcome = 'B' AND rp.p_exact = 'מן') AS b_min_full,
                                   count(*) FILTER (WHERE rp.outcome = 'B' AND rp.p_exact = 'מ') AS b_min_prefix,
                                   {_ids("rp.outcome = 'A'")}[1:3] AS ids_a_pp, {_ids("rp.outcome = 'B'")}[1:3] AS ids_b_pp
                            FROM j JOIN rp USING (instance_id) WHERE {where} GROUP BY 1)
                    SELECT s.key, count(*) AS n_tokens, count(*) FILTER (WHERE has_do) AS n_with_object,
                           count(*) FILTER (WHERE outcome = 'A') AS n_a, count(*) FILTER (WHERE outcome = 'B') AS n_b,
                           count(*) FILTER (WHERE outcome = 'NON_LOCATIVE') AS n_nonlocative,
                           count(*) FILTER (WHERE outcome = 'AMBIGUOUS') AS n_ambiguous,
                           count(*) FILTER (WHERE outcome = 'UNDETERMINED') AS n_undetermined,
                           count(*) FILTER (WHERE reason = 'partitive') AS n_a_partitive,
                           count(*) FILTER (WHERE reason = 'bare_np') AS n_b_bare_np,
                           count(*) FILTER (WHERE function_use) AS n_function_use,
                           any_value(function_class) AS function_class, bool_or(in_lexicon) AS in_lexicon,
                           any_value(paper_class) AS paper_class,
                           list_concat(list_transform({_ids("outcome = 'A'")}[1:{N_IDS}], lambda z: 'A:' || z),
                                       list_transform({_ids("outcome = 'B'")}[1:{N_IDS}], lambda z: 'B:' || z),
                                       list_transform({_ids("outcome = 'NON_LOCATIVE'")}[1:{N_IDS}], lambda z: 'NON_LOCATIVE:' || z),
                                       list_transform({_ids("outcome = 'AMBIGUOUS'")}[1:{N_IDS}], lambda z: 'AMBIGUOUS:' || z)) AS deciding_ids,
                           coalesce(any_value(fam.fa), []::VARCHAR[]) AS fa, coalesce(any_value(fam.fb), []::VARCHAR[]) AS fb,
                           coalesce(any_value(fam.a_min_full), 0) AS a_min_full, coalesce(any_value(fam.a_min_prefix), 0) AS a_min_prefix,
                           coalesce(any_value(fam.b_min_full), 0) AS b_min_full, coalesce(any_value(fam.b_min_prefix), 0) AS b_min_prefix,
                           coalesce(any_value(fam.ids_a_pp), []::VARCHAR[]) AS ids_a_pp, coalesce(any_value(fam.ids_b_pp), []::VARCHAR[]) AS ids_b_pp
                    FROM s LEFT JOIN fam USING (key) GROUP BY s.key""").to_arrow_table()
                con.register("prof", prof)
                if scope == "all":
                    tabs["verb_profiles"].append(con.sql(f"""SELECT '{level}' AS level, '{view}' AS view, key AS verb_key, n_tokens, n_with_object,
                        n_a, n_b, n_nonlocative, n_ambiguous, n_undetermined, n_a_partitive, n_b_bare_np, n_function_use,
                        function_class, in_lexicon, paper_class FROM prof ORDER BY key""").to_arrow_table())
                for k in ks:
                    cls, basis = _class_sql("n_a", "n_b", "n_nonlocative", "n_ambiguous", "n_with_object", k, m)
                    cls_np, _ = _class_sql("(n_a - n_a_partitive)", "n_b", "n_nonlocative", "n_ambiguous", "n_with_object", k, m)
                    fa_l = "list_distinct(list_concat(fa, CASE WHEN list_contains(fa, 'AL') THEN ['B'] ELSE []::VARCHAR[] END))"
                    tabs["verb_classes"].append(con.sql(f"""
                        WITH c AS (SELECT *, {cls} AS class, {basis} AS class_basis, {cls_np} AS class_without_partitive FROM prof)
                        SELECT '{level}' AS level, '{view}' AS view, '{scope}' AS scope, {k} AS k, key AS verb_key, class, class_basis,
                               class_without_partitive, n_tokens, n_with_object, n_a, n_b, n_nonlocative, n_ambiguous, n_undetermined,
                               n_a_partitive, n_b_bare_np, n_function_use, function_class, in_lexicon, paper_class,
                               CASE WHEN n_a + n_b + n_nonlocative > 0 THEN n_nonlocative / (n_a + n_b + n_nonlocative) END AS nonlocative_share,
                               CASE WHEN paper_class IN ('A', 'A/B', 'B') THEN true WHEN paper_class IS NULL THEN NULL ELSE false END AS paper_comparable,
                               CASE WHEN paper_class IN ('A', 'A/B', 'B') AND class IN ('A', 'A/B', 'B') THEN class = paper_class END AS agrees_with_paper,
                               CASE WHEN class = 'A/B' THEN {_identity_sql('fa', 'fb')} END AS identity_verdict,
                               CASE WHEN class = 'A/B' THEN array_to_string(list_sort(list_intersect(fa, fb)), '|') END AS identity_family,
                               CASE WHEN class = 'A/B' THEN {_identity_sql(fa_l, 'fb')} END AS identity_verdict_al_as_b,
                               CASE WHEN class = 'A/B' THEN array_to_string(list_sort(list_intersect({fa_l}, fb)), '|') END AS identity_family_al_as_b,
                               list_sort(fa) AS families_frame_a, list_sort(fb) AS families_frame_b,
                               (a_min_full > 0 AND a_min_prefix > 0 AND b_min_full > 0 AND b_min_prefix > 0) AS fn8_min_both_forms_both_frames,
                               CASE WHEN list_contains(fa, 'B') OR list_contains(fb, 'B') THEN
                                         CASE WHEN list_contains(fa, 'MIN') OR list_contains(fb, 'MIN') THEN 'BOTH' ELSE 'PUTTING' END
                                    WHEN list_contains(fa, 'MIN') OR list_contains(fb, 'MIN') THEN 'REMOVAL' ELSE 'UNKNOWN' END AS putting_removal,
                               deciding_ids, list_concat(list_transform(ids_a_pp, lambda z: 'A:' || z), list_transform(ids_b_pp, lambda z: 'B:' || z)) AS identity_ids
                        FROM c ORDER BY key""").to_arrow_table())
                if scope == "all":
                    tabs["verb_signatures"].append(con.sql(f"""SELECT '{level}' AS level, '{view}' AS view, {kcol} AS verb_key, signature,
                        count(*) AS n FROM j WHERE {where} GROUP BY ALL ORDER BY verb_key, n DESC, signature""").to_arrow_table())
                    tabs["verb_preps"].append(con.sql(f"""
                        WITH x AS (SELECT j.{kcol} AS verb_key, j.outcome AS frame, j.instance_id,
                                          CASE WHEN a.arg_idx = j.location_arg_idx THEN 'location' WHEN a.arg_idx = j.locatum_arg_idx THEN 'locatum'
                                               ELSE 'other' END AS role, a.p_family, a.p_exact
                                   FROM j JOIN args a USING (instance_id) WHERE {where} AND j.outcome IN ('A', 'B') AND a.slot = 'PP')
                        SELECT '{level}' AS level, '{view}' AS view, verb_key, frame, role, p_family, p_exact, count(*) AS count,
                               {_ids('TRUE')}[1:{N_IDS}] AS example_ids
                        FROM x GROUP BY ALL ORDER BY verb_key, frame, role, count DESC, p_exact""").to_arrow_table())
                    tabs["swap_candidates"].append(con.sql(f"""
                        WITH x AS (SELECT j.{kcol} AS verb_key, j.instance_id, a.slot, a.p_family, a.head_lemma
                                   FROM j JOIN args a USING (instance_id)
                                   WHERE {where} AND NOT a.is_pronoun AND a.head_upos IN ('NOUN', 'PROPN') AND a.head_lemma IS NOT NULL
                                         AND a.head_lemma <> '[BLANK]' AND (a.slot = 'DO' OR a.slot = 'PP')),
                        d AS (SELECT verb_key, head_lemma, count(*) AS n_do FROM x WHERE slot = 'DO' GROUP BY ALL),
                        p AS (SELECT verb_key, p_family, head_lemma, count(*) AS n_p FROM x WHERE slot = 'PP' GROUP BY ALL),
                        s AS (SELECT p.verb_key, p.p_family, p.head_lemma, d.n_do, p.n_p FROM p JOIN d USING (verb_key, head_lemma)),
                        e AS (SELECT s.verb_key, s.p_family, (list(DISTINCT x.instance_id))[1:200] AS ids
                              FROM s JOIN x ON x.verb_key = s.verb_key AND x.head_lemma = s.head_lemma
                                            AND (x.slot = 'DO' OR x.p_family = s.p_family) GROUP BY ALL)
                        SELECT '{level}' AS level, '{view}' AS view, s.verb_key, s.p_family, count(*) AS n_swap_nouns,
                               (list(s.head_lemma ORDER BY s.n_do + s.n_p DESC, s.head_lemma))[1:20] AS swap_nouns,
                               sum(s.n_do)::BIGINT AS n_as_do, sum(s.n_p)::BIGINT AS n_as_pobj,
                               (list_sort(any_value(e.ids)))[1:{N_IDS}] AS example_ids
                        FROM s JOIN e USING (verb_key, p_family) GROUP BY s.verb_key, s.p_family ORDER BY s.verb_key, s.p_family""").to_arrow_table())
                con.unregister("prof")
    written = {}
    for name, parts in tabs.items():
        t = pa.concat_tables(parts, promote_options="default") if parts else pa.table({})
        atomic_write_parquet(t, out / f"{name}.parquet")
        if t.num_rows <= 1_000_000:
            write_csv(t, out / f"{name}.csv")
        written[name] = t.num_rows
    vc = (out / "verb_classes.parquet").as_posix()
    summary = con.sql(f"""SELECT class, count(*) FROM read_parquet('{vc}') WHERE level = 'unit' AND view = 'full' AND scope = 'all'
                          AND k = 1 GROUP BY 1 ORDER BY 1""").fetchall()
    return write_manifest(out, what=f"verb classes, identity and swap test ({resolver_id(variant)})", git=git,
                          source={"extract": xman.get("output_id"), "extract_manifest_sha256": file_sha256(folder / "manifest.json"),
                                  "roles_manifest_sha256": file_sha256(rfolder / "manifest.json")},
                          extra={"classify_version": CLASSIFY_VERSION, "resolver_id": resolver_id(variant), "k": ks,
                                 "primary_k": cfg["classes"]["primary_k"], "nonlocative_min_examined": m,
                                 "config_sha256": cfg["_sha256"], "rows": written,
                                 "classes_unit_full_all_k1": {c: n for c, n in summary}})
