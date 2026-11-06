"""Byte-level decoding and text profiling for one file.

Definitions here are the project's canonical ones, reused in later milestones:

* **Encoding detection** (deterministic, strict, per file):
  empty → ``empty``; UTF-8 BOM → ``utf-8-sig``; pure ASCII → ``ascii``; strict UTF-8 → ``utf-8``;
  strict Windows-1255 → ``cp1255``; otherwise lossy decoding with the fewer replacements,
  labelled ``utf-8-lossy`` / ``cp1255-lossy`` and counted in ``decode_errors``.
* **Line**: a segment delimited by ``\\n`` only (a trailing ``\\r`` belongs to the CRLF ending).
  Python's ``str.splitlines`` is NOT used, because it also splits on ``\\x0b \\x0c \\x1c-\\x1e
  \\x85 \\u2028 \\u2029`` and lone ``\\r`` — such characters are counted as anomalies instead.
* **Token**: a maximal run of non-whitespace characters (``str.split()`` semantics).
* **Hebrew token**: a token containing at least one Hebrew letter (U+05D0–U+05EA).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

UTF8_BOM = b"\xef\xbb\xbf"

HEBREW_LETTERS = "א-ת"
RE_HEB_LETTER = re.compile(f"[{HEBREW_LETTERS}]")
RE_HEB_TOKEN = re.compile(rf"[{HEBREW_LETTERS}]\S*")  # exactly one match per Hebrew token
RE_NIQQUD = re.compile("[ְ-ׇֽֿׁׂׅׄ]")
RE_CANTILLATION = re.compile("[֑-֯]")
RE_LATIN = re.compile("[A-Za-z]")
RE_DIGIT = re.compile("[0-9]")
RE_CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
RE_ODD_LINE_SEP = re.compile("\r(?!\n)|[\x85  ]")
RE_LATIN1_SUPPLEMENT = re.compile("[À-ÿ]")  # mojibake indicator in Hebrew text
RE_URL = re.compile(r"https?://|www\.")
# Pre-tokenization artifacts found in the Modern corpus (see docs/corpus_report.md):
# "prefix=ב token=רח'" encodes "ברח'"; "[ IMG ]" marks a removed image.
PREFIX_TAG, TOKEN_TAG, IMG_TAG = "prefix=", "token=", "[ IMG ]"
RE_7ZIP_LOG = re.compile(rb"Zip\s+7.{0,200}?Igor\s+Pavlov", re.DOTALL)


def looks_like_7zip_log(data: bytes) -> bool:
    """Content signature of the 7-Zip archiving logs found among Modern files."""
    return bool(RE_7ZIP_LOG.search(data[:400]))


def decode_bytes(data: bytes) -> tuple[str, str, int]:
    """Return ``(text, encoding_label, n_decode_errors)``. Never raises."""
    if not data:
        return "", "empty", 0
    if data.startswith(UTF8_BOM):
        try:
            return data[len(UTF8_BOM):].decode("utf-8"), "utf-8-sig", 0
        except UnicodeDecodeError:
            pass
    try:
        return data.decode("ascii"), "ascii", 0
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("utf-8"), "utf-8", 0
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1255"), "cp1255", 0
    except UnicodeDecodeError:
        pass
    u = data.decode("utf-8", errors="replace")
    c = data.decode("cp1255", errors="replace")
    nu, nc = u.count("�"), c.count("�")
    return (u, "utf-8-lossy", nu) if nu <= nc else (c, "cp1255-lossy", nc)


def split_lines(text: str) -> list[str]:
    """Canonical line split: on ``\\n`` only, stripping one trailing ``\\r`` per line.

    A final newline does not create an extra empty line. ``""`` → ``[]``.
    """
    if not text:
        return []
    parts = text.split("\n")
    if text.endswith("\n"):
        parts.pop()
    return [p[:-1] if p.endswith("\r") else p for p in parts]


@dataclass(frozen=True)
class TextProfile:
    encoding: str
    decode_errors: int
    has_bom: bool
    n_feff: int  # U+FEFF characters inside the text (stray BOMs)
    line_endings: str  # none | lf | crlf | mixed
    n_lines: int
    n_nonempty_lines: int
    max_line_chars: int
    n_chars: int
    n_hebrew_letters: int
    n_niqqud: int
    n_cantillation: int
    n_latin_letters: int
    n_digits: int
    n_control_chars: int
    n_odd_line_separators: int
    n_latin1_supplement: int
    n_prefix_tags: int
    n_token_tags: int
    n_img_tags: int
    n_urls: int
    n_tokens: int
    n_hebrew_tokens: int
    is_blank: bool

    def as_dict(self) -> dict:
        return asdict(self)


def profile_text(data: bytes) -> TextProfile:
    text, encoding, errors = decode_bytes(data)
    n_crlf = text.count("\r\n")
    n_lf = text.count("\n")
    if n_lf == 0:
        endings = "none"
    elif n_crlf == n_lf:
        endings = "crlf"
    elif n_crlf == 0:
        endings = "lf"
    else:
        endings = "mixed"
    lines = split_lines(text)
    return TextProfile(
        encoding=encoding,
        decode_errors=errors,
        has_bom=encoding == "utf-8-sig",
        n_feff=text.count("﻿"),
        line_endings=endings,
        n_lines=len(lines),
        n_nonempty_lines=sum(1 for ln in lines if ln.strip()),
        max_line_chars=max((len(ln) for ln in lines), default=0),
        n_chars=len(text),
        n_hebrew_letters=len(RE_HEB_LETTER.findall(text)),
        n_niqqud=len(RE_NIQQUD.findall(text)),
        n_cantillation=len(RE_CANTILLATION.findall(text)),
        n_latin_letters=len(RE_LATIN.findall(text)),
        n_digits=len(RE_DIGIT.findall(text)),
        n_control_chars=len(RE_CONTROL.findall(text)),
        n_odd_line_separators=len(RE_ODD_LINE_SEP.findall(text)),
        n_latin1_supplement=len(RE_LATIN1_SUPPLEMENT.findall(text)),
        n_prefix_tags=text.count(PREFIX_TAG),
        n_token_tags=text.count(TOKEN_TAG),
        n_img_tags=text.count(IMG_TAG),
        n_urls=len(RE_URL.findall(text)),
        n_tokens=len(text.split()),
        n_hebrew_tokens=len(RE_HEB_TOKEN.findall(text)),
        is_blank=not text.strip(),
    )
