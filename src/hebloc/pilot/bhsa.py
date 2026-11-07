"""ETCBC BHSA (2021) as an external reference for Biblical Hebrew (decision D-005).

BHSA is an expert annotation, but its conventions differ from Dicta's (Universal-Dependencies-like)
ones, so the comparison is a *convention-aware agreement*, not a gold-standard accuracy:

* BHSA splits the proclitics ו ה ב כ ל מ (and ש) into separate words and keeps pronominal suffixes
  on the host; Dicta keeps one orthographic word with a segmented prefix and a suffix flag. We
  align on ORTHOGRAPHIC words (BHSA words joined until a non-empty trailer) and compare the BHSA
  host (last word of the group) with Dicta's host analysis, and the BHSA proclitic letters with
  Dicta's prefix segmentation.
* Parts of speech are compared through an explicit many-to-one mapping (``SP_TO_UPOS``).
* Lexemes: BHSA uses roots/consonantal lexemes for verbs (e.g. יצא for הוציא); Dicta lemmas follow
  Modern-Hebrew dictionary forms. Lemma agreement is therefore reported for nouns and for qal verbs
  separately from other binyanim (where disagreement is expected by convention).
* BHSA's word analyses follow the Ketiv; the Qere is a separate feature (``qere_utf8``).
* Dicta does not predict the verbal stem (binyan); BHSA ``vs`` is reported, but cannot be compared.
* Dependency trees cannot be compared: BHSA encodes phrase/clause structure, not dependencies.

Data: Text-Fabric feature files fetched from GitHub at a pinned commit into
``data/external/bhsa/`` with sha256 checksums (``SOURCE.json``). Licence: CC BY-NC 4.0
(cite DOI 10.17026/dans-z6y-skyh).
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hebloc.normalize import RE_POINTS
from hebloc.paths import EXTERNAL_DIR

COMMIT = "4db00e2157915495e1a4d3d57e41223df24775da"
VERSION = "2021"
BASE_URL = f"https://raw.githubusercontent.com/ETCBC/bhsa/{COMMIT}/tf/{VERSION}/"
BHSA_DIR = EXTERNAL_DIR / "bhsa"
TF_DIR = BHSA_DIR / "tf" / VERSION
WORDS_PATH = BHSA_DIR / "words.parquet"
WORD_FEATURES = ["g_cons_utf8", "g_word_utf8", "trailer_utf8", "qere_utf8", "qere_trailer_utf8", "lex_utf8",
                 "voc_lex_utf8", "sp", "pdp", "vs", "vt", "ps", "nu", "gn", "prs", "st", "language"]
FILES = ["otype", "oslots", "book", "chapter", "verse", *WORD_FEATURES]
LICENSE = "CC BY-NC 4.0 (data); cite 10.17026/dans-z6y-skyh"

SP_TO_UPOS = {
    "subs": {"NOUN"}, "nmpr": {"PROPN"}, "verb": {"VERB", "AUX"}, "adjv": {"ADJ"}, "advb": {"ADV"},
    "prep": {"ADP"}, "conj": {"CCONJ", "SCONJ"}, "prps": {"PRON"}, "prde": {"PRON", "DET"},
    "prin": {"PRON"}, "intj": {"INTJ"}, "nega": {"ADV", "PART"}, "inrg": {"ADV", "PART", "SCONJ"},
    "art": {"DET"},
}
FINALS = str.maketrans("ךםןףץ", "כמנפצ")
RE_LEX_MARKS = re.compile(r"[/\[=]+$")


# ------------------------------------------------------------------------------ fetching

def fetch() -> dict:
    TF_DIR.mkdir(parents=True, exist_ok=True)
    files = {}
    for f in FILES:
        url = BASE_URL + f + ".tf"
        data = urllib.request.urlopen(url, timeout=120).read()  # noqa: S310 — fixed https URL
        (TF_DIR / f"{f}.tf").write_bytes(data)
        files[f + ".tf"] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    src = {"dataset": "ETCBC/bhsa", "version": VERSION, "commit": COMMIT, "base_url": BASE_URL,
           "license": LICENSE, "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": files}
    (BHSA_DIR / "SOURCE.json").write_text(json.dumps(src, indent=1) + "\n", encoding="utf-8")
    return src


def verify_files() -> list[str]:
    src = json.loads((BHSA_DIR / "SOURCE.json").read_text(encoding="utf-8"))
    return [f for f, m in src["files"].items()
            if hashlib.sha256((TF_DIR / f).read_bytes()).hexdigest() != m["sha256"]]


# ------------------------------------------------------------------------------ TF reader

def _spec(s: str) -> list[int]:
    out = []
    for part in s.split(","):
        a, _, b = part.partition("-")
        out.extend(range(int(a), int(b or a) + 1))
    return out


def _unescape(v: str) -> str:
    return v.replace("\\t", "\t").replace("\\n", "\n").replace("\\\\", "\\")


def read_tf(path: Path) -> tuple[dict[int, str], bool]:
    """Minimal Text-Fabric reader: returns ({node: value}, is_edge). For edges, value = target spec."""
    text = path.read_text(encoding="utf-8")
    if text.endswith("\n"):
        text = text[:-1]
    lines = text.split("\n")
    i, is_edge = 0, False
    while i < len(lines) and lines[i].startswith("@"):
        is_edge |= lines[i] == "@edge"
        i += 1
    if i < len(lines) and lines[i] == "":
        i += 1
    data: dict[int, str] = {}
    node = 0
    for line in lines[i:]:
        if "\t" in line:
            spec, val = line.split("\t", 1)
            nodes = _spec(spec)
        else:
            nodes, val = [node + 1], line
        val = val if is_edge else _unescape(val)
        for n in nodes:
            data[n] = val
        node = nodes[-1]
    return data, is_edge


def build_words() -> pa.Table:
    """One row per BHSA word with its verse reference (cached in words.parquet)."""
    if WORDS_PATH.exists():
        return pq.read_table(WORDS_PATH)
    otype, _ = read_tf(TF_DIR / "otype.tf")
    max_slot = max(n for n, t in otype.items() if t == "word")
    oslots, _ = read_tf(TF_DIR / "oslots.tf")
    book, _ = read_tf(TF_DIR / "book.tf")
    chapter, _ = read_tf(TF_DIR / "chapter.tf")
    verse, _ = read_tf(TF_DIR / "verse.tf")
    feats = {f: read_tf(TF_DIR / f"{f}.tf")[0] for f in WORD_FEATURES}
    slot_ref: dict[int, tuple[str, int, int]] = {}
    for n, t in otype.items():
        if t == "verse":
            ref = (book[n], int(chapter[n]), int(verse[n]))
            for s in _spec(oslots[n]):
                slot_ref[s] = ref
    rows = []
    for w in range(1, max_slot + 1):
        b, c, v = slot_ref[w]
        rows.append({"w": w, "book": b, "chapter": c, "verse": v, **{f: feats[f].get(w) for f in WORD_FEATURES}})
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, WORDS_PATH, compression="zstd")
    return table


BHSA_BOOKS = {  # BHSA (Latin) book name → our Mikra work name
    "Genesis": "Genesis", "Exodus": "Exodus", "Leviticus": "Leviticus", "Numeri": "Numbers",
    "Deuteronomium": "Deuteronomy", "Josua": "Joshua", "Judices": "Judges", "Samuel_I": "I Samuel",
    "Samuel_II": "II Samuel", "Reges_I": "I Kings", "Reges_II": "II Kings", "Jesaia": "Isaiah",
    "Jeremia": "Jeremiah", "Ezechiel": "Ezekiel", "Hosea": "Hosea", "Joel": "Joel", "Amos": "Amos",
    "Obadia": "Obadiah", "Jona": "Jonah", "Micha": "Micah", "Nahum": "Nahum", "Habakuk": "Habakkuk",
    "Zephania": "Zephaniah", "Haggai": "Haggai", "Sacharia": "Zechariah", "Maleachi": "Malachi",
    "Psalmi": "Psalms", "Iob": "Job", "Proverbia": "Proverbs", "Ruth": "Ruth", "Canticum": "Song of Songs",
    "Ecclesiastes": "Ecclesiastes", "Threni": "Lamentations", "Esther": "Esther", "Daniel": "Daniel",
    "Esra": "Ezra", "Nehemia": "Nehemiah", "Chronica_I": "I Chronicles", "Chronica_II": "II Chronicles",
}


def book_map(our_books: list[str], bhsa_books: list[str]) -> dict[str, str]:
    """BHSA book name → our Mikra work name; raises if any of the 39 books is unmapped."""
    m = {b: BHSA_BOOKS[b] for b in bhsa_books if b in BHSA_BOOKS and BHSA_BOOKS[b] in set(our_books)}
    if len(m) != len(bhsa_books) or set(m.values()) != set(our_books):
        raise ValueError(f"book mapping incomplete: {sorted(set(bhsa_books) - set(m))}")
    return m


# ------------------------------------------------------------------------------ alignment

def cons(s: str | None) -> str:
    """Comparable consonantal form: no points, no maqaf/punctuation, final letters → regular."""
    s = RE_POINTS.sub("", s or "")
    s = re.sub(r"[^א-ת]", "", s)
    return s.translate(FINALS)


def ortho_groups(words: list[dict], reading: str = "qere") -> list[dict]:
    """BHSA words of one verse → orthographic words for the given reading (qere|ketiv)."""
    groups, cur = [], []
    for w in words:
        use_qere = reading == "qere" and w.get("qere_utf8")
        form = w["qere_utf8"] if use_qere else w["g_cons_utf8"]
        trailer = (w.get("qere_trailer_utf8") if use_qere else w.get("trailer_utf8")) or ""
        cur.append((w, form))
        if trailer:  # any trailer (space, maqaf, sof pasuq…) ends the written word
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        host = g[-1][0]
        out.append({
            "cons": cons("".join(f for _, f in g)), "host": host, "words": [w for w, _ in g],
            "prefix_cons": cons("".join(f for _, f in g[:-1])),
            "is_kq": any(w.get("qere_utf8") for w, _ in g),
        })
    return [o for o in out if o["cons"]]


def dicta_groups(tokens: list[dict]) -> list[dict]:
    """Dicta words of one unit → one group per whitespace token (punctuation-only tokens dropped)."""
    by_ws: dict[tuple[int, int], list[dict]] = defaultdict(list)
    part, prev_ws = 0, None
    for t in sorted(tokens, key=lambda t: t["sent_word_idx"]):
        if t["ws_idx"] != prev_ws:
            part, prev_ws = 0, t["ws_idx"]
        if t["surface"] in ("-", "־"):   # a kept maqaf separates written words, as in BHSA
            part += 1
            continue
        by_ws[(t["ws_idx"], part)].append(t)
    out = []
    for key in sorted(by_ws):
        ws = key[0]
        ts = by_ws[key]
        lex = [t for t in ts if t["upos"] != "PUNCT"] or ts
        c = cons("".join(t["surface"] for t in ts))
        if c:
            out.append({"cons": c, "host": lex[-1], "ws_idx": ws, "n_words": len(ts)})
    return out


def align(dg: list[dict], bg: list[dict]) -> list[tuple[dict, dict]]:
    if [d["cons"] for d in dg] == [b["cons"] for b in bg]:
        return list(zip(dg, bg))
    sm = difflib.SequenceMatcher(a=[d["cons"] for d in dg], b=[b["cons"] for b in bg], autojunk=False)
    pairs = []
    for blk in sm.get_matching_blocks():
        pairs += [(dg[blk.a + i], bg[blk.b + i]) for i in range(blk.size)]
    return pairs


def norm_lex(s: str | None) -> str:
    return cons(RE_LEX_MARKS.sub("", s or ""))


def compare(pairs: list[tuple[dict, dict]]) -> list[dict]:
    """Per aligned orthographic word: agreement indicators (None = not applicable)."""
    rows = []
    for d, b in pairs:
        h, t = b["host"], d["host"]
        sp = h.get("sp")
        allowed = SP_TO_UPOS.get(sp, set())
        dicta_prefix = cons(t.get("prefix") or "")
        is_verb = sp == "verb"
        lenient = set(allowed)
        if sp == "subs":
            lenient |= {"NUM", "DET"}                       # BHSA has no NUM; כל is subs in BHSA, DET in UD
        if is_verb and h.get("vt") in ("ptca", "ptcp"):
            lenient |= {"NOUN", "ADJ"}                      # participles
        r = {
            "pos_agree_lenient": (t["upos"] in lenient) if allowed else None,
            "ws_idx": d["ws_idx"], "bhsa_w": h["w"], "language": h.get("language"), "is_kq": b["is_kq"],
            "bhsa_sp": sp, "bhsa_vs": h.get("vs"), "bhsa_vt": h.get("vt"), "dicta_upos": t["upos"],
            "dicta_tense": t.get("tense"),
            "pos_agree": (t["upos"] in allowed) if allowed else None,
            "prefix_agree": dicta_prefix == b["prefix_cons"],
            "bhsa_has_prefix": bool(b["prefix_cons"]), "dicta_has_prefix": bool(dicta_prefix),
            "lemma_agree": None if t.get("lemma_blank") else norm_lex(t.get("lemma")) == norm_lex(h.get("lex_utf8")),
            "lemma_blank": bool(t.get("lemma_blank")),
            "lemma_class": ("verb_qal" if is_verb and h.get("vs") == "qal" else "verb_other_stem" if is_verb
                            else "noun" if sp in ("subs", "nmpr") else "other"),
        }
        if is_verb and t["upos"] in ("VERB", "AUX"):
            for feat, bf, mp in (("person", "ps", {"p1": "1", "p2": "2", "p3": "3"}),
                                 ("number", "nu", {"sg": "Sing", "pl": "Plur", "du": "Dual"}),
                                 ("gender", "gn", {"m": "Masc", "f": "Fem"})):
                bv = mp.get(h.get(bf) or "")
                dv = t.get(feat)
                r[f"{feat}_agree"] = None if (bv is None or dv is None or "," in (dv or "")) else bv == dv
        rows.append(r)
    return rows


def verse_words_index(table: pa.Table, bmap: dict[str, str]) -> dict[str, list[dict]]:
    idx: dict[str, list[dict]] = defaultdict(list)
    for w in table.to_pylist():
        b = bmap.get(w["book"])
        if b:
            idx[f"{b} {w['chapter']}:{w['verse']}"].append(w)
    return idx


def summarize(rows: list[dict], n_bhsa_words: int, n_dicta_groups: int) -> dict:
    def rate(key, sub=None):
        v = [r[key] for r in (sub if sub is not None else rows) if r.get(key) is not None]
        return {"n": len(v), "agree": round(sum(v) / len(v), 4) if v else None}
    heb = [r for r in rows if r["language"] == "Hebrew"]
    return {
        "aligned_words": len(rows), "bhsa_ortho_words": n_bhsa_words, "dicta_ws_words": n_dicta_groups,
        "alignment_rate_bhsa": round(len(rows) / n_bhsa_words, 4) if n_bhsa_words else None,
        "hebrew": {"pos": rate("pos_agree", heb), "pos_lenient": rate("pos_agree_lenient", heb), "prefix_segmentation": rate("prefix_agree", heb),
                   "lemma_noun": rate("lemma_agree", [r for r in heb if r["lemma_class"] == "noun"]),
                   "lemma_verb_qal": rate("lemma_agree", [r for r in heb if r["lemma_class"] == "verb_qal"]),
                   "lemma_verb_other_stem": rate("lemma_agree", [r for r in heb if r["lemma_class"] == "verb_other_stem"]),
                   "lemma_blank_rate": round(sum(r["lemma_blank"] for r in heb) / len(heb), 4) if heb else None,
                   "verb_person": rate("person_agree", heb), "verb_number": rate("number_agree", heb),
                   "verb_gender": rate("gender_agree", heb)},
        "aramaic": {"pos": rate("pos_agree", [r for r in rows if r["language"] == "Aramaic"])},
        "pos_confusion": Counter(f"{r['bhsa_sp']}→{r['dicta_upos']}" for r in heb).most_common(40),
        "tense_confusion": Counter(f"{r['bhsa_vt']}→{r['dicta_tense']}" for r in heb if r["bhsa_sp"] == "verb").most_common(25),
    }
