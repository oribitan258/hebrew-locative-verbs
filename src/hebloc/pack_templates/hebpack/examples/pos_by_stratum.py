"""Example 1: part-of-speech shares per stratum (sub-corpus), all five corpora.

Pattern: aggregate the large `words` view in SQL, joining document metadata on doc_id (cheap: one row per file),
then bring only the small result into pandas. Output: analyses/examples/pos_by_stratum.csv + a chart.
"""

from hebpack import ANALYSES, CORPORA
from hebpack.charts import COLORS, new_figure, save
from hebpack.db import q

out = ANALYSES / "examples"
out.mkdir(parents=True, exist_ok=True)

df = q("""
    WITH c AS (
        SELECT w.corpus_id, d.stratum, w.upos, count(*) AS n
        FROM words w JOIN documents d USING (doc_id)
        GROUP BY ALL)
    SELECT *, n / sum(n) OVER (PARTITION BY corpus_id, stratum) AS share
    FROM c ORDER BY corpus_id, stratum, n DESC""")
df.to_csv(out / "pos_by_stratum.csv", index=False, encoding="utf-8-sig")

order = {c: i for i, c in enumerate(CORPORA)}                 # chronological corpus order, then stratum name
for upos in ("VERB", "ADJ"):
    s = df[df.upos == upos].assign(o=lambda d: d.corpus_id.map(order)).sort_values(["o", "stratum"])
    fig, ax = new_figure(f"{upos}: share of words per stratum", "% of words", "", size=(10, 7))
    ax.barh(s.stratum, 100 * s.share, color=[COLORS[c] for c in s.corpus_id])
    ax.invert_yaxis()
    print("wrote", save(fig, f"{upos.lower()}_share_by_stratum", out))
print("wrote", out / "pos_by_stratum.csv")
