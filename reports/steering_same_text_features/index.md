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

## 512-token stronger-dose follow-up

The same fixed task sets were rerun with the original 512-token budget and
stronger negative doses. This follow-up preserved the earlier run rather than
overwriting it.

| Feature | Arm | Passed | Fail to pass | Pass to fail | Evaluated code changed | Mean intervention/residual |
|---:|---:|---:|---:|---:|---:|---:|
| 6258 | 0 | 3/15 | 0 | 0 | 0/15 | 0 |
| 6258 | -0.50 P99 | 3/15 | 0 | 0 | 2/15 | 0.01618 |
| 6258 | -1.00 P99 | 3/15 | 0 | 0 | 3/15 | 0.03240 |
| 6873 | 0 | 3/15 | 0 | 0 | 0/15 | 0 |
| 6873 | -0.50 P99 | 3/15 | 0 | 0 | 2/15 | 0.01330 |
| 6873 | -1.00 P99 | 3/15 | 0 | 0 | 2/15 | 0.02660 |

No verdict changed. The larger doses did, however, expose a semantically
coherent effect. For feature 6258 at -1.00 P99, HumanEval/160 changed from
`# Write your code here; pass` to a complete arithmetic implementation. The new
implementation remained incorrect. For feature 6873, HumanEval/143 changed from
`TODO; pass` to `TODO; return ""`; it also remained incorrect. Both features
also changed repeated helper-function naming or long suffixes in a small number
of examples.

Increasing the token budget fixed HumanEval/151's truncation but did not fully
restore the historical controls: only three of five passed in each zero arm.
One historically failed task also passed in each contemporary zero arm. The
paired zero-versus-steering comparison is still internally valid, but the old
labels are not a reliable substitute for a fresh baseline verdict.

The result supports a narrow mechanistic hypothesis: these decoder directions
influence placeholder/incomplete-code style, but simply subtracting either
direction is insufficient to produce correct programs. A next experiment should
use baseline-reproducing tasks, add a norm-matched random-direction control, and
intervene selectively near tokens where the feature is active rather than at
every decoding step.

## High-dose follow-up: -2, -3, and -4 P99

The same paired samples and 512-token generation budget were retained. All six
new arms completed without numerical or GPU failures.

| Feature | Arm | Passed | Fail to pass | Pass to fail | Evaluated code changed | Syntax-valid | Mean intervention/residual |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 6258 | -2 P99 | 3/15 | 0 | 0 | 6/15 | 9/15 | 0.06484 |
| 6258 | -3 P99 | 3/15 | 0 | 0 | 6/15 | 9/15 | 0.09727 |
| 6258 | -4 P99 | 3/15 | 0 | 0 | 7/15 | 9/15 | 0.12971 |
| 6873 | -2 P99 | 3/15 | 0 | 0 | 4/15 | 7/15 | 0.05291 |
| 6873 | -3 P99 | 3/15 | 0 | 0 | 5/15 | 8/15 | 0.07956 |
| 6873 | -4 P99 | 3/15 | 0 | 0 | 5/15 | 8/15 | 0.10618 |

The intervention produces a clear dose-response in the probability of changing
the generated program, but no dose-response in functional correctness. Feature
6258 continues to turn some placeholders into concrete implementation attempts;
for example, HumanEval/160 receives a complete arithmetic loop, but it remains
incorrect. Other changes are mostly helper renaming, comments, repeated suffixes,
or equivalent rewrites of already passing code.

For feature 6873, the high-dose regime is actively concerning. At -4 P99,
HumanEval/151 changes from a nontrivial algorithm to `return 0`, HumanEval/115
expands a placeholder into a long sequence of repetitive comments, and
HumanEval/143 removes the TODO comment while retaining `pass`. These are signs of
distributional distortion, not targeted repair.

The practical conclusion is that increasing traditional-steering magnitude past
-1 P99 makes the decoder direction behaviorally stronger without improving the
target outcome. The absence of verdict regressions is partly masked by the low
contemporary baseline pass rate and must not be interpreted as safety. Further
magnitude escalation is not justified on this sample. The next useful test is a
feature-gated intervention or a norm-matched random-direction control, not a
larger constant alpha.
