#!/usr/bin/env bash
set -euo pipefail

cd "${REPO_ROOT:-$HOME/crosscoder-recatcher-steering}"
run_dir="runs/steering_harmful_feature_7608"
checkpoint="runs/crosscoder_training_v1/deepseek_base_vs_deepseek_finetuned_layer16_lat16384_steps20000/final.pt"
input="$run_dir/selection/feature_7608_p95_selected5.jsonl"
mkdir -p "$run_dir/generations" "$run_dir/logs"

for alpha in -0.5 -1 -2 -3 -4 2; do
  tag="${alpha/-/neg}"; tag="${tag/./p}"
  .venv/bin/python tools/run_crosscoder_intervention.py \
    --checkpoint "$checkpoint" \
    --model-a-id deepseek-ai/deepseek-coder-6.7b-base \
    --model-b-id JetBrains/deepseek-coder-6.7B-kexer \
    --target-side b --layer 16 --feature-id 7608 --alpha "$alpha" \
    --intervention-mode traditional --token-scope last_token \
    --input-jsonl "$input" \
    --output-jsonl "$run_dir/generations/feature_7608_p95_alpha_${tag}.jsonl" \
    --max-new-tokens 512 --temperature 0.2 --top-p 0.95 \
    --device-b cuda:0 --dtype float16 --trust-remote-code \
    >"$run_dir/logs/feature_7608_p95_alpha_${tag}.log" 2>&1
done
