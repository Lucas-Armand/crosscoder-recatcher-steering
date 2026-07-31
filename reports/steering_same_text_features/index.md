# Same-text PR-AUC steering smoke: features 6258 and 6873

## Design

This exploratory test compares the statistically strongest same-text feature
(6258/P99) with the most semantically coherent candidate (6873/max). For each
feature, the sample contains the ten historically failed base solutions with the
highest selected aggregate and five high-activation historical pass controls.

Traditional steering subtracts the feature's base decoder direction from the
last hidden token at every autoregressive step. Generation is greedy with 192
new tokens. Each feature has three paired arms: zero, -0.10 times its observed
P99 scale, and -0.25 times its observed P99 scale. All outputs pass through the
extraction-v4 postprocessor and the local HumanEval+ evaluator.

| Feature | Selection | P99 scale | Effective alpha -0.10 | Effective alpha -0.25 |
|---:|---|---:|---:|---:|
| 6258 | solution P99 | 5.621951 | -0.562195 | -1.405488 |
| 6873 | solution max | 4.554658 | -0.455466 | -1.138665 |

## Results

| Feature | Arm | Passed | Fail to pass | Pass to fail | Evaluated code changed | Mean intervention/residual |
|---:|---:|---:|---:|---:|---:|---:|
| 6258 | 0 | 2/15 | 0 | 0 | 0/15 | 0 |
| 6258 | -0.10 P99 | 2/15 | 0 | 0 | 1/15 | 0.00323 |
| 6258 | -0.25 P99 | 2/15 | 0 | 0 | 1/15 | 0.00807 |
| 6873 | 0 | 3/15 | 0 | 0 | 0/15 | 0 |
| 6873 | -0.10 P99 | 3/15 | 0 | 0 | 1/15 | 0.00266 |
| 6873 | -0.25 P99 | 3/15 | 0 | 0 | 1/15 | 0.00664 |

There were no verdict transitions. For both features and both nonzero arms, the
only evaluated-code change was HumanEval/151. Steering shortened the final
incomplete prose continuation from `If the input list is empty` to
`If the input list is`; the solution remained invalid. All other evaluated code
was byte-identical to the corresponding zero arm.

## Interpretation and limitation

This is a valid negative local-dose result: the tested decoder interventions
were active but usually did not cross a greedy token-decision boundary. It does
not show that the features lack a causal effect at stronger doses.

The baseline reproduced only two of five historical pass controls for feature
6258 and three of five for feature 6873. The most visible discrepancy is a
completion truncated at the 192-token generation limit. Therefore this run
should not be used as a final causal comparison. A confirmatory run should use
the original 512-token budget, require baseline agreement before including a
task, and then test stronger doses (for example -0.5 and -1.0 P99) with a
matched random decoder-direction control.
