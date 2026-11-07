"""Parse-time "pieces": splitting a COMPLETE unit's ``text_norm`` to fit a model's input limit.

Since segment v2 (decision D-020) the ``units`` table stores only complete linguistic units
(sentences / verses). A unit that is too long for the parser is split here, at parse time, into
*pieces*. A piece is a processing artifact, never a linguistic unit: it is always stored with
its parent ``sent_id`` and its exact character span in that unit's ``text_norm``, so that

    annotation token → (sent_id, piece_idx, token) → text_norm offsets → sent_id → doc_id
                      → rel_path + line_no + char offsets (+ file sha256)

and the parent sentence can never be confused with a neighbouring one.

Rule (``PIECE_VERSION = "1"``): whitespace tokens of ``text_norm`` are packed greedily into pieces
whose total *cost* is ≤ ``budget``; a piece that has to be cut is preferably cut after the last
token ending in ``, ; :`` that lies in its second half. The cost of a token is 1 by default
(whitespace tokens); the parser supplies a sub-word cost from its own tokenizer, measured in M3.
With cost 1 and budget 200 this reproduces the segment-v1 chunk boundaries exactly (verified on
all 3,000 v1-chunked sentences, ``hebloc.units_migrate``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

import pyarrow as pa

PIECE_VERSION = "1"
SOFT_BREAKS = frozenset(",;:")
RE_TOKEN = re.compile(r"\S+")

# Schema of the per-piece metadata that every parse run must store (M3/M5) next to the raw
# parser output. Primary key: (sent_id, piece_idx).
PIECES_SCHEMA = pa.schema(
    [
        ("sent_id", pa.string()),          # parent unit (complete sentence / verse)
        ("piece_idx", pa.int16()),         # 0-based position of the piece within the unit
        ("n_pieces", pa.int16()),          # 1 = the unit was parsed whole (complete tree)
        ("norm_char_start", pa.int32()),   # span in the unit's text_norm
        ("norm_char_end", pa.int32()),
        ("tok_start", pa.int32()),         # whitespace-token range [tok_start, tok_end) of text_norm
        ("tok_end", pa.int32()),
        ("cost", pa.int32()),              # total cost of the piece in `cost_unit`
        ("budget", pa.int32()),            # budget used for this run
        ("cost_unit", pa.string()),        # e.g. "ws_token" or "<tokenizer>@<revision>:subword"
        ("piece_version", pa.string()),
    ]
)


@dataclass(frozen=True)
class Piece:
    start: int       # char offsets in the text
    end: int
    tok_start: int   # whitespace-token index range [tok_start, tok_end)
    tok_end: int
    cost: int


def plan_pieces(text: str, budget: int, cost: Callable[[str], int] | None = None) -> list[Piece]:
    """Split ``text`` into contiguous pieces of total cost ≤ ``budget`` (see module docstring).

    A single token whose own cost exceeds the budget becomes a piece of its own (its ``cost`` then
    exceeds ``budget``; the caller must detect and log this, never silently truncate).
    """
    if budget < 1:
        raise ValueError("budget must be ≥ 1")
    toks = [(m.start(), m.end()) for m in RE_TOKEN.finditer(text)]
    if not toks:
        return []
    costs = [cost(text[s:e]) if cost else 1 for s, e in toks]
    n = len(toks)
    out: list[Piece] = []
    i = 0
    while i < n:
        j, total = i, 0
        while j < n and (j == i or total + costs[j] <= budget):
            total += costs[j]
            j += 1
        if j < n:  # the unit continues: prefer a soft break in the second half of this piece
            for k in range(j - 1, i + (j - i) // 2, -1):
                if text[toks[k][1] - 1] in SOFT_BREAKS:
                    j = k + 1
                    break
        out.append(Piece(toks[i][0], toks[j - 1][1], i, j, sum(costs[i:j])))
        i = j
    return out


def verify_pieces(text: str, pieces: list[Piece]) -> None:
    """Raise AssertionError unless the pieces reconstruct ``text`` exactly (nothing lost/added)."""
    toks = RE_TOKEN.findall(text)
    if not toks:
        assert not pieces, "pieces for an empty text"
        return
    assert pieces and pieces[0].tok_start == 0 and pieces[-1].tok_end == len(toks), "token range not covered"
    assert pieces[0].start == len(text) - len(text.lstrip()), "first piece does not start at the text"
    assert pieces[-1].end == len(text.rstrip()), "last piece does not end at the text"
    for a, b in zip(pieces, pieces[1:]):
        assert a.tok_end == b.tok_start, "token ranges not contiguous"
        gap = text[a.end:b.start]
        assert gap and gap.isspace(), "pieces must be separated by whitespace only"
    for p in pieces:
        assert text[p.start:p.end].split() == toks[p.tok_start:p.tok_end], "piece text ≠ its tokens"


def piece_rows(sent_id: str, text: str, budget: int, cost: Callable[[str], int] | None = None,
               cost_unit: str = "ws_token") -> list[dict]:
    """Rows in ``PIECES_SCHEMA`` for one unit (verified before they are returned)."""
    pieces = plan_pieces(text, budget, cost)
    verify_pieces(text, pieces)
    return [
        {"sent_id": sent_id, "piece_idx": i, "n_pieces": len(pieces), "norm_char_start": p.start,
         "norm_char_end": p.end, "tok_start": p.tok_start, "tok_end": p.tok_end, "cost": p.cost,
         "budget": budget, "cost_unit": cost_unit, "piece_version": PIECE_VERSION}
        for i, p in enumerate(pieces)
    ]
