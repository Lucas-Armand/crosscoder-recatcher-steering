#!/usr/bin/env bash
set -euo pipefail

cd "${REPO_ROOT:-$HOME/crosscoder-recatcher-steering}"

CHECKPOINT="runs/crosscoder_training_v1/deepseek_base_vs_deepseek_finetuned_layer16_lat16384_steps20000/final.pt"
INPUT="runs/crosscoder_intervention_smoke/feature_5666_high_activation_5.jsonl"
OUTPUT_DIR="runs/crosscoder_intervention_smoke/feature_5666_high_activation_512"

FEATURE_ID=5666
MAX_EXAMPLES=1
MAX_NEW_TOKENS=512

mkdir -p "$OUTPUT_DIR"

declare -A OUTPUT_NAMES=(
  ["1"]="alpha_1p0.jsonl"
  ["0"]="alpha_0.jsonl"
  ["-0.5"]="alpha_neg_0p5.jsonl"
  ["-1"]="alpha_neg_1p0.jsonl"
)

ALPHAS=(1 0 -0.5 -1)

for ALPHA in "${ALPHAS[@]}"; do
  OUTPUT="$OUTPUT_DIR/${OUTPUT_NAMES[$ALPHA]}"

  echo
  echo "================================================================"
  echo "Feature: $FEATURE_ID"
  echo "Alpha:   $ALPHA"
  echo "Output:  $OUTPUT"
  echo "================================================================"

  time python tools/run_crosscoder_intervention.py \
    --checkpoint "$CHECKPOINT" \
    --model-a-id deepseek-ai/deepseek-coder-6.7b-base \
    --model-b-id JetBrains/deepseek-coder-6.7B-kexer \
    --target-side b \
    --layer 16 \
    --feature-id "$FEATURE_ID" \
    --alpha "$ALPHA" \
    --input-jsonl "$INPUT" \
    --output-jsonl "$OUTPUT" \
    --max-examples "$MAX_EXAMPLES" \
    --max-new-tokens "$MAX_NEW_TOKENS" \
    --temperature 0 \
    --device-a cuda:0 \
    --device-b cuda:1 \
    --dtype float16 \
    --trust-remote-code

  echo "Finished alpha=$ALPHA"
done

echo
echo "All alpha runs finished."
find "$OUTPUT_DIR" -maxdepth 1 -name 'alpha_*.jsonl' -printf '%f\n' | sort
