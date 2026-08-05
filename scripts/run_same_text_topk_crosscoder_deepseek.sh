#!/usr/bin/env bash
set -euo pipefail
cd "${REPO_ROOT:-$HOME/crosscoder-recatcher-steering}"

activation_root="runs/same_text_activations/deepseek_base_finetuned_layer16_rms"
output_dir="runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1"
mkdir -p "$activation_root" "$output_dir"

if [[ ! -f "$activation_root/CAPTURE_COMPLETE" ]]; then
.venv/bin/python tools/capture_same_text_crosscoder_activations.py \
  --results-dir /tmp/crosscoder_postprocess_and_eval_v4/out/results_repaired \
  --output-root "$activation_root" \
  --model-a-id deepseek-ai/deepseek-coder-6.7b-base \
  --model-b-id JetBrains/deepseek-coder-6.7B-kexer \
  --model-a-label deepseek_base --model-b-label deepseek_finetuned \
  --benchmarks humanevalplus bigcodebench --layer 16 \
  --device-a cuda:0 --device-b cuda:1 --trust-remote-code \
  >"$output_dir/capture.log" 2>&1
  date -Is > "$activation_root/CAPTURE_COMPLETE"
fi

.venv/bin/python tools/train_topk_crosscoder_from_npz.py \
  --activation-root "$activation_root" \
  --benchmarks humanevalplus bigcodebench \
  --model-a deepseek_base --model-b deepseek_finetuned --layer 16 \
  --latent-dim 16384 --top-k 100 --batch-size 2048 --tokens-per-pair 128 \
  --steps 20000 --lr 1e-4 --l1-coef 0 --val-frac 0.10 \
  --eval-every 500 --save-every 2000 --pairing-mode same_position \
  --device cuda --dtype float32 --output-dir "$output_dir" \
  >"$output_dir/train.log" 2>&1

date -Is > "$output_dir/COMPLETE"
