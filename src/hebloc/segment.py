"""Segmentation of a raw source line into units, returned as character spans.

Spans index the decoded source line exactly, so ``line[start:end]`` IS the unit's ``text_raw``.
Rules (versioned, ``SEGMENT_VERSION``; evidence in docs/m2_preprocessing.md):

* Mikra: one verse per line → one unit (``verse``); never split.
* Other corpora: split after a run of terminators ``. ? !`` that is followed by whitespace and
  more text, unless (a) inside (), [], {} or <> brackets, (b) the token ending in the terminator
  is a single letter (initials such as "י. ל.") or a bare number at the start of the span (list
  enumerators "1 ."). The colon is NOT a terminator: mid-line it introduces quotations
  ("שנאמר: ...", "אמר :"); line-final colons need no split.
* Units are COMPLETE linguistic units (segment v2). Over-long sentences are no longer cut here:
  splitting for a model's input limit is a parse-time step (``hebloc.pieces``) that references
  the whole unit by ``sent_id``. (Segment v1 cut units > 200 whitespace tokens into ``chunk``
  units BEFORE normalization; see decision D-020.)
"""

from __future__ import annotations

import re

SEGMENT_VERSION = "2"
TERMINATORS = ".?!"
OPENERS = {"(": ")", "[": "]", "{": "}", "<": ">"}
CLOSERS = {v: k for k, v in OPENERS.items()}
RE_SINGLE_LETTER = re.compile(r"^[א-תA-Za-z]$")
RE_DIGITS = re.compile(r"^\d+$")


def _trim(line: str, s: int, e: int) -> tuple[int, int] | None:
    while s < e and line[s].isspace():
        s += 1
    while e > s and line[e - 1].isspace():
        e -= 1
    return (s, e) if e > s else None


MAX_PROTECTED = 400  # brackets longer than this do not block sentence splitting


def _protected(line: str) -> list[bool]:
    """Mark characters inside MATCHED bracket pairs (unmatched brackets protect nothing)."""
    mask = [False] * len(line)
    stack: list[tuple[str, int]] = []
    for i, ch in enumerate(line):
        if ch in OPENERS:
            stack.append((ch, i))
        elif ch in CLOSERS:
            for k in range(len(stack) - 1, -1, -1):  # match the nearest opener of this type
                if stack[k][0] == CLOSERS[ch]:
                    o = stack[k][1]
                    del stack[k:]
                    if i - o <= MAX_PROTECTED:
                        for p in range(o + 1, i):
                            mask[p] = True
                    break
    return mask


def sentence_spans(line: str) -> list[tuple[int, int]]:
    """Sentence spans (start, end) covering all non-whitespace text of ``line``."""
    spans: list[tuple[int, int]] = []
    inside = _protected(line)
    start = 0
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if ch in TERMINATORS and not inside[i]:
            j = i
            while True:  # absorb "!!", and space-separated terminator tokens "! !", ". . ."
                while j + 1 < n and line[j + 1] in TERMINATORS:
                    j += 1
                m = j + 1
                while m < n and line[m].isspace():
                    m += 1
                if m < n and line[m] in TERMINATORS and (m + 1 == n or line[m + 1] in TERMINATORS or line[m + 1].isspace()):
                    j = m
                    continue
                break
            nxt = j + 1
            if nxt < n and line[nxt].isspace() and line[nxt:].strip():
                # token that ends at the terminator run (may be attached, e.g. "וכו." or "י.")
                tok_start = i
                while tok_start > start and not line[tok_start - 1].isspace():
                    tok_start -= 1
                word = line[tok_start:i]
                if not word:  # pre-tokenized "word ." → look at the previous token
                    k = tok_start - 1
                    while k > start and line[k].isspace():
                        k -= 1
                    ws = k
                    while ws > start and not line[ws - 1].isspace():
                        ws -= 1
                    word = line[ws:k + 1]
                    is_first = not line[start:ws].strip()
                else:
                    is_first = not line[start:tok_start].strip()
                guarded = bool(RE_SINGLE_LETTER.match(word)) or (bool(RE_DIGITS.match(word)) and is_first)
                if not guarded:
                    sp = _trim(line, start, nxt)
                    if sp:
                        spans.append(sp)
                    start = nxt
            i = j + 1
            continue
        i += 1
    sp = _trim(line, start, n)
    if sp:
        spans.append(sp)
    return spans


def segment_line(line: str, corpus_id: str) -> list[tuple[int, int, str]]:
    """Units of one source line as (start, end, unit_type); unit_type is ``verse`` or ``sentence``."""
    if not line.strip():
        return []
    if corpus_id == "mikra":
        sp = _trim(line, 0, len(line))
        return [(sp[0], sp[1], "verse")] if sp else []
    return [(s, e, "sentence") for s, e in sentence_spans(line)]
