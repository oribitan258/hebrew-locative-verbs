"""The local role resolver (S56-v1 §5.4; D-054) under rule zero as stated in D-059 (P7).

RULE ZERO. No preposition is ever used to decide whether a PP is the Locatum or the Location, to decide the frame of
an instance that has a PP argument, or to select which PP is the argument. The resolver therefore reads ONLY the
columns listed in ``INSTANCE_COLUMNS`` and ``ARGUMENT_COLUMNS``: never ``p_exact``, ``p_family``, ``signature`` or
``flags``. Its single preposition-derived input is the extractor's boolean ``lone_min_complement`` (no DO, one
MIN-family phrase as the only complement), used by the partitive rule (fn 24, 27), whose instances end with a DO
and no PP, so they never enter the identity test (tested by permuting every preposition).

ORDER (fixed; S56-v1 §5.4): structural rules -> noun types -> complementary inference -> DO only -> pronouns.
1. Structural: a listed idiom -> NON_LOCATIVE; a clausal complement and no nominal object -> NON_LOCATIVE;
   DO + one indefinite bare NP -> B (bare NP = Locatum; fn 13, 21); a partitive (``lone_min_complement`` on a
   transitive use) -> A with the מן-phrase as the Locatum object, unless its noun is LOCATION-typed (an elided object:
   UNDETERMINED; the D-059 guard).
2. Noun types: ``config/noun_types.yaml``; R1 adds induced location-likeness for untyped nouns (from intransitive
   motion/position verbs, never a lexicon verb); R2 adds the antecedent of third-person pronouns.
3. Complementary inference between the DO and ONE PP. Every PP is a candidate; two or more typed PPs ->
   AMBIGUOUS (D-059 P7); one typed PP -> that PP; no typed PP -> the PP if it is the only one.
4. DO only: LOCATION -> B, LOCATUM -> A, else UNDETERMINED.
Outcomes: A / B / NON_LOCATIVE / AMBIGUOUS / UNDETERMINED, always with a ``reason`` and ``decided_by``; never forced.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import yaml

from hebloc.loc import METHODOLOGY
from hebloc.loc.lexicon import Lexicon
from hebloc.loc.manifest import write_csv, write_manifest
from hebloc.loc.nouns import NOUN_TYPES_PATH, load_types
from hebloc.loc.source import connect
from hebloc.loc.units import lexicon_lemmas
from hebloc.paths import CONFIG_DIR
from hebloc.store.io import atomic_write_parquet, file_sha256, read_json

RESOLVER_VERSION = "resolver-r2.0"
CONFIG_PATH = CONFIG_DIR / "locative_resolver.yaml"
VARIANTS = ("R0", "R1", "R2")
OUTCOMES = ("A", "B", "NON_LOCATIVE", "AMBIGUOUS", "UNDETERMINED")
#: rule zero: the ONLY columns the resolver reads (no p_exact, p_family, signature, flags)
INSTANCE_COLUMNS = ("instance_id", "unit_id", "in_lexicon", "members", "has_do", "n_pp", "has_clausal_comp",
                    "lone_min_complement")
ARGUMENT_COLUMNS = ("instance_id", "arg_idx", "slot", "do_kind", "head_lemma", "is_pronoun", "head_definite", "ante_lemma")
ROLES_SCHEMA = pa.schema([("instance_id", pa.string()), ("resolver_id", pa.string()), ("outcome", pa.string()),
                          ("reason", pa.string()), ("locatum_arg_idx", pa.int32()), ("location_arg_idx", pa.int32()),
                          ("decided_by", pa.list_(pa.string())), ("do_type", pa.string()), ("pp_type", pa.string())])
INDUCED_SCHEMA = pa.schema([("lemma", pa.string()), ("n_loc", pa.int64()), ("n_obj", pa.int64()), ("share", pa.float64()),
                            ("induced_type", pa.string())])


class ResolveError(Exception):
    pass


def resolver_id(variant: str) -> str:
    return f"rules-{variant}@{METHODOLOGY.lower()}"


def load_config(path: Path = CONFIG_PATH) -> dict:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    for k in ("induced_location", "partitive", "classes"):
        if k not in raw:
            raise ResolveError(f"{path}: missing section {k!r}")
    raw["_sha256"] = file_sha256(Path(path))
    return raw


def _parts(folder: Path, table: str) -> list[Path]:
    parts = sorted((Path(folder) / table).glob("*.parquet"))
    if not parts:
        raise ResolveError(f"no {table} parquet files in {folder}")
    return parts


def _lst(paths: list[Path]) -> str:
    return "[" + ", ".join("'" + p.as_posix().replace("'", "''") + "'" for p in paths) + "]"


def _q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


# ---------------------------------------------------------------------------------------------- R1 induced scores
def induce(all_verbs_folder: Path, lex: Lexicon, cfg: dict, *, git: dict) -> dict:
    """Location-likeness of every noun lemma from an ALL-VERBS extraction (full view): ``n_loc`` = heads a PP (any
    preposition) of an intransitive motion/position verb, ``n_obj`` = heads the noun DO of a non-lexicon verb; LOCATION
    when ``n_loc >= min_count`` and ``n_loc / (n_loc + n_obj) >= min_share`` (config). Written to ``<folder>/induced``."""
    folder = Path(all_verbs_folder)
    man = read_json(folder / "manifest.json")
    if man.get("mode") != "all-verbs":
        raise ResolveError("induced scores need an all-verbs extraction (lexicon mode lacks the non-lexicon verbs)")
    ic = cfg["induced_location"]
    lexl = lexicon_lemmas(lex)
    verbs = [v for v in ic["verbs"] if v not in lexl]
    excluded = [v for v in ic["verbs"] if v in lexl]
    con = connect()
    t = con.sql(f"""
        WITH i AS (SELECT instance_id, lemma, unit_id, in_lexicon FROM read_parquet({_lst(_parts(folder, 'instances'))}) WHERE in_full_view),
             a AS (SELECT instance_id, slot, do_kind, head_lemma FROM read_parquet({_lst(_parts(folder, 'arguments'))})
                   WHERE NOT is_pronoun AND head_upos IN ('NOUN', 'PROPN') AND head_lemma IS NOT NULL AND head_lemma <> '[BLANK]')
        SELECT a.head_lemma AS lemma,
               count(*) FILTER (WHERE a.slot = 'PP' AND NOT i.in_lexicon
                                AND (i.lemma IN ({', '.join(_q(v) for v in verbs) or "''"})
                                     OR i.unit_id IN ({', '.join(_q('unit:' + v) for v in verbs) or "''"})))::BIGINT AS n_loc,
               count(*) FILTER (WHERE a.slot = 'DO' AND a.do_kind = 'noun' AND NOT i.in_lexicon)::BIGINT AS n_obj
        FROM a JOIN i USING (instance_id) GROUP BY 1""").to_arrow_table()
    con.register("t_in", t)
    out = con.sql(f"""SELECT lemma, n_loc, n_obj, CASE WHEN n_loc + n_obj > 0 THEN n_loc / (n_loc + n_obj) END AS share,
                             CASE WHEN n_loc >= {int(ic['min_count'])} AND n_loc / (n_loc + n_obj) >= {float(ic['min_share'])}
                                  THEN 'LOCATION' END AS induced_type
                      FROM t_in WHERE n_loc > 0 ORDER BY lemma""").to_arrow_table().cast(INDUCED_SCHEMA)
    od = folder / "induced"
    atomic_write_parquet(out, od / "scores.parquet")
    write_csv(out, od / "scores.csv")
    n_loc = sum(1 for x in out["induced_type"].to_pylist() if x == "LOCATION")
    return write_manifest(od, what="R1 induced location-likeness (S56-v1 §5.4)", git=git, source={"extract": man.get("output_id"),
                          "extract_manifest_sha256": file_sha256(folder / "manifest.json")},
                          extra={"resolver_version": RESOLVER_VERSION, "config_sha256": cfg["_sha256"], "verbs_used": verbs,
                                 "verbs_excluded_as_lexicon": excluded, "min_count": ic["min_count"],
                                 "min_share": ic["min_share"], "n_nouns_scored": out.num_rows, "n_location": n_loc})


# ---------------------------------------------------------------------------------------------- the rules (SQL)
def _types_sql(r1: bool, r2: bool) -> str:
    """Per argument: its noun type (file -> R1 induced; pronouns: R2 antecedent) and where the type came from."""
    R1, R2 = ("TRUE" if r1 else "FALSE"), ("TRUE" if r2 else "FALSE")
    return f"""
    CREATE OR REPLACE TEMP TABLE atyp AS
    SELECT x.*, coalesce(x.typ, 'UNCLEAR') AS eff FROM (
      SELECT a.*, (a.is_pronoun OR a.do_kind = 'suffix') AS pron,
             CASE WHEN a.is_pronoun OR a.do_kind = 'suffix' THEN
                    CASE WHEN {R2} AND a.ante_lemma IS NOT NULL THEN coalesce(t2.type, CASE WHEN {R1} THEN s2.induced_type END) END
                  ELSE coalesce(t1.type, CASE WHEN {R1} THEN s1.induced_type END) END AS typ,
             (a.is_pronoun OR a.do_kind = 'suffix') AND {R2} AND a.ante_lemma IS NOT NULL
                 AND coalesce(t2.type, CASE WHEN {R1} THEN s2.induced_type END) IS NOT NULL AS by_ante,
             CASE WHEN a.is_pronoun OR a.do_kind = 'suffix' THEN {R2} AND {R1} AND a.ante_lemma IS NOT NULL AND t2.type IS NULL AND s2.induced_type IS NOT NULL
                  ELSE {R1} AND t1.type IS NULL AND s1.induced_type IS NOT NULL END AS by_induced
      FROM a LEFT JOIN nt t1 ON t1.lemma = a.head_lemma LEFT JOIN ind s1 ON s1.lemma = a.head_lemma
             LEFT JOIN nt t2 ON t2.lemma = a.ante_lemma LEFT JOIN ind s2 ON s2.lemma = a.ante_lemma) x"""


def _decide_sql(variant: str, t_min: float) -> str:
    rid = resolver_id(variant)
    S = "struct_pack(o := {o}, r := {r}, lt := {lt}::INTEGER, lc := {lc}::INTEGER, d := {d})"

    def st(o, r, lt="NULL", lc="NULL", d="[]::VARCHAR[]"):
        return S.format(o=_q(o), r=_q(r), lt=lt, lc=lc, d=d)

    extra = "list_filter([CASE WHEN {a} THEN 'antecedent' END, CASE WHEN {i} THEN 'induced' END], lambda z: z IS NOT NULL)"
    do_ex = extra.format(a="d_ante", i="d_ind")
    pair_ex = extra.format(a="d_ante OR p_ante", i="d_ind OR p_ind")
    pp_ex = extra.format(a="o_ante", i="o_ind")
    return f"""
    CREATE OR REPLACE TEMP TABLE d1 AS
      SELECT * FROM (SELECT atyp.*, row_number() OVER (PARTITION BY instance_id ORDER BY CASE do_kind WHEN 'noun' THEN 0
                     WHEN 'pronoun' THEN 1 WHEN 'suffix' THEN 2 ELSE 3 END, arg_idx) AS rk FROM atyp WHERE slot IN ('DO', 'PASSIVE_SUBJ')) WHERE rk = 1;
    CREATE OR REPLACE TEMP TABLE pp AS
      SELECT instance_id, count(*) AS npp, count(*) FILTER (WHERE eff <> 'UNCLEAR') AS n_typed,
             min(arg_idx) FILTER (WHERE eff <> 'UNCLEAR') AS typed_idx, min(arg_idx) AS only_idx
      FROM atyp WHERE slot = 'PP' GROUP BY 1;
    CREATE OR REPLACE TEMP TABLE bare AS
      SELECT instance_id, count(*) FILTER (WHERE NOT coalesce(head_definite, false)) AS n_indef,
             min(arg_idx) FILTER (WHERE NOT coalesce(head_definite, false)) AS bare_idx
      FROM atyp WHERE slot = 'BARE_NP' GROUP BY 1;
    CREATE OR REPLACE TEMP TABLE idm AS
      SELECT DISTINCT d1.instance_id FROM d1 JOIN i USING (instance_id) JOIN idioms x ON x.noun = d1.head_lemma
      WHERE i.in_lexicon AND list_contains(i.members, x.entry_id);
    CREATE OR REPLACE TEMP TABLE res AS
    WITH base AS (
      SELECT i.instance_id, i.has_do, i.has_clausal_comp, coalesce(i.n_pp, 0) AS n_pp,
             (i.lone_min_complement AND (i.in_lexicon OR coalesce(ut.do_share, 0) >= {t_min})) AS partitive,
             d1.arg_idx AS do_idx, coalesce(d1.eff, 'UNCLEAR') AS d, coalesce(d1.by_ante, false) AS d_ante,
             coalesce(d1.by_induced, false) AS d_ind,
             coalesce(pp.npp, 0) AS npp, coalesce(pp.n_typed, 0) AS n_typed, pp.typed_idx, pp.only_idx,
             coalesce(bare.n_indef, 0) AS n_indef, bare.bare_idx, idm.instance_id IS NOT NULL AS is_idiom
      FROM i LEFT JOIN d1 USING (instance_id) LEFT JOIN pp USING (instance_id) LEFT JOIN bare USING (instance_id)
             LEFT JOIN idm USING (instance_id) LEFT JOIN ut USING (unit_id)),
    sel AS (
      SELECT b.*, CASE WHEN n_typed = 1 THEN typed_idx WHEN n_typed = 0 AND npp = 1 THEN only_idx END AS p_idx FROM base b),
    pr AS (
      SELECT s.*, ap.eff AS p, coalesce(ap.by_ante, false) AS p_ante, coalesce(ap.by_induced, false) AS p_ind,
             ao.eff AS o_eff, coalesce(ao.by_ante, false) AS o_ante, coalesce(ao.by_induced, false) AS o_ind
      FROM sel s LEFT JOIN atyp ap ON ap.instance_id = s.instance_id AND ap.arg_idx = s.p_idx
                 LEFT JOIN atyp ao ON ao.instance_id = s.instance_id AND ao.arg_idx = s.only_idx),
    pf AS (
      SELECT *, CASE WHEN p IS NULL THEN NULL
                     WHEN d = p AND d IN ('LOCATION', 'LOCATUM') THEN 'AMB'
                     WHEN d = 'LOCATION' THEN 'B' WHEN p = 'LOCATION' THEN 'A'
                     WHEN d = 'LOCATUM' THEN 'A' WHEN p = 'LOCATUM' THEN 'B' ELSE 'UND' END AS pairf
      FROM pr)
    SELECT instance_id, npp, CASE WHEN do_idx IS NOT NULL THEN d END AS do_type, p AS pp_type, CASE
      WHEN is_idiom THEN {st('NON_LOCATIVE', 'idiom', d="['idiom']")}
      WHEN has_clausal_comp AND NOT has_do THEN {st('NON_LOCATIVE', 'clausal_complement', d="['clausal_complement']")}
      WHEN has_do AND n_indef = 1 THEN {st('B', 'bare_np', 'bare_idx', 'do_idx', "['bare_np']")}
      WHEN has_do AND n_indef > 1 THEN {st('AMBIGUOUS', 'multiple_bare_np', d="['bare_np']")}
      WHEN NOT has_do AND partitive AND o_eff = 'LOCATION' THEN {st('UNDETERMINED', 'elided_object', d="list_concat(['partitive_guard'], " + pp_ex + ")")}
      WHEN NOT has_do AND partitive THEN {st('A', 'partitive', 'only_idx', d="list_concat(['partitive'], " + pp_ex + ")")}
      WHEN has_do AND n_typed >= 2 THEN {st('AMBIGUOUS', 'several_typed_pps', d="['noun_types']")}
      WHEN has_do AND pairf = 'A' THEN {st('A', 'complementary', 'do_idx', 'p_idx', "list_concat(['noun_types', 'complementary'], " + pair_ex + ")")}
      WHEN has_do AND pairf = 'B' THEN {st('B', 'complementary', 'p_idx', 'do_idx', "list_concat(['noun_types', 'complementary'], " + pair_ex + ")")}
      WHEN has_do AND pairf = 'AMB' THEN {st('AMBIGUOUS', 'same_inherent_type', d="list_concat(['noun_types'], " + pair_ex + ")")}
      WHEN has_do AND pairf = 'UND' THEN {st('UNDETERMINED', 'animate_or_unclear_pair')}
      WHEN has_do AND d = 'LOCATION' THEN {st('B', 'do_only_location', lc='do_idx', d="list_concat(['noun_types', 'do_only'], " + do_ex + ")")}
      WHEN has_do AND d = 'LOCATUM' THEN {st('A', 'do_only_locatum', lt='do_idx', d="list_concat(['noun_types', 'do_only'], " + do_ex + ")")}
      WHEN has_do THEN {st('UNDETERMINED', 'do_only_untyped')}
      WHEN n_pp >= 1 THEN {st('UNDETERMINED', 'no_object')}
      ELSE {st('UNDETERMINED', 'no_arguments')} END AS x
    FROM pf;
    SELECT instance_id, {_q(rid)} AS resolver_id, x.o AS outcome,
           CASE WHEN x.r IN ('do_only_location', 'do_only_locatum') AND npp >= 2
                THEN x.r || '_multi_pp' ELSE x.r END AS reason,
           x.lt AS locatum_arg_idx, x.lc AS location_arg_idx, x.d AS decided_by, do_type, pp_type
    FROM res ORDER BY instance_id"""


def resolve(extract_folder: Path, variant: str, lex: Lexicon, cfg: dict, *, git: dict,
            noun_types_path: Path = NOUN_TYPES_PATH, induced_folder: Path | None = None, progress: bool = True) -> dict:
    """Roles of every instance of an extractor output, one resolver variant; written to ``<folder>/roles-<variant>``."""
    if variant not in VARIANTS:
        raise ResolveError(f"variant must be one of {VARIANTS}")
    folder = Path(extract_folder)
    man = read_json(folder / "manifest.json")
    if variant in ("R1", "R2") and induced_folder is None:
        raise ResolveError(f"{variant} needs induced scores (hebloc loc resolve --induce-from <all-verbs folder>)")
    con = connect()
    types = load_types(noun_types_path)
    con.register("nt_in", pa.table({"lemma": sorted(types), "type": [types[k]["type"] for k in sorted(types)]},
                                   schema=pa.schema([("lemma", pa.string()), ("type", pa.string())])))
    con.execute("CREATE OR REPLACE TEMP TABLE nt AS SELECT * FROM nt_in")
    ind_info = None
    if induced_folder is not None:
        sc = Path(induced_folder) / "scores.parquet"
        con.execute(f"CREATE OR REPLACE TEMP TABLE ind AS SELECT lemma, induced_type FROM read_parquet('{sc.as_posix()}') WHERE induced_type IS NOT NULL")
        ind_info = {"folder": str(induced_folder), "scores_sha256": file_sha256(sc),
                    "manifest_sha256": file_sha256(Path(induced_folder) / "manifest.json")}
    else:
        con.execute("CREATE OR REPLACE TEMP TABLE ind (lemma VARCHAR, induced_type VARCHAR)")
    idi = [(e.id, x["noun"]) for e in lex.entries for x in e.nonlocative_idioms if x.get("noun")]
    con.register("idioms_in", pa.table({"entry_id": [r[0] for r in idi], "noun": [r[1] for r in idi]},
                                       schema=pa.schema([("entry_id", pa.string()), ("noun", pa.string())])))
    con.execute("CREATE OR REPLACE TEMP TABLE idioms AS SELECT * FROM idioms_in")
    ip = _parts(folder, "instances")
    con.execute(f"CREATE OR REPLACE TEMP TABLE ut AS SELECT unit_id, avg(has_do::INTEGER) AS do_share "
                f"FROM read_parquet({_lst(ip)}) GROUP BY 1")
    t_min = float(cfg["partitive"]["transitive_min_do_share"])
    out = folder / f"roles-{variant}"
    if (out / "manifest.json").exists():
        raise ResolveError(f"{out} already exists")
    counts: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for f in ip:
        if progress:
            print(f"  resolve {variant}: {f.stem}", flush=True)
        con.execute(f"CREATE OR REPLACE TEMP TABLE i AS SELECT {', '.join(INSTANCE_COLUMNS)} FROM read_parquet('{f.as_posix()}')")
        af = folder / "arguments" / f.name
        con.execute(f"CREATE OR REPLACE TEMP TABLE a AS SELECT {', '.join(ARGUMENT_COLUMNS)} FROM read_parquet('{af.as_posix()}')")
        con.execute(_types_sql(variant in ("R1", "R2"), variant == "R2"))
        roles = con.sql(_decide_sql(variant, t_min)).to_arrow_table().cast(ROLES_SCHEMA)
        atomic_write_parquet(roles, out / "roles" / f.name)
        if roles.num_rows <= 1_000_000:
            write_csv(roles, (out / "roles" / f.name).with_suffix(".csv"))
        con.register("r_now", roles)
        for k, n in con.sql("SELECT outcome, count(*) FROM r_now GROUP BY 1").fetchall():
            counts[k] = counts.get(k, 0) + n
        for k, n in con.sql("SELECT reason, count(*) FROM r_now GROUP BY 1").fetchall():
            reasons[k] = reasons.get(k, 0) + n
        con.unregister("r_now")
    nt_sha = file_sha256(Path(noun_types_path)) if Path(noun_types_path).exists() else None
    return write_manifest(out, what=f"roles ({resolver_id(variant)})", git=git,
                          source={"extract": man.get("output_id"), "extract_manifest_sha256": file_sha256(folder / "manifest.json")},
                          extra={"resolver_id": resolver_id(variant), "resolver_version": RESOLVER_VERSION, "variant": variant,
                                 "config_sha256": cfg["_sha256"], "noun_types_sha256": nt_sha, "n_noun_types": len(types),
                                 "induced": ind_info, "transitive_min_do_share": t_min,
                                 "rule_zero": {"instance_columns": list(INSTANCE_COLUMNS), "argument_columns": list(ARGUMENT_COLUMNS)},
                                 "outcomes": counts, "reasons": reasons})
