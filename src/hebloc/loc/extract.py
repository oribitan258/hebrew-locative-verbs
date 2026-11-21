"""The shared extractor (S56-v1 §5.3; I3 tables ``instances`` and ``arguments``; release R2, Phase B).

One row per VERB token (``--mode all-verbs``, §6) or per lexicon-identified VERB token (``--mode lexicon``, §5).
Lexicon mode is a FILTER of the all-verbs rows, so a token gives byte-identical rows in both modes (§5.3 design
rule). Rows depend only on the token, its tree and the versioned global maps (lexicon, unit map, function list),
never on the mode or the data source (repo = package, tested). Nothing is decided here: no frame, role or class.

Per instance (I3 + the D-059 columns):
- provenance: ``instance_id`` = ``sent_id|piece_idx|word_idx``, corpus, subcorpus, run, shard, doc, unit, ``ref``,
  ``in_full_view`` / ``in_curated_view``;
- the verb: ``form``, ``lemma``, ``upos``; ``verb_key`` (lexicon key; else ``lemma:<lemma>``; else ``form:<host>``
  for unlemmatized tokens) and ``unit_id`` (lexicon key; else ``unit:<unit lemma>`` by the unit map, D-059 P1;
  else the same ``form:<host>``), ``link_status``, ``in_lexicon``, ``members``, ``paper_class``, ``match_method``,
  ``voice`` and ``template_proxy`` (lexicon -> unit map -> shape, D-059 P4);
- structure: ``signature``, ``has_do``, ``do_kind``, ``n_pp``, ``has_bare_np``, ``has_clausal_comp``,
  ``has_clausal_subj``, ``lone_min_complement`` (no DO, one PP of the MIN family, no bare NP, not passive: the
  only preposition-derived input the resolver may read, D-059 P7);
- ``flags`` (never filters): partitive_candidate (lone_min_complement on a lexicon verb; fn 24, 27),
  instrument_candidate (two ב-PPs; fn 7), al_for_b (על and no ב; fn 22), conj_shared, tree_invalid, multi_piece
  (D-021), function_lemma (a lexicon token whose Dicta lemma is a listed function predicate, D-059 P6);
- ``function_class`` (lemma level) and ``function_use`` (token level, structural; D-059 P6).

Per argument: slot (DO / PP / BARE_NP / PASSIVE_SUBJ, read by ``hebloc.loc.tree.arguments_sql``, unchanged from
R1), head word and lemma, pronoun features, ``p_exact`` / ``p_family``, head gender / number / definiteness, and
for third-person pronouns the nearest preceding gender/number-matching noun in the same or previous unit
(``ante_lemma``; used only by resolver variant R2).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc

from hebloc.loc import METHODOLOGY
from hebloc.loc import identify as ID
from hebloc.loc import tree as TR
from hebloc.loc.lexicon import Lexicon
from hebloc.loc.manifest import write_csv, write_manifest
from hebloc.loc.source import Source, connect
from hebloc.loc.units import FunctionList, UnitMap
from hebloc.paths import DATA_DIR
from hebloc.store.io import atomic_write_parquet

EXTRACT_VERSION = "extract-r2.0"
OUT_DIR = DATA_DIR / "loc"
MODES = ("lexicon", "all-verbs")
#: CSV copies (UTF-8 BOM) are written next to a parquet file only up to this many rows (Modern files are too large)
CSV_MAX_ROWS = 1_000_000
FAMILY_ORDER = ("B", "MIN", "AL", "EL", "LE", "OTHER")
FLAG_NAMES = ("partitive_candidate", "instrument_candidate", "al_for_b", "conj_shared", "tree_invalid", "multi_piece",
              "function_lemma")

INSTANCES_SCHEMA = pa.schema([
    ("instance_id", pa.string()), ("corpus", pa.string()), ("subcorpus", pa.string()), ("run_id", pa.string()),
    ("shard", pa.string()), ("doc_id", pa.string()), ("sent_id", pa.string()), ("piece_idx", pa.int16()),
    ("word_idx", pa.int32()), ("sent_word_idx", pa.int32()), ("ref", pa.string()), ("in_full_view", pa.bool_()),
    ("in_curated_view", pa.bool_()), ("form", pa.string()), ("lemma", pa.string()), ("upos", pa.string()),
    ("verb_key", pa.string()), ("unit_id", pa.string()), ("link_status", pa.string()), ("in_lexicon", pa.bool_()),
    ("members", pa.list_(pa.string())), ("paper_class", pa.string()), ("match_method", pa.string()),
    ("voice", pa.string()), ("template_proxy", pa.string()), ("signature", pa.string()), ("has_do", pa.bool_()),
    ("do_kind", pa.string()), ("n_pp", pa.int32()), ("has_bare_np", pa.bool_()), ("has_clausal_comp", pa.bool_()),
    ("has_clausal_subj", pa.bool_()), ("lone_min_complement", pa.bool_()), ("flags", pa.list_(pa.string())),
    ("function_class", pa.string()), ("function_use", pa.bool_()), ("n_pieces", pa.int16()),
    ("piece_tree_valid", pa.bool_())])
ARGUMENTS_SCHEMA = pa.schema([
    ("instance_id", pa.string()), ("arg_idx", pa.int32()), ("slot", pa.string()), ("do_kind", pa.string()),
    ("head_word_idx", pa.int32()), ("head_form", pa.string()), ("head_lemma", pa.string()), ("head_upos", pa.string()),
    ("is_pronoun", pa.bool_()), ("pron_feats", pa.string()), ("deprel", pa.string()), ("p_exact", pa.string()),
    ("p_family", pa.string()), ("flags", pa.list_(pa.string())), ("head_gender", pa.string()),
    ("head_number", pa.string()), ("head_definite", pa.bool_()), ("ante_lemma", pa.string()),
    ("ante_upos", pa.string()), ("ante_sent_word_idx", pa.int32())])


class ExtractError(Exception):
    pass


def output_id(corpus: str, mode: str, lex: Lexicon, umap: UnitMap, flist: FunctionList, runs: list[str] | None) -> str:
    """Depends on the code version, corpus, mode, the three maps and the run scope — never on the data source."""
    key = "|".join([EXTRACT_VERSION, corpus, mode, lex.sha256, str(umap.sha256), str(umap.audit.get("status")),
                    str(umap.allow_unaudited), str(flist.sha256), ",".join(sorted(runs or []))])
    return f"{corpus}-{mode}-{hashlib.sha256(key.encode()).hexdigest()[:10]}"


def _lexkey_table(lex: Lexicon, keys: list[str]) -> pa.Table:
    """Per lexicon key: the templates and paper classes of its members (combined keys keep every member)."""
    by = lex.by_id()
    rows = []
    for k in keys:
        mem = [m for m in k.split("|") if not m.startswith("~")]
        tpl = sorted({by[m].template for m in mem if m in by})
        cls = sorted({(by[m].klass or "none") for m in mem if m in by})
        rows.append((k, "|".join(tpl) or "unknown", "|".join(cls) or None))
    return pa.table({"lex_key": [r[0] for r in rows], "lex_template": [r[1] for r in rows], "paper_class": [r[2] for r in rows]},
                    schema=pa.schema([("lex_key", pa.string()), ("lex_template", pa.string()), ("paper_class", pa.string())]))


def _lemma_table(lemmas: list[str], umap: UnitMap, flist: FunctionList) -> pa.Table:
    rows = [(x, umap.unit_of(x), umap.status(x), umap.voice(x), umap.template(x), flist.classes.get(x)) for x in sorted(lemmas)]
    names = ("lemma", "unit_lemma", "link_status", "map_voice", "map_template", "function_class")
    return pa.table({n: [r[i] for r in rows] for i, n in enumerate(names)},
                    schema=pa.schema([(n, pa.string()) for n in names]))


def _family_rank_sql(col: str) -> str:
    return "CASE " + " ".join(f"WHEN {col} = '{f}' THEN {i}" for i, f in enumerate(FAMILY_ORDER)) + f" ELSE {len(FAMILY_ORDER)} END"


def _feat(col: str, name: str) -> str:
    return f"nullif(regexp_extract({col}, '{name}=([^|]+)', 1), '')"


def _match_sql(a: str, b: str) -> str:
    """Two Dicta feature values agree (a comma value such as 'Fem,Masc' agrees with either part); NULLs never agree."""
    return f"({a} IS NOT NULL AND {b} IS NOT NULL AND ({a} = {b} OR {a} LIKE '%,%' OR {b} LIKE '%,%'))"


def run_tables(con, source: Source, run, corpus: str, lex: Lexicon, umap: UnitMap, flist: FunctionList) -> tuple[pa.Table, pa.Table]:
    """The instances and arguments of one run, all VERB tokens (the caller filters for lexicon mode)."""
    con.execute(f"CREATE OR REPLACE TEMP TABLE tok AS SELECT * FROM {source.tokens_sql(run)}")
    con.execute(f"CREATE OR REPLACE TEMP TABLE idn AS {ID.identify_sql('tok')}")
    lemmas = [r[0] for r in con.sql("SELECT DISTINCT lemma FROM tok WHERE upos = 'VERB' AND lemma IS NOT NULL "
                                    "AND NOT coalesce(lemma_blank, false)").fetchall()]
    con.register("lem_in", _lemma_table(lemmas, umap, flist))
    con.execute("CREATE OR REPLACE TEMP TABLE lem AS SELECT * FROM lem_in")
    keys = [r[0] for r in con.sql("SELECT DISTINCT verb_key FROM idn").fetchall()]
    con.register("lk_in", _lexkey_table(lex, keys))
    con.execute("CREATE OR REPLACE TEMP TABLE lk AS SELECT * FROM lk_in")
    blank = "(t.lemma IS NULL OR coalesce(t.lemma_blank, false))"
    con.execute(f"""CREATE OR REPLACE TEMP TABLE v AS
        SELECT t.sent_id, t.piece_idx, t.word_idx, t.sent_word_idx, t.n_pieces, t.piece_tree_valid, t.form, t.host, t.lemma,
               {blank} AS is_blank, t.upos, t.suffix, t.suffix_feats, t.deprel, t.run_id, t.shard, t.doc_id,
               i.verb_key AS lex_key, i.members, i.match_method AS lex_match, l.unit_lemma, l.link_status, l.map_template,
               l.function_class,
               CASE WHEN i.verb_key IS NOT NULL THEN i.voice WHEN {blank} THEN 'unknown' ELSE coalesce(l.map_voice, 'unknown') END AS voice
        FROM tok t LEFT JOIN idn i USING (sent_id, piece_idx, word_idx) LEFT JOIN lem l ON l.lemma = t.lemma
        WHERE t.upos = 'VERB'""")
    con.execute(f"CREATE OR REPLACE TEMP TABLE a AS {TR.arguments_sql('v', 'tok')}")
    con.execute("""CREATE OR REPLACE TEMP TABLE ch AS
        SELECT v.sent_id, v.piece_idx, v.word_idx,
               bool_or(c.deprel IN ('ccomp', 'xcomp') AND c.upos IN ('VERB', 'AUX')) AS has_clausal_comp,
               bool_or(c.deprel LIKE 'csubj%' AND c.upos IN ('VERB', 'AUX')) AS has_clausal_subj
        FROM v JOIN tok c ON c.sent_id = v.sent_id AND c.piece_idx = v.piece_idx AND c.head = v.word_idx GROUP BY ALL""")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE ag AS
        SELECT sent_id, piece_idx, verb_word_idx AS word_idx,
               bool_or(slot = 'DO' AND do_kind = 'noun') AS do_noun, bool_or(slot = 'DO' AND do_kind = 'pronoun') AS do_pron,
               bool_or(slot = 'DO' AND do_kind = 'suffix') AS do_suf, bool_or(slot = 'PASSIVE_SUBJ') AS do_pass,
               count(*) FILTER (WHERE slot = 'PP')::INTEGER AS n_pp, bool_or(slot = 'BARE_NP') AS has_bare_np,
               count(*) FILTER (WHERE slot = 'PP' AND p_family = 'B') AS n_b, count(*) FILTER (WHERE slot = 'PP' AND p_family = 'MIN') AS n_min,
               count(*) FILTER (WHERE slot = 'PP' AND p_family = 'AL') AS n_al,
               list(p_family ORDER BY {_family_rank_sql('p_family')}, head_word_idx) FILTER (WHERE slot = 'PP') AS fams
        FROM a GROUP BY ALL""")
    inst = con.sql(f"""
        WITH x AS (
          SELECT v.*, coalesce(ag.n_pp, 0) AS n_pp_, coalesce(ag.has_bare_np, false) AS bare_,
                 CASE WHEN ag.do_noun THEN 'noun' WHEN ag.do_pron THEN 'pronoun' WHEN ag.do_suf THEN 'suffix'
                      WHEN ag.do_pass THEN 'passive_subject' ELSE 'none' END AS do_kind_,
                 coalesce(ag.n_b, 0) AS n_b, coalesce(ag.n_min, 0) AS n_min, coalesce(ag.n_al, 0) AS n_al,
                 coalesce(ag.fams, []::VARCHAR[]) AS fams, coalesce(ch.has_clausal_comp, false) AS cc,
                 coalesce(ch.has_clausal_subj, false) AS cs
          FROM v LEFT JOIN ag USING (sent_id, piece_idx, word_idx) LEFT JOIN ch USING (sent_id, piece_idx, word_idx)),
        y AS (
          SELECT x.*, do_kind_ <> 'none' AS has_do_,
                 (do_kind_ = 'none' AND n_pp_ = 1 AND n_min = 1 AND NOT bare_ AND voice NOT IN ('passive', 'middle')) AS lone_min
          FROM x)
        SELECT y.sent_id || '|' || y.piece_idx || '|' || y.word_idx AS instance_id, '{corpus}' AS corpus, d.subcorpus,
               y.run_id, y.shard, y.doc_id, y.sent_id, y.piece_idx, y.word_idx, y.sent_word_idx, u.ref,
               u.in_full_view, u.in_curated_view, y.form, y.lemma, y.upos,
               CASE WHEN y.lex_key IS NOT NULL THEN y.lex_key WHEN y.is_blank THEN 'form:' || coalesce(y.host, '') ELSE 'lemma:' || y.lemma END AS verb_key,
               CASE WHEN y.lex_key IS NOT NULL THEN y.lex_key WHEN y.is_blank THEN 'form:' || coalesce(y.host, '')
                    ELSE 'unit:' || coalesce(y.unit_lemma, y.lemma) END AS unit_id,
               CASE WHEN y.lex_key IS NOT NULL THEN 'lexicon' WHEN y.is_blank THEN 'unlemmatized' ELSE coalesce(y.link_status, 'own') END AS link_status,
               y.lex_key IS NOT NULL AS in_lexicon, coalesce(y.members, []::VARCHAR[]) AS members, lk.paper_class,
               coalesce(y.lex_match, 'none') AS match_method, y.voice,
               CASE WHEN y.lex_key IS NOT NULL THEN lk.lex_template WHEN y.is_blank THEN 'unknown' ELSE coalesce(y.map_template, 'unknown') END AS template_proxy,
               'V' || CASE WHEN has_do_ THEN '+DO' ELSE '' END
                   || array_to_string(list_transform(y.fams, lambda f: '+PP[' || f || ']'), '')
                   || CASE WHEN bare_ THEN '+BARE' ELSE '' END AS signature,
               has_do_ AS has_do, do_kind_ AS do_kind, n_pp_ AS n_pp, bare_ AS has_bare_np,
               cc AS has_clausal_comp, cs AS has_clausal_subj, lone_min AS lone_min_complement,
               list_filter([CASE WHEN lone_min AND y.lex_key IS NOT NULL THEN 'partitive_candidate' END,
                            CASE WHEN n_b >= 2 THEN 'instrument_candidate' END,
                            CASE WHEN n_al >= 1 AND n_b = 0 THEN 'al_for_b' END,
                            CASE WHEN y.deprel = 'conj' THEN 'conj_shared' END,
                            CASE WHEN NOT coalesce(y.piece_tree_valid, true) THEN 'tree_invalid' END,
                            CASE WHEN y.n_pieces > 1 THEN 'multi_piece' END,
                            CASE WHEN y.lex_key IS NOT NULL AND y.function_class IS NOT NULL THEN 'function_lemma' END],
                           lambda z: z IS NOT NULL) AS flags,
               y.function_class,
               (y.function_class IS NOT NULL AND NOT has_do_
                AND (cc OR cs OR y.function_class IN ('EXISTENTIAL', 'COPULA'))) AS function_use,
               y.n_pieces, y.piece_tree_valid
        FROM y LEFT JOIN units u USING (sent_id) LEFT JOIN docs d USING (doc_id) LEFT JOIN lk ON lk.lex_key = y.lex_key
        ORDER BY y.sent_id, y.piece_idx, y.word_idx""").to_arrow_table()
    # pronoun antecedents (R2): nearest preceding noun in the same unit or the previous unit of the document
    con.execute("""CREATE OR REPLACE TEMP TABLE uo AS
        SELECT sent_id, doc_id, row_number() OVER (PARTITION BY doc_id ORDER BY ln, k, sent_id) AS ur
        FROM (SELECT DISTINCT sent_id, doc_id, TRY_CAST(split_part(sent_id, ':', 3) AS BIGINT) AS ln,
                     TRY_CAST(split_part(sent_id, ':', 4) AS BIGINT) AS k FROM tok)""")
    con.execute("""CREATE OR REPLACE TEMP TABLE nc AS
        SELECT u.doc_id, u.ur, t.sent_word_idx AS pos, t.lemma, t.upos, t.gender,
               replace(t.number, 'Dual', 'Plur') AS number
        FROM tok t JOIN uo u USING (sent_id)
        WHERE t.upos IN ('NOUN', 'PROPN') AND t.sent_word_idx IS NOT NULL AND NOT coalesce(t.lemma_blank, false)""")
    feats = "CASE WHEN a.do_kind = 'suffix' THEN v.suffix_feats ELSE coalesce(h.suffix_feats, CASE WHEN a.is_pronoun THEN 'Gender=' || coalesce(h.gender, '') || '|Number=' || coalesce(h.number, '') || '|Person=' || coalesce(h.person, '') END) END"
    con.execute(f"""CREATE OR REPLACE TEMP TABLE ax AS
        SELECT a.*, row_number() OVER (PARTITION BY a.sent_id, a.piece_idx, a.verb_word_idx
                                       ORDER BY a.head_word_idx, a.slot, a.deprel, a.p_exact) - 1 AS arg_idx,
               CASE WHEN a.is_pronoun THEN {feats} END AS pron_feats,
               CASE WHEN a.do_kind = 'suffix' THEN {_feat('v.suffix_feats', 'Gender')} WHEN a.is_pronoun AND h.suffix_feats IS NOT NULL
                    THEN {_feat('h.suffix_feats', 'Gender')} ELSE h.gender END AS head_gender,
               replace(CASE WHEN a.do_kind = 'suffix' THEN {_feat('v.suffix_feats', 'Number')} WHEN a.is_pronoun AND h.suffix_feats IS NOT NULL
                    THEN {_feat('h.suffix_feats', 'Number')} ELSE h.number END, 'Dual', 'Plur') AS head_number,
               CASE WHEN a.do_kind = 'suffix' THEN {_feat('v.suffix_feats', 'Person')} WHEN a.is_pronoun AND h.suffix_feats IS NOT NULL
                    THEN {_feat('h.suffix_feats', 'Person')} ELSE h.person END AS head_person,
               (a.is_pronoun OR a.do_kind = 'suffix' OR h.upos = 'PROPN' OR coalesce(list_contains(h.prefix_upos, 'DET'), false)) AS head_definite,
               CASE WHEN a.do_kind = 'suffix' THEN v.sent_word_idx ELSE h.sent_word_idx END AS pos,
               uo.doc_id AS p_doc, uo.ur AS p_ur
        FROM a JOIN v ON v.sent_id = a.sent_id AND v.piece_idx = a.piece_idx AND v.word_idx = a.verb_word_idx
        LEFT JOIN tok h ON h.sent_id = a.sent_id AND h.piece_idx = a.piece_idx AND h.word_idx = a.head_word_idx
        LEFT JOIN uo ON uo.sent_id = a.sent_id""")
    args = con.sql(f"""
        WITH an AS (
          SELECT ax.sent_id, ax.piece_idx, ax.verb_word_idx, ax.arg_idx,
                 arg_max(nc.lemma, nc.ur * 1000000 + nc.pos) AS ante_lemma, arg_max(nc.upos, nc.ur * 1000000 + nc.pos) AS ante_upos,
                 arg_max(CASE WHEN nc.ur = ax.p_ur THEN nc.pos END, nc.ur * 1000000 + nc.pos) AS ante_pos
          FROM ax JOIN nc ON nc.doc_id = ax.p_doc AND ((nc.ur = ax.p_ur AND nc.pos < ax.pos) OR nc.ur = ax.p_ur - 1)
          WHERE (ax.is_pronoun OR ax.do_kind = 'suffix') AND ax.pos IS NOT NULL AND coalesce(ax.head_person, '3') = '3'
                AND {_match_sql('nc.gender', 'ax.head_gender')} AND {_match_sql('nc.number', 'ax.head_number')}
          GROUP BY ALL)
        SELECT ax.sent_id || '|' || ax.piece_idx || '|' || ax.verb_word_idx AS instance_id, ax.arg_idx, ax.slot, ax.do_kind,
               ax.head_word_idx, ax.head_form, ax.head_lemma, ax.head_upos, ax.is_pronoun, ax.pron_feats, ax.deprel,
               ax.p_exact, ax.p_family,
               list_filter([CASE WHEN ax.head_definite THEN 'definite' END, CASE WHEN an.ante_lemma IS NOT NULL THEN 'antecedent' END],
                           lambda z: z IS NOT NULL) AS flags,
               ax.head_gender, ax.head_number, ax.head_definite, an.ante_lemma, an.ante_upos, an.ante_pos AS ante_sent_word_idx
        FROM ax LEFT JOIN an USING (sent_id, piece_idx, verb_word_idx, arg_idx)
        ORDER BY ax.sent_id, ax.piece_idx, ax.verb_word_idx, ax.arg_idx""").to_arrow_table()
    return inst.cast(INSTANCES_SCHEMA), args.cast(ARGUMENTS_SCHEMA)


def _write_table(t: pa.Table, path: Path) -> None:
    atomic_write_parquet(t, path)
    if t.num_rows <= CSV_MAX_ROWS:
        write_csv(t, path.with_suffix(".csv"))


def extract(corpus: str, source: Source, lex: Lexicon, umap: UnitMap, flist: FunctionList, *, mode: str, git: dict,
            out_root: Path = OUT_DIR, runs: list[str] | None = None, progress: bool = True) -> dict:
    if mode not in MODES:
        raise ExtractError(f"mode must be one of {MODES}")
    all_runs = source.runs(corpus)
    names = [r.run_id for r in all_runs]
    if runs:
        unknown = sorted(set(runs) - set(names))
        if unknown:
            raise ExtractError(f"unknown runs for {corpus}: {unknown}")
    oid = output_id(corpus, mode, lex, umap, flist, runs)
    folder = Path(out_root) / corpus / oid
    if (folder / "manifest.json").exists():
        raise ExtractError(f"{folder} already exists (an output is written once; its id fixes its inputs)")
    con = connect()
    ID.register(con, lex)
    con.execute(f"CREATE OR REPLACE TEMP TABLE units AS SELECT sent_id, ref, in_full_view, in_curated_view FROM "
                f"{source.units_sql(corpus, ('sent_id', 'ref', 'in_full_view', 'in_curated_view'))}")
    con.execute(f"CREATE OR REPLACE TEMP TABLE docs AS SELECT doc_id, subcorpus FROM {source.documents_sql(('doc_id', 'subcorpus'))}")
    counts = {"instances": 0, "arguments": 0, "in_lexicon": 0, "by_link_status": {}, "function_use": 0}
    done = []
    for run in all_runs:
        if runs and run.run_id not in runs:
            continue
        if progress:
            print(f"  extract {corpus} ({mode}): {run.run_id}", flush=True)
        inst, args = run_tables(con, source, run, corpus, lex, umap, flist)
        if mode == "lexicon":      # a pure filter of the all-verbs rows: same rows, same order (§5.3 design rule)
            inst = inst.filter(pc.field("in_lexicon"))
            args = args.filter(pc.is_in(args["instance_id"], value_set=inst["instance_id"]))
        _write_table(inst, folder / "instances" / f"{run.run_id}.parquet")
        _write_table(args, folder / "arguments" / f"{run.run_id}.parquet")
        counts["instances"] += inst.num_rows
        counts["arguments"] += args.num_rows
        con.register("i_now", inst)
        counts["in_lexicon"] += con.sql("SELECT count(*) FROM i_now WHERE in_lexicon").fetchall()[0][0]
        counts["function_use"] += con.sql("SELECT count(*) FROM i_now WHERE function_use").fetchall()[0][0]
        for k, n in con.sql("SELECT link_status, count(*) FROM i_now GROUP BY 1").fetchall():
            counts["by_link_status"][k] = counts["by_link_status"].get(k, 0) + n
        con.unregister("i_now")
        done.append(run.run_id)
    m = write_manifest(folder, what=f"extractor output ({mode}): instances + arguments", git=git,
                       source=source.describe(corpus),
                       extra={"corpus": corpus, "mode": mode, "output_id": oid, "extract_version": EXTRACT_VERSION,
                              "lexicon_sha256": lex.sha256, "forms_rule": lex.forms_meta.get("rule_version"),
                              "units": umap.describe(), "functions": flist.describe(),
                              "scope": {"runs": done, "complete": not runs or sorted(done) == sorted(names)},
                              "csv_max_rows": CSV_MAX_ROWS, "counts": counts, "methodology": METHODOLOGY})
    return m


def read(folder: Path, table: str, con=None, columns: tuple[str, ...] | None = None) -> str:
    """SQL relation over the parquet parts of ``table`` (instances | arguments) of an extractor output folder."""
    parts = sorted((Path(folder) / table).glob("*.parquet"))
    if not parts:
        raise ExtractError(f"no {table} in {folder}")
    cols = ", ".join(columns) if columns else "*"
    lst = ", ".join("'" + p.as_posix().replace("'", "''") + "'" for p in parts)
    return f"(SELECT {cols} FROM read_parquet([{lst}]))"
