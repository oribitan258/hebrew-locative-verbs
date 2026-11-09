# Work Plan: who parses what (generated)

*Generated 2026-11-09T09:26:24+00:00 by `uv run hebloc plan measure` from `config/parse_plan.yaml` (sha256 `b47bc2202975`). Do not edit by hand.*

**Plan status: `draft`, coverage: `pending`, settings: `base-topk-v1`.** While the status is `draft`, `hebloc parse` refuses real slices: wait for Ori's go-ahead.

Sizes are exact model sub-word counts (dicta-il/dictabert-joint@7b1256fc0846 tokenizer). Hours assume the reference rate of 534 sub-words/s measured on Ori's laptop (base + `topk`); your machine may differ, and `hebloc agreement` reports your actual rate.

## Option A: all of Modern

Total 197.8 M sub-words; largest share / average share = 1.001.

| Person | Sub-words | Hours (reference rate) | Slices |
|---|---|---|---|
| Ori | 66.0 M | 34.3 | `mikra`, `hazal`, `modern-blogs`, `modern-haaretz-b10`, `modern-haaretz-b11`, `modern-haaretz-b15`, `modern-haaretz-b08`, `modern-haaretz-b00`, `modern-haaretz-b13`, `modern-haaretz-b07`, `modern-news-other`, `modern-tapuz` |
| Efrat | 65.8 M | 34.2 | `modern-a7`, `modern-haaretz-b04`, `modern-haaretz-b18`, `modern-haaretz-b01`, `modern-haaretz-b12`, `modern-haaretz-b06`, `modern-haaretz-b05`, `modern-haaretz-b09`, `medieval` |
| Adi | 66.0 M | 34.4 | `modern-knesset`, `haskala`, `modern-haaretz-b19`, `modern-haaretz-b03`, `modern-haaretz-b17`, `modern-haaretz-b02`, `modern-haaretz-b14`, `modern-haaretz-b16`, `modern-medical`, `modern-literary` |

## Option B: Modern with a 10% Haaretz document sample

Total 80.4 M sub-words; largest share / average share = 1.006.

| Person | Sub-words | Hours (reference rate) | Slices |
|---|---|---|---|
| Ori | 26.9 M | 14.0 | `mikra`, `hazal`, `modern-blogs`, `modern-haaretz-b00`, `modern-news-other`, `modern-tapuz` |
| Efrat | 26.5 M | 13.8 | `modern-a7`, `modern-haaretz-b01`, `medieval` |
| Adi | 27.0 M | 14.0 | `modern-knesset`, `haskala`, `modern-medical`, `modern-literary` |

## Slices

| Slice | Corpus | Units | Whitespace tokens | Sub-words | Units over budget | In option |
|---|---|---|---|---|---|---|
| `mikra` | mikra | 23,206 | 328,720 | 387,454 | 0 | A, B |
| `hazal` | hazal | 418,758 | 6,503,346 | 8,551,724 | 149 | A, B |
| `medieval` | medieval | 115,415 | 3,522,454 | 4,320,398 | 73 | A, B |
| `haskala` | haskala | 275,166 | 5,428,359 | 7,408,362 | 206 | A, B |
| `modern-a7` | modern | 805,398 | 14,776,314 | 15,633,208 | 0 | A, B |
| `modern-news-other` | modern | 105,668 | 2,154,127 | 2,373,507 | 14 | A, B |
| `modern-knesset` | modern | 873,131 | 14,795,922 | 15,341,149 | 0 | A, B |
| `modern-blogs` | modern | 801,171 | 6,867,497 | 7,827,789 | 2 | A, B |
| `modern-medical` | modern | 186,926 | 2,422,057 | 2,639,963 | 0 | A, B |
| `modern-tapuz` | modern | 80,671 | 936,836 | 1,278,624 | 0 | A, B |
| `modern-literary` | modern | 83,534 | 1,432,965 | 1,562,520 | 0 | A, B |
| `modern-haaretz-b00` | modern | 294,338 | 5,999,179 | 6,491,374 | 15 | A, B |
| `modern-haaretz-b01` | modern | 299,143 | 6,068,477 | 6,568,365 | 10 | A, B |
| `modern-haaretz-b02` | modern | 294,782 | 6,008,826 | 6,504,885 | 18 | A |
| `modern-haaretz-b03` | modern | 299,136 | 6,061,006 | 6,563,207 | 10 | A |
| `modern-haaretz-b04` | modern | 302,525 | 6,137,438 | 6,644,351 | 13 | A |
| `modern-haaretz-b05` | modern | 293,449 | 5,987,938 | 6,483,366 | 14 | A |
| `modern-haaretz-b06` | modern | 298,948 | 6,024,306 | 6,519,533 | 17 | A |
| `modern-haaretz-b07` | modern | 290,528 | 5,882,817 | 6,369,326 | 12 | A |
| `modern-haaretz-b08` | modern | 297,243 | 6,035,662 | 6,532,358 | 14 | A |
| `modern-haaretz-b09` | modern | 292,218 | 5,970,913 | 6,463,644 | 18 | A |
| `modern-haaretz-b10` | modern | 301,888 | 6,109,499 | 6,611,517 | 17 | A |
| `modern-haaretz-b11` | modern | 300,279 | 6,079,702 | 6,577,075 | 20 | A |
| `modern-haaretz-b12` | modern | 300,227 | 6,042,408 | 6,540,114 | 13 | A |
| `modern-haaretz-b13` | modern | 293,204 | 5,981,834 | 6,474,551 | 17 | A |
| `modern-haaretz-b14` | modern | 294,433 | 5,990,648 | 6,481,791 | 15 | A |
| `modern-haaretz-b15` | modern | 297,753 | 6,047,493 | 6,546,706 | 21 | A |
| `modern-haaretz-b16` | modern | 293,560 | 5,928,820 | 6,414,583 | 6 | A |
| `modern-haaretz-b17` | modern | 296,971 | 6,041,790 | 6,539,483 | 9 | A |
| `modern-haaretz-b18` | modern | 300,114 | 6,097,699 | 6,600,649 | 11 | A |
| `modern-haaretz-b19` | modern | 299,879 | 6,086,588 | 6,587,952 | 19 | A |

Run id of a slice: `<corpus>/<settings_id>__<slice>`, e.g. `mikra/base-topk-v1__mikra`.
