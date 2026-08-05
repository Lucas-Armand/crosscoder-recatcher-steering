# Negative steering of regression-associated feature 7608

## Objective

Test whether subtracting DeepSeek finetuned-side decoder feature 7608 can
convert selected BigCodeBench regressions from failure to pass. The paired
P95 screen classified this feature as
`variant_increase_associated_with_regression` (PR-AUC 0.6167, ROC-AUC 0.7045,
E/V 6.05, maxT-adjusted p=0.0348).

## Selection and reproduction gate

The ten historical `base_pass_variant_fail` tasks with the largest positive
finetuned-minus-base P95 contribution were regenerated without intervention.
Three passed under the current stochastic baseline and were excluded. The five
highest-differential reproduced failures were retained:

| Task | Base contribution | Finetuned contribution | Difference |
|---|---:|---:|---:|
| BigCodeBench/1130 | 1.7715 | 4.3927 | 2.6212 |
| BigCodeBench/57 | 1.0303 | 3.3490 | 2.3187 |
| BigCodeBench/67 | 1.5339 | 3.5807 | 2.0467 |
| BigCodeBench/58 | 1.3857 | 3.4124 | 2.0267 |
| BigCodeBench/908 | 2.0198 | 3.9424 | 1.9226 |

## Intervention

Traditional last-token steering was applied at layer 16 on every autoregressive
step using the finetuned-side decoder vector. Negative alpha tests the predicted
removal direction; `+2` is the directionality control. Generation matches the
paper-v1 smoke regime: float16, 512 new tokens, temperature 0.2, top-p 0.95,
and stored per-task seeds. Postprocessing uses extraction v4 and evaluation uses
the isolated official BigCodeBench 0.1.5 subset harness.

Alpha is a direct decoder-vector multiplier, not P95 activation scaling. The
decoder norm is approximately 0.68115.

## Results

| Alpha | Intervention norm | Raw completions changed | Evaluated code changed | Passed |
|---:|---:|---:|---:|---:|
| -0.5 | 0.3406 | 2/5 | 0/5 | 0/5 |
| -1 | 0.6812 | 2/5 | 0/5 | 0/5 |
| -2 | 1.3623 | 2/5 | 0/5 | 0/5 |
| -3 | 2.0435 | 2/5 | 0/5 | 0/5 |
| -4 | 2.7246 | 3/5 | 0/5 | 0/5 |
| +2 | 1.3623 | 1/5 | 0/5 | 0/5 |

There were no fail-to-pass transitions. More importantly, every raw change
occurred after the prefix retained by extraction v4: the exact evaluated code
was invariant in all 30 generations. The negative doses mainly changed trailing
explanations, examples, and repetitive comments in tasks 57 and 908. At -4,
task 1130 additionally drifted into Markdown and an unrelated Kotlin task after
the retained Python solution. Tasks 58 and 67 were byte-identical throughout.

## Interpretation

This is not evidence that feature 7608 is globally non-causal. It is evidence
against the tested claim that unconditional traditional subtraction of its
decoder vector, at direct doses through -4, repairs the evaluated program in
these five selected regressions. The hook affects continuation style, but only
after the evaluator cutoff.

The observational P95 association is measured inside evaluated tokens, while
the visible generation effect appears later. Before increasing alpha further,
the useful diagnostic is activation-gated or activation-matched intervention:
measure feature 7608 during generation and subtract/clamp it only at positions
where it is active, especially before the first incorrect program decision.
That directly tests the proposed harmful mechanism and avoids accumulating a
constant direction in irrelevant suffix tokens.

## Same-text token-feature map

The [top-500 same-text heatmap for BigCodeBench/1130](task_1130_top500_same_text_heatmap.png)
forwards both the base-generated and finetuned-generated evaluated code through
both models. Rows are fixed across all panels and ranked by the base-side P80 on
the base-generated text; the two right-hand panels show finetuned-minus-base
encoder contribution on each controlled text.

Feature 7608 has natural rank **3540**, so it is not silently presented as a
top-500 feature. It is appended as row 501 and outlined/labeled in green. The
source token counts are 163 for the base-generated code and 277 for the
finetuned-generated code. The accompanying
[machine-readable metadata](task_1130_top500_same_text_heatmap.json) records the
complete feature order and boundary information.
