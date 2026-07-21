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

The machine-readable release definition is
[`manifests/paper_v1.json`](manifests/paper_v1.json). The evidence-backed status,
including known limitations, is in
[`docs/CURRENT_STATUS.md`](docs/CURRENT_STATUS.md).

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
