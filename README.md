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
