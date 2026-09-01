#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering
root=runs/codellama_bm_repetition_10token_probe_v1
mkdir -p "$root/logs"

run_feature() {
  local gpu="$1" feature="$2" dir="$root/feature_$2"
  for alpha in 0 -1 -3; do
    local label
    case "$alpha" in 0) label=zero;; -1) label=neg1;; -3) label=neg3;; esac
    local output="$dir/${label}.jsonl"
    if [[ -s "$output" ]]; then continue; fi
    echo "[$(date -Iseconds)] gpu=$gpu feature=$feature alpha=$alpha"
    CUDA_VISIBLE_DEVICES="$gpu" python tools/run_crosscoder_token_position.py \
      --checkpoint runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt \
      --model-a-id meta-llama/CodeLlama-7b-hf --model-b-id DevQuasar-5/coma-7B-v0.1 \
      --target-side b --layer 16 --feature-id "$feature" --alpha "$alpha" \
      --intervention-mode traditional --token-scope last_token --no-special-tokens \
      --input-jsonl "$dir/input.jsonl" --output-jsonl "$output" \
      --intervention-token-manifest "$dir/positions.csv" --max-new-tokens 10 \
      --temperature 0.2 --top-p 0.95 --generation-backend paired_cached --seed 1000 \
      --device-a cuda:0 --device-b cuda:0 --dtype float16 \
      --tokenizer-id meta-llama/CodeLlama-7b-hf >"$root/logs/f${feature}_${label}.log" 2>&1
  done
}

run_feature 0 9608 & p0=$!
run_feature 1 1058 & p1=$!
wait "$p0" "$p1"
run_feature 0 8313 & p0=$!
run_feature 1 5411 & p1=$!
wait "$p0" "$p1"
run_feature 0 7915
touch "$root/PROBE_COMPLETE"
