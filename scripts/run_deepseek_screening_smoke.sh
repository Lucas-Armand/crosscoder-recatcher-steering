#!/usr/bin/env bash
set -euo pipefail

cd "${REPO_ROOT:-$HOME/crosscoder-recatcher-steering}"

ACTIVATION_ROOT="${ACTIVATION_ROOT:-/tmp/crosscoder_deepseek_activations}"
RESULT_ROOT="${RESULT_ROOT:-recatcher_crosscoder_humaneval/deepseek_rerun_1gen_max512/results}"
OUT_ROOT="${OUT_ROOT:-runs/crosscoder_failure_screening_smoke}"
MAX_EXAMPLES="${MAX_EXAMPLES:-50}"
DEVICE="${DEVICE:-cuda}"

python tools/screen_crosscoder_auc.py \
  --checkpoint runs/crosscoder_training_v1/deepseek_base_vs_deepseek_finetuned_layer16_lat16384_steps20000/final.pt \
  --activation-root "$ACTIVATION_ROOT" \
  --results-jsonl \
    "$RESULT_ROOT/humanevalplus__deepseek_finetuned_results.jsonl" \
    "$RESULT_ROOT/bigcodebench__deepseek_finetuned_results.jsonl" \
  --model-a deepseek_base \
  --model-b deepseek_finetuned \
  --target-model deepseek_finetuned \
  --layer 16 \
  --aggregation max \
  --device "$DEVICE" \
  --max-examples "$MAX_EXAMPLES" \
  --skip-errors \
  --output-dir "$OUT_ROOT/deepseek_base_vs_finetuned_target_finetuned"
