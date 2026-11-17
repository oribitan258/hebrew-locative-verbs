# Hebrew Corpora Analysis Package

The team's complete analysis of five Hebrew corpora (Mikra, Hazal, Medieval, Haskala, Modern):
- every word with its lemma, part of speech, inflection, prefixes, suffixes, grammatical tree and named-entity
  type ({{TOKENS}} tokens);
- {{UNITS}} sentences with their original text and source;
- the official statistics of the assignment;
- tools that let Claude Code compute new statistics and charts for you.

Built {{BUILT}}. **Private: it contains corpus text. Do not upload it anywhere public.**

## How to start

1. Open this folder in **VS Code** (File → Open Folder…). It is the folder that contains this README.
2. Open **Claude Code** in VS Code.
3. Type **`start`**.

Claude sets everything up. The first time it takes about 20 minutes and includes checking that the download is
complete. Then it shows you what the data contains and suggests things to explore. Answer in your own words;
Claude writes the code, makes the tables and charts, and explains the results.

Your work is saved in `analyses/`. When you want to share it, tell Claude "send to Ori".

## What is where (no need to know this to start)

| Path | Content |
|---|---|
| `CLAUDE.md` | Claude's instructions |
| `official/stats_report.md` | the official statistics report (tables, figures, definitions) |
| `official/results/` | official tables (CSV, opens in Excel) and figures |
| `ASSIGNMENT.md`, `RESEARCH_IDEAS.md` | the assignment in brief; ideas for additional statistics |
| `docs/` | data dictionary and project documentation |
| `data/` | the data (read-only) |
| `hebpack/` | tools Claude uses |
| `analyses/` | **your work** |
| `MANIFEST.json`, `VERIFICATION.json` | checksums of every file; checks run when the package was built |
