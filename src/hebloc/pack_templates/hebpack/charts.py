"""Chart helpers in the style of the official report (same corpus colours everywhere).

    from hebpack.charts import COLORS, LABELS, new_figure, save
    fig, ax = new_figure("Mean sentence length by stratum", "stratum", "words")
    ...
    save(fig, "length_by_stratum")          # -> analyses/figures/length_by_stratum.png

Hebrew text: matplotlib does not lay out right-to-left text, so Hebrew in a chart appears reversed. Keep Hebrew
words in tables (CSV) and use corpus names, codes or transliteration in charts (the official report does the same).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from hebpack import ANALYSES, CORPORA  # noqa: E402

COLORS = dict(zip(CORPORA, ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4")))   # = official report
LABELS = dict(CORPORA)
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"


def new_figure(title: str, xlabel: str = "", ylabel: str = "", size=(9, 5)):
    fig, ax = plt.subplots(figsize=size, facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=13)
    ax.set_xlabel(xlabel, color=INK2)
    ax.set_ylabel(ylabel, color=INK2)
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2)
    return fig, ax


def save(fig, name: str, folder: Path | None = None, dpi: int = 150) -> Path:
    folder = folder or ANALYSES / "figures"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.png"
    fig.tight_layout()
    fig.savefig(path, dpi=dpi, facecolor=SURFACE)
    plt.close(fig)
    return path
