"""M6: descriptive statistics required by project.pdf §4, and parser accuracy (design: docs/m6_design.md).

One code path for the provisional and the final run (D-045, D-046):

    runset   which parse runs feed which corpus; completeness gate (refuses partial corpora)
    metrics  one row per unit: words, punctuation, distinct words, tree status, depth (R2–R4)
    tables   corpus-level aggregates: frequencies (R1), POS and inflection features (R5),
             relation types (R6), sentence statistics, coverage; reconciliation checks
    compute  orchestration → data/stats/<status>-<date>-<hash>/ (Parquet + manifest)
    report   CSV, PNG and the generated Markdown report
    accuracy Mikra vs BHSA on the full Mikra run (reuses the M3 pilot comparison)
"""

STATS_VERSION = "1"
