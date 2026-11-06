# Hebrew Locative Verbs — Data Foundation

Academic NLP mini-project (Ben-Gurion University, 2027). It tests Doron & Dubnov's (2017)
*Locative Alternation Preposition Identity* on five Hebrew corpora, using Dicta's parser.

- Project context and rules: [CLAUDE.md](CLAUDE.md)
- Full roadmap: [docs/roadmap.md](docs/roadmap.md)
- Decision log: [docs/decisions.md](docs/decisions.md)

## Setup

Requires [uv](https://docs.astral.sh/uv/). Python 3.12 is pinned.

```
uv sync                 # create the environment from uv.lock
uv run hebloc baseline  # one-time: record checksums of the original corpora (read-only)
uv run pytest           # fast tests
uv run pytest -m slow   # full checksum re-verification of corpora/
```

The original corpora live in `corpora/`. They are treated as **immutable** and are not tracked in
git. All derived data is written to `data/`, which is reproducible and also not tracked.
