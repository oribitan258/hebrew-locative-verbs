"""Unvocalized paradigm forms of a (root, template), for the identification fallback (S56-v1 §5.2).

Dicta leaves many Biblical-Hebrew verb tokens without a lemma (``[BLANK]``: 14.7% of Mikra verbs) or with
another verb's lemma; for about 40 lexicon entries Dicta has no lemma of their own in any corpus. The fallback
therefore matches the token's ``host`` (the word without proclitics, object suffix included) against forms
generated from the root and the template — linguistic knowledge, never BHSA.

Generation deliberately OVER-generates (all persons, both spellings, weak-root variants, object suffixes); the
caller keeps only forms that are attested as VERB hosts in the corpora AND not owned by another verb
(``hebloc.loc.lexicon.build_forms``). So a wrong candidate costs nothing unless it is a real word that Dicta
does not attribute to another verb — the residual error is measured against BHSA on Mikra (Phase C).
"""

from __future__ import annotations

from itertools import product

#: morph-v2 (2026-11-20 correction): weak-letter deletions only in the forms where Hebrew makes them; no ן suffix
MORPH_VERSION = "morph-v2"

FINAL = {"כ": "ך", "מ": "ם", "נ": "ן", "פ": "ף", "צ": "ץ"}
NONFINAL = {v: k for k, v in FINAL.items()}

PERF_END = ("", "ה", "ת", "תה", "תי", "נו", "תם", "תן", "ו")
IMPF_PRE = ("י", "ת", "א", "נ")
IMPF_END = ("", "ו", "י", "נה", "ון")
#: morph-v2: the prefix/ending pairs that exist (י-…-י or א-…-ו do not): 3ms/3mp, 2ms/3fs/2fs/2mp/3fp-2fp, 1s, 1p
IMPF_PAIRS = (("י", ""), ("י", "ו"), ("י", "ון"), ("ת", ""), ("ת", "ו"), ("ת", "י"), ("ת", "נה"), ("ת", "ון"),
              ("א", ""), ("נ", ""))
PART_END = ("", "ת", "ה", "ים", "ות")
OBJ = ("", "ו", "ה", "ם", "נו", "ני", "ך", "הו", "הם", "מו", "כם", "הן", "יו", "יה", "נה")   # morph-v2: no rare ן
#: perfect endings that start with a consonant: the only place a final nun assimilates (נָתַתִּי)
III_NUN_PERF_END = ("ת", "תה", "תי", "תם", "תן", "נו")
SIBILANT_HITP = {"ס": "הסת", "ש": "השת", "צ": "הצט", "ז": "הזד"}


def nonfinal(s: str) -> str:
    return "".join(NONFINAL.get(c, c) for c in s)


def finalize(s: str) -> str:
    s = nonfinal(s)
    return s[:-1] + FINAL.get(s[-1], s[-1]) if s else s


def _root_variants(root: str) -> list[tuple[tuple[str, ...], frozenset[str]]]:
    """Letter slots of the root with weak-root alternatives, each tagged with the deletions it makes.

    Tags: ``I_drop`` (I-nun / I-yod letter deleted), ``I_waw`` (I-yod written ו), ``III_nun`` (final nun
    assimilated), ``gem`` (geminate), ``II_weak`` (hollow letter not written), ``II_swap`` (hollow ו/י
    alternation), ``III_he``. :func:`forms` allows each tag only in the
    forms where Hebrew makes that change (morph-v2)."""
    r = nonfinal(root)
    if len(r) != 3:
        return [(tuple(r), frozenset())]
    a, b, c = r
    A = [(a, None)] + ([("", "I_drop")] if a in "ני" else []) + ([("ו", "I_waw")] if a == "י" else [])
    B = [(b, None)] + ([("", "II_weak"), ("ו" if b == "י" else "י", "II_swap")] if b in "וי" else [])
    C = [(c, None)]
    if b == c:
        C.append(("", "gem"))
    elif c == "נ":
        C.append(("", "III_nun"))
    if c == "ה":
        C += [(x, "III_he") for x in ("", "ת", "י", "ית", "ו")]
    out = []
    for (x, tx), (y, ty), (z, tz) in product(A, B, C):
        # keep only variants that retain at least 2 of the root's own letters (doubly weak roots otherwise
        # degenerate to one consonant and generate junk)
        if sum(u == v for u, v in zip((x, y, z), (a, b, c))) >= 2:
            out.append(((x, y, z), frozenset(t for t in (tx, ty, tz) if t)))
    return out


def _allowed(template: str, kind: str, tags: frozenset[str]) -> bool:
    """Where a weak-letter change may occur (morph-v2)."""
    if "I_drop" in tags:
        # I-nun / I-yod deletion: Simple imperfect, imperative, infinitive and nif'al; every causative form; never Intensive
        if template == "Intensive" or (template == "Simple" and kind in ("perf", "part")):
            return False
    if "I_waw" in tags:
        # I-yod written with waw: causative (הוציא) and nif'al (נולד) only
        if not (template == "Causative" or kind.endswith("_n")):
            return False
    if "II_swap" in tags and template != "Causative":
        return False   # hollow ו/י alternate only in the causative (הֵקִים from קום, הֵשִׂים); qal keeps the root letter
    if "III_nun" in tags and kind != "perf":
        return False   # final nun assimilates only before a consonant-initial perfect ending (handled in forms)
    return True


def _simple(a: str, b: str, c: str) -> dict[str, set[str]]:
    bc, abc = b + c, a + b + c
    return {
        "perf": {abc},
        "impf": {abc, a + b + "ו" + c, "י" + abc},
        "imp": {abc, a + b + "ו" + c},
        # infinitive in -ת only for I-nun / I-yod roots (גשת, רשת); נתן: תת
        "inf": {a + b + "ו" + c, abc} | ({bc + "ת"} if a in ("", "ו") else set()) | ({b + "ת"} if (a, c) == ("", "נ") else set()),
        "part": {a + "ו" + bc, abc, a + b + "ו" + c},
        # nif'al
        "perf_n": {"נ" + abc},
        "inf_n": {"ה" + abc, "הי" + abc, "לה" + abc, "להי" + abc},
        "part_n": {"נ" + abc},
    }


def _intensive(a: str, b: str, c: str, d: str = "") -> dict[str, set[str]]:
    core = a + b + c + d
    hitp = SIBILANT_HITP.get(a, "הת")
    hitp_core = (b + c + d) if a in SIBILANT_HITP else core
    return {
        "perf": {a + "י" + b + c + d, core, a + "ו" + b + c + d},
        "impf": {core, a + "ו" + b + c + d, (hitp[1:] if a not in SIBILANT_HITP else hitp[1:]) + hitp_core},
        "imp": {core, hitp + hitp_core},
        "inf": {core, hitp + hitp_core},
        "part": {"מ" + core, "מ" + a + "ו" + b + c + d, "מ" + hitp[1:] + hitp_core},
        "perf_n": {hitp + hitp_core},
    }


def _causative(a: str, b: str, c: str) -> dict[str, set[str]]:
    return {
        "perf": {"ה" + a + b + "י" + c, "ה" + a + b + c, "הו" + a + b + c},
        "impf": {a + b + "י" + c, a + b + c, "ו" + a + b + c},
        "imp": {"ה" + a + b + c, "ה" + a + b + "י" + c},
        "inf": {"ה" + a + b + "י" + c, "ה" + a + b + c},
        "part": {"מ" + a + b + "י" + c, "מו" + a + b + c, "מ" + a + b + c},
    }


def forms(root: str, template: str, exclude_kinds: tuple[str, ...] = ()) -> set[str]:
    """All candidate host strings (final letters normalized) of ``root`` in ``template`` (minus ``exclude_kinds``)."""
    out: set[str] = set()
    variants = _root_variants(root)
    for slots, tags in variants:
        if template == "Simple":
            g = _simple(*slots) if len(slots) == 3 else {}
        elif template == "Intensive":
            g = _intensive(*slots) if len(slots) in (3, 4) else {}
        elif template == "Causative":
            g = _causative(*slots) if len(slots) == 3 else {}
        else:
            raise ValueError(f"unknown template {template!r}")
        for kind, bases in g.items():
            if kind in exclude_kinds or not _allowed(template, kind, tags):
                continue
            for base in bases:
                if len(base) < 2:
                    continue
                passive_kind = kind.endswith("_n")       # nif'al / hitpa'el-type forms take no object suffix
                if kind.startswith("perf"):
                    stems = {base + e for e in (III_NUN_PERF_END if "III_nun" in tags else PERF_END)}
                elif kind == "impf":
                    stems = {p + base + e for p, e in IMPF_PAIRS}
                elif kind.startswith("part"):
                    stems = {base + e for e in PART_END}
                    out.update(stems)
                    continue
                else:   # imp / inf
                    stems = {base, base + "ו", base + "י"} | ({"ל" + base} if kind.startswith("inf") else set())
                out.update(s + o for s in stems for o in (("",) if passive_kind else OBJ))
    return {finalize(f) for f in out if len(f) >= 2}
