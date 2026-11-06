"""Stratum and period-status tagging from ``config/curation.yaml`` (decision D-003).

Tagging is metadata only: it never removes a document. See the YAML header for semantics.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from hebloc.paths import CONFIG_DIR

CURATION_PATH = CONFIG_DIR / "curation.yaml"
PERIOD_STATUSES = ("in_period", "out_of_period", "needs_review")


@dataclass(frozen=True)
class Rule:
    id: str
    corpus: str
    pattern: re.Pattern
    stratum: str
    period_status: str
    note: str | None


@dataclass(frozen=True)
class Curation:
    rules: tuple[Rule, ...]
    haskala_cutoff_year: int
    version_hash: str  # sha256 of the YAML file — recorded in the catalog for provenance

    def classify(self, corpus_id: str, rel_in_corpus: str) -> Rule:
        for rule in self.rules:
            if rule.corpus == corpus_id and rule.pattern.search(rel_in_corpus):
                return rule
        raise LookupError(f"No curation rule for {corpus_id}:{rel_in_corpus} (missing catch-all?)")


def load_curation(path: Path = CURATION_PATH) -> Curation:
    raw_bytes = path.read_bytes()
    raw = yaml.safe_load(raw_bytes.decode("utf-8"))
    rules = []
    seen = set()
    for r in raw["rules"]:
        if r["id"] in seen:
            raise ValueError(f"duplicate rule id {r['id']}")
        seen.add(r["id"])
        if r["period_status"] not in PERIOD_STATUSES:
            raise ValueError(f"rule {r['id']}: bad period_status {r['period_status']!r}")
        rules.append(
            Rule(r["id"], r["corpus"], re.compile(r["path_regex"]), r["stratum"], r["period_status"], r.get("note"))
        )
    return Curation(tuple(rules), int(raw["haskala_cutoff_year"]), hashlib.sha256(raw_bytes).hexdigest()[:16])
