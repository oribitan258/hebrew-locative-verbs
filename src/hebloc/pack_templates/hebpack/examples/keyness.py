"""Example 3: keyness, i.e. which lemmas are characteristic of one corpus compared with another.

Log-likelihood (Dunning's G2) on lemma frequencies; [BLANK] lemmas excluded (as in the official tables).
Usage: uv run python -m hebpack.examples.keyness mikra hazal
Output: analyses/examples/keyness_<a>_vs_<b>.csv (Hebrew stays in the CSV; open it in Excel or VS Code).
"""

import sys

import numpy as np

from hebpack import ANALYSES
from hebpack.db import q

a, b = sys.argv[1:3] if len(sys.argv) >= 3 else ("mikra", "hazal")
out = ANALYSES / "examples"
out.mkdir(parents=True, exist_ok=True)

df = q("""
    SELECT lemma,
           count(*) FILTER (WHERE corpus_id = $1) AS n_a,
           count(*) FILTER (WHERE corpus_id = $2) AS n_b
    FROM words WHERE corpus_id IN ($1, $2) AND NOT lemma_blank
    GROUP BY lemma""", params=[a, b])
na, nb = df.n_a.sum(), df.n_b.sum()
tot = df.n_a + df.n_b
ea, eb = tot * na / (na + nb), tot * nb / (na + nb)
with np.errstate(divide="ignore", invalid="ignore"):
    g2 = 2 * (np.where(df.n_a > 0, df.n_a * np.log(df.n_a / ea), 0) + np.where(df.n_b > 0, df.n_b * np.log(df.n_b / eb), 0))
df["per_million_a"] = 1e6 * df.n_a / na
df["per_million_b"] = 1e6 * df.n_b / nb
df["g2"] = g2
df["direction"] = np.where(df.per_million_a > df.per_million_b, a, b)
df = df[tot >= 10].sort_values("g2", ascending=False)
path = out / f"keyness_{a}_vs_{b}.csv"
df.to_csv(path, index=False, encoding="utf-8-sig")
print(df.groupby("direction").head(15).to_string(index=False))
print("wrote", path)
