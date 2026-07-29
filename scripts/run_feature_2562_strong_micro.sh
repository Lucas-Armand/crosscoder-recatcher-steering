#!/usr/bin/env bash
set -euo pipefail

cd "${REPO_ROOT:-$HOME/crosscoder-recatcher-steering}"

RUN_DIR="runs/steering_feature_2562_traditional"
CHECKPOINT="runs/crosscoder_training_v1/deepseek_base_vs_deepseek_finetuned_layer16_lat16384_steps20000/final.pt"
INPUT="${RUN_DIR}/strong_micro_input.jsonl"

mkdir -p "${RUN_DIR}/strong_generations" "${RUN_DIR}/strong_logs"

for alpha in -1.5 -2 -3 -4; do
  tag="neg_${alpha#-}"
  tag="${tag/./p}"
  python tools/run_crosscoder_intervention.py \
    --checkpoint "$CHECKPOINT" \
    --model-a-id deepseek-ai/deepseek-coder-6.7b-base \
    --model-b-id JetBrains/deepseek-coder-6.7B-kexer \
    --target-side b \
    --layer 16 \
    --feature-id 2562 \
    --alpha "$alpha" \
    --intervention-mode traditional \
    --token-scope last_token \
    --input-jsonl "$INPUT" \
    --output-jsonl "${RUN_DIR}/strong_generations/alpha_${tag}.jsonl" \
    --max-new-tokens 512 \
    --temperature 0.2 \
    --top-p 0.95 \
    --device-b cuda:0 \
    --dtype float16 \
    --trust-remote-code \
    2>&1 | tee "${RUN_DIR}/strong_logs/alpha_${tag}.log"
done
