#!/usr/bin/env bash
set -euo pipefail

cd "${REPO_ROOT:-$HOME/crosscoder-recatcher-steering}"

FEATURE_ID="${FEATURE_ID:?Set FEATURE_ID, e.g. FEATURE_ID=9341}"
ALPHA="${ALPHA:-0}"
MAX_EXAMPLES="${MAX_EXAMPLES:-2}"
MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-64}"

python tools/run_crosscoder_intervention.py \
  --checkpoint runs/crosscoder_training_v1/deepseek_base_vs_deepseek_finetuned_layer16_lat16384_steps20000/final.pt \
  --model-a-id deepseek-ai/deepseek-coder-6.7b-base \
  --model-b-id JetBrains/deepseek-coder-6.7B-kexer \
  --target-side b \
  --layer 16 \
  --feature-id "$FEATURE_ID" \
  --alpha "$ALPHA" \
  --input-jsonl recatcher_crosscoder_humaneval/deepseek_rerun_1gen_max512/results/humanevalplus__deepseek_finetuned_results.jsonl \
  --output-jsonl "runs/intervention_smoke/feature_${FEATURE_ID}_alpha_${ALPHA}.jsonl" \
  --max-examples "$MAX_EXAMPLES" \
  --max-new-tokens "$MAX_NEW_TOKENS" \
  --temperature 0 \
  --device-a cuda:0 \
  --device-b cuda:1 \
  --dtype float16 \
  --trust-remote-code
