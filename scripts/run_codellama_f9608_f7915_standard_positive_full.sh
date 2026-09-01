#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering
root=runs/codellama_bm_f9608_f7915_standard_positive_full_v1
input=runs/codellama_bm_repetition_10token_probe_v1/feature_5411/input.jsonl
mkdir -p "$root"/{generations,logs,audit}
cp -n "$input" "$root/input.jsonl"

run_arm() {
  local gpu="$1" feature="$2" name="$3" alpha="$4"
  local dir="$root/generations/feature_$feature" output
  mkdir -p "$dir"; output="$dir/${name}.jsonl"
  if [[ -f "$output" && "$(wc -l < "$output")" == 41 ]]; then return; fi
  echo "[$(date -Iseconds)] gpu=$gpu feature=$feature alpha=$alpha"
  CUDA_VISIBLE_DEVICES="$gpu" python tools/run_crosscoder_intervention.py \
    --checkpoint runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt \
    --model-a-id meta-llama/CodeLlama-7b-hf --model-b-id DevQuasar-5/coma-7B-v0.1 \
    --target-side b --layer 16 --feature-id "$feature" --alpha "$alpha" \
    --intervention-mode traditional --token-scope last_token \
    --generation-backend paired_cached --input-jsonl "$root/input.jsonl" \
    --output-jsonl "$output" --max-new-tokens 512 --temperature 0.2 --top-p 0.95 \
    --seed 1000 --device-a cuda:0 --device-b cuda:0 --dtype float16 \
    --tokenizer-id meta-llama/CodeLlama-7b-hf >"$root/logs/f${feature}_${name}.log" 2>&1
}

run_feature() {
  local gpu="$1" feature="$2"
  run_arm "$gpu" "$feature" zero 0
  run_arm "$gpu" "$feature" pos0p5 0.5
  run_arm "$gpu" "$feature" pos1 1
  run_arm "$gpu" "$feature" pos2 2
  run_arm "$gpu" "$feature" pos3 3
}

run_feature 0 9608 & p0=$!
run_feature 1 7915 & p1=$!
wait "$p0" "$p1"
touch "$root/PROBE_COMPLETE"
