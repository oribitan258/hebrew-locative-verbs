"""§5–§6 locative-verb machinery under the shared methodology ``S56-v1``.

Normative specification: ``docs/EFRAT_SECTION_6.md`` §5 (decisions D-053–D-057).

Release R1 (this package so far):

- ``lexicon``   the verb lexicon (``config/locative_verbs.yaml``) + generated forms file; checks
- ``identify``  which tokens are occurrences of which entry (one token = one instance; combined keys)
- ``tree``      direct objects and prepositional phrases read from Dicta's dependency trees
- ``gold``      the deterministic gold sampler, local annotation sheets, and the text-free gold check
- ``nouns``     frequent-argument-noun lists (to be typed by a human) and the reviewed-types merge
- ``source``    one reader for the repo's registered runs or the D-051 analysis package
- ``manifest``  provenance (git state, hashes, data source) written next to every output

Release R2 (extractor, resolver, classes, identity test, statistics) is not built yet.
"""

METHODOLOGY = "S56-v1"
R1_TAG = "s56-r1"
R2_TAG = "s56-v1"
