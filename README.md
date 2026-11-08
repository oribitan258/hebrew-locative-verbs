# Hebrew Locative Verbs — Data Foundation

Academic NLP mini-project (Ben-Gurion University, 2027). It tests Doron & Dubnov's (2017)
*Locative Alternation Preposition Identity* on five Hebrew corpora, using Dicta's parser.

- **New partner? Start with [docs/PARTNERS.md](docs/PARTNERS.md)** (installation, corpora, checks,
  parsing tasks, sharing results)
- Current state and pending decisions: [docs/HANDOFF.md](docs/HANDOFF.md)
- Project context and rules: [CLAUDE.md](CLAUDE.md)
- Full roadmap: [docs/roadmap.md](docs/roadmap.md)
- Decision log: [docs/decisions.md](docs/decisions.md)

## Setup

Requires [uv](https://docs.astral.sh/uv/). Python 3.12 is pinned.

```
uv sync                 # create the environment from uv.lock
uv run hebloc baseline  # record checksums of the original corpora (read-only); must match
                        # the git-tracked config/corpora_anchor.json or it refuses
uv run hebloc inventory # M1: build the document catalog (data/catalog/documents.parquet, ~75 s)
uv run hebloc prepare   # M2: extract sentence/verse units (data/units/, ~5 min)
uv run hebloc pilot fetch-models   # M3: download the pinned Dicta models (~0.9 GB, verified)
uv run hebloc pilot <step>         # M3 pilot steps; see docs/pilot_report.md §16
uv run pytest           # fast tests
uv run pytest -m slow   # full checksum re-verification of corpora/
```

The original corpora live in `corpora/`. They are treated as **immutable** and are not tracked in
git: each team member downloads them from the course link, and `hebloc baseline` proves the copy is
identical. All derived data is written to `data/`, which is reproducible and also not tracked; parse
results are shared as verified bundles (`hebloc bundle`), never through git. The course documents
(`project.pdf`, the paper, the slides) are kept as local copies only.
