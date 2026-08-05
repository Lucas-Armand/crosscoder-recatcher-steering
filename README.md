# ReCatcher CrossCoder Reproducibility Package

This repository contains the auditable pipeline used to study internal feature
differences between base, fine-tuned, and merged code language models. The
current paper checkpoint covers DeepSeek Coder and CodeLlama on HumanEval+ and
BigCodeBench, with layer-16 activations and four canonical CrossCoders.

## Current paper checkpoint

The frozen experimental scope is:

| Family | Comparison | Benchmarks | Activation layer | CrossCoder |
|---|---|---|---:|---|
| DeepSeek | base vs. fine-tuned | HumanEval+, BigCodeBench | 16 | complete |
| DeepSeek | base vs. merged | HumanEval+, BigCodeBench | 16 | complete |
| CodeLlama | base vs. fine-tuned | HumanEval+, BigCodeBench | 16 | complete |
| CodeLlama | base vs. merged | HumanEval+, BigCodeBench | 16 | complete |

The large artifacts remain in Google Cloud Storage. The repository stores code,
configuration, manifests, validation logic, and compact reports; it does not
duplicate model outputs, activations, or checkpoints.

The corrected machine-readable evaluation definition is
[`manifests/paper_v1_extraction_v4.json`](manifests/paper_v1_extraction_v4.json);
the original [`manifests/paper_v1.json`](manifests/paper_v1.json) remains frozen
for v3 provenance. The evidence-backed status,
including known limitations, is in
[`docs/CURRENT_STATUS.md`](docs/CURRENT_STATUS.md).

## Evaluated results

The table below is recomputed from evaluator artifacts rather than copied from
the original summary. Timeouts remain separate from functional failures; the
audit found no missing task verdicts.

| Benchmark | Model | Evaluated | Pass | Pass % | Non-pass | Non-pass % |
|---|---|---:|---:|---:|---:|---:|
| HumanEval+ | DeepSeek base | 164 | 66 | 40.24% | 98 | 59.76% |
| HumanEval+ | DeepSeek fine-tuned | 164 | 101 | 61.59% | 63 | 38.41% |
| HumanEval+ | DeepSeek merged | 164 | 123 | 75.00% | 41 | 25.00% |
| HumanEval+ | CodeLlama base | 164 | 55 | 33.54% | 109 | 66.46% |
| HumanEval+ | CodeLlama fine-tuned | 164 | 58 | 35.37% | 106 | 64.63% |
| HumanEval+ | CodeLlama merged | 164 | 17 | 10.37% | 147 | 89.63% |
| BigCodeBench | DeepSeek base | 1,140 | 268 | 23.51% | 872 | 76.49% |
| BigCodeBench | DeepSeek fine-tuned | 1,140 | 404 | 35.44% | 736 | 64.56% |
| BigCodeBench | DeepSeek merged | 1,140 | 471 | 41.32% | 669 | 58.68% |
| BigCodeBench | CodeLlama base | 1,140 | 314 | 27.54% | 826 | 72.46% |
| BigCodeBench | CodeLlama fine-tuned | 1,140 | 319 | 27.98% | 821 | 72.02% |
| BigCodeBench | CodeLlama merged | 1,140 | 27 | 2.37% | 1,113 | 97.63% |

These are extraction-v4 results. The immutable v3 baseline and the complete
machine-readable comparison remain available in
[`reports/postprocessing_v4_validation.md`](reports/postprocessing_v4_validation.md).
One BigCodeBench evaluator verdict changed from pass to fail despite byte-identical
code; it is reported as evaluator nondeterminism, not a post-processing regression.
Traceable pass/fail examples showing network completion, pre-repair code,
post-repair code, and evaluator verdict are in
[`reports/paper_v1_evaluation_samples.md`](reports/paper_v1_evaluation_samples.md).

## Bidirectional PR-AUC feature screening

The current feature screen discovers cases from the paper manifest and analyzes
failure and success as separate positive classes. Each CrossCoder latent is
aggregated by its maximum over exactly the generated tokens submitted to
evaluation. Because raw PR-AUC depends on class prevalence, ranking uses
prevalence-normalized lift and a permutation effect/variability score (`E/V`).
The five supported features with the highest `E/V` are marked on each plot.

```bash
ACTIVATION_ROOTS=/path/to/deepseek:/path/to/codellama \
CHECKPOINT_ROOT=/path/to/crosscoder/checkpoints \
scripts/run_pr_auc_feature_screening.sh smoke

# Paper-v1 analysis: 200 permutations by default.
ACTIVATION_ROOTS=/path/to/deepseek:/path/to/codellama \
CHECKPOINT_ROOT=/path/to/crosscoder/checkpoints \
scripts/run_pr_auc_feature_screening.sh full
```

Legacy paper-v1 masks are reconstructed only when retokenizing the exact historical
forward-pass text reproduces every stored token ID; otherwise the example is
rejected. New captures store the mask directly. See
[`reports/pr_auc_feature_screening/IMPLEMENTATION_NOTES.md`](reports/pr_auc_feature_screening/IMPLEMENTATION_NOTES.md)
for definitions, validation, limitations, and exact reproduction commands.
Extraction v4 additionally materializes exact mask sidecars under
`evaluated_token_masks/` in its versioned dataset prefix. The previous ROC-AUC
report is retained as historical output and is not the current screening result.

## Paired base-versus-variant screening

The differential screen connects features more directly to fine-tuning and
merging outcomes. It decomposes the joint CrossCoder preactivation into base-
and variant-side additive contributions, then tests whether their paired
difference separates:

- regressions from preserved successes among tasks passed by the base model;
- improvements from persistent failures among tasks failed by the base model.

Four jointly maxT-corrected mechanisms cover variant increases/decreases
associated with regressions/improvements. These quantities are contributions to
a shared latent, not independent model-specific latent activations.

```bash
ACTIVATION_ROOTS=/path/to/deepseek:/path/to/codellama \
CHECKPOINT_ROOT=/path/to/crosscoder/checkpoints \
DATASET=/path/to/extraction_v4/out \
scripts/run_differential_pr_auc_screening.sh full
```

See the [global differential report](reports/differential_pr_auc_feature_screening/index.md)
and [implementation notes](reports/differential_pr_auc_feature_screening/IMPLEMENTATION_NOTES.md).
Stored activations come from different generated texts, so shortlisted
feature/task pairs require a same-text paired forward before steering.

The percentile-sensitivity extension repeats this paired analysis with P50,
P60, P70, P80, P90, P95, and P99 positive contribution over evaluated tokens.
Feature, percentile, sign, and transition category are included in the same
permutation maxT search. See the
[percentile analysis](reports/differential_percentile_pr_auc_screening/PERCENTILE_ANALYSIS.md)
and its [machine-readable comparison](reports/differential_percentile_pr_auc_screening/percentile_comparison.csv).

## Same-text joint-latent screening

The first DeepSeek base-versus-merged follow-up passes each evaluated HumanEval+
solution through both models with identical token IDs, captures layer 16,
applies RMS normalization, and calculates the complete joint CrossCoder latent.
It screens mean, maximum, P95, P99, and active-fraction summaries using PR-AUC
with failure as the positive class. The compact report includes permutation
effect/variability, maxT evidence, decoder and activation specificity, temporal
diagnostics, and peak-token contexts.

See the [same-text PR-AUC report](reports/same_text_joint_latent_pr_auc/deepseek_base_merged_humaneval_layer16/index.md)
and [implementation notes](reports/same_text_joint_latent_pr_auc/IMPLEMENTATION_NOTES.md).
The run retained 295/328 solutions; 33 were excluded because no paired token
survived the historical finite-state and norm filter. This material limitation
is documented and prevents treating the current screen as final paper evidence.

An intra-task DeepSeek base-versus-finetuned analysis separately compares both
models on identical content-token IDs and compares each model on its own
generated answer. Raw layer-16 principal directions are dominated by a global
checkpoint displacement. After global centering, same-text directions show a
weak, non-significant outcome-group trend (2,000-permutation `p=0.110`), while
different-own-text directions show no separation (`p=0.536`). See the
[intra-task direction report](reports/intra_task_directions/deepseek_base_finetuned_humaneval_layer16/index.md).

A follow-up direction discriminant uses all 49 HumanEval base/finetuned
transitions and evaluates every score leave-one-task-out. Controlled same-text
displacement remains inconclusive (ROC-AUC 0.633, permutation `p=0.165`), while
the confounded different-own-text representation reaches ROC-AUC and balanced
accuracy 0.738 (`p≈0.02`). The latter is predictive but mixes model and code
content and is not yet a causal steering direction. See the
[LOTO discriminant report](reports/intra_task_discriminant/deepseek_base_finetuned_humaneval_layer16/index.md).

A causal smoke applies the task-held-out discriminant directions to ten aligned
DeepSeek-base failures. Expected-direction steering shows a 0/10, 1/10, 2/10
dose response at norms 2, 4, and 6, but a matched random direction also reaches
2/10, so there is no aggregate specificity. HumanEval/158 is a candidate
direction-specific effect: expected +6 fixes its lexicographic tie break, while
the opposite direction and 10/10 orthogonal random directions fail. See the
[discriminant-direction steering report](reports/discriminant_direction_steering_smoke/index.md).

A follow-up local decomposition asks which dimensions explain the checkpoint
difference without assuming that they generalize across tasks. On
`HumanEval/158`, the fail-to-pass effect survives removing both the direct
same-task displacement and the joint local PC1--PC5 subspace from the causal
LOTO direction. The dominant checkpoint variation is therefore not the causal
carrier in this example; a lower-variance residual produces the correct
lexicographic tie-break behavior. See the
[local mechanism report](reports/local_task_mechanisms/index.md).

A paired traditional-steering smoke tested features 6258 and 6873 at local
negative doses. Neither feature produced a verdict transition; only one of 15
evaluated programs changed, without becoming correct. Because the 192-token
baseline reproduced only two or three of five historical pass controls, this is
a negative exploratory result rather than a final causal test. See the
[same-text steering report](reports/steering_same_text_features/index.md).

The subsequent historical-protocol replication recovered the exact original
20-task cohort, NF4 generation, positive token-level P99 scaling, and alpha
grid. Current feature 6873 at `-1 P99` corrected HumanEval/78—the same task fixed
by old feature 962—but regressed HumanEval/56, for zero net gain. The historical
and corrected v4 extractors agree on both transitions. See the
[historical-protocol replication report](reports/historical_protocol_replication/index.md).

## Validate the checkpoint

On a machine with authenticated `gcloud` access:

```bash
python tools/validate_paper_release.py \
  --manifest manifests/paper_v1.json \
  --output-json reports/paper_v1_validation.json \
  --output-markdown reports/paper_v1_validation.md
```

The command is read-only. It validates:

1. all 12 model/benchmark result sets that form the eight comparison cells;
2. generation metadata, task coverage, seeds, and layer-16 provenance;
3. raw-to-repaired lineage and the allowed deterministic repair rules;
4. HumanEval+ rows and BigCodeBench evaluator completion evidence;
5. canonical activation coverage, including declared exceptions;
6. final checkpoints, exit codes, metrics, and hyperparameter parity for the
   four canonical CrossCoders.

To evaluate future steering or ablation generations through the same pipeline,
follow [`docs/STEERING_EVALUATION.md`](docs/STEERING_EVALUATION.md). The
normalizer deliberately overwrites stale baseline `candidate_code` and
correctness fields before post-processing.

The first PR-AUC-guided steering smoke tested DeepSeek-base feature 6873 on 20
HumanEval tasks. Both `alpha=-1` and `alpha=+1` reduced compilation and pass
rates sharply, showing that magnitude 1 is outside the useful local regime
rather than confirming the predicted direction. See the paired transitions,
post-processing audit, runner correction, and next calibration recommendation
in [`reports/steering_smoke_feature_6873/index.md`](reports/steering_smoke_feature_6873/index.md).

The validator exits non-zero when an undeclared discrepancy is found. It does
not execute generated code; evaluator re-execution is a separate, sandboxed
validation stage described in
[`docs/VALIDATION_PROTOCOL.md`](docs/VALIDATION_PROTOCOL.md).

## Repository map

```text
configs/       Model aliases and experiment configuration templates
docs/          Design, provenance, status, safety, and validation documentation
manifests/     Machine-readable paper release definitions
reports/       Compact generated validation reports (no large artifacts)
scripts/       Reproducible stage launchers
tests/         Unit tests for validation and deterministic processing logic
tools/         Python CLIs for processing, training, screening, and intervention
```

The original generation entry point is `run_recatcher_benchmarks.py`. Historical
scripts remain available for traceability, but the release manifest identifies
which artifacts and configurations are canonical.

## Environment

Create an isolated environment and install the core dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Evaluation requires separately pinned environments because generated code is
executed and the two benchmark harnesses have different dependency surfaces.
See [`docs/VALIDATION_PROTOCOL.md`](docs/VALIDATION_PROTOCOL.md) before running
either evaluator.

## Scientific boundary

The current checkpoint ends after CrossCoder training and artifact validation.
Feature screening and causal intervention are work in progress and must not be
presented as part of the frozen baseline. Existing exploratory screening and
intervention outputs are retained as development evidence.

## Safety and data policy

- Never execute untrusted generated code outside an isolated evaluator.
- Never place credentials, model tokens, or private bucket URLs in logs.
- Treat existing GCS prefixes as immutable historical records.
- Publish a new versioned release prefix instead of overwriting an old release.
- Do not infer model failure from infrastructure errors or missing evaluator
  output.

See [`docs/SECURITY_NOTES.md`](docs/SECURITY_NOTES.md) for additional guidance.
## Causal steering experiments

The first traditional-steering smoke test targets CodeLlama merged feature
8994 at layer 16, using `alpha = 0, 0.25, 0.5, 0.75, 1.0` on ten historical
regressions and ten preserved-success controls. The intervention acts on only
the final hidden token of each autoregressive forward. See
[`reports/steering_feature_8994_traditional/index.md`](reports/steering_feature_8994_traditional/index.md)
for the design, limitations, task-level results, and dose-response figure.

A historical-style replication uses the new DeepSeek base-versus-merged
CrossCoder's strongest HumanEval+ base-side ROC-AUC feature (4672), selects
high-activation failures and pass controls, and applies negative P99-scaled
traditional steering. The smoke found no fail-to-pass transitions and one
pass-to-fail transition at every nonzero strength. See
[`reports/steering_historical_auc_feature_4672/index.md`](reports/steering_historical_auc_feature_4672/index.md)
for the fixed design, paired results, diagnostics, and interpretation.

A low-percentile paired screen then selected CodeLlama base-versus-merged
BigCodeBench regression features 4815/P80, 13439/P80, and 4567/P60. Traditional
merged-side steering changed up to three of five completions per arm but rescued
none of the 60 evaluated generations. See
[`reports/steering_percentile_pass_to_fail_smoke/index.md`](reports/steering_percentile_pass_to_fail_smoke/index.md)
for the task selection, intervention norms, qualitative effects, and the
activation-matched clamping follow-up motivated by this negative result.
