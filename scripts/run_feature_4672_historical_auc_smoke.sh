#!/usr/bin/env bash
set -euo pipefail

cd "${REPO_ROOT:-$HOME/crosscoder-recatcher-steering}"

run_dir="runs/steering_historical_auc_feature_4672"
checkpoint="runs/crosscoder_training_v1/deepseek_base_vs_deepseek_merged_layer16_lat16384_steps20000/final.pt"
input="${run_dir}/input_20_smoke.jsonl"

mkdir -p "${run_dir}/generations" "${run_dir}/logs"

run_arm() {
  local alpha="$1"
  local tag="$2"
  local device="$3"
  .venv/bin/python tools/run_crosscoder_intervention.py \
    --checkpoint "$checkpoint" \
    --model-a-id deepseek-ai/deepseek-coder-6.7b-base \
    --model-b-id ori-ai-fabric/ds-trinity-7b-v1 \
    --target-side a \
    --layer 16 \
    --feature-id 4672 \
    --alpha "$alpha" \
    --intervention-mode traditional \
    --token-scope last_token \
    --input-jsonl "$input" \
    --output-jsonl "${run_dir}/generations/alpha_${tag}.jsonl" \
    --max-new-tokens 192 \
    --temperature 0 \
    --device-a "$device" \
    --dtype float16 \
    --trust-remote-code \
    >"${run_dir}/logs/alpha_${tag}.log" 2>&1
}

(
  run_arm 0 zero cuda:0
  run_arm -1.7681800127 neg_0p25_p99 cuda:0
  run_arm -7.0727200508 neg_1p00_p99 cuda:0
) &
pid_gpu0=$!

(
  run_arm -0.7072720051 neg_0p10_p99 cuda:1
  run_arm -3.5363600254 neg_0p50_p99 cuda:1
) &
pid_gpu1=$!

wait "$pid_gpu0"
wait "$pid_gpu1"
