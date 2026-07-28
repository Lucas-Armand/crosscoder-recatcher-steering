# Paired differential PR-AUC screening implementation notes

## Objective

This analysis asks which CrossCoder features are associated specifically with
behavioral changes from a base model to its fine-tuned or merged variant.
It does not treat a model's outcome in isolation.

For every task with strict activation/label alignment, the evaluator transition
is one of:

- base pass, variant fail: regression;
- base pass, variant pass: preserved success;
- base fail, variant pass: improvement;
- base fail, variant fail: persistent failure.

Regression screening is conditioned on the base model passing and compares
regressions with preserved successes. Improvement screening is conditioned on
the base model failing and compares improvements with persistent failures.
This avoids comparing regressions and improvements from different baseline
outcome strata.

## Model-side contribution

The current CrossCoder has one joint encoder:

`z = ReLU(W_base h_base + W_variant h_variant + b)`.

It therefore does not produce independent `z_base` and `z_variant` values.
The analysis decomposes the additive preactivation into model-side
contributions:

`c_base = W_base h_base`

`c_variant = W_variant h_variant`.

For each side and feature, the score is the maximum positive contribution over
that side's exact evaluated-token mask. Bias is excluded because it is shared
and cancels in the paired contrast. The task score is:

`delta = max_positive(c_variant) - max_positive(c_base)`.

The report deliberately calls these values model-side contributions, not
model-specific latent activations.

## Four mechanistic searches

The jointly corrected searches are:

1. variant increase associated with regression: potentially harmful behavior
   introduced by the process;
2. variant decrease associated with regression: potentially useful behavior
   removed by the process;
3. variant increase associated with improvement: potentially useful behavior
   introduced by the process;
4. variant decrease associated with improvement: potentially harmful behavior
   removed by the process.

A category is eligible only if the median delta in its positive transition
class has the corresponding sign. PR-AUC uses the relevant transition as the
positive class and is normalized relative to its prevalence:

`normalized_effect = (PR_AUC - prevalence) / (1 - prevalence)`.

`E/V` is the normalized effect above its permutation mean divided by its
permutation SD. Candidates are ranked first by category-specific maxT-adjusted
`p_maxT`, then E/V and normalized effect.

## Permutation correction

Labels are permuted independently within the base-pass regression population
and the base-fail improvement population. Each permutation records the maximum
positive normalized effect across every valid feature and all four categories.
Each reported category-specific `p_maxT` is compared with that joint maximum.

The paper-v1 screening uses 200 permutations and seed 42, so the smallest
attainable value is `1/201 = 0.00498`. E/V is a ranking statistic, not a
Gaussian z-test.

## Alignment and populations

The implementation reuses the existing manifest discovery, label index,
activation index, checkpoint loader, layer loader, historical tokenizer, and
exact evaluated-token-mask reconstruction. Both model sides must have a
nonempty exact mask after the historical last-N pairing; otherwise the task is
excluded and its reason is recorded.

Stored activations come from different model-generated texts. Consequently,
the model-side contribution comparison is exploratory. Before causal steering,
the best feature/task candidates should be validated by forwarding the same
prompt and code through both models and comparing the contributions on
identical token positions.

Feature selection also uses evaluator outcomes from these benchmarks. Steering
confirmation should freeze the candidates and use held-out tasks,
cross-benchmark replication, or both.

## Outputs

Every CrossCoder/benchmark case contains:

- `feature_statistics.csv`;
- `ranked_differential_pr_auc_envelope.png`.

Global outputs:

- `index.md`;
- `all_cases_summary.csv`;
- `top_feature_candidates.csv`;
- `candidate_task_examples.csv`;
- `skipped_cases.json`.

`candidate_task_examples.csv` links each top candidate to the relevant
regression/preserved-success or improvement/persistent-failure tasks and their
base, variant, and delta contributions.

## Reproduction

```bash
ACTIVATION_ROOTS=/path/to/deepseek:/path/to/codellama \
CHECKPOINT_ROOT=/path/to/checkpoints \
DATASET=/path/to/extraction_v4/out \
scripts/run_differential_pr_auc_screening.sh smoke

ACTIVATION_ROOTS=/path/to/deepseek:/path/to/codellama \
CHECKPOINT_ROOT=/path/to/checkpoints \
DATASET=/path/to/extraction_v4/out \
scripts/run_differential_pr_auc_screening.sh full
```

## Modified files

- `tools/run_differential_pr_auc_screening.py` (new);
- `scripts/run_differential_pr_auc_screening.sh` (new);
- `tests/test_differential_pr_auc_screening.py` (new);
- `README.md`;
- `reports/differential_pr_auc_feature_screening/IMPLEMENTATION_NOTES.md`.
