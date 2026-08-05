#!/usr/bin/env bash
set -euo pipefail

cd "${REPO_ROOT:-$HOME/crosscoder-recatcher-steering}"
run_dir="runs/steering_percentile_pass_to_fail_smoke"
checkpoint="runs/crosscoder_codellama_base_merged_layer16_float32_v1/codellama_base_vs_codellama_merged_layer16_lat16384_steps20000/final.pt"
features=(4815 13439 4567)
aggregations=(p80 p80 p60)
alphas=(1 2 4 -2)
mkdir -p "$run_dir/generations" "$run_dir/logs"

for index in "${!features[@]}"; do
  feature="${features[$index]}"
  aggregation="${aggregations[$index]}"
  input="$run_dir/selection/feature_${feature}_${aggregation}_selected5.jsonl"
  for alpha in "${alphas[@]}"; do
    tag="${alpha/-/neg}"; tag="${tag/./p}"
    .venv/bin/python tools/run_crosscoder_intervention.py \
      --checkpoint "$checkpoint" \
      --model-a-id meta-llama/CodeLlama-7b-hf \
      --model-b-id DevQuasar-5/coma-7B-v0.1 \
      --target-side b --layer 16 --feature-id "$feature" --alpha "$alpha" \
      --intervention-mode traditional --token-scope last_token \
      --input-jsonl "$input" \
      --output-jsonl "$run_dir/generations/feature_${feature}_${aggregation}_alpha_${tag}.jsonl" \
      --max-new-tokens 512 --temperature 0.2 --top-p 0.95 \
      --device-b cuda:0 --dtype float16 --trust-remote-code \
      >"$run_dir/logs/feature_${feature}_${aggregation}_alpha_${tag}.log" 2>&1
  done
done
