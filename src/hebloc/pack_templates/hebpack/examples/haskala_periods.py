"""Example 2: Haskala before vs after 1881, and by decade (year from the file name).

Pattern: sentence-level measures come from `unit_metrics` (official definitions); `documents` gives year,
subperiod and genre. Output: analyses/examples/haskala_by_decade.csv + a chart.
"""

from hebpack import ANALYSES
from hebpack.charts import COLORS, new_figure, save
from hebpack.db import q

out = ANALYSES / "examples"
out.mkdir(parents=True, exist_ok=True)

by_period = q("""
    SELECT d.subperiod, d.genre, count(*) AS sentences, avg(m.n_words) AS mean_length,
           median(m.n_words) AS median_length, avg(m.depth) AS mean_depth
    FROM unit_metrics m JOIN documents d USING (doc_id)
    WHERE m.corpus_id = 'haskala' AND m.tree_status IN ('complete', 'invalid_tree', 'multi_piece')
    GROUP BY ALL ORDER BY subperiod, genre""")
print(by_period.to_string(index=False))

dec = q("""
    SELECT (d.year // 10) * 10 AS decade, count(*) AS sentences, median(m.n_words) AS median_length,
           avg(m.depth) FILTER (WHERE m.tree_status = 'complete') AS mean_depth
    FROM unit_metrics m JOIN documents d USING (doc_id)
    WHERE m.corpus_id = 'haskala' AND d.year IS NOT NULL
      AND m.tree_status IN ('complete', 'invalid_tree', 'multi_piece')
    GROUP BY 1 ORDER BY 1""")
dec.to_csv(out / "haskala_by_decade.csv", index=False, encoding="utf-8-sig")
fig, ax = new_figure("Haskala: median sentence length by decade", "decade", "words")
ax.plot(dec.decade, dec.median_length, color=COLORS["haskala"], marker="o")
ax.axvline(1881, color="#999999", linestyle="--", linewidth=1)
print("wrote", save(fig, "haskala_length_by_decade", out))
