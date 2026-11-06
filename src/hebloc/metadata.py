"""Source metadata parsed from file paths/names, one parser per corpus.

Every parser receives the path *relative to its corpus folder* (POSIX separators) and returns a
dict with the generic catalog fields below (missing ones are None). Corpus-specific extras go into
the same dict and end up in the catalog's ``meta_json`` column. A parser never guesses: if a name
does not match the expected pattern, it fills what it safely can and sets ``meta_issue``.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

GENERIC_FIELDS = (
    "subcorpus",    # Modern: blogs/news/...; Medieval: Rambam/Musar/Thought; Hazal: Mishnah/Tosefta/Midrash
    "source",       # Modern: haaretz/a7/... , medical site, Knesset number
    "section",      # Mikra: Torah/Prophets/Writings; Hazal: Seder / Aggadah / Halakhah; Rambam: sefer
    "work",         # book / tractate / midrash / treatise / Haskala title / Rambam hilchot
    "base_work",    # for commentaries: the work commented on
    "commentary",   # commentary name, if the file is a commentary
    "era_label",    # era label present in the source naming (e.g. "Rishonim", "Modern")
    "author",       # Haskala
    "year",         # Haskala publication year (int)
    "genre",        # Haskala genre
    "ext_id",       # external id (Haskala Ytext id, Rambam file sequence, Modern file stem)
    "date",         # ISO date if the path encodes one (TheMarker folders)
    "meta_issue",   # non-empty string if the name did not fully match the expected pattern
)

MIKRA_SECTIONS = {"Torah", "Prophets", "Writings"}


def _empty() -> dict:
    return {k: None for k in GENERIC_FIELDS}


def parse_mikra(rel: str) -> dict:
    m = _empty()
    stem = PurePosixPath(rel).stem
    parts = stem.split(" - ")
    if len(parts) == 3 and parts[0] == "Tanakh" and parts[1] in MIKRA_SECTIONS:
        m.update(section=parts[1], work=parts[2])
    else:
        m.update(work=stem, meta_issue="unexpected Mikra file name")
    return m


def parse_hazal(rel: str) -> dict:
    m = _empty()
    stem = PurePosixPath(rel).stem
    parts = stem.split(" - ")
    head = parts[0]
    m["subcorpus"] = head
    if head in ("Mishnah", "Tosefta") and len(parts) == 3 and parts[1].startswith("Seder "):
        m.update(section=parts[1], work=parts[2])
        m["tractate"] = parts[2].removeprefix(head + " ").strip()
    elif head == "Midrash":
        rest = parts[1:]
        if rest and rest[0] in ("Aggadah", "Aggadic Midrash", "Halakhah"):
            m["section"] = "Halakhah" if rest[0] == "Halakhah" else "Aggadah"
            m["section_label_raw"] = rest[0]
            rest = rest[1:]
        if "Commentary" in rest:
            i = rest.index("Commentary")
            m["series"] = " - ".join(rest[:i]) or None
            m["commentary"] = rest[i + 1] if i + 1 < len(rest) else None
            last = rest[-1]
            m["work"] = last
            if " on " in last:
                m["base_work"] = last.split(" on ", 1)[1]
            else:
                m["meta_issue"] = "commentary without 'X on Y' title"
        elif rest:
            m["work"] = rest[-1]
            if len(rest) > 1:
                m["series"] = " - ".join(rest[:-1])
        else:
            m["meta_issue"] = "unexpected Midrash file name"
    else:
        m.update(work=stem, meta_issue="unexpected Hazal file name")
    return m


RE_RAMBAM_FILE = re.compile(r"^(?P<seq>\d{6})td(?P<code>\d+?)(?P<label>[a-z_]+)$")


def parse_medieval(rel: str) -> dict:
    m = _empty()
    p = PurePosixPath(rel)
    top = p.parts[0]
    m["subcorpus"] = top
    if top == "Rambam":
        m["work"] = "Mishneh Torah"
        if len(p.parts) == 4:
            m["section"] = p.parts[1]          # sefer (transliterated, e.g. AHAVA)
            m["hilchot"] = p.parts[2]          # hilchot (transliterated, e.g. brkowt)
            mm = RE_RAMBAM_FILE.match(p.stem)
            if mm:
                m["ext_id"] = mm["seq"]
                m["rambam_code"] = mm["code"]
                m["unit_label"] = mm["label"]  # prk_a (chapter a), hkdmh (introduction), ...
            else:
                m["meta_issue"] = "unexpected Rambam file name"
        else:
            m["meta_issue"] = "unexpected Rambam path depth"
    elif top in ("Musar", "Thought"):
        parts = p.stem.split(" - ")
        prefix = "Musar" if top == "Musar" else "Jewish Thought"
        if parts[0] != prefix:
            m.update(work=p.stem, meta_issue=f"expected '{prefix} - ' prefix")
            return m
        rest = parts[1:]
        if rest and rest[0] in ("Rishonim", "Modern"):
            m["era_label"] = rest[0]
            rest = rest[1:]
        if "Commentary" in rest:
            i = rest.index("Commentary")
            m["base_work"] = " - ".join(rest[:i])
            m["commentary"] = rest[i + 1] if i + 1 < len(rest) else None
            m["work"] = m["commentary"]
        else:
            m["work"] = " - ".join(rest)
            if len(rest) == 2:  # e.g. "Duties of the Heart - Duties of the Heart"
                m["base_work"] = rest[0]
        if not m["work"]:
            m["meta_issue"] = "no work title"
    else:
        m.update(work=p.stem, meta_issue="unexpected Medieval subfolder")
    return m


RE_HASKALA_YEAR = re.compile(r"^שנת (\d{4})$")
RE_YTEXT = re.compile(r"^Ytext\d+$")


def parse_haskala(rel: str) -> dict:
    m = _empty()
    stem = PurePosixPath(rel).stem
    parts = stem.split("--")
    if len(parts) != 5:
        m.update(work=stem, meta_issue=f"expected 5 '--' fields, got {len(parts)}")
        return m
    author, title, year_s, genre, ytext = parts
    m.update(author=author.strip(), work=title.strip(), genre=genre.strip(), ext_id=ytext.strip())
    m["text_only_edition"] = "(טקסט בלבד)" in title
    issues = []
    ym = RE_HASKALA_YEAR.match(year_s.strip())
    if ym:
        m["year"] = int(ym.group(1))
    else:
        issues.append(f"unparsed year field {year_s!r}")
    if not RE_YTEXT.match(m["ext_id"]):
        issues.append(f"unexpected id {ytext!r}")
    if issues:
        m["meta_issue"] = "; ".join(issues)
    return m


RE_DATE8 = re.compile(r"^(\d{4})(\d{2})(\d{2})$")


def parse_modern(rel: str) -> dict:
    m = _empty()
    p = PurePosixPath(rel)
    parts = p.parts
    top = parts[0]
    m["subcorpus"] = top
    m["ext_id"] = p.stem
    dirs = parts[1:-1]
    if top in ("news", "medical"):
        if dirs:
            m["source"] = dirs[0]
            if len(dirs) > 1:
                m["section"] = "/".join(dirs[1:])
        else:
            m["meta_issue"] = f"{top} file without source folder"
        if m["source"] == "themarker" and len(dirs) > 1:
            dm = RE_DATE8.match(dirs[1])
            if dm:
                m["date"] = f"{dm[1]}-{dm[2]}-{dm[3]}"
    elif top == "kneset":
        if dirs:
            m["source"] = f"knesset_{dirs[0]}"
        else:
            m["meta_issue"] = "kneset file without Knesset-number folder"
    elif top == "literary":
        m["source"] = {"O": "original", "T": "translated"}.get(p.stem)
        if m["source"] is None:
            m["meta_issue"] = "unexpected literary file name"
    elif top in ("blogs", "tapuz"):
        if dirs:
            m["section"] = "/".join(dirs)
    else:
        m["meta_issue"] = "unexpected Modern subfolder"
    return m


PARSERS = {
    "mikra": parse_mikra,
    "hazal": parse_hazal,
    "medieval": parse_medieval,
    "haskala": parse_haskala,
    "modern": parse_modern,
}


def parse_metadata(corpus_id: str, rel_in_corpus: str) -> dict:
    return PARSERS[corpus_id](rel_in_corpus)
