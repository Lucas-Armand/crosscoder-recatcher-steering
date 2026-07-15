# CrossCoder failure-AUC and intervention pipeline

This package implements:

1. **Offline screening:** calculate the ROC-AUC of all 16,384 CrossCoder dimensions for predicting `correct=False`.
2. **Feature selection:** choose the top dimensions by oriented AUC.
3. **Intervention smoke tests:** regenerate code while suppressing or amplifying a selected dimension.
4. **Failure-rate summary:** after benchmark evaluation, calculate failure percentage and the change relative to `alpha=0`.

## Label

```python
failure = int(not result["correct"])
```

The baseline failure percentage is:

```text
100 × failures / evaluated examples
```

## Intervention convention

```text
alpha = -1.00  remove the estimated decoded contribution
alpha = -0.75  remove 75%
alpha = -0.50  remove 50%
alpha =  0.00  control
alpha =  1.00  add one extra copy
```

The implementation applies:

```text
h_target' = h_target + alpha × z_j × decoder_target[:, j]
```

## Installation

Copy `tools/`, `scripts/`, and `requirements_crosscoder_eval.txt` into the repository root, then:

```bash
cd ~/crosscoder-recatcher-steering
python -m pip install -r requirements_crosscoder_eval.txt
chmod +x scripts/run_*screening*.sh scripts/run_*intervention*.sh scripts/run_alpha_sweep_smoke.sh
```

## Activation layout

The screening scripts expect:

```text
ACTIVATION_ROOT/
├── humanevalplus/
│   ├── deepseek_base/*.npz
│   ├── deepseek_finetuned/*.npz
│   └── deepseek_merged/*.npz
└── bigcodebench/
    ├── deepseek_base/*.npz
    ├── deepseek_finetuned/*.npz
    └── deepseek_merged/*.npz
```

Use the canonical float32 activation bucket. `BigCodeBench/764` can be absent; run with `--skip-errors`.

## Screening smoke test

```bash
ACTIVATION_ROOT=/path/to/canonical/selected_layer_activations \
MAX_EXAMPLES=50 \
DEVICE=cuda \
./scripts/run_deepseek_screening_smoke.sh
```

Outputs:

```text
runs/crosscoder_failure_screening_smoke/.../
├── auc_ranking.csv
├── examples.csv
├── features.npz
├── skipped.json
└── summary.json
```

The smoke output contains elapsed time. A rough full-time estimate is:

```text
estimated full seconds ≈ smoke seconds × full examples / smoke examples
```

## Full DeepSeek screening

```bash
ACTIVATION_ROOT=/path/to/canonical/selected_layer_activations \
DEVICE=cuda \
./scripts/run_deepseek_screening_full.sh
```

## Select top features

```bash
python tools/select_top_features.py \
  --auc-csv runs/crosscoder_failure_screening_full/deepseek_base_vs_finetuned_target_finetuned/auc_ranking.csv \
  --top-k 10 \
  --min-nonzero-rate 0.01 \
  --output runs/selected_features/deepseek_base_vs_finetuned.txt
```

## Intervention smoke test

The provided runner is intentionally slow and transparent. It recomputes the complete prefix for both models at every generated token. Use it first to validate correctness and estimate runtime.

```bash
FEATURE_ID=9341 \
ALPHA=0 \
MAX_EXAMPLES=2 \
MAX_NEW_TOKENS=64 \
./scripts/run_intervention_smoke_example.sh
```

Run the full alpha smoke sweep:

```bash
FEATURE_ID=9341 \
MAX_EXAMPLES=2 \
MAX_NEW_TOKENS=64 \
./scripts/run_alpha_sweep_smoke.sh
```

The generated JSONL is compatible with a samples-style pipeline because it preserves the original task metadata and adds `completion`, `feature_id`, and `alpha`.

## Evaluation integration

Run the repository's existing HumanEval+/BigCodeBench evaluation on each intervention JSONL. The evaluated output must preserve:

```text
benchmark
model_label or target_model_id
feature_id
alpha
correct
```

Then summarize:

```bash
python tools/summarize_interventions.py \
  --evaluated-jsonl runs/evaluated_interventions/*.jsonl \
  --output runs/evaluated_interventions/summary.csv
```

## Reusing with CodeLlama

No Python changes are needed.

For screening, change:

- checkpoint path;
- `model-a`, `model-b`, and `target-model`;
- results JSONL paths;
- activation root.

For intervention, change:

- `model-a-id`;
- `model-b-id`;
- checkpoint;
- `target-side`.

CodeLlama and DeepSeek generally expose transformer blocks through `model.model.layers`, which this runner supports.

## Recommended experimental sequence

1. Smoke screening with 50 examples.
2. Full screening over HumanEval+ and BigCodeBench.
3. Select top 10–20 features.
4. Intervention smoke with 2 tasks, 64 tokens, all five alphas.
5. Evaluate those generations.
6. Increase to 20–100 tasks for promising dimensions.
7. Run the complete benchmarks only for dimensions showing a consistent dose-response effect.

## Important statistical caution

With 16,384 dimensions, the maximum in-sample AUC can be inflated by multiple testing. Treat the ranking as feature discovery. Confirm top dimensions on held-out tasks or grouped cross-validation before making strong claims.
