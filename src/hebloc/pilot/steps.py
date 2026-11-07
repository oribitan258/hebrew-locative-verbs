"""``hebloc pilot <step>`` — the M3 pilot, step by step (each step is re-runnable / resumable).

    fetch-models   download the pinned models (network) and verify checksums
    fetch-bhsa     download the pinned BHSA feature files (network) and build words.parquet
    sample         build annotation/pilot_sample.csv
    smoke          50-unit bounded run with the base model + validation
    parse          full pilot sample with base, tiny, and base with the original (unfixed) MST
    variants       normalization-hypothesis runs (Mikra) + defaults reproduction check
    diacritics     exhaustive tokenizer-level test of diacritic stripping (all corpora)
    census         sub-word length of every unit → multi-piece share (D-021)
    analyze        hypotheses vs BHSA, base vs tiny, diagnostics, MST-bug impact → results/*.json
    audit          write the manual-audit sheets (judgment columns left blank)
    audit-score    score the filled sheets (only human-filled cells)
    bench          bounded grid, equivalence checks, then scaled runs → bench/*.json
"""

from __future__ import annotations

import json

from hebloc.parse import models as M
from hebloc.pilot import PILOT_DIR


def _print(obj) -> None:
    print(json.dumps(obj, indent=1, ensure_ascii=False, default=str)[:6000])


def step(name: str, threads: int = 8) -> int:
    if name == "fetch-models":
        for m in ("base", "tiny"):
            print(m, M.fetch(m))
    elif name == "fetch-bhsa":
        from hebloc.pilot import bhsa as B
        B.fetch()
        print("words:", B.build_words().num_rows)
    elif name == "sample":
        from hebloc.pilot import sample as S
        print(len(S.build()), "units ->", S.SAMPLE_PATH)
    elif name == "smoke":
        from hebloc.pilot import runs as R
        m, c = R.run_default("base", limit_per_corpus=10, threads=threads)
        print(R.summary(m, c))
        return 0 if c["ok"] else 1
    elif name == "parse":
        from hebloc.pilot import runs as R
        ok = True
        for model, rid, kw in [("base", "base__default", {}), ("tiny", "tiny__default", {}),
                               ("base", "base__default__orig_mst", {"mst_fix": False})]:
            m, c = R.run_default(model, run_id=rid, threads=threads, **kw)
            print(R.summary(m, c))
            ok &= c["ok"] or rid.endswith("orig_mst")
        return 0 if ok else 1
    elif name == "variants":
        from hebloc.pilot import experiments as E
        _print(E.run_variants(M.load("base", threads), M.load("tiny", threads), threads=threads))
    elif name == "diacritics":
        from hebloc.pilot import experiments as E
        _print(E.diacritics_tokenizer_test(M.load("base")))
    elif name == "census":
        from hebloc.pilot import experiments as E
        _print(E.piece_census(M.load("base")))
    elif name == "analyze":
        from hebloc.pilot import analyze
        _print(analyze.run_all())
    elif name == "audit":
        from hebloc.pilot import audit
        _print(audit.build())
    elif name == "audit-score":
        from hebloc.pilot import audit
        _print(audit.score())
    elif name == "bench":
        from hebloc.pilot import benchmark_plan
        _print(benchmark_plan.run_all(threads_grid=(4, 8, 12)))
    else:
        raise SystemExit(f"unknown pilot step {name!r}; see `hebloc pilot --help`")
    return 0
