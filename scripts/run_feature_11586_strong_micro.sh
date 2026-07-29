#!/usr/bin/env bash
set -euo pipefail

cd "${REPO_ROOT:-$HOME/crosscoder-recatcher-steering}"

RUN_DIR="runs/steering_feature_11586_traditional"
CHECKPOINT="runs/crosscoder_codellama_base_merged_layer16_float32_v1/codellama_base_vs_codellama_merged_layer16_lat16384_steps20000/final.pt"
INPUT="${RUN_DIR}/strong_micro_input.jsonl"

mkdir -p "${RUN_DIR}/strong_generations" "${RUN_DIR}/strong_logs"

for alpha in 1.5 2 3 4; do
  tag="${alpha/./p}"
  python tools/run_crosscoder_intervention.py \
    --checkpoint "$CHECKPOINT" \
    --model-a-id meta-llama/CodeLlama-7b-hf \
    --model-b-id DevQuasar-5/coma-7B-v0.1 \
    --target-side b \
    --layer 16 \
    --feature-id 11586 \
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
