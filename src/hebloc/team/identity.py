"""Who this computer belongs to (Ori, Efrat or Adi), remembered locally in ``data/team/identity.json``.

Set once at the start of setup (``hebloc whoami --set efrat``). Afterwards every team command
(``doctor``, ``agreement``, ``work``, ``parse``) uses it when ``--as`` is omitted, and REFUSES an
``--as`` that names somebody else, so a later session on the same computer cannot silently parse
another person's workload. Changing it needs ``--change`` (e.g. the wrong name was chosen).
"""

from __future__ import annotations

from datetime import datetime, timezone

from hebloc.paths import DATA_DIR
from hebloc.store.io import atomic_write_json, read_json

IDENTITY_PATH = DATA_DIR / "team" / "identity.json"


class IdentityError(RuntimeError):
    pass


def _people() -> tuple[str, ...]:
    from hebloc.team import plan as P

    return P.load().people


def normalize(name: str) -> str:
    n = (name or "").strip().lower()
    people = _people()
    if n not in people:
        raise IdentityError(f"{name!r} is not a team member; expected one of {', '.join(p.capitalize() for p in people)}")
    return n


def get() -> str | None:
    return read_json(IDENTITY_PATH).get("person") if IDENTITY_PATH.exists() else None


def set_identity(name: str, *, change: bool = False) -> dict:
    n = normalize(name)
    cur = read_json(IDENTITY_PATH) if IDENTITY_PATH.exists() else {}
    if cur.get("person") and cur["person"] != n and not change:
        raise IdentityError(f"this computer is already set up for {cur['person'].capitalize()}; "
                            f"to change it deliberately: uv run hebloc whoami --set {n} --change")
    history = cur.get("history", [])
    if cur.get("person") != n:
        history.append({"person": n, "set_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    rec = {"person": n, "history": history}
    atomic_write_json(rec, IDENTITY_PATH)
    return rec


def resolve(given: str | None) -> str:
    """The person to act as: ``--as`` if given (must agree with the stored identity), else the stored one."""
    stored = get()
    if given:
        n = normalize(given)
        if stored and stored != n:
            raise IdentityError(f"this computer is set up for {stored.capitalize()}, not {n.capitalize()} "
                                f"(data/team/identity.json). Each person runs only their own work")
        return n
    if stored:
        return stored
    raise IdentityError("who are you? Run: uv run hebloc whoami --set <ori|efrat|adi>")
