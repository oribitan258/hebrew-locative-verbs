"""CSV, PNG and the generated Markdown report for a stats folder (docs/m6_design.md §4).

* provisional: everything goes into ``data/stats/<id>/report/`` (local only, never git);
* final: ``results/stats/`` (CSV + ``figures/``) and ``docs/stats_report.md`` (git).

Numbers in the report are rendered from the Parquet tables, never typed by hand. Charts carry no
Hebrew (matplotlib does not lay out right-to-left text): Hebrew words appear only in tables.
Every chart has its data in a CSV next to it. Colours are fixed per corpus (chronological order), so
a corpus has the same colour in every chart and in the provisional and final reports.
"""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc

from hebloc.paths import CORPORA, DOCS_DIR, RESULTS_DIR
from hebloc.stats.compute import TABLES, load
from hebloc.stats.tables import ALL_WORDS, NONE, WORD_FEATURES

# dataviz reference categorical palette, slots 1-5, validated for 5 adjacent series (light surface)
COLORS = dict(zip(CORPORA, ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4")))
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
TOP_CSV, TOP_MD = 1000, 20
ACCURACY_JSON = RESULTS_DIR / "stats" / "accuracy" / "mikra_vs_bhsa.json"


def _rows(t: pa.Table, **eq) -> list[dict]:
    mask = None
    for k, v in eq.items():
        m = pc.equal(t[k], v)
        mask = m if mask is None else pc.and_(mask, m)
    return (t.filter(mask) if mask is not None else t).to_pylist()


def _n(x) -> str:
    if x is None:
        return "–"
    if isinstance(x, int) or float(x).is_integer():
        return f"{int(x):,}"
    return f"{x:,.2f}"


def _pct(x) -> str:
    return "–" if x is None else f"{100 * x:.1f}%"


def _md_table(head: list[str], rows: list[list[str]], align: str | None = None) -> str:
    align = align or ("l" + "r" * (len(head) - 1))
    sep = ["---:" if a == "r" else "---" for a in align]
    return "\n".join(["| " + " | ".join(head) + " |", "| " + " | ".join(sep) + " |"]
                     + ["| " + " | ".join(r) + " |" for r in rows]) + "\n"


# ------------------------------------------------------------------------------------------ CSV

def write_csv(tables: dict[str, pa.Table], out: Path) -> list[str]:
    import pyarrow.csv as pacsv

    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name in TABLES:
        t = tables[name]
        if name in ("word_freq", "lemma_freq"):
            t = t.filter(pc.less_equal(t["rank"], TOP_CSV))
            name = f"{name}_top{TOP_CSV}"
        if "measure_order" in t.column_names:
            t = t.drop(["measure_order"])
        pacsv.write_csv(t, out / f"{name}.csv")
        written.append(f"{name}.csv")
    return written


# ------------------------------------------------------------------------------------------ figures

def _style(ax, title: str, xlabel: str, ylabel: str):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=11)
    ax.set_xlabel(xlabel, color=INK2, fontsize=9)
    ax.set_ylabel(ylabel, color=INK2, fontsize=9)
    ax.tick_params(colors=INK2, labelsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def _fig(w=7.5, h=4.2):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(w, h), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    return plt, fig, ax


def _legend(ax):
    leg = ax.legend(frameon=False, fontsize=8, labelcolor=INK2)
    return leg


def write_figures(tables: dict[str, pa.Table], out: Path) -> list[tuple[str, str, str]]:
    """→ [(file, caption, csv with its data)]"""
    out.mkdir(parents=True, exist_ok=True)
    corpora = [c for c in CORPORA if _rows(tables["coverage"], corpus_id=c)]
    figs = []
    titles = {"length": ("Sentence length", "words per sentence (Mikra: per verse)"),
              "distinct_words": ("Distinct words per sentence", "distinct words per sentence"),
              "depth": ("Sentence depth (units with one valid tree)", "depth (levels, root = 1)")}
    for measure, (title, xl) in titles.items():
        plt, fig, ax = _fig()
        xmax = 1
        for c in corpora:
            st = _rows(tables["sentence_stats"], corpus_id=c, measure=measure)[0]
            xmax = max(xmax, int(st["p99"] or 1))
        for c in corpora:
            d = _rows(tables["distributions"], corpus_id=c, measure=measure)
            xs = [r["value"] for r in d if r["value"] <= xmax]
            ys = [100 * r["share"] for r in d if r["value"] <= xmax]
            ax.plot(xs, ys, color=COLORS[c], linewidth=1.6, label=CORPORA[c])
        _style(ax, title, xl + f" (shown up to {xmax}, the largest 99th percentile)", "% of units")
        _legend(ax)
        f = f"{measure}_distribution.png"
        fig.tight_layout(); fig.savefig(out / f); plt.close(fig)
        figs.append((f, f"{title}: share of units per value, per corpus", "distributions.csv"))

    plt, fig, ax = _fig()
    for c in corpora:
        d = sorted(_rows(tables["depth_by_length"], corpus_id=c), key=lambda r: r["band_order"])
        ax.plot([r["length_band"] for r in d], [r["mean_depth"] for r in d], color=COLORS[c], linewidth=1.6,
                marker="o", markersize=4, label=CORPORA[c])
    _style(ax, "Mean depth by sentence length", "sentence length band (words)", "mean depth")
    _legend(ax)
    fig.tight_layout(); fig.savefig(out / "depth_by_length.png"); plt.close(fig)
    figs.append(("depth_by_length.png", "Mean depth per sentence-length band, per corpus", "depth_by_length.csv"))

    plt, fig, ax = _fig()
    for c in corpora:
        wf = tables["word_freq"].filter(pc.equal(tables["word_freq"]["corpus_id"], c))
        ranks, ns = wf["rank"].to_pylist(), wf["n"].to_pylist()
        idx, i = [], 1
        while i <= len(ranks):                      # log-spaced sample of ranks (Modern has millions)
            idx.append(i - 1)
            i = max(i + 1, int(i * 1.05))
        ax.loglog([ranks[j] for j in idx], [ns[j] for j in idx], color=COLORS[c], linewidth=1.6, label=CORPORA[c])
    _style(ax, "Word frequency by rank (Zipf plot)", "rank of the word type (log)", "frequency (log)")
    _legend(ax)
    fig.tight_layout(); fig.savefig(out / "zipf_words.png"); plt.close(fig)
    figs.append(("zipf_words.png", "Frequency of each word type against its rank, log-log", "word_freq_top1000.csv"))

    for name, key, share, title, ylab in (("pos", "upos", "share_words", "Word categories (POS)", "POS"),
                                          ("deprel", "deprel", "share_words", "Dependency relations (top 20)", "relation")):
        t = tables[name]
        tot: dict[str, float] = {}
        for r in t.to_pylist():
            if r[share] is not None:
                tot[r[key]] = tot.get(r[key], 0) + r[share]
        cats = [k for k, _ in sorted(tot.items(), key=lambda kv: -kv[1]) if k != "punct"][:20]
        plt, fig, ax = _fig(7.5, 0.28 * len(cats) + 1.2)
        k = len(corpora)
        for j, c in enumerate(corpora):
            vals = {r[key]: r[share] for r in _rows(t, corpus_id=c)}
            ys = [i + (j - (k - 1) / 2) * 0.16 for i in range(len(cats))]
            ax.scatter([100 * (vals.get(x) or 0) for x in cats], ys, s=18, color=COLORS[c], label=CORPORA[c],
                       edgecolors=SURFACE, linewidths=0.8, zorder=3)
        ax.set_yticks(range(len(cats)), cats)
        ax.invert_yaxis()
        _style(ax, title, "% of words (punctuation excluded)", ylab)
        _legend(ax)
        f = f"{name}_shares.png"
        fig.tight_layout(); fig.savefig(out / f); plt.close(fig)
        figs.append((f, f"{title}: share of words, per corpus", f"{name}.csv"))
    return figs


# ------------------------------------------------------------------------------------------ Markdown

def _by_corpus(corpora, fn) -> list[str]:
    return [fn(c) for c in corpora]


def markdown(tables: dict[str, pa.Table], manifest: dict, figs: list[tuple[str, str, str]], fig_prefix: str,
             csv_prefix: str) -> str:
    corpora = [c for c in CORPORA if _rows(tables["coverage"], corpus_id=c)]
    names = [CORPORA[c] for c in corpora]
    cov = {c: _rows(tables["coverage"], corpus_id=c)[0] for c in corpora}
    final = manifest["status"] == "final"
    L = []
    L.append("# Descriptive Statistics of the Five Corpora (project.pdf §4)\n")
    if not final:
        L.append("> **PROVISIONAL.** These numbers come from the runs listed below, not from the final "
                 "registered run set. They are for review only and are recomputed once, centrally, after the "
                 "merge (D-045). Corpora not listed are not computed yet.\n")
    L.append(f"*Generated by `hebloc stats` from `data/stats/{manifest['stats_id']}` (status **{manifest['status']}**, "
             f"code `{manifest['code_commit'][:12]}`, {manifest['created_utc']}). Design and definitions: "
             f"`docs/m6_design.md` (D-046). View: full view (D-015).*\n")
    L.append("Runs: " + "; ".join(f"{CORPORA[c]}: " + ", ".join(f"`{r}`" for r in refs)
                                    for c, refs in manifest["runs"].items()) + "\n")

    L.append("## 1. Definitions\n")
    L.append("- **Word**: a Dicta word that is not punctuation. Punctuation tokens are counted separately.\n"
             "- **Word type**: the word as written in the normalized text (prefixes attached, niqqud removed). "
             "**Lemma**: Dicta's lemma (for verbs, the dictionary form of the binyan, not the root); "
             "`[BLANK]` lemmas are counted, not typed.\n"
             "- **Sentence**: the unit, i.e. a **verse** in Mikra and a sentence elsewhere. Empty and "
             "punctuation-only units are counted, not measured.\n"
             "- **Depth**: levels on the longest path from the root word down to a word (root = 1, a word attached "
             "to the root = 2, …), punctuation ignored. Measured only on units with one valid dependency tree; "
             "units parsed in several pieces (D-021) or with an invalid word-level tree (D-025) are excluded and "
             "reported in §4.\n")

    L.append("## 2. Coverage\n")
    rows_def = [("Units (sentences/verses)", "units"), ("empty (no text)", "units_empty"),
                ("punctuation only", "units_punctuation_only"), ("with a parse error", "units_parse_error"),
                ("measured (length, distinct words)", "units_measured"), ("with depth (one valid tree)", "units_with_depth"),
                ("parsed in several pieces", "units_multi_piece"), ("invalid word-level tree", "units_invalid_tree"),
                ("Dicta tokens", "tokens"), ("words", "words"), ("punctuation tokens", "punctuation_tokens"),
                ("words with a [BLANK] lemma", "words_lemma_blank"), ("pieces", "pieces"),
                ("pieces decoded without MST (mst_fallback)", "mst_fallback_pieces")]
    L.append(_md_table(["", *names], [[lab, *_by_corpus(corpora, lambda c: _n(cov[c][k]))] for lab, k in rows_def]))

    L.append("\n## 3. Words and lemmas, and their frequencies (R1)\n")
    lex = {(r["corpus_id"], r["kind"]): r for r in tables["lexicon"].to_pylist()}
    rows = []
    for kind, lab in (("word", "Word"), ("lemma", "Lemma")):
        rows += [[f"{lab} tokens", *_by_corpus(corpora, lambda c: _n(lex[(c, kind)]["tokens"]))],
                 [f"{lab} types (distinct)", *_by_corpus(corpora, lambda c: _n(lex[(c, kind)]["types"]))],
                 [f"{lab} types occurring once", *_by_corpus(corpora, lambda c: _n(lex[(c, kind)]["types_once"]))]]
    rows.append(["Words with a [BLANK] lemma", *_by_corpus(corpora, lambda c: f"{_n(cov[c]['words_lemma_blank'])} "
                                                         f"({_pct(cov[c]['words_lemma_blank'] / cov[c]['words'])})")])
    L.append(_md_table(["", *names], rows))
    L.append("\n*Raw type counts depend on corpus size and are not comparable across corpora of very different "
             "sizes.*\n")
    for name, key, lab in (("word_freq", "word", "words"), ("lemma_freq", "lemma", "lemmas")):
        L.append(f"\n**The {TOP_MD} most frequent {lab}** (frequency per 1,000 {'words' if key == 'word' else 'lemma tokens'}; "
                 f"complete lists in `{name}.parquet`, top {TOP_CSV} in `{csv_prefix}{name}_top{TOP_CSV}.csv`):\n\n")
        top = {c: _rows(tables[name].filter(pc.less_equal(tables[name]["rank"], TOP_MD)), corpus_id=c) for c in corpora}
        rows = [[str(i + 1), *_by_corpus(corpora, lambda c: f"{top[c][i][key]} ({1000 * top[c][i]['share']:.1f})"
                                         if i < len(top[c]) else "")] for i in range(TOP_MD)]
        L.append(_md_table(["#", *names], rows, "r" + "l" * len(names)))
    L += _fig_md(figs, "zipf_words.png", fig_prefix)

    L.append("\n## 4. Sentence length, distinct words per sentence, depth (R2–R4)\n")
    stat_rows = [("units", "n_units", _n), ("mean", "mean", _n), ("standard deviation", "sd", _n), ("min", "min", _n),
                 ("5th percentile", "p5", _n), ("25th percentile", "p25", _n), ("median", "p50", _n),
                 ("75th percentile", "p75", _n), ("95th percentile", "p95", _n), ("99th percentile", "p99", _n),
                 ("max", "max", _n)]
    for measure, title in (("length", "Sentence length in words (R2)"),
                           ("distinct_words", "Distinct words per sentence (R3)"),
                           ("depth", "Sentence depth (R4)")):
        st = {c: _rows(tables["sentence_stats"], corpus_id=c, measure=measure)[0] for c in corpora}
        L.append(f"\n### {title}\n\n")
        L.append(_md_table(["", *names], [[lab, *_by_corpus(corpora, lambda c: f(st[c][k]))] for lab, k, f in stat_rows]))
        L += _fig_md(figs, f"{measure}_distribution.png", fig_prefix)
    L.append("\n**Depth by sentence length** (mean depth; number of units in brackets):\n\n")
    bands = sorted({(r["band_order"], r["length_band"]) for r in tables["depth_by_length"].to_pylist()})
    dbl = {(r["corpus_id"], r["length_band"]): r for r in tables["depth_by_length"].to_pylist()}
    L.append(_md_table(["Length (words)", *names],
                       [[b, *_by_corpus(corpora, lambda c: f"{dbl[(c, b)]['mean_depth']:.2f} ({dbl[(c, b)]['n_units']:,})"
                                        if (c, b) in dbl else "–")] for _, b in bands]))
    L += _fig_md(figs, "depth_by_length.png", fig_prefix)
    L.append("\n**What depth excludes** (units and words per tree status; depth uses `complete` only):\n\n")
    ts = {(r["corpus_id"], r["tree_status"]): r for r in tables["tree_status"].to_pylist()}
    statuses = ("complete", "multi_piece", "invalid_tree", "parse_error", "no_words", "empty")
    L.append(_md_table(["Tree status", *names],
                       [[s, *_by_corpus(corpora, lambda c: (f"{ts[(c, s)]['units']:,} units ({_pct(ts[(c, s)]['share_units'])}), "
                                                           f"{_pct(ts[(c, s)]['share_words'])} of words, mean length "
                                                           f"{ts[(c, s)]['mean_length']:.1f}") if (c, s) in ts else "–")]
                        for s in statuses]))

    L.append("\n## 5. Morphological features (R5)\n\n### Word categories (POS)\n\n")
    pos = {(r["corpus_id"], r["upos"]): r for r in tables["pos"].to_pylist()}
    cats = sorted({u for _, u in pos}, key=lambda u: (u == "PUNCT", -sum(pos.get((c, u), {}).get("n", 0) for c in corpora)))
    L.append(_md_table(["POS", *names], [[u, *_by_corpus(corpora, lambda c: (
        f"{_n(pos[(c, u)]['n'])} ({_pct(pos[(c, u)]['share_words'])})" if u != "PUNCT" else _n(pos[(c, u)]['n']))
        if (c, u) in pos else "–")] for u in cats]))
    L.append("\n*Percentages are shares of words (punctuation excluded).*\n")
    L += _fig_md(figs, "pos_shares.png", fig_prefix)
    L.append("\n### Inflection features\n\n"
             "Every feature Dicta outputs is covered: Gender, Number, Person and Tense of the word; the pronominal "
             "suffix (PRON = possessive, e.g. ספרו; ADP_PRON = on a preposition, e.g. לו) with its Gender, Number "
             "and Person; and definiteness, derived from the DET prefix as Dicta's own UD converter does. "
             "Dicta does **not** output construct/absolute state (נפרד/נסמך; construct appears only as the relation "
             "`compound:smixut`, §6), binyan, or verbal form (participle, infinitive). Multi-values (`Fem,Masc`, "
             "`1,2,3`) are Dicta's own. `(none)` = the feature is not marked on the word. Below: all words, and "
             f"verbs; every POS is in `{csv_prefix}features.csv`.\n")
    feat = tables["features"]
    order = [*WORD_FEATURES, "Suffix", "Suffix.Gender", "Suffix.Number", "Suffix.Person", "Definite (DET prefix)"]
    for upos, label in ((ALL_WORDS, "all words"), ("VERB", "verbs")):
        for f in order:
            if upos == "VERB" and f.startswith("Suffix.") or (upos == "VERB" and f.startswith("Definite")):
                continue
            rows = {(r["corpus_id"], r["value"]): r for r in _rows(feat, upos=upos, feature=f)}
            values = sorted({v for _, v in rows}, key=lambda v: (v == NONE, -sum(rows.get((c, v), {}).get("n", 0) for c in corpora)))
            scope = " (words with a suffix)" if f.startswith("Suffix.") else ""
            L.append(f"\n**{f}**, {label}{scope}:\n\n")
            L.append(_md_table([f, *names], [[v, *_by_corpus(corpora, lambda c: f"{_n(rows[(c, v)]['n'])} "
                                                             f"({_pct(rows[(c, v)]['share'])})" if (c, v) in rows else "–")]
                                             for v in values]))

    L.append("\n## 6. Syntactic relations (R6)\n\n")
    dr = {(r["corpus_id"], r["deprel"]): r for r in tables["deprel"].to_pylist()}
    rels = sorted({d for _, d in dr}, key=lambda d: -sum(dr.get((c, d), {}).get("n", 0) for c in corpora))
    L.append(_md_table(["Relation", *names], [[f"`{d}`", *_by_corpus(corpora, lambda c: (
        f"{_n(dr[(c, d)]['n'])} ({_pct(dr[(c, d)]['share_words'])})" if d != "punct" else _n(dr[(c, d)]['n']))
        if (c, d) in dr else "–")] for d in rels]))
    L.append("\n*Percentages are shares of words (punctuation excluded); `punct` attaches punctuation tokens. "
             "Relation labels are counted on all words, including units excluded from depth.*\n")
    L += _fig_md(figs, "deprel_shares.png", fig_prefix)

    L.append("\n## 7. Parser accuracy: Mikra vs BHSA\n\n")
    L.append(_accuracy_md())
    L.append("\n## 8. Files\n\n"
             f"Parquet (all rows): `data/stats/{manifest['stats_id']}/` ({', '.join(f'`{t}`' for t in TABLES)}, and "
             "`unit_metrics/` with one row per unit). CSV: " + f"`{csv_prefix}`. Figures: `{fig_prefix}`.\n")
    return "\n".join(x.strip("\n") + "\n" for x in L)      # a blank line between blocks


def _fig_md(figs, name: str, prefix: str) -> list[str]:
    for f, cap, data in figs:
        if f == name:
            return [f"\n![{cap}]({prefix}{f})\n\n*{cap}. Data: `{data}`.*\n"]
    return []


def _accuracy_md() -> str:
    if not ACCURACY_JSON.exists():
        return "*Not computed yet (`hebloc stats accuracy`).*\n"
    a = json.loads(ACCURACY_JSON.read_text(encoding="utf-8"))
    s = a["summary"]
    rep = a["pilot_reproduction"]
    out = (f"Dicta vs the BHSA expert annotation (ETCBC 2021, CC BY-NC) on all Mikra verses (run `{a['run']}`). "
           "**Convention-aware agreement, not gold accuracy**: the two annotations follow different conventions; "
           "BHSA has no dependency trees, so syntax is not measured. "
           f"{s['verses']:,} verses; {s['verses_excluded_low_alignment']} excluded because the texts align below 80% "
           f"(listed in `results/stats/accuracy/excluded_verses.csv`); {s['aligned_words']:,} aligned written words "
           f"({_pct(s['alignment_rate_bhsa'])} of BHSA's).\n\n")
    out += _md_table(["Layer", "Words", "Agreement", "95% interval"],
                     [[l["layer"], _n(l["n"]), _pct(l["agreement"]), f"{_pct(l['ci95_low'])}–{_pct(l['ci95_high'])}"]
                      for l in a["layers"]])
    out += (f"\n*Cross-check:* restricted to the pilot's {rep.get('verses', '?')} random verses, the full run reproduces "
            f"the pilot report's figures (§8.1) {'**exactly**' if rep.get('identical') else '**NOT exactly**: ' + str(rep)}. "
            "Verb lemmas of other stems agree rarely because BHSA lists the root and Dicta the binyan's dictionary "
            "form; wayyiqtol forms are mostly tagged `Tense=Fut` (`results/stats/accuracy/tense_confusion.csv`).\n")
    return out


def render(stats_dir: Path) -> dict:
    """Write CSV, figures and the Markdown report for ``stats_dir`` (location by its status)."""
    stats_dir = Path(stats_dir)
    manifest = json.loads((stats_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] == "scale_test":
        raise ValueError("a scale test is never rendered (D-045)")
    tables = load(stats_dir)
    if manifest["status"] == "final":
        base, md_path = RESULTS_DIR / "stats", DOCS_DIR / "stats_report.md"
        fig_prefix, csv_prefix = "../results/stats/figures/", "results/stats/"
    else:
        base = stats_dir / "report"
        md_path = base / "stats_report.md"
        fig_prefix, csv_prefix = "figures/", "report/"
    from hebloc.store.io import atomic_write_text

    csvs = write_csv(tables, base)
    figs = write_figures(tables, base / "figures")
    atomic_write_text(markdown(tables, manifest, figs, fig_prefix, csv_prefix), md_path)
    return {"report": str(md_path), "csv": [str(base / c) for c in csvs], "figures": [str(base / "figures" / f) for f, _, _ in figs]}
