"""Reconstruction of old-tokenizer artifacts ``prefix=X`` / ``token=Y`` (decision D-016).

Evidence (all 1,159,353 occurrences classified, see docs/m2_preprocessing.md): an earlier
tokenizer split a Hebrew prefix (ב ל כ ה מ ו ש and combinations) off a following non-word token
and wrote it as ``prefix=X``. The rest of the original word follows as separate tokens.

Rules are applied only where the original surface form is unambiguous:

  R1 token     ``prefix=X token=Y``             → ``XY``      e.g. prefix=ל token=פרופ'  → לפרופ'
  R2 hyphen    ``prefix=X - H`` (H number/Latin) → ``X-H``     e.g. prefix=ה - 13       → ה-13
  R3 quote     ``prefix=X " W`` / ``' W`` (W Hebrew word)
                                               → ``X"W``     e.g. prefix=ל " ב        → ל"ב
                 (covers gershayim acronyms/numerals and a prefix before a quoted word, which are
                 written identically in Hebrew orthography)
  R4 bare      ``token=Y`` not after prefix=     → ``Y``       (tag removal only; also inside a
               token, e.g. literary ``ו-token=פרופ'`` → ``ו-פרופ'``)
  (pre-pass)   ``prefix= X`` (tag separated from its 1–3-letter value by a space, nrg) is first
               re-attached to ``prefix=X`` and then handled by the rules above (flag ``prefix_spaced``).

Everything else is AMBIGUOUS — e.g. ``prefix=ב - דולר`` (the number was lost in the source),
``prefix=ה - , 17`` (punctuation reordered before the number), ``prefix=ב ?``. These are NOT
reconstructed: only the literal tag text ``prefix=`` is removed (``X`` stays a separate token,
nothing is joined, added or reordered) and the unit is flagged ``prefix_unresolved:<class>``.
The original text is always preserved in ``text_raw``.
"""

from __future__ import annotations

import re

RE_HEBREW = re.compile(r"[א-ת]")
RE_NUMBER = re.compile(r"\d[\d.,/:%]*")
RE_LATIN = re.compile(r"[A-Za-z][A-Za-z0-9.&'_+-]*")
HYPHENS = {"-", "–", "־"}
RE_PREFIX_VALUE = re.compile(r"[א-ת]{1,3}")
QUOTES = {'"', "'", "״", "׳"}


def _classify_host(tok: str | None) -> str:
    if tok is None:
        return "eol"
    if tok.startswith("prefix="):
        return "prefix"
    if RE_NUMBER.fullmatch(tok):
        return "number"
    if RE_LATIN.fullmatch(tok):
        return "latin"
    if RE_HEBREW.search(tok):
        return "hebrew"
    return "punct"


def reconstruct(text: str) -> tuple[str, list[str]]:
    """Return ``(new_text, flags)``. Text without artifacts is returned unchanged.

    Operates on whitespace tokens (the affected corpora are pre-tokenized); output tokens are
    joined with single spaces. Flags: ``prefix_R1``..``prefix_R3``, ``token_R4``,
    ``prefix_unresolved:<class>``.
    """
    if "prefix=" not in text and "token=" not in text:
        return text, []
    raw_toks = text.split()
    flags: list[str] = []
    toks: list[str] = []
    j = 0
    while j < len(raw_toks):  # pre-pass: "prefix= X" → "prefix=X"
        if raw_toks[j] == "prefix=" and j + 1 < len(raw_toks) and RE_PREFIX_VALUE.fullmatch(raw_toks[j + 1]):
            toks.append("prefix=" + raw_toks[j + 1])
            flags.append("prefix_spaced")
            j += 2
            continue
        toks.append(raw_toks[j])
        j += 1
    out: list[str] = []
    i = 0
    n = len(toks)
    while i < n:
        t = toks[i]
        if t.startswith("prefix=") and len(t) > len("prefix="):
            x = t[len("prefix="):]
            n1 = toks[i + 1] if i + 1 < n else None
            n2 = toks[i + 2] if i + 2 < n else None
            if n1 is not None and n1.startswith("token=") and len(n1) > len("token="):
                out.append(x + n1[len("token="):])
                flags.append("prefix_R1")
                i += 2
                continue
            if n1 in HYPHENS and _classify_host(n2) in ("number", "latin"):
                out.append(f"{x}{n1}{n2}")
                flags.append("prefix_R2")
                i += 3
                continue
            if n1 in QUOTES and n2 is not None and _classify_host(n2) == "hebrew" and n2 not in QUOTES:
                out.append(f"{x}{n1}{n2}")
                flags.append("prefix_R3")
                i += 3
                continue
            # Ambiguous: remove only the tag text; keep every token, in order, unjoined.
            if n1 in HYPHENS:
                cls = f"hyphen_{_classify_host(n2)}"
            elif n1 in QUOTES:
                cls = f"quote_{_classify_host(n2)}"
            else:
                cls = _classify_host(n1)
            out.append(x)
            flags.append(f"prefix_unresolved:{cls}")
            i += 1
            continue
        if "token=" in t and len(t) > len("token="):
            out.append(t.replace("token=", ""))
            flags.append("token_R4")
            i += 1
            continue
        out.append(t)
        i += 1
    return " ".join(out), flags
