"""The S56-v1 verb lexicon: load, validate, check against the paper and against Dicta's inventory, and
generate the fallback forms (``config/locative_verb_forms.yaml``).

Only Ori edits ``config/locative_verbs.yaml``; ``hebloc loc lexicon forms`` regenerates the forms file from it
and from the five verb inventories (``hebloc loc lexicon inventory``). ``lexicon_sha256`` covers both files.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from hebloc.paths import CONFIG_DIR

LEXICON_PATH = CONFIG_DIR / "locative_verbs.yaml"
FORMS_PATH = CONFIG_DIR / "locative_verb_forms.yaml"

TEMPLATES = ("Simple", "Intensive", "Causative")
TEMPLATE_CODE = {"Simple": "S", "Intensive": "I", "Causative": "C"}
CLASSES = ("A", "A/B", "B")
STATUSES = ("core", "paper_other", "mh_supplement")
PUTTING_REMOVAL = ("PUTTING", "REMOVAL", "BOTH", "UNKNOWN")
VOICES = ("active", "passive", "middle")
FLAGS = ("template_ambiguous", "homograph", "homograph_nonlexicon", "paper_conflict", "mh_meaning_shift",
         "no_own_lemma", "odd_lemma_string", "template_mismatch_variant", "change_of_state_use")
MH_PREDICTIONS = ("preserved_alternation", "lost_frame_A_survives", "mh_alternates", "mh_new_alternator",
                  "mh_manner_locative")
#: Listed counts of the core class lists (what the paper's lists actually contain; D-057).
EXPECTED_CORE = {("Causative", "A"): 38, ("Causative", "A/B"): 7, ("Causative", "B"): 3,
                 ("Intensive", "A"): 12, ("Intensive", "A/B"): 7, ("Intensive", "B"): 15,
                 ("Simple", "A"): 46, ("Simple", "A/B"): 31, ("Simple", "B"): 19}
#: Fallback-form rule forms-v2 (D-057; correction of 2026-11-20). For a candidate host, the FOREIGN SHARE is the share of
#: all its VERB tokens (blank lemmas included) that carry an established, non-neutral lemma that is not a lemma of a
#: same-root lexicon entry. <= CLEAN: a clean form; <= DROP: an AMBIGUOUS form (kept, with ~partners); above: dropped.
FORMS_CLEAN_MAX_FOREIGN = 0.10
FORMS_DROP_ABOVE_FOREIGN = 0.50
FORMS_MAX_PARTNERS = 2
#: Hosts seen with the entry's own lemmas are candidates only with >= this many own-lemma tokens and an own
#: share of the host's lemmatized tokens >= FORMS_MIN_LEMMA_PURITY (Dicta sometimes mis-lemmatizes a rare word).
FORMS_MIN_LEMMA_TOKENS = 2
FORMS_MIN_LEMMA_PURITY = 0.8
#: ... and when the host is NOT a paradigm form of the root (any template), stronger support is required: >= this
#: many own-lemma tokens AND an own share of ALL its tokens (blanks included) >= this share (e.g. ימליכו: 4 השליך / 24).
FORMS_OFFPARADIGM_MIN_TOKENS = 5
FORMS_OFFPARADIGM_MIN_SHARE = 0.5
#: Only an ESTABLISHED lemma (a real competing verb) counts as foreign: >= this many VERB tokens over >= this many
#: distinct hosts. Rare odd strings (prefix glued on, inflected form, sub-word junk) are neutral, like [BLANK].
FORMS_ESTABLISHED_MIN_TOKENS = 50
FORMS_ESTABLISHED_MIN_HOSTS = 3
#: proclitics Dicta sometimes leaves glued to a copied lemma (lemma ושמת for host שמת)
PROCLITICS = ("ו", "ה", "ב", "כ", "ל", "מ", "ש")
FORMS_RULE_VERSION = "forms-v2"
#: Which entries get GENERATED (paradigm) forms. Decided by the pre-registered BHSA rule (D-057, 2026-11-20): full
#: generation failed it (F1 0.684 < 0.695 without generated forms), so the pre-registered FALLBACK applies: generated
#: forms only for entries with no Dicta lemma of their own, and every such form is marked ambiguous (``~form``).
#: "all" / "none" remain available for the measurement only (hebloc.loc.bhsa_eval).
FORMS_GENERATED_POLICY = "no_own_lemma"
GENERATED_PARTNER = "~form"
#: Phase C identification candidates (D-059 addendum, pre-registered; code D-065). They are OFF in R1 and are used only
#: to build candidate folders (hebloc.loc.ident), never the config files:
#: - I-2 ``lemma_partners``: a token matched by LEMMA ONLY on a host that is a morph-v2 form of ANOTHER template of the
#:   same root gets the partner ``~<root>.<T>`` (a combined key, never dropped);
#: - I-3 ``established_self_foreign`` (forms-v3): an established lemma that is Dicta's copy of the word itself is
#:   FOREIGN (the self-copy exemption applies only to non-established lemmas, which are neutral anyway);
#: - I-4 ``generated="clean_keys"``: V2 generated paradigm forms also for entries WITH a Dicta lemma of their own, kept
#:   only where the host is clean (no partner at all); entries without an own lemma keep R1's ``~form`` treatment.
FORMS_RULE_VERSION_I3 = "forms-v3"
GENERATED_POLICIES = ("all", "none", "no_own_lemma", "clean_keys")


class LexiconError(Exception):
    """The lexicon file is invalid (a STOP condition)."""


@dataclass
class Entry:
    id: str
    root: str
    template: str
    citation: str
    gloss: str
    klass: str | None
    status: str
    putting_removal: str
    dicta_lemmas: list[dict] = field(default_factory=list)
    shared_lemmas: list[dict] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    paper_refs: list[dict] = field(default_factory=list)
    nonlocative_idioms: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def own_lemmas(self) -> set[str]:
        return {d["lemma"] for d in self.dicta_lemmas}

    @property
    def shared(self) -> dict[str, str]:
        return {d["lemma"]: d["other"] for d in self.shared_lemmas}


@dataclass
class Lexicon:
    meta: dict
    entries: list[Entry]
    forms: dict[str, list[str]]          # entry id -> hosts (empty if the forms file is absent)
    sha256: str
    forms_meta: dict = field(default_factory=dict)
    ambiguous: dict[str, dict[str, list[str]]] = field(default_factory=dict)   # entry id -> host -> ~partners
    #: I-2 (Phase C candidates only; empty in R1): entry id -> host -> ~<root>.<T> partners of LEMMA-ONLY matches
    lemma_partners: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    def by_id(self) -> dict[str, Entry]:
        return {e.id: e for e in self.entries}


def _sha(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(p.name.encode() + b"\0")
        h.update(p.read_bytes() if p.exists() else b"<absent>")
    return h.hexdigest()


def load(path: Path = LEXICON_PATH, forms_path: Path = FORMS_PATH, *, validate: bool = True) -> Lexicon:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    entries = []
    for e in raw.get("entries") or []:
        entries.append(Entry(id=e.get("id"), root=e.get("root"), template=e.get("template"), citation=e.get("citation"),
                             gloss=e.get("gloss"), klass=e.get("class"), status=e.get("status"),
                             putting_removal=e.get("putting_removal"), dicta_lemmas=e.get("dicta_lemmas") or [],
                             shared_lemmas=e.get("shared_lemmas") or [], flags=e.get("flags") or [],
                             paper_refs=e.get("paper_refs") or [], nonlocative_idioms=e.get("nonlocative_idioms") or [],
                             raw=e))
    forms, fmeta, amb, lp = {}, {}, {}, {}
    if Path(forms_path).exists():
        fr = yaml.safe_load(Path(forms_path).read_text(encoding="utf-8")) or {}
        fmeta = fr.get("meta") or {}
        forms = {k: list(v or []) for k, v in (fr.get("forms") or {}).items()}
        amb = {k: {h: list(x) for h, x in (v or {}).items()} for k, v in (fr.get("ambiguous") or {}).items()}
        lp = {k: {h: list(x) for h, x in (v or {}).items()} for k, v in (fr.get("lemma_partners") or {}).items()}
    lex = Lexicon(raw.get("meta") or {}, entries, forms, _sha([Path(path), Path(forms_path)]), fmeta, amb, lp)
    if validate:
        probs = problems(lex)
        if probs:
            raise LexiconError("invalid lexicon:\n  " + "\n  ".join(probs[:40]))
    return lex


# ---------------------------------------------------------------------------------------------- validation
def problems(lex: Lexicon) -> list[str]:
    """Schema and consistency problems (empty = valid). Config only: no corpus data needed."""
    out = []
    ids = Counter(e.id for e in lex.entries)
    out += [f"duplicate id {i}" for i, n in ids.items() if n > 1]
    keys = Counter((e.root, e.template, e.raw.get("homograph")) for e in lex.entries)
    out += [f"duplicate (root, template, homograph) {k}" for k, n in keys.items() if n > 1]
    for e in lex.entries:
        w = f"{e.id}:"
        if not e.id or not e.root or not e.citation or not e.gloss:
            out.append(f"{w} id/root/citation/gloss required")
        if e.template not in TEMPLATES:
            out.append(f"{w} template {e.template!r}")
        elif e.id and not e.id.startswith(f"{e.root}.{TEMPLATE_CODE[e.template]}"):
            out.append(f"{w} id must be <root>.<{TEMPLATE_CODE[e.template]}>[.<homograph>]")
        if e.status not in STATUSES:
            out.append(f"{w} status {e.status!r}")
        if e.status == "core" and e.klass not in CLASSES:
            out.append(f"{w} core entry needs a class in {CLASSES}")
        if e.klass is not None and e.klass not in CLASSES:
            out.append(f"{w} class {e.klass!r}")
        if e.putting_removal not in PUTTING_REMOVAL:
            out.append(f"{w} putting_removal {e.putting_removal!r}")
        for d in e.dicta_lemmas:
            if not d.get("lemma") or d.get("voice") not in VOICES:
                out.append(f"{w} bad dicta_lemma {d}")
        for d in e.shared_lemmas:
            if not d.get("lemma") or not d.get("other"):
                out.append(f"{w} bad shared_lemma {d}")
        out += [f"{w} unknown flag {f}" for f in e.flags if f not in FLAGS]
        mh = e.raw.get("mh")
        if mh and mh.get("prediction") not in MH_PREDICTIONS:
            out.append(f"{w} mh prediction {mh.get('prediction')!r}")
        if e.raw.get("bh_counterpart") and e.raw["bh_counterpart"] not in ids:
            out.append(f"{w} bh_counterpart {e.raw['bh_counterpart']} is not an entry")
        if not e.dicta_lemmas and not e.shared_lemmas and "no_own_lemma" not in e.flags:
            out.append(f"{w} no dicta_lemmas: flag no_own_lemma")
        for r in e.paper_refs:
            if "frame" in r and r["frame"] not in ("A", "B"):
                out.append(f"{w} paper_ref frame {r['frame']!r}")
    # every lemma shared by two entries must be flagged on all of them (ambiguity rule)
    owners = defaultdict(set)
    for e in lex.entries:
        for lem in e.own_lemmas:
            owners[lem].add(e.id)
    by = lex.by_id()
    for lem, ents in owners.items():
        if len(ents) > 1:
            for i in ents:
                if not {"template_ambiguous", "homograph"} & set(by[i].flags):
                    out.append(f"{i}: lemma {lem} is shared with {sorted(ents - {i})}: flag template_ambiguous or homograph")
    return out


def counts(lex: Lexicon) -> dict:
    """Listed counts of core entries per template x class, against the paper's stated and listed numbers."""
    c = Counter((e.template, e.klass) for e in lex.entries if e.status == "core")
    rows = []
    for (t, k), expected in EXPECTED_CORE.items():
        stated = (lex.meta.get("stated_by_template") or {}).get(t, {}).get(k)
        rows.append({"template": t, "class": k, "in_lexicon": c.get((t, k), 0), "listed_in_paper": expected,
                     "stated_in_paper": stated})
    totals = Counter(e.klass for e in lex.entries if e.status == "core")
    return {"by_template": rows, "totals": dict(totals), "stated_totals": lex.meta.get("stated_counts"),
            "supplements": dict(Counter(e.status for e in lex.entries if e.status != "core")),
            "n_entries": len(lex.entries)}


def count_problems(lex: Lexicon) -> list[str]:
    return [f"{r['template']} {r['class']}: {r['in_lexicon']} entries, the paper lists {r['listed_in_paper']}"
            for r in counts(lex)["by_template"] if r["in_lexicon"] != r["listed_in_paper"]]


# ---------------------------------------------------------------------------------------------- forms
#: a lemma equal to the word itself is Dicta's COPY of the word (neutral) only if at least this share of the lemma's
#: tokens sit on that same word; a real lemma (שתה 'drink') is spread over many words (שתו, תשת, …)
FORMS_SELF_COPY_MIN_SHARE = 0.7


def neutral_lemma(lem: str, host: str, established: set[str], self_share: float = 1.0) -> bool:
    """A lemma that is no evidence for ANOTHER verb on this host (forms-v2): blank, a ##-fragment, a rare string, or
    Dicta's copy of the word itself (with or without a proclitic) that it uses (almost) only on this word."""
    if lem == "[BLANK]" or lem.startswith("##") or lem not in established:
        return True
    return (lem == host or any(lem == p + host for p in PROCLITICS)) and self_share >= FORMS_SELF_COPY_MIN_SHARE


#: an established lemma that is a paradigm string of the entry is Dicta's inflected COPY of this verb (neutral) only
#: when it LOOKS inflected: a glued proclitic or a person/number ending (שמתי, ושמת, וישם). A bare citation-shaped
#: string (שתה for שית) is another verb whose citation form happens to coincide with a form of this one.
INFLECTED_ENDINGS = ("תי", "תם", "תן", "נו", "ו", "ים", "ות", "ני")


def looks_inflected(lem: str, own_space: set[str] = frozenset()) -> bool:
    """A person/number ending, or a glued proclitic ו/ש whose remainder is itself a form of this verb (וישם)."""
    if lem.endswith(INFLECTED_ENDINGS):
        return True
    return lem[:1] in ("ו", "ש") and lem[1:] in own_space


def build_forms(lex: Lexicon, inventory, *, generated: str = FORMS_GENERATED_POLICY, established_self_foreign: bool = False,
                lemma_partners: bool = False) -> dict:
    """Fallback forms per entry from the pooled verb inventory (pyarrow table lemma, host, n, corpus); forms-v2.

    ``generated``: "all" (every entry), "none", or "no_own_lemma" (only entries without a Dicta lemma of their own;
    their generated forms are always AMBIGUOUS, partner ``~form``); "clean_keys" (Phase C candidate I-4).
    ``established_self_foreign`` (I-3) and ``lemma_partners`` (I-2) are the other Phase C candidates (off in R1).

    Candidates = generated paradigm forms (hebloc.loc.morph; per ``generated``) + hosts seen with the entry's
    own lemmas (stronger support when the host is outside the root's paradigm). Each attested candidate is then
    clean, AMBIGUOUS (kept with ~partners: the competing lemmas, or ``~<root>.S`` when a Causative/Intensive form is
    also a Simple form of the same root and the lexicon has no Simple entry for it), or dropped."""
    from hebloc.loc import morph

    by_host: dict[str, Counter] = defaultdict(Counter)
    for lem, host, n in zip(inventory["lemma"].to_pylist(), inventory["host"].to_pylist(), inventory["n"].to_pylist()):
        if host:
            by_host[host][lem] += n
    hosts_of_lemma: dict[str, set[str]] = defaultdict(set)
    lemma_total: Counter = Counter()
    for host, c in by_host.items():
        for lem, n in c.items():
            hosts_of_lemma[lem].add(host)
            lemma_total[lem] += n
    established = {lem for lem, n in lemma_total.items() if lem != "[BLANK]" and n >= FORMS_ESTABLISHED_MIN_TOKENS
                   and len(hosts_of_lemma[lem]) >= FORMS_ESTABLISHED_MIN_HOSTS}
    # a lemma of another lexicon entry WITH THE SAME ROOT (the other template / homograph) is not foreign: that
    # overlap is a genuine ambiguity and becomes a combined key (ambiguity rule); other entries' lemmas are foreign
    lexicon_lemma_roots: dict[str, set[str]] = defaultdict(set)
    for x in lex.entries:
        for lem in x.own_lemmas | set(x.shared):
            lexicon_lemma_roots[lem].add(x.root)
    root_templates = {(x.root, x.template) for x in lex.entries}
    paradigm: dict[tuple[str, str], set[str]] = {}

    def gen(root: str, template: str) -> set[str]:
        if (root, template) not in paradigm:
            try:
                paradigm[(root, template)] = morph.forms(root, template)
            except ValueError:
                paradigm[(root, template)] = set()
        return paradigm[(root, template)]

    other_cache: dict[tuple[str, str], set[str]] = {}

    def other_template_forms(root: str, template: str) -> set[str]:
        """I-2: the morph-v2 forms of ``root`` in ``template`` (Simple without the hollow nif'al infinitive shapes,
        as for the ~<root>.S partner below)."""
        if (root, template) not in other_cache:
            try:
                other_cache[(root, template)] = morph.forms(root, template, exclude_kinds=("inf_n",) if template == "Simple" else ())
            except ValueError:
                other_cache[(root, template)] = set()
        return other_cache[(root, template)]

    lemma_on_host: dict[tuple[str, str], int] = {}
    for host, c in by_host.items():
        for lem, n in c.items():
            lemma_on_host[(lem, host)] = n

    def self_share(lem: str, host: str) -> float:
        if established_self_foreign:
            return 0.0                           # I-3: an established self-copy is never neutral
        on = sum(lemma_on_host.get((lem, p + host), 0) for p in ("",) + PROCLITICS)
        return on / lemma_total[lem] if lemma_total[lem] else 0.0

    if generated not in GENERATED_POLICIES:
        raise ValueError(f"generated={generated!r}")
    out, amb, stats, blockers, dropped, lpart = {}, {}, {}, {}, [], {}
    for e in lex.entries:
        mine = e.own_lemmas | set(e.shared)
        own_gen = gen(e.root, e.template)
        any_gen = own_gen | gen(e.root, "Simple") | gen(e.root, "Intensive") | gen(e.root, "Causative")
        gen_here = generated in ("all", "clean_keys") or (generated == "no_own_lemma" and not e.own_lemmas)
        mark_generated = generated == "no_own_lemma" or (generated == "clean_keys" and not e.own_lemmas)
        clean_generated_only = generated == "clean_keys" and bool(e.own_lemmas)
        if lemma_partners:
            lpart_e = {}
            for h in sorted({h for lem in mine for h in hosts_of_lemma.get(lem, ())}):
                ps = sorted(f"~{e.root}.{TEMPLATE_CODE[t]}" for t in TEMPLATES if t != e.template and h in other_template_forms(e.root, t))
                if ps:
                    lpart_e[h] = ps
            if lpart_e:
                lpart[e.id] = lpart_e
        cands = {h for h in own_gen if h in by_host} if gen_here else set()
        attested_here: set[str] = set()
        for lem in e.own_lemmas:
            for h in hosts_of_lemma.get(lem, set()):
                c = by_host[h]
                own = sum(n for k, n in c.items() if k in e.own_lemmas)
                lemmatized = sum(n for k, n in c.items() if k != "[BLANK]")
                if own < FORMS_MIN_LEMMA_TOKENS or own / lemmatized < FORMS_MIN_LEMMA_PURITY:
                    continue
                if h not in any_gen and (own < FORMS_OFFPARADIGM_MIN_TOKENS
                                         or own / sum(c.values()) < FORMS_OFFPARADIGM_MIN_SHARE):
                    continue
                cands.add(h)
                attested_here.add(h)
        simple_partner = e.template in ("Causative", "Intensive") and (e.root, "Simple") not in root_templates
        # the Simple shapes a derived form can be confused with (the hollow nif'al infinitive הִקּוֹם-type shapes are left
        # out: they would mark every ה-initial causative form)
        simple_forms = morph.forms(e.root, "Simple", exclude_kinds=("inf_n",)) if simple_partner else set()
        own_space = own_gen | {h for lem in e.own_lemmas for h in hosts_of_lemma.get(lem, ())}
        entry_partners = [f"~{x}" for x in (e.raw.get("form_partners") or [])]   # sense screen (D-057)
        kept, ambig, blocked, n_drop = [], {}, Counter(), 0
        for h in sorted(cands):
            c = by_host[h]
            total = sum(c.values())
            foreign, simple_ev = {}, 0
            for lem, n in c.items():
                if lem in mine or e.root in lexicon_lemma_roots.get(lem, ()) or neutral_lemma(lem, h, established, self_share(lem, h)):
                    continue
                if simple_partner and lem in simple_forms:
                    simple_ev += n                       # the same root's Simple verb: a genuine ambiguity, never a drop
                elif lem in own_space and looks_inflected(lem, own_space):
                    continue                             # Dicta's inflected copy of this verb
                else:
                    foreign[lem] = n
            share = sum(foreign.values()) / total if total else 1.0
            top = [k for k, _ in sorted(foreign.items(), key=lambda x: (-x[1], x[0]))]
            if share > FORMS_DROP_ABOVE_FOREIGN:
                if clean_generated_only and h not in attested_here:
                    continue                             # I-4: never a candidate of R1, so not an R1 drop either
                blocked.update(foreign)
                n_drop += 1
                dropped.append({"entry": e.id, "host": h, "tokens": total, "foreign_share": round(share, 3),
                                "foreign": "; ".join(f"{k}:{foreign[k]}" for k in top[:3])})
                continue
            partners = ["~" + k for k in top[:FORMS_MAX_PARTNERS]] if share > FORMS_CLEAN_MAX_FOREIGN else []
            if simple_partner and (h in simple_forms or simple_ev / total > FORMS_CLEAN_MAX_FOREIGN):
                partners.append(f"~{e.root}.S")
            partners += entry_partners
            if clean_generated_only and h not in attested_here and partners:
                continue                                 # I-4: a generated form is added only where it is clean
            if mark_generated and h not in attested_here:
                partners.append(GENERATED_PARTNER)
            kept.append(h)
            if partners:
                ambig[h] = sorted(set(partners))
        out[e.id] = kept
        if ambig:
            amb[e.id] = ambig
        stats[e.id] = {"candidates_attested": len(cands), "kept": len(kept), "ambiguous": len(ambig), "dropped": n_drop}
        blockers[e.id] = blocked.most_common(5)
    return {"forms": out, "ambiguous": amb, "stats": stats, "blockers": blockers, "dropped": dropped, "lemma_partners": lpart}


def write_forms(lex: Lexicon, inventory, path: Path = FORMS_PATH, inventory_info: dict | None = None, *,
                generated: str = FORMS_GENERATED_POLICY, established_self_foreign: bool = False,
                lemma_partners: bool = False, lexicon_path: Path | None = None, candidates: list[str] | None = None) -> dict:
    """Write a forms file. With the defaults it is the R1 file (byte-identical rule text); the Phase C options
    (``generated="clean_keys"``, ``established_self_foreign``, ``lemma_partners``) are written only into candidate
    folders (hebloc.loc.ident) and recorded in ``meta.candidates``."""
    from hebloc.loc import morph
    from hebloc.store.io import atomic_write_text

    r = build_forms(lex, inventory, generated=generated, established_self_foreign=established_self_foreign,
                    lemma_partners=lemma_partners)
    if lexicon_path is not None:
        lex_sha = hashlib.sha256(Path(lexicon_path).read_bytes()).hexdigest()
    else:
        lex_sha = hashlib.sha256(LEXICON_PATH.read_bytes()).hexdigest() if path == FORMS_PATH else None
    header = ("# GENERATED by `hebloc loc lexicon forms` from config/locative_verbs.yaml and the five verb\n"
              "# inventories (data/loc/inventory). Do not edit by hand (D-057). Rule: meta.rule.\n")
    st = r["stats"]
    doc = {"meta": {"rule_version": FORMS_RULE_VERSION, "morph_version": morph.MORPH_VERSION, "generated_forms": generated,
                    "generated_policy_decision": "pre-registered BHSA rule, 2026-11-20 (data/loc/review/quality/bhsa/decision.json; D-057)",
                    "established_lemma": f">= {FORMS_ESTABLISHED_MIN_TOKENS} VERB tokens over >= {FORMS_ESTABLISHED_MIN_HOSTS} hosts",
                    "thresholds": {"clean_max_foreign_share": FORMS_CLEAN_MAX_FOREIGN,
                                   "drop_above_foreign_share": FORMS_DROP_ABOVE_FOREIGN,
                                   "lemma_host_min_tokens": FORMS_MIN_LEMMA_TOKENS, "lemma_host_min_purity": FORMS_MIN_LEMMA_PURITY,
                                   "offparadigm_min_tokens": FORMS_OFFPARADIGM_MIN_TOKENS,
                                   "offparadigm_min_share": FORMS_OFFPARADIGM_MIN_SHARE},
                    "rule": ("candidates = generated paradigm forms (hebloc.loc.morph) + hosts seen with the entry's own lemmas "
                             f"(>= {FORMS_MIN_LEMMA_TOKENS} tokens, purity >= {FORMS_MIN_LEMMA_PURITY:.0%}; outside the root's paradigm also "
                             f">= {FORMS_OFFPARADIGM_MIN_TOKENS} tokens and >= {FORMS_OFFPARADIGM_MIN_SHARE:.0%} of all its tokens). Foreign "
                             "share = share of the host's tokens carrying an ESTABLISHED lemma that is not neutral ([BLANK], ##-fragments, "
                             "copies of the word, inflected forms of this root) and not a lemma of this root in the lexicon. "
                             f"<= {FORMS_CLEAN_MAX_FOREIGN:.0%}: clean; <= {FORMS_DROP_ABOVE_FOREIGN:.0%}: AMBIGUOUS (kept; ~partners = "
                             "competing lemmas); above: dropped. A Causative/Intensive form that is also a Simple form of the same root "
                             "(no Simple entry) gets the partner ~<root>.S. Generated forms only for entries with no Dicta lemma of their own "
                             "(policy no_own_lemma), always marked ~form. Pooled over the corpora listed in `inventory`."),
                    "counts": {"kept": sum(x["kept"] for x in st.values()), "ambiguous": sum(x["ambiguous"] for x in st.values()),
                               "dropped": sum(x["dropped"] for x in st.values())},
                    "lexicon_file_sha256": lex_sha, "inventory": inventory_info or {}},
           "forms": r["forms"], "ambiguous": r["ambiguous"]}
    if candidates:     # Phase C candidate folder only (hebloc.loc.ident); the R1 file never has these keys
        if established_self_foreign:
            doc["meta"]["rule_version"] = FORMS_RULE_VERSION_I3
        doc["meta"]["candidates"] = list(candidates)
        doc["meta"]["candidate_options"] = {"generated_forms": generated, "established_self_foreign": established_self_foreign,
                                            "lemma_partners": lemma_partners}
        header = ("# Phase C identification CANDIDATE (hebloc.loc.ident; D-059 addendum, D-065). Not the R1 config.\n" + header)
        if lemma_partners:
            doc["lemma_partners"] = r["lemma_partners"]
    atomic_write_text(header + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=200), path)
    return {"stats": st, "blockers": r["blockers"], "dropped": r["dropped"], "forms": r["forms"],
            "ambiguous": r["ambiguous"], "lemma_partners": r["lemma_partners"]}


# ---------------------------------------------------------------------------------------------- data checks
def data_report(lex: Lexicon, inventory) -> dict:
    """Per-entry frequencies of each lemma variant per corpus, zero-frequency variants, near-miss lemmas."""
    freq: dict[str, Counter] = defaultdict(Counter)
    for lem, n, c in zip(inventory["lemma"].to_pylist(), inventory["n"].to_pylist(), inventory["corpus"].to_pylist()):
        freq[lem][c] += n
    known = {lem for e in lex.entries for lem in (e.own_lemmas | set(e.shared))}
    known |= {d["lemma"] for e in lex.entries for d in e.raw.get("excluded_lemmas") or []}
    rows, zero = [], []
    for e in lex.entries:
        for d in e.dicta_lemmas + [{"lemma": s["lemma"], "voice": "shared"} for s in e.shared_lemmas]:
            f = dict(freq.get(d["lemma"], {}))
            rows.append({"entry": e.id, "lemma": d["lemma"], "voice": d["voice"], **f, "total": sum(f.values())})
            if not f:
                zero.append(f"{e.id}: {d['lemma']}")
    # near misses: inventory lemmas with the same consonant skeleton as an entry's root, not mentioned anywhere
    def skel(s: str) -> str:
        from hebloc.loc.morph import nonfinal

        return "".join(ch for ch in nonfinal(s) if ch not in "וי")

    roots = {skel(e.root): e.id for e in lex.entries if len(skel(e.root)) >= 3}
    near = []
    for lem, f in freq.items():
        if lem in known or lem == "[BLANK]":
            continue
        s = skel(lem)
        for pre in ("", "ה", "נ", "הת", "ו", "מ"):
            if s.startswith(pre) and s[len(pre):] in roots and sum(f.values()) >= 5:
                near.append({"lemma": lem, "near_entry": roots[s[len(pre):]], "total": sum(f.values()), **f})
                break
    return {"lemma_rows": rows, "zero_frequency_variants": zero,
            "near_misses": sorted(near, key=lambda r: -r["total"])}


def paper_example_check(lex: Lexicon, source, identify_fn) -> list[dict]:
    """For every paper_ref with a Hebrew Mikra ref: does that verse contain a token identified as the entry?"""
    from hebloc.loc.source import connect
    from hebloc.store.io import sql_str

    refs = sorted({r["he"] for e in lex.entries for r in e.paper_refs if r.get("he")})
    con = connect()
    con.execute(f"CREATE TEMP TABLE u AS SELECT sent_id, ref FROM {source.units_sql('mikra', ('sent_id', 'ref'))} "
                f"WHERE ref IN ({', '.join(sql_str(x) for x in refs)})")
    found: dict[str, set[str]] = defaultdict(set)
    for run in source.runs("mikra"):
        t = con.sql(f"SELECT u.ref, t.lemma, t.host, t.upos FROM {source.tokens_sql(run, ('sent_id', 'lemma', 'host', 'upos'))} t "
                    "JOIN u USING (sent_id) WHERE t.upos = 'VERB'").fetchall()
        for ref, lemma, host, upos in t:
            m = identify_fn(lemma, host, upos)
            if m:
                for member in m["members"]:
                    found[ref].add(member)
    out = []
    for e in lex.entries:
        for r in e.paper_refs:
            if r.get("he"):
                out.append({"entry": e.id, "where": r.get("where"), "he": r["he"], "found": e.id in found.get(r["he"], set())})
    return out


def forms_stale(lex: Lexicon, path: Path = LEXICON_PATH) -> bool:
    """True when the forms file was generated from a different lexicon file (regenerate: lexicon forms)."""
    want = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return lex.forms_meta.get("lexicon_file_sha256") != want


def review_rows(lex: Lexicon, inventory, example_rows: list[dict] | None = None, blockers: dict | None = None) -> list[dict]:
    """One row per entry for Ori's lexicon review (written as CSV with a BOM)."""
    freq: dict[str, Counter] = defaultdict(Counter)
    for lem, n, c in zip(inventory["lemma"].to_pylist(), inventory["n"].to_pylist(), inventory["corpus"].to_pylist()):
        freq[lem][c] += n
    ex = defaultdict(lambda: [0, 0])
    for r in example_rows or []:
        ex[r["entry"]][1] += 1
        ex[r["entry"]][0] += int(r["found"])
    out = []
    for e in lex.entries:
        lem_tot = {c: sum(freq[d["lemma"]][c] for d in e.dicta_lemmas) for c in ("mikra", "hazal", "medieval", "haskala", "modern")}
        out.append({
            "id": e.id, "status": e.status, "class": e.klass or "", "template": e.template, "root": e.root, "citation": e.citation,
            "gloss": e.gloss, "putting_removal": e.putting_removal, "list": e.raw.get("list", ""), "flags": "; ".join(e.flags),
            "dicta_lemmas": "; ".join(f"{d['lemma']}({d['voice'][0]}):{sum(freq[d['lemma']].values())}" for d in e.dicta_lemmas),
            "shared_lemmas": "; ".join(f"{d['lemma']} ~ {d['other']}" for d in e.shared_lemmas),
            "excluded_lemmas": "; ".join(f"{d['lemma']} ({d['why']})" for d in e.raw.get("excluded_lemmas") or []),
            **{f"lemma_tokens_{c}": n for c, n in lem_tot.items()},
            "n_forms": len(lex.forms.get(e.id, [])),
            "paper_refs_found": f"{ex[e.id][0]}/{ex[e.id][1]}" if ex[e.id][1] else "",
            "blocking_lemmas": "; ".join(f"{lem}:{n}" for lem, n in (blockers or {}).get(e.id, [])[:3]),
            "idioms": "; ".join(d["noun"] for d in e.nonlocative_idioms),
            "mh": (e.raw.get("mh") or {}).get("prediction", ""), "note": e.raw.get("note", ""),
        })
    return out
