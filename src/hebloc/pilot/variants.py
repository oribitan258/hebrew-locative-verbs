"""Alternative normalizations for testing the D-018 hypotheses — WITHOUT changing the defaults.

The variants are built from ``hebloc.normalize``'s own regexes and reading function; with every
option at its default, ``mikra_text`` reproduces ``units.text_norm`` (and the Ketiv
``text_norm_alt``) exactly — this is asserted for all 23,206 verses by ``check_mikra_defaults``.

* ``qere``          True (default, Qere)  | False (Ketiv)
* ``strip_points``  True (default)        | False (keep niqqud and cantillation)
* ``maqaf``         "space" (default)     | "keep" (the edition's "-" stays attached)
* ``sof_pasuq``     "period" (default)    | "drop"
"""

from __future__ import annotations

import contextlib
import re

from hebloc import normalize as N


def mikra_text(raw: str, *, qere: bool = True, strip_points: bool = True, maqaf: str = "space",
               sof_pasuq: str = "period") -> str:
    s = N._mikra_reading(raw, qere=qere)
    s = N.RE_PARASHA.sub(" ", s)
    s = N.RE_MIKRA_ACCENT_QUOTES.sub("", s)
    s = s.replace("׀", " ")
    if maqaf == "space":
        s = s.replace("-", " ").replace("־", " ")
    elif maqaf != "keep":
        raise ValueError(maqaf)
    if sof_pasuq == "period":
        s = s.replace("׃", " .")
    elif sof_pasuq == "drop":
        s = s.replace("׃", " ")
    else:
        raise ValueError(sof_pasuq)
    with points_kept(not strip_points):
        return N._common(s, [])


@contextlib.contextmanager
def points_kept(active: bool = True):
    """Temporarily make the normalizer keep niqqud/cantillation (process-local; restored after)."""
    if not active:
        yield
        return
    saved = N.RE_POINTS
    N.RE_POINTS = re.compile(r"(?!)")  # matches nothing
    try:
        yield
    finally:
        N.RE_POINTS = saved


def strip_points(text: str) -> str:
    return N.RE_SPACES.sub(" ", N.RE_POINTS.sub("", text)).strip()


def check_mikra_defaults(rows: list[tuple[str, str, str | None]]) -> dict:
    """rows: (text_raw, text_norm, text_norm_alt). Counts where the default variant ≠ stored text."""
    bad_q = sum(1 for raw, norm, _ in rows if mikra_text(raw) != norm)
    bad_k = sum(1 for raw, _, alt in rows if alt is not None and mikra_text(raw, qere=False) != alt)
    return {"verses": len(rows), "qere_default_mismatches": bad_q, "ketiv_alt_mismatches": bad_k}
