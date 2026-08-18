#!/usr/bin/env bash
set -euo pipefail
cd "${REPO_ROOT:-$HOME/crosscoder-recatcher-steering}"
export CUDA_VISIBLE_DEVICES=1

activation_root="runs/same_text_activations/codellama_base_merged_layer16_rms"
output_dir="runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1"
mkdir -p "$activation_root" "$output_dir"

if [[ ! -f "$activation_root/CAPTURE_COMPLETE" ]]; then
.venv/bin/python tools/capture_same_text_crosscoder_activations.py \
  --results-dir /tmp/crosscoder_postprocess_and_eval_v4/out/results_repaired \
  --output-root "$activation_root" \
  --model-a-id meta-llama/CodeLlama-7b-hf \
  --model-b-id DevQuasar-5/coma-7B-v0.1 \
  --model-a-label codellama_base --model-b-label codellama_merged \
  --benchmarks humanevalplus bigcodebench --layer 16 \
  --device-a cuda:0 --device-b cuda:0 --native-special-tokens \
  >"$output_dir/capture.log" 2>&1
  date -Is > "$activation_root/CAPTURE_COMPLETE"
fi

.venv/bin/python tools/train_topk_crosscoder_from_npz.py \
  --activation-root "$activation_root" \
  --benchmarks humanevalplus bigcodebench \
  --model-a codellama_base --model-b codellama_merged --layer 16 \
  --latent-dim 16384 --top-k 100 --batch-size 2048 --tokens-per-pair 128 \
  --steps 10000 --lr 1e-4 --l1-coef 0 --val-frac 0.10 \
  --eval-every 500 --save-every 2000 --pairing-mode same_position \
  --device cuda --dtype float32 --output-dir "$output_dir" \
  >"$output_dir/train.log" 2>&1

date -Is > "$output_dir/COMPLETE"
