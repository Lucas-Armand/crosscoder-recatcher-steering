# Differential feature candidates for causal validation

## Selection rule

Candidates below have exact paired task/label alignment, the expected
model-side contribution sign, support in at least five tasks, and
category-specific `p_maxT <= 0.05` after searching all valid features and all
four mechanisms. The run used 200 permutations and seed 42.

Only three features pass this initial adjusted threshold. No
improvement-associated feature passes it. This is a useful negative result:
the current data support targeted regression experiments more strongly than
claims about causal mechanisms of improvement.

## Tier 1

### CodeLlama base versus merged: feature 8994

- benchmark: BigCodeBench;
- mechanism: variant decrease associated with regression;
- PR-AUC: 0.986;
- normalized effect: 0.777;
- E/V: 3.31;
- `p_maxT`: 0.0348;
- median delta in regressions: -0.342;
- median delta in preserved successes: +0.248.

Interpretation: when the base solution passes, regressions after merging are
associated with losing base-side contribution to feature 8994. This is the
cleanest current candidate for a useful feature removed by merging.

Largest aligned regression deltas include BigCodeBench tasks 415 (-2.46), 1083
(-1.61), 974 (-1.48), 756 (-1.47), and 536 (-1.41).

Causal prediction: restoring/clamping this feature upward in the merged model
should produce fail-to-pass transitions; subtracting it in the base model
should risk reproducing the failure.

### CodeLlama base versus merged: feature 11586

- benchmark: BigCodeBench;
- mechanism: variant decrease associated with regression;
- PR-AUC: 0.986;
- normalized effect: 0.768;
- E/V: 3.31;
- `p_maxT`: 0.0498;
- median delta in regressions: -0.650;
- median delta in preserved successes: +0.190.

This has the same mechanistic interpretation as feature 8994 and an even larger
median loss in regression tasks, although its adjusted evidence is at the
threshold.

Largest aligned regression deltas include tasks 135 (-1.97), 536 (-1.92), 983
(-1.88), 504 (-1.88), and 841 (-1.75).

## Tier 2

### DeepSeek base versus fine-tuned: feature 2562

- benchmark: BigCodeBench;
- mechanism: variant increase associated with regression;
- PR-AUC: 0.598;
- normalized effect: 0.389;
- E/V: 5.79;
- `p_maxT`: 0.0448;
- median delta in regressions: +1.150;
- median delta in preserved successes: +0.774.

Fine-tuning increases this contribution more strongly in regression tasks, but
the contribution also increases in preserved successes. It is statistically
adjusted but mechanistically less clean than the CodeLlama candidates.

Largest aligned regression deltas include tasks 240 (+2.68), 589 (+2.29), 134
(+2.20), 238 (+2.11), and 133 (+2.11).

Causal prediction: suppressing the feature in the fine-tuned model should
reduce regressions; increasing it in the base model should risk inducing them.

## Exploratory coverage gaps

- DeepSeek base versus merged: no adjusted candidate; the closest
  regression-oriented feature is 10786 (`p_maxT=0.194`).
- CodeLlama base versus fine-tuned: no adjusted candidate; the closest
  regression-oriented feature is 8847 on HumanEval+ (`p_maxT=0.159`) or 12529
  on BigCodeBench (`p_maxT=0.154`).
- No improvement mechanism has adjusted evidence in any comparison.
- HumanEval+ has few aligned regressions for the DeepSeek comparisons (2 for
  fine-tuning and 1 for merging), so its regression rankings are not suitable
  for confirmation.

## Required validation before steering

The stored base and variant activations were captured on different generated
texts. Before intervention, run both models on the same prompt and the same
candidate code for each shortlisted task, capture layer 16 on identical token
positions, and confirm the contribution difference.

For features 8994 and 11586, the existing multiplicative steering cannot
reliably restore a feature that is weak or absent. Add a target/clamp mode:

`h' = h + (z_target - z_current) d_feature`.

Use the base task-specific contribution or a conservative base quantile as the
initial target. Calibrate on a small task subset before causal evaluation.
