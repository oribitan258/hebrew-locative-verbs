"""Text normalization: ``text_raw`` (exact source slice) → ``text_norm`` (model input).

Versioned (``NORM_VERSION``); every rule that fires on a unit is recorded in its ``norm_flags``,
so each change is traceable and statistics can be split by flag. All rules are corpus-specific,
evidence-based defaults (docs/m2_preprocessing.md) and several are explicit HYPOTHESES to be
validated with Dicta in the M3 pilot (decision D-009): niqqud stripping, Qere over Ketiv,
maqaf → space, sof pasuq → '.'.

Common to all corpora (applied last):
  * remove invisible format/bidi characters (LRM/RLM, embeddings, ZWJ/ZWNJ, CGJ, BOM);
  * strip niqqud, cantillation and other Hebrew points; keep letters, geresh/gershayim, maqaf;
  * map exotic spaces (NBSP, thin space, …) to a space and collapse whitespace.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from hebloc.artifacts import reconstruct

NORM_VERSION = "1"

RE_INVISIBLE = re.compile("[​-‏‪-‮⁦-⁩͏﻿­]")
RE_POINTS = re.compile("[֑-ׇֽֿׁׂׅׄ]")  # cantillation + niqqud
RE_SPACES = re.compile(r"[\s  -   　]+")
RE_HEBREW_LETTER = re.compile("[א-ת]")


@dataclass
class Normalized:
    text: str
    flags: list[str] = field(default_factory=list)
    alt: str | None = None  # alternative reading (Mikra: Ketiv), same normalization otherwise


def _common(text: str, flags: list[str]) -> str:
    if RE_INVISIBLE.search(text):
        text = RE_INVISIBLE.sub("", text)
        flags.append("invisible_chars_removed")
    if RE_POINTS.search(text):
        text = RE_POINTS.sub("", text)
        flags.append("diacritics_stripped")
    return RE_SPACES.sub(" ", text).strip()


# ---------------------------------------------------------------------------------- Mikra

RE_KQ_PAIR = re.compile(r"\(([^()\[\]]*)\)\s*\[([^()\[\]]*)\]")   # (ketiv) [qere]
RE_QK_PAIR = re.compile(r"\[([^()\[\]]*)\]\s*\(([^()\[\]]*)\)")   # [qere] (ketiv) — also used
RE_QERE_ONLY = re.compile(r"\[([^()\[\]]*)\]")
RE_KETIV_ONLY = re.compile(r"\(([^()\[\]]*)\)")
RE_PARASHA = re.compile(r"\{([פס])\}")
RE_MIKRA_ACCENT_QUOTES = re.compile(r"['\"]")


def _mikra_reading(raw: str, qere: bool) -> str:
    """Resolve Ketiv/Qere notation to one reading (pairs, qere-only, ketiv-only)."""
    if qere:
        s = RE_KQ_PAIR.sub(lambda m: m.group(2), raw)
        s = RE_QK_PAIR.sub(lambda m: m.group(1), s)
        s = RE_QERE_ONLY.sub(lambda m: m.group(1), s)       # qere wela ketiv: read
        s = RE_KETIV_ONLY.sub("", s)                          # ketiv wela qere: not read
    else:
        s = RE_KQ_PAIR.sub(lambda m: m.group(1), raw)
        s = RE_QK_PAIR.sub(lambda m: m.group(2), s)
        s = RE_QERE_ONLY.sub("", s)
        s = RE_KETIV_ONLY.sub(lambda m: m.group(1), s)
    return s


def _mikra_finish(s: str, flags: list[str]) -> str:
    s = RE_PARASHA.sub(" ", s)
    s = RE_MIKRA_ACCENT_QUOTES.sub("", s)        # ASCII ' " are converted accents in this edition
    s = s.replace("׀", " ")                  # paseq ׀ (accent divider)
    s = s.replace("-", " ").replace("־", " ")  # maqaf → space (HYPOTHESIS, D-009)
    s = s.replace("׃", " .")                 # sof pasuq → '.' (HYPOTHESIS, D-009)
    return _common(s, flags)


def normalize_mikra(raw: str) -> Normalized:
    flags: list[str] = []
    if m := RE_PARASHA.search(raw):
        flags.append(f"parasha_marker:{m.group(1)}")
    has_kq = bool(RE_QERE_ONLY.search(raw) or RE_KETIV_ONLY.search(raw))
    if has_kq:
        if RE_KQ_PAIR.search(raw) or RE_QK_PAIR.search(raw):
            flags.append("ketiv_qere")
        rest = RE_QK_PAIR.sub("", RE_KQ_PAIR.sub("", raw))
        if RE_QERE_ONLY.search(rest):
            flags.append("qere_only")
        if RE_KETIV_ONLY.search(rest):
            flags.append("ketiv_only")
    if RE_MIKRA_ACCENT_QUOTES.search(raw):
        flags.append("accent_quotes_removed")
    if "-" in raw or "־" in raw:
        flags.append("maqaf_to_space")
    text = _mikra_finish(_mikra_reading(raw, qere=True), flags)
    alt = _mikra_finish(_mikra_reading(raw, qere=False), []) if has_kq else None
    return Normalized(text, flags, alt)


# ------------------------------------------------------------------- Hazal and Medieval

RE_ENUMERATOR = re.compile(
    r"^\s*\((?:[א-ט]|[יכלמנסעפצ][א-ט]?|[קרשת](?:[יכלמנסעפצ]?[א-ט]?))\)\s+"
)  # line-initial editorial paragraph numbers (א)…(תצט) — only valid Hebrew numerals
RE_RAMBAM_CITATION = re.compile(r"\+ ([^+]{1,60}?) \+")


def _rabbinic(raw: str, flags: list[str], *, line_start: bool) -> str:
    s = raw
    if "&" in s and re.search(r"&(?:[a-z]+|#\d+);", s):
        s = html.unescape(s)
        flags.append("html_entities_decoded")
    if line_start and RE_ENUMERATOR.match(s):
        s = RE_ENUMERATOR.sub("", s, count=1)
        flags.append("enumerator_removed")
    return s


def normalize_hazal(raw: str, *, line_start: bool = False) -> Normalized:
    flags: list[str] = []
    s = _rabbinic(raw, flags, line_start=line_start)
    return Normalized(_common(s, flags), flags)


def normalize_medieval(raw: str, *, line_start: bool = False, rambam: bool = False) -> Normalized:
    flags: list[str] = []
    s = _rabbinic(raw, flags, line_start=line_start)
    if rambam:
        if RE_RAMBAM_CITATION.search(s):
            s = RE_RAMBAM_CITATION.sub(r"( \1 )", s)          # "+ דברים כ"ב +" → "( דברים כ"ב )"
            flags.append("citation_plus_to_parens")
        s, art = reconstruct(s)
        flags += art
    return Normalized(_common(s, flags), flags)


# ---------------------------------------------------------------------------------- Haskala

RE_HTML_TAG = re.compile(r"</?[A-Za-z][^<>]{0,200}>")
RE_SIC = re.compile(r"<!>")
RE_EMPTY_ANGLE = re.compile(r"<>")
RE_EDITION_NOTE = re.compile(r"<\s*(?:במהד'|במהדורה|בדפוס)[^<>]{0,300}>")  # editor's variant-reading note


def normalize_haskala(raw: str) -> Normalized:
    flags: list[str] = []
    s = raw
    if RE_HTML_TAG.search(s):
        s = RE_HTML_TAG.sub(" ", s)
        flags.append("html_tags_removed")
    if RE_EDITION_NOTE.search(s):
        s = RE_EDITION_NOTE.sub(" ", s)               # apparatus, not the author's text: drop
        flags.append("edition_note_removed")
    if RE_SIC.search(s):
        s = RE_SIC.sub(" ", s)
        flags.append("sic_marker_removed")
    if RE_EMPTY_ANGLE.search(s):
        s = RE_EMPTY_ANGLE.sub(" ", s)
        flags.append("separator_removed")
    if "<" in s or ">" in s:
        s = s.replace("<", "").replace(">", "")       # quotation brackets: keep the quoted text
        flags.append("quote_brackets_removed")
    if "{" in s or "}" in s:
        s = s.replace("{", "").replace("}", "")       # editorial emphasis braces: keep content
        flags.append("braces_removed")
    if "#" in s:
        s = s.replace("#", " ")
        flags.append("hash_marker_removed")
    return Normalized(_common(s, flags), flags)


# ---------------------------------------------------------------------------------- Modern

RE_HAARETZ_HEADER = re.compile(r"^\s*עדכון\s+אחרון\s+-\s+\d{1,2}:\d{2}\s+\d{1,2}/\d{1,2}/\d{2,4}\s*")
RE_IMG = re.compile(r"\[ IMG \]")
RE_URL = re.compile(r"https?://|www\.")


def normalize_modern(raw: str, *, line_start: bool = False, haaretz: bool = False) -> Normalized:
    flags: list[str] = []
    s = raw
    if haaretz and line_start and RE_HAARETZ_HEADER.match(s):
        s = RE_HAARETZ_HEADER.sub("", s, count=1)
        flags.append("haaretz_header_removed")
    if RE_IMG.search(s):
        s = RE_IMG.sub(" ", s)
        flags.append("img_marker_removed")
    s, art = reconstruct(s)
    flags += art
    if RE_URL.search(s):
        flags.append("contains_url")
    return Normalized(_common(s, flags), flags)


def hebrew_token_count(text: str) -> int:
    return sum(1 for t in text.split() if RE_HEBREW_LETTER.search(t))
