# Percentile sensitivity analysis

The paired score is `P_variant - P_base`, where each P is a token-level
positive model-side CrossCoder encoder-contribution percentile over exact
evaluated tokens. P50, P60, P70, P80, P90, P95, and P99 are searched
jointly with 16,384 features and four signed transition hypotheses.
`p_maxT` therefore corrects the percentile choice as part of the search.

## Main findings

- Analyzed 8 model-pair/benchmark cases with no skipped cases.
- No fail-to-pass candidate passed the joint maxT threshold of 0.05.
- 66 feature/percentile rows passed maxT; these represent 36 unique case-feature pairs, all associated with pass-to-fail transitions.
- Significant rows are distributed across all tested percentiles: P50=8, P60=6, P70=8, P80=8, P90=12, P95=16, P99=8.

The result does not support one universally optimal percentile. Lower and
middle percentiles can outperform P99, showing that broadly sustained
activation differences contain information that a peak-only analysis misses.

## Corrected candidates

### `codellama_base_merged_layer16__bigcodebench__layer16__paired_transitions`

| Feature | P | Direction | PR-AUC | ROC-AUC | E/V | p_maxT |
|---:|---:|---|---:|---:|---:|---:|
| 4815 | P80 | variant_decrease_associated_with_regression | 0.9916 | 0.8806 | 4.10 | 0.0050 |
| 8994 | P99 | variant_decrease_associated_with_regression | 0.9919 | 0.8821 | 3.70 | 0.0050 |
| 13439 | P80 | variant_decrease_associated_with_regression | 0.9914 | 0.8862 | 3.57 | 0.0050 |
| 14336 | P90 | variant_decrease_associated_with_regression | 0.9887 | 0.8448 | 3.90 | 0.0100 |
| 4567 | P60 | variant_decrease_associated_with_regression | 0.9882 | 0.8336 | 3.82 | 0.0100 |
| 11344 | P99 | variant_decrease_associated_with_regression | 0.9890 | 0.8534 | 3.80 | 0.0100 |
| 11883 | P70 | variant_decrease_associated_with_regression | 0.9893 | 0.8537 | 3.70 | 0.0100 |
| 9442 | P80 | variant_decrease_associated_with_regression | 0.9889 | 0.8631 | 3.61 | 0.0100 |
| 13681 | P90 | variant_decrease_associated_with_regression | 0.9883 | 0.8399 | 3.55 | 0.0100 |
| 15525 | P95 | variant_decrease_associated_with_regression | 0.9885 | 0.8364 | 3.54 | 0.0100 |
| 2264 | P80 | variant_decrease_associated_with_regression | 0.9902 | 0.8651 | 3.53 | 0.0100 |
| 6058 | P50 | variant_decrease_associated_with_regression | 0.9881 | 0.8361 | 3.50 | 0.0100 |

### `deepseek_base_finetuned_layer16__bigcodebench__layer16__paired_transitions`

| Feature | P | Direction | PR-AUC | ROC-AUC | E/V | p_maxT |
|---:|---:|---|---:|---:|---:|---:|
| 7608 | P95 | variant_increase_associated_with_regression | 0.6167 | 0.7045 | 6.05 | 0.0348 |

## Previously studied features

In CodeLlama base-versus-merged BigCodeBench, feature 8994 is corrected at
P99 (`p_maxT=0.00498`) and P95 (`p_maxT=0.0448`); feature 11586 is corrected
at P99 (`p_maxT=0.0299`) and P95 (`p_maxT=0.0348`). Both are categorized as
variant decrease associated with regression: the model-side contribution is
lower in merged-model regressions than in preserved successes. Feature 2562
does not survive correction at any percentile.

## Interpretation limits

- CodeLlama base-versus-merged BigCodeBench has 246 regressions and only 16
preserved successes among aligned base-pass tasks. Its regression PR baseline
is therefore 0.9389. The normalized effect and maxT result, rather than raw
PR-AUC alone, carry the interpretation.
- HumanEval regression results with one or two positive events are descriptive
only, even when raw PR-AUC equals 1.
- Model-side contributions are additive encoder terms of a joint latent, not
independently encoded activations.
- Stored own-text activations mix checkpoint and generated-text differences.
Same-text confirmation remains necessary before causal steering.
- Failure association does not by itself identify whether adding or removing a
feature decoder will reproduce the transition.

Machine-readable summaries: [percentile comparison](percentile_comparison.csv)
and [corrected feature/percentile rows](significant_feature_percentiles.csv).
