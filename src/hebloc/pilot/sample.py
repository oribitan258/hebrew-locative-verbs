"""M3 pilot sample: 200 units per corpus = 120 random (full view) + 80 targeted difficult cases.

Deterministic: units are ranked by ``md5(sent_id || seed)`` (stable across DuckDB versions), the
targeted categories are filled in the listed order without repeating a unit, and if a category has
fewer candidates than requested the shortfall is recorded (never silently replaced). Units that
are empty after normalization are excluded (the parser skips them; M2 counts them).

Output: ``annotation/pilot_sample.csv`` (versioned) with the reason each unit was selected.
"""

from __future__ import annotations

import csv
from pathlib import Path

import duckdb

from hebloc.paths import ANNOTATION_DIR, CORPORA, UNITS_DIR

SEED = "m3-pilot-2026"
N_RANDOM = 120
SAMPLE_PATH = ANNOTATION_DIR / "pilot_sample.csv"
HAS = "list_contains(norm_flags, '{}')"
ANY_PREFIX = "len(list_filter(norm_flags, lambda f: starts_with(f, '{}'))) > 0"
ARAMAIC_RABBINIC = r"(^|\s)(דאמר|אמר ליה|איכא|תניא|מאי|הכא|היכי|ליה|נמי|דלא)(\s|$)"

# (reason, SQL condition, n, order) — order "rand" (seeded) or "longest"
TARGETS: dict[str, list[tuple[str, str, int, str]]] = {
    "mikra": [
        ("ketiv_qere", HAS.format("ketiv_qere"), 20, "rand"),
        ("qere_or_ketiv_only", f"({HAS.format('qere_only')} OR {HAS.format('ketiv_only')})", 6, "rand"),
        ("aramaic", "aramaic IS NOT NULL", 14, "rand"),
        ("poetry", "ref SIMILAR TO '(Psalms|Job|Proverbs) .*'", 15, "rand"),
        ("late_biblical", "ref SIMILAR TO '(Esther|Ezra|Nehemiah|I Chronicles|II Chronicles|Ecclesiastes) .*'", 10, "rand"),
        ("longest", "TRUE", 10, "longest"),
        ("parasha_marker", ANY_PREFIX.format("parasha_marker"), 5, "rand"),
    ],
    "hazal": [
        ("vocalized_mishnah", f"stratum = 'hazal.mishnah' AND {HAS.format('diacritics_stripped')}", 20, "rand"),
        ("aramaic_markers", f"regexp_matches(text_norm, '{ARAMAIC_RABBINIC}')", 12, "rand"),
        ("abbreviation", r"regexp_matches(text_norm, '[א-ת]+''(\s|$)')", 12, "rand"),
        ("tosefta", "stratum = 'hazal.tosefta'", 8, "rand"),
        ("halakhic_midrash", "stratum = 'hazal.halakhic_midrash'", 8, "rand"),
        ("late_anthology", "stratum = 'hazal.late_anthology'", 5, "rand"),
        ("commentary", "stratum = 'hazal.commentary'", 5, "rand"),
        ("longest", "TRUE", 10, "longest"),
    ],
    "medieval": [
        ("mishneh_torah", "stratum = 'medieval.mishneh_torah'", 15, "rand"),
        ("rambam_prefix_tags", f"stratum = 'medieval.mishneh_torah' AND {ANY_PREFIX.format('prefix_')}", 5, "rand"),
        ("thought_translated", "stratum = 'medieval.thought_translated'", 12, "rand"),
        ("thought", "stratum = 'medieval.thought'", 10, "rand"),
        ("musar", "stratum IN ('medieval.musar', 'medieval.musar_translated')", 10, "rand"),
        ("musar_unverified", "stratum = 'medieval.musar_unverified'", 5, "rand"),
        ("later_or_post_medieval", "stratum IN ('medieval.later_commentary', 'medieval.post_medieval')", 8, "rand"),
        ("vocalized", HAS.format("diacritics_stripped"), 5, "rand"),
        ("longest", "TRUE", 10, "longest"),
    ],
    "haskala": [
        ("post_1881", "doc_subperiod = 'post_haskala'", 15, "rand"),
        ("pre_1881", "doc_subperiod = 'haskala'", 15, "rand"),
        ("markup_removed", f"({HAS.format('edition_note_removed')} OR {HAS.format('quote_brackets_removed')} OR {HAS.format('braces_removed')} OR {HAS.format('hash_marker_removed')})", 15, "rand"),
        ("vocalized", HAS.format("diacritics_stripped"), 10, "rand"),
        ("science", "stratum = 'haskala.science'", 10, "rand"),
        ("longest", "TRUE", 15, "longest"),
    ],
    "modern": [
        *[(f"source:{s}", f"stratum = 'modern.{s}'", 6, "rand") for s in
          ("blogs", "forum.tapuz", "knesset", "literary.original", "literary.translated", "medical",
           "news.a7", "news.nrg", "news.themarker", "news.ynet")],
        ("prefix_unresolved", ANY_PREFIX.format("prefix_unresolved"), 5, "rand"),
        ("reversed_number_pattern", r"regexp_matches(text_raw, '% \d')", 5, "rand"),
        ("contains_url", HAS.format("contains_url"), 3, "rand"),
        ("longest", "TRUE", 7, "longest"),
    ],
}


def _con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    from hebloc.catalog import DOCUMENTS_PATH

    con.execute(f"""CREATE VIEW u AS SELECT u.*, d.subperiod AS doc_subperiod
                    FROM read_parquet('{(UNITS_DIR / '*' / '*.parquet').as_posix()}') u
                    JOIN read_parquet('{DOCUMENTS_PATH.as_posix()}') d USING (doc_id)
                    WHERE NOT u.is_empty_norm""")
    return con


def build(seed: str = SEED, out: Path = SAMPLE_PATH) -> list[dict]:
    con = _con()
    rows: list[dict] = []
    shortfalls = []
    for corpus in CORPORA:
        taken: set[str] = set()

        def pick(cond: str, n: int, order: str) -> list[tuple]:
            o = "n_tokens_norm DESC, sent_id" if order == "longest" else f"md5(sent_id || '{seed}')"
            excl = ",".join(f"'{s}'" for s in taken) or "''"
            return con.execute(f"""SELECT sent_id, ref, stratum, n_tokens_norm FROM u
                                   WHERE corpus_id = '{corpus}' AND ({cond}) AND sent_id NOT IN ({excl})
                                   ORDER BY {o} LIMIT {n}""").fetchall()

        for sid, ref, stratum, ntok in pick("TRUE", N_RANDOM, "rand"):
            taken.add(sid)
            rows.append(dict(corpus_id=corpus, sent_id=sid, ref=ref, stratum=stratum, n_tokens_norm=ntok, selection="random"))
        for reason, cond, n, order in TARGETS[corpus]:
            got = pick(cond, n, order)
            if len(got) < n:
                shortfalls.append(f"{corpus}:{reason} {len(got)}/{n}")
            for sid, ref, stratum, ntok in got:
                taken.add(sid)
                rows.append(dict(corpus_id=corpus, sent_id=sid, ref=ref, stratum=stratum, n_tokens_norm=ntok,
                                 selection=f"targeted:{reason}"))
    for i, r in enumerate(rows):
        r["sample_id"] = f"P{i + 1:04d}"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["sample_id", "corpus_id", "sent_id", "ref", "stratum", "n_tokens_norm", "selection"])
        w.writeheader()
        w.writerows(rows)
    if shortfalls:
        print("shortfalls:", shortfalls)
    return rows


def load(path: Path = SAMPLE_PATH) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))
