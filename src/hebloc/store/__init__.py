"""M4 data layer: storage primitives and services shared by every milestone.

- ``io``         crash-safe (atomic) writers, hashing, SQL quoting
- ``schemas``    registry of every persisted table (schema, key, version, location)
- ``runs``       parse-run discovery/references and the canonical-run registry
- ``catalog``    DuckDB views over all Parquet tables (``hebloc catalog``)
- ``integrity``  read-only checks of the whole data layer (``hebloc check``)
- ``conllu``     CoNLL-U export from stored raw output (``hebloc export-conllu``)
- ``bundle``     verified backup/sharing bundles, D-012 (``hebloc bundle``)

The public read API is ``hebloc.data``. Usage guide: ``docs/data_layer.md``.
"""
