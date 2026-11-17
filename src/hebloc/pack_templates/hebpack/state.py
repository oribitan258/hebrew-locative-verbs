"""Remembers which one-time checks passed (analyses/_status.json), so `start` runs them only once."""

from __future__ import annotations

import json
from datetime import datetime

from hebpack import ANALYSES

STATUS = ANALYSES / "_status.json"


def load() -> dict:
    try:
        return json.loads(STATUS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def record(key: str, ok: bool, detail: str = "") -> None:
    s = load()
    s[key] = {"ok": bool(ok), "when": datetime.now().isoformat(timespec="seconds"), "detail": detail}
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
