"""`start`: check the package and print a plain-language overview of the data and of the work so far.

    uv run python -m hebpack.start            # quick check + overview (seconds)
    uv run python -m hebpack.start --first    # also the one-time checks: every file's sha256 + the quick self-test
                                              # (about 15–20 minutes; skipped automatically once they have passed)
"""

from __future__ import annotations

import argparse
import json
import sys

from hebpack import ANALYSES, CORPORA, ROOT, state


def _fmt(n) -> str:
    n = float(n)
    return f"{n / 1e6:.1f} M" if n >= 1e6 else f"{int(n):,}"


def overview() -> None:
    from hebpack.db import q

    cov = q("SELECT corpus_id, units, words FROM official_coverage")
    lex = q("SELECT corpus_id, kind, types FROM official_lexicon")
    st = q("SELECT corpus_id, measure, p50 FROM official_sentence_stats")
    strata = q("SELECT corpus_id, count(DISTINCT stratum) n FROM documents WHERE file_kind = 'text' GROUP BY 1")
    print("\nTHE DATA (official numbers, full view)")
    print(f"{'corpus':10}{'sentences':>12}{'words':>12}{'word forms':>12}{'lemmas':>10}{'median length':>15}"
          f"{'median depth':>14}{'sub-corpora':>13}")
    for c, name in CORPORA.items():
        u = cov[cov.corpus_id == c].iloc[0]
        wt = lex[(lex.corpus_id == c) & (lex.kind == "word")].types.iloc[0]
        lt = lex[(lex.corpus_id == c) & (lex.kind == "lemma")].types.iloc[0]
        ml = st[(st.corpus_id == c) & (st.measure == "length")].p50.iloc[0]
        md = st[(st.corpus_id == c) & (st.measure == "depth")].p50.iloc[0]
        ns = strata[strata.corpus_id == c].n
        print(f"{name:10}{_fmt(u.units):>12}{_fmt(u.words):>12}{_fmt(wt):>12}{_fmt(lt):>10}{ml:>15.0f}{md:>14.0f}"
              f"{(int(ns.iloc[0]) if len(ns) else 0):>13}")
    print("\nFor every word: lemma, part of speech, gender/number/person/tense, prefixes, pronoun suffix,")
    print("its head word and relation in the sentence's dependency tree, and named-entity tag.")
    print("For every sentence: original and normalized text, source file, sub-corpus; Haskala also author and year.")


def work_so_far() -> None:
    items = sorted(p for p in ANALYSES.iterdir() if p.is_dir() and not p.name.startswith("_")) if ANALYSES.exists() else []
    print("\nYOUR WORK (analyses/)")
    if not items:
        print("  nothing yet")
    for p in items:
        files = [f for f in p.rglob("*") if f.is_file()]
        print(f"  {p.name}: {sum(f.suffix == '.png' for f in files)} figures, {sum(f.suffix == '.csv' for f in files)} tables")
    if (ANALYSES / "REPORT.md").exists():
        print("  REPORT.md exists (findings for Ori)")


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--first", action="store_true", help="run the one-time checks if they have not passed yet")
    a = p.parse_args(argv)
    man = json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
    print(f"Package: {man['package']} v{man['pack_version']}, built from {man['stats_id']}")
    import duckdb, matplotlib, numpy, pandas, pyarrow  # noqa: E401, F401
    print("Python environment: OK")

    from hebpack import verify
    probs = verify.check(sizes_only=True)
    if probs:
        print("FILES: PROBLEM\n  " + "\n  ".join(probs[:20]))
        print("The download is incomplete or damaged: download the zip again (or tell Ori).")
        return 1
    print(f"Files present: OK ({len(man['files'])} files)")

    s = state.load()
    if a.first and not s.get("verify_full", {}).get("ok"):
        print("\nOne-time check 1/2: re-reading every file and comparing checksums (10–15 minutes)...", flush=True)
        probs = verify.check()
        state.record("verify_full", not probs, f"{len(probs)} problems")
        if probs:
            print("FILES: PROBLEM\n  " + "\n  ".join(probs[:20]))
            return 1
        print("  all files intact")
    if a.first and not s.get("selftest_quick", {}).get("ok"):
        print("\nOne-time check 2/2: recomputing the official statistics from the data (2–5 minutes)...", flush=True)
        from hebpack import selftest
        if not selftest.run(list(selftest.QUICK)):
            return 1
    s = state.load()
    for key, label in (("verify_full", "all files checksum-verified"),
                       ("selftest_quick", "official statistics reproduced (Mikra, Hazal, Medieval, Haskala)"),
                       ("selftest_all", "official statistics reproduced (all five corpora)")):
        v = s.get(key)
        print(f"Check: {label}: " + ("yes" if v and v["ok"] else "FAILED" if v else "not run yet"))
    overview()
    work_so_far()
    print("\nREADY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
