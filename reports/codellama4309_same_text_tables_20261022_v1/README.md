# CodeLlama feature 4309: natural and same-text tables

The three-page `CODELLAMA4309_NATURAL_AND_SAME_TEXT_TABLES.pdf` gives the CodeLlama analogues of the DeepSeek tables, with an explicit change of temporal anchor. No GPU/model execution, generation or new evaluation was performed.

## Natural expression on different generated texts

50 original BigCodeBench base-pass / merged-fail task pairs. The same joint sparse CrossCoder feature is measured on the base-generated or merged-generated text, not independently activated in one model.

| Metric | Base-generated text | Merged-generated text |
|---|---:|---:|
| Any activation | 50/50 | 44/50 |
| Mean task-mean activation | 0.199695 | 0.197944 |
| Median first activation, among active texts | 31.5% | 58.9% |
| First activation strictly after main-function end | 0/50 | 0/50 |

The ending newline is included in the function; activation on that newline is NOT classified after-function. First activation can still be followed by later activations elsewhere. Normalized positions across different texts do not imply that the same event was delayed. Mean activation is not greater in failing merged text for this cohort.

## Same-text contributions

Both models replay the exact SAME original failing merged text. We verify identical token IDs for all 100 text/model pairs (50 tasks times two source texts). Encoder contributions are the separate terms of one shared preactivation, before a single shared bias, ReLU and joint TopK. Negative mean contributions are not negative sparse activations; less negative is numerically larger.

| Scope | Base contribution | Merged contribution | Merged lower |
|---|---:|---:|---:|
| All tokens | -0.999 | -0.428 | 2/50 |
| 10 tokens before region start | -0.791 | -0.210 | 12/48 |
| Region start plus next 10 | -1.238 | -0.584 | 5/48 |
| Region start +/-10 | -1.125 | -0.504 | 4/48 |

The region anchor reuses previously documented failure localization: runtime execution sites, provisional lines/intervals, and omission regions. These are NOT validated earliest semantic errors and NOT a uniform test/import heuristic as used in DeepSeek. The anchor is mapped from current alpha-zero code to frozen source only through an exact matching block. /115 and /423 have no matching start anchor, so local rows have 48 rather than 50 tasks. They remain in the whole-text table; no approximate anchor is invented. Available token windows are clipped at code boundaries.

## Readout sensitivity and localization

Around the localized region, own-branch normalized encoder alignment is larger in merged in 42/48 cases; own-branch decoder cosine is larger in 40/48. But projecting BOTH model residuals onto one common mean-of-unit-decoder direction makes the merged alignment smaller in 45/48. Thus it is not defensible to summarize every measurement as a robust increase in independent feature activation. The own model-specific readouts and fixed-vector geometric comparisons answer different questions.

The raw encoder contribution difference is already large across the whole text. A local-versus-outside check has only 45 eligible tasks (3 local windows cover the entire frozen text, in addition to 2 unavailable anchors). Its raw-contribution contrast is more positive locally in 26/45; mean +0.09165. This is weaker localization than observed for DeepSeek. Exact paired bootstrap intervals and all normalized metrics are saved separately, without multiplicity-corrected significance claims.

These are exploratory geometric comparisons on the selected discovery cohort. They do not prove that feature 4309 mediates regression, and a shared feature that supports useful interventions need not have a simple natural activation difference between models. No claims of generalization or specificity against random features follow from these tables.

## Files / reproduce

- `natural_summary.json`, `natural_task_metrics.json`: natural-text quantities.
- `paired_summary.json`, `task_scope_metrics.json` / `.csv`: all sources, regions, readouts and equal-task summaries.
- `local_specificity_summary.json`: within-window minus outside-window paired model contrast.
- `per_token_measurements.npz`: each replayed text's contributions and normalized readouts.
- `VALIDATION.json`: token identity checks, checkpoint/input hashes, weight norms, missing anchors, and cached active-z reconstruction check (max error below 1e-5).

Run `tools/analyze_4309_same_text_tables_v1.py` using the existing original capture corpus. Natural measurements and temporal coordinates are taken from frozen capture text; localization is mapped explicitly from current re-extracted baseline. The script does not silently substitute one code version for the other.
