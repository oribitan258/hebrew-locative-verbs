"""Render real pilot analyses as Markdown for docs/pilot_report.md (examples, not judgments)."""

from __future__ import annotations

from collections import defaultdict

import pyarrow.compute as pc

from hebloc.parse.tokens import read_tokens

from hebloc.pilot.runs import run_dir, unit_rows


def render(sent_id: str, rid: str = "base__default", max_words: int = 40) -> str:
    toks = sorted((t for t in read_tokens(run_dir(rid)).filter(pc.field("sent_id") == sent_id).to_pylist()),
                  key=lambda t: t["sent_word_idx"])
    (raw, norm, ref), = [(r[0], r[1], r[2]) for r in unit_rows([sent_id], "text_raw, text_norm, ref")]
    from hebloc.parse.run import read_run
    parsed = {r["sent_id"]: r["text"] for r in read_run(run_dir(rid), "inputs").to_pylist()}.get(sent_id, norm)
    if parsed != norm:
        norm = f"{norm}` → parsed variant: `{parsed}"
    forms = {t["sent_word_idx"]: t["form"] for t in toks}
    lines = [f"**{ref}** · `{sent_id}` · {toks[0]['n_pieces'] if toks else 0} piece(s)", "",
             f"- Raw: `{raw[:300]}{' …' if len(raw) > 300 else ''}`", f"- Norm: `{norm[:300]}{' …' if len(norm) > 300 else ''}`", "",
             "| # | word | prefix+host | lemma | UPOS | features | head | relation |", "|---|---|---|---|---|---|---|---|"]
    for t in toks[:max_words]:
        head = "ROOT" if t["head_sent"] == -1 else f"{t['head_sent'] + 1} {forms.get(t['head_sent'], '?')}"
        seg = f"{t['prefix']}+{t['host']}" if t["prefix"] else t["host"]
        suf = f" +suffix:{t['suffix']}" if t["suffix"] else ""
        lines.append(f"| {t['sent_word_idx'] + 1} | {t['surface']} | {seg} | {t['lemma']} | {t['upos']} | {(t['feats'] or '') + suf} | {head} | {t['deprel']} |")
    if len(toks) > max_words:
        lines.append(f"| … | ({len(toks) - max_words} more words) | | | | | | |")
    return "\n".join(lines) + "\n"


def by_corpus(sent_ids: list[str], rid: str = "base__default") -> str:
    groups = defaultdict(list)
    for s in sent_ids:
        groups[s.split(":", 1)[0]].append(s)
    return "\n".join(f"#### {c}\n\n" + "\n".join(render(s, rid) for s in ids) for c, ids in groups.items())
