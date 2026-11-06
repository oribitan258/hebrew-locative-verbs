# Corpus inventory — summary tables

> **Auto-generated** by `uv run hebloc inventory` from `data/catalog/documents.parquet`. Do not edit by hand. Full CSVs: `results/inventory/`. Interpretation: `docs/corpus_report.md`.

Definitions: *line* = `\n`-delimited; *token* = whitespace-separated run; *Hebrew token* = token containing ≥1 Hebrew letter (U+05D0–U+05EA).

**Views (D-015):** *FULL* = every corpus text file as supplied — the **primary reference**. *CURATED* = an additional analytical view: full minus blank files, documents not tagged `in_period`, and exact duplicate copies within the same stratum and source.

## Per-corpus totals: FULL view (primary reference) and CURATED view (additional)
`results/inventory/corpus_summary.csv`

| corpus_id | files_cataloged | empty_files | auxiliary_files | mib | full_files | full_nonempty_lines | full_tokens | full_hebrew_tokens | curated_files | curated_hebrew_tokens | curated_pct_of_full |
|---|---|---|---|---|---|---|---|---|---|---|---|
| mikra | 39 | 0 | 0 | 5.2 | 39 | 23,206 | 270,170 | 267,866 | 39 | 267,866 | 100 |
| hazal | 204 | 0 | 0 | 62.9 | 204 | 118,481 | 6,503,364 | 6,493,912 | 147 | 2,588,484 | 39.9 |
| medieval | 1,128 | 91 | 0 | 31.3 | 1,037 | 44,457 | 3,523,084 | 3,459,940 | 1,024 | 2,848,979 | 82.3 |
| haskala | 320 | 0 | 0 | 49.1 | 320 | 72,284 | 5,437,243 | 5,336,775 | 317 | 5,336,775 | 100 |
| modern | 402,603 | 7 | 100 | 926.1 | 402,496 | 8,617,412 | 167,057,568 | 134,095,012 | 396,231 | 132,320,112 | 98.7 |

## Strata and period status (tags only — nothing is deleted)
`results/inventory/stratum_summary.csv`

| corpus_id | stratum | period_status | files | nonempty_lines | hebrew_tokens | curated_files | curated_hebrew_tokens |
|---|---|---|---|---|---|---|---|
| mikra | mikra.prophets | in_period | 21 | 9,296 | 123,812 | 21 | 123,812 |
| mikra | mikra.torah | in_period | 5 | 5,846 | 69,318 | 5 | 69,318 |
| mikra | mikra.writings | in_period | 13 | 8,064 | 74,736 | 13 | 74,736 |
| hazal | hazal.aggadic_midrash | in_period | 18 | 9,569 | 1,679,281 | 18 | 1,679,281 |
| hazal | hazal.commentary | out_of_period | 54 | 83,874 | 2,465,663 | 0 | 0 |
| hazal | hazal.halakhic_midrash | in_period | 5 | 6,665 | 421,430 | 5 | 421,430 |
| hazal | hazal.late_anthology | out_of_period | 2 | 10,100 | 1,437,008 | 0 | 0 |
| hazal | hazal.mishnah | in_period | 63 | 4,192 | 192,535 | 63 | 192,535 |
| hazal | hazal.post_talmudic | out_of_period | 1 | 10 | 2,757 | 0 | 0 |
| hazal | hazal.tosefta | in_period | 61 | 4,071 | 295,238 | 61 | 295,238 |
| medieval | medieval.later_commentary | out_of_period | 3 | 11,630 | 282,839 | 0 | 0 |
| medieval | medieval.mishneh_torah | in_period | 1,091 | 14,947 | 637,790 | 1,000 | 637,790 |
| medieval | medieval.musar | in_period | 10 | 2,961 | 348,198 | 10 | 348,198 |
| medieval | medieval.musar_translated | in_period | 2 | 857 | 21,818 | 2 | 21,818 |
| medieval | medieval.musar_unverified | needs_review | 7 | 2,907 | 218,404 | 0 | 0 |
| medieval | medieval.post_medieval | out_of_period | 3 | 2,036 | 109,718 | 0 | 0 |
| medieval | medieval.thought | in_period | 7 | 5,199 | 1,491,214 | 7 | 1,491,214 |
| medieval | medieval.thought_translated | in_period | 5 | 3,920 | 349,959 | 5 | 349,959 |
| haskala | haskala.belles_lettres | in_period | 122 | 36,757 | 1,955,102 | 121 | 1,955,102 |
| haskala | haskala.essays_press | in_period | 166 | 20,019 | 1,859,125 | 164 | 1,859,125 |
| haskala | haskala.science | in_period | 32 | 15,508 | 1,522,548 | 32 | 1,522,548 |
| modern | modern.auxiliary | out_of_period | 100 | 99,541 | 0 | 0 | 0 |
| modern | modern.blogs | in_period | 11,176 | 763,821 | 5,218,145 | 10,524 | 4,930,565 |
| modern | modern.forum.tapuz | in_period | 255 | 75,919 | 672,089 | 244 | 611,295 |
| modern | modern.knesset | in_period | 282 | 867,725 | 11,532,134 | 282 | 11,532,134 |
| modern | modern.literary.original | in_period | 1 | 34,496 | 565,510 | 1 | 565,510 |
| modern | modern.literary.translated | in_period | 1 | 43,683 | 593,519 | 1 | 593,519 |
| modern | modern.medical | in_period | 12,750 | 185,189 | 1,979,973 | 12,671 | 1,923,273 |
| modern | modern.news.a7 | in_period | 92,273 | 799,437 | 12,447,305 | 91,903 | 12,404,224 |
| modern | modern.news.haaretz | in_period | 279,359 | 5,744,309 | 99,351,410 | 274,206 | 98,024,800 |
| modern | modern.news.nrg | in_period | 2,500 | 24,796 | 401,446 | 2,493 | 401,311 |
| modern | modern.news.themarker | in_period | 837 | 31,542 | 569,021 | 837 | 569,021 |
| modern | modern.news.ynet | in_period | 3,069 | 46,495 | 764,460 | 3,069 | 764,460 |

## Detected encodings
`results/inventory/encoding_summary.csv`

| corpus_id | subcorpus | encoding | line_endings | files | mib |
|---|---|---|---|---|---|
| mikra |  | utf-8 | crlf | 39 | 5.2 |
| hazal | Midrash | utf-8 | crlf | 80 | 57.4 |
| hazal | Mishnah | utf-8 | crlf | 63 | 2.9 |
| hazal | Tosefta | utf-8 | crlf | 61 | 2.6 |
| medieval | Musar | utf-8 | crlf | 22 | 6.4 |
| medieval | Rambam | empty | none | 91 | 0 |
| medieval | Rambam | utf-8 | lf | 1,000 | 5.6 |
| medieval | Thought | utf-8 | crlf | 15 | 19.3 |
| haskala |  | ascii | none | 3 | 0 |
| haskala |  | utf-8 | lf | 316 | 49.1 |
| haskala |  | utf-8 | none | 1 | 0 |
| modern | blogs | ascii | lf | 57 | 0 |
| modern | blogs | cp1255 | lf | 11,119 | 30.1 |
| modern | kneset | cp1255 | lf | 282 | 66.1 |
| modern | literary | cp1255 | lf | 2 | 6.8 |
| modern | medical | ascii | lf | 1 | 0 |
| modern | medical | cp1255 | lf | 12,749 | 11.7 |
| modern | news | ascii | lf | 101 | 3 |
| modern | news | cp1255 | lf | 378,030 | 803.7 |
| modern | news | empty | none | 7 | 0 |
| modern | tapuz | cp1255 | lf | 255 | 4.6 |

## Modern sub-corpora and sources
`results/inventory/modern_sources.csv`

| subcorpus | source | files | duplicate_copies | non_text_or_blank | mib | nonempty_lines | hebrew_tokens | pct_of_modern_tokens |
|---|---|---|---|---|---|---|---|---|
| news | haaretz | 279,459 | 5,146 | 107 | 722.7 | 5,843,850 | 99,351,410 | 74.1 |
| news | a7 | 92,273 | 370 | 0 | 72 | 799,437 | 12,447,305 | 9.3 |
| kneset | knesset_16 | 164 | 0 | 0 | 40.9 | 543,228 | 7,140,457 | 5.3 |
| blogs |  | 11,176 | 652 | 0 | 30.1 | 763,821 | 5,218,145 | 3.9 |
| kneset | knesset_17 | 118 | 0 | 0 | 25.2 | 324,497 | 4,391,677 | 3.3 |
| medical | questions | 11,123 | 0 | 0 | 8.4 | 140,375 | 1,427,375 | 1.1 |
| news | ynet | 3,069 | 0 | 0 | 5.6 | 46,495 | 764,460 | 0.6 |
| tapuz |  | 255 | 11 | 0 | 4.6 | 75,919 | 672,089 | 0.5 |
| literary | translated | 1 | 0 | 0 | 3.4 | 43,683 | 593,519 | 0.4 |
| news | themarker | 837 | 0 | 0 | 3.4 | 31,542 | 569,021 | 0.4 |
| literary | original | 1 | 0 | 0 | 3.4 | 34,496 | 565,510 | 0.4 |
| news | nrg | 2,500 | 7 | 0 | 3 | 24,796 | 401,446 | 0.3 |
| medical | doctors | 290 | 61 | 0 | 1.1 | 12,315 | 188,430 | 0.1 |
| medical | infomed | 1,086 | 1 | 0 | 0.9 | 15,045 | 157,268 | 0.1 |
| medical | bari | 192 | 16 | 0 | 0.9 | 12,571 | 145,920 | 0.1 |
| medical | ripui | 59 | 1 | 0 | 0.4 | 4,883 | 60,980 | 0 |

## Haskala: publication year sub-periods (cut-off from config/curation.yaml)
`results/inventory/haskala_subperiods.csv`

| subperiod | genre | files | min_year | max_year | hebrew_tokens |
|---|---|---|---|---|---|
| haskala | ספרות יפה | 20 | 1,853 | 1,881 | 774,178 |
| haskala | ספרות מדע | 28 | 1,765 | 1,878 | 1,395,936 |
| haskala | עיון, עיתונות ופובליציסטיקה | 56 | 1,755 | 1,880 | 1,168,010 |
| post_haskala | ספרות יפה | 102 | 1,885 | 1,934 | 1,180,924 |
| post_haskala | ספרות מדע | 4 | 1,886 | 1,920 | 126,612 |
| post_haskala | עיון, עיתונות ופובליציסטיקה | 110 | 1,882 | 1,933 | 691,115 |

## Vocalization (niqqud) and cantillation by stratum (text files)
`results/inventory/vocalization.csv`

| corpus_id | stratum | files | niqqud_per_letter | cantillation_per_letter | files_mostly_vocalized |
|---|---|---|---|---|---|
| mikra | mikra.prophets | 21 | 0.862 | 0.203 | 21 |
| mikra | mikra.torah | 5 | 0.882 | 0.206 | 5 |
| mikra | mikra.writings | 13 | 0.864 | 0.193 | 13 |
| hazal | hazal.aggadic_midrash | 18 | 0.464 | 0 | 11 |
| hazal | hazal.commentary | 54 | 0 | 0 | 0 |
| hazal | hazal.halakhic_midrash | 5 | 0.004 | 0 | 0 |
| hazal | hazal.late_anthology | 2 | 0 | 0 | 0 |
| hazal | hazal.mishnah | 63 | 0.808 | 0 | 63 |
| hazal | hazal.post_talmudic | 1 | 0 | 0 | 0 |
| hazal | hazal.tosefta | 61 | 0 | 0 | 0 |
| medieval | medieval.later_commentary | 3 | 0 | 0 | 0 |
| medieval | medieval.mishneh_torah | 1,000 | 0 | 0 | 0 |
| medieval | medieval.musar | 10 | 0.046 | 0 | 4 |
| medieval | medieval.musar_translated | 2 | 0.459 | 0 | 1 |
| medieval | medieval.musar_unverified | 7 | 0 | 0 | 0 |
| medieval | medieval.post_medieval | 3 | 0 | 0 | 0 |
| medieval | medieval.thought | 7 | 0 | 0 | 0 |
| medieval | medieval.thought_translated | 5 | 0.115 | 0 | 1 |
| haskala | haskala.belles_lettres | 122 | 0.013 | 0 | 0 |
| haskala | haskala.essays_press | 166 | 0.001 | 0 | 0 |
| haskala | haskala.science | 32 | 0.011 | 0 | 0 |
| modern | modern.blogs | 11,176 | 0 | 0 | 4 |
| modern | modern.forum.tapuz | 255 | 0.001 | 0 | 0 |
| modern | modern.knesset | 282 | 0 | 0 | 0 |
| modern | modern.literary.original | 1 | 0.001 | 0 | 0 |
| modern | modern.literary.translated | 1 | 0.004 | 0 | 0 |
| modern | modern.medical | 12,750 | 0 | 0 | 0 |
| modern | modern.news.a7 | 92,273 | 0 | 0 | 0 |
| modern | modern.news.haaretz | 279,352 | 0 | 0 | 0 |
| modern | modern.news.nrg | 2,500 | 0 | 0 | 0 |
| modern | modern.news.themarker | 837 | 0 | 0 | 0 |
| modern | modern.news.ynet | 3,069 | 0 | 0 | 0 |

## Exact duplicates (identical bytes, non-empty files); scope = stratum|source
`results/inventory/duplicates.csv`

| corpus_id | groups_within_scope | copies_excluded_from_curated | hebrew_tokens_in_copies | largest_group_within_scope | files_with_identical_copy_in_other_scope | files_with_identical_copy_in_other_corpus |
|---|---|---|---|---|---|---|
| mikra | 0 | 0 | 0 | 1 | 0 | 0 |
| hazal | 0 | 0 | 0 | 1 | 0 | 0 |
| medieval | 0 | 0 | 0 | 1 | 0 | 0 |
| haskala | 1 | 1 | 0 | 2 | 3 | 0 |
| modern | 4,295 | 6,265 | 1,774,900 | 24 | 0 | 0 |

## Anomaly counts (files affected)
`results/inventory/anomalies.csv`

| corpus_id | lossy_decoding | utf8_bom | stray_feff | control_chars | odd_line_separators | mixed_line_endings | mostly_non_hebrew | latin1_supplement_chars | metadata_issues | longest_line_chars |
|---|---|---|---|---|---|---|---|---|---|---|
| mikra | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 450 |
| hazal | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 29,335 |
| medieval | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 31,474 |
| haskala | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 43,705 |
| modern | 0 | 0 | 0 | 0 | 0 | 0 | 205 | 1 | 0 | 9,977 |

## Markup/tokenization artifacts and near-empty 'stub' files (text files; cleaned in M2)
`results/inventory/artifacts.csv`

| corpus_id | source | files_prefix_tags | prefix_tags | token_tags | img_tags | urls | stub_files_le15_hebrew_tokens | files_without_hebrew |
|---|---|---|---|---|---|---|---|---|
| medieval | Rambam | 87 | 141 | 0 | 0 | 0 | 0 | 0 |
| haskala |  | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| modern | haaretz | 209,487 | 1,149,769 | 8,906 | 0 | 12,374 | 8,695 | 0 |
| modern | ynet | 1,899 | 7,368 | 2 | 0 | 19 | 129 | 0 |
| modern | nrg | 1,120 | 2,075 | 4 | 0 | 9 | 5 | 8 |
| modern | a7 | 0 | 0 | 0 | 115 | 367 | 1,960 | 0 |
| modern | bari | 0 | 0 | 0 | 0 | 60 | 0 | 0 |
| modern | blogs | 0 | 0 | 0 | 0 | 1,625 | 510 | 57 |
| modern | doctors | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| modern | infomed | 0 | 0 | 0 | 0 | 571 | 2 | 0 |
| modern | knesset_16 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| modern | original | 0 | 0 | 1 | 0 | 12 | 0 | 0 |
| modern | questions | 0 | 0 | 0 | 0 | 1 | 108 | 1 |
| modern | tapuz | 0 | 0 | 0 | 0 | 7,679 | 2 | 0 |
| modern | translated | 0 | 0 | 9 | 0 | 16 | 0 | 0 |

## Documents awaiting verification (in the full view; outside the curated view until decided)
`results/inventory/needs_review.csv`

| corpus_id | rel_path | stratum | hebrew_tokens | nonempty_lines |
|---|---|---|---|---|
| medieval | Medieval/Musar/Musar - Ahavat David.txt | medieval.musar_unverified | 170,245 | 1,077 |
| medieval | Medieval/Musar/Musar - Davar Be'ito.txt | medieval.musar_unverified | 23,594 | 81 |
| medieval | Medieval/Musar/Musar - Shekel HaKodesh.txt | medieval.musar_unverified | 8,258 | 1,068 |
| medieval | Medieval/Musar/Musar - Maamar Mezake HaRabim.txt | medieval.musar_unverified | 6,135 | 59 |
| medieval | Medieval/Musar/Musar - Yesod HaYirah.txt | medieval.musar_unverified | 5,241 | 574 |
| medieval | Medieval/Musar/Musar - Shuvah Yisrael.txt | medieval.musar_unverified | 3,315 | 40 |
| medieval | Medieval/Musar/Musar - Letter from Ramban to his Son.txt | medieval.musar_unverified | 1,616 | 8 |

## Out-of-period documents (in the full view; outside the curated view)
`results/inventory/out_of_period.csv`

| corpus_id | stratum | curation_rule | files | hebrew_tokens |
|---|---|---|---|---|
| hazal | hazal.commentary | hazal-commentary | 54 | 2,465,663 |
| hazal | hazal.late_anthology | hazal-yalkut | 2 | 1,437,008 |
| hazal | hazal.post_talmudic | hazal-seder-olam-zutta | 1 | 2,757 |
| medieval | medieval.later_commentary | medieval-thought-later-commentary | 3 | 282,839 |
| medieval | medieval.post_medieval | medieval-musar-modern | 1 | 104,203 |
| medieval | medieval.post_medieval | medieval-musar-known-later | 2 | 5,515 |
| modern | modern.auxiliary | modern-aux-logs | 100 | 0 |

## Why documents are outside the curated view (a document may have several reasons)
`results/inventory/exclusion_reasons.csv`

| corpus_id | reason | files | hebrew_tokens |
|---|---|---|---|
| hazal | period:out_of_period | 57 | 3,905,428 |
| medieval | file_kind:empty | 91 | 0 |
| medieval | period:needs_review | 7 | 218,404 |
| medieval | period:out_of_period | 6 | 392,557 |
| haskala | blank | 3 | 0 |
| haskala | duplicate_copy_within_scope | 1 | 0 |
| modern | duplicate_copy_within_scope | 6,265 | 1,774,900 |
| modern | file_kind:auxiliary | 100 | 0 |
| modern | period:out_of_period | 100 | 0 |
| modern | file_kind:empty | 7 | 0 |
