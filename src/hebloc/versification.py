"""Tanakh versification: map Mikra verse lines to ``Book chapter:verse`` references.

The Mikra files contain one verse per line but no chapter/verse labels. The chapter lengths come
from Sefaria's API (the files appear to be Sefaria's "Miqra according to the Masorah", so the
versification should coincide). The table is fetched ONCE by ``uv run hebloc versification`` into
the git-tracked ``config/reference/tanakh_versification.json`` with its source URL, retrieval
date and digest (decision D-005). It is trusted only if, for every book, the sum of its chapter
lengths equals the number of verse lines in the corresponding Mikra file.
"""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from hebloc.paths import CONFIG_DIR

VERSIFICATION_PATH = CONFIG_DIR / "reference" / "tanakh_versification.json"
SOURCE_URL = "https://www.sefaria.org/api/shape/{book}"

# Aramaic passages (by verse). Ranges are inclusive (chapter, verse). Daniel 2:4 begins in Hebrew
# and switches to Aramaic mid-verse; Gen 31:47 has a two-word Aramaic toponym.
ARAMAIC_FULL = {
    "Daniel": [((2, 5), (7, 28))],
    "Ezra": [((4, 8), (6, 18)), ((7, 12), (7, 26))],
    "Jeremiah": [((10, 11), (10, 11))],
}
ARAMAIC_PARTIAL = {"Daniel": [(2, 4)], "Genesis": [(31, 47)]}


def fetch(books: list[str], path: Path = VERSIFICATION_PATH) -> dict:
    """Download chapter lengths for ``books`` (network). Writes the git-tracked reference file."""
    data = {}
    for book in books:
        url = SOURCE_URL.format(book=urllib.parse.quote(book))
        with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 — fixed https host
            payload = json.loads(resp.read().decode("utf-8"))
        entry = payload[0] if isinstance(payload, list) else payload
        if entry.get("title") != book:
            raise ValueError(f"Sefaria returned {entry.get('title')!r} for {book!r}")
        data[book] = [int(n) for n in entry["chapters"]]
    body = {
        "description": "Chapter lengths (verses per chapter) per Tanakh book.",
        "source": "Sefaria API /api/shape/<Book> (Miqra according to the Masorah versification)",
        "source_url_template": SOURCE_URL,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "books": data,
    }
    body["books_sha256"] = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return body


@lru_cache(maxsize=1)
def load(path: Path = VERSIFICATION_PATH) -> dict[str, list[int]]:
    body = json.loads(path.read_text(encoding="utf-8"))
    books = body["books"]
    if hashlib.sha256(json.dumps(books, sort_keys=True).encode()).hexdigest() != body["books_sha256"]:
        raise ValueError("Versification table digest mismatch — file was edited")
    return books


def verse_refs(book: str) -> list[tuple[int, int]]:
    """Ordered (chapter, verse) pairs for every verse of ``book``."""
    return [(c, v) for c, n in enumerate(load()[book], start=1) for v in range(1, n + 1)]


def aramaic_status(book: str, chapter: int, verse: int) -> str | None:
    """'aramaic' for fully Aramaic verses, 'aramaic_partial' for mixed verses, else None."""
    for lo, hi in ARAMAIC_FULL.get(book, []):
        if lo <= (chapter, verse) <= hi:
            return "aramaic"
    if (chapter, verse) in ARAMAIC_PARTIAL.get(book, []):
        return "aramaic_partial"
    return None
