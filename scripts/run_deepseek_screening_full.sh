#!/usr/bin/env bash
set -euo pipefail

cd "${REPO_ROOT:-$HOME/crosscoder-recatcher-steering}"

ACTIVATION_ROOT="${ACTIVATION_ROOT:-/tmp/crosscoder_deepseek_activations}"
RESULT_ROOT="${RESULT_ROOT:-recatcher_crosscoder_humaneval/deepseek_rerun_1gen_max512/results}"
OUT_ROOT="${OUT_ROOT:-runs/crosscoder_failure_screening_full}"
DEVICE="${DEVICE:-cuda}"

run_one() {
  local checkpoint="$1"
  local model_a="$2"
  local model_b="$3"
  local target_model="$4"
  local out_name="$5"

  python tools/screen_crosscoder_auc.py \
    --checkpoint "$checkpoint" \
    --activation-root "$ACTIVATION_ROOT" \
    --results-jsonl \
      "$RESULT_ROOT/humanevalplus__${target_model}_results.jsonl" \
      "$RESULT_ROOT/bigcodebench__${target_model}_results.jsonl" \
    --model-a "$model_a" \
    --model-b "$model_b" \
    --target-model "$target_model" \
    --layer 16 \
    --aggregation max \
    --device "$DEVICE" \
    --skip-errors \
    --output-dir "$OUT_ROOT/$out_name"
}

run_one \
  runs/crosscoder_training_v1/deepseek_base_vs_deepseek_finetuned_layer16_lat16384_steps20000/final.pt \
  deepseek_base deepseek_finetuned deepseek_finetuned \
  deepseek_base_vs_finetuned_target_finetuned

run_one \
  runs/crosscoder_training_v1/deepseek_base_vs_deepseek_merged_layer16_lat16384_steps20000/final.pt \
  deepseek_base deepseek_merged deepseek_merged \
  deepseek_base_vs_merged_target_merged
