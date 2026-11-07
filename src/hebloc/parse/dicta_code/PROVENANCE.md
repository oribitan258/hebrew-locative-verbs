# Vendored Dicta model code (unmodified)

These four files are **byte-identical** copies of the custom model code published in the Hugging
Face repository `dicta-il/dictabert-joint` at revision
`7b1256fc0846e22d1af431eae299e2dcecee2778` (licence CC-BY-4.0, © Dicta: The Israel Center for
Text Analysis; Shmidman et al. 2023). Their sha256 checksums are pinned in `config/models.yaml`
and verified by `hebloc.parse.models` before every model load.

Why vendored:
- the code is executed in-process, so it was reviewed (2026-11-07) before first use: no network,
  file, subprocess, `exec`/`eval` or pickle access;
- `dictabert-tiny-joint` has no code of its own; its `auto_map` points at the base repository with
  no revision, which would otherwise download whatever code is current at run time.

Do **not** edit these files. Known behaviours that the wrapper (`hebloc.parse.run`) handles:
- inputs are tokenized with `truncation=True` (max 512 sub-words incl. [CLS]/[SEP]); text beyond
  the limit is silently dropped. Units are therefore split into pieces ≤ 510 sub-words beforehand
  (`hebloc.pieces`), and every output is checked for complete coverage of its input;
- `convert_output_to_ud` calls `exit(0)` on malformed input; it is only called through a guarded
  wrapper on a deep copy;
- the MST tree decoder can raise `ValueError` ("Stuck in endless loop…"); this is caught, logged,
  and the piece is re-parsed with `compute_syntax_mst=False` (flagged).
