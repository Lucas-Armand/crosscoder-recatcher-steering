#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering
root=runs/codellama_bm_f9608_f7915_standard_negative_full_v1
source_root=runs/codellama_bm_f9608_f7915_standard_positive_full_v1
input="$source_root/input.jsonl"
mkdir -p "$root"/{generations,logs,audit}
cp -n "$input" "$root/input.jsonl"
for feature in 9608 7915; do
  mkdir -p "$root/generations/feature_$feature"
  cp -n "$source_root/generations/feature_$feature/zero.jsonl" "$root/generations/feature_$feature/zero.jsonl"
done

run_arm() {
  local feature="$1" name="$2" alpha="$3"
  local dir="$root/generations/feature_$feature" output="$root/generations/feature_$feature/${name}.jsonl"
  if [[ -f "$output" && "$(wc -l < "$output")" == 41 ]]; then return; fi
  echo "[$(date -Iseconds)] gpu=1 feature=$feature alpha=$alpha"
  CUDA_VISIBLE_DEVICES=1 python tools/run_crosscoder_intervention.py \
    --checkpoint runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt \
    --model-a-id meta-llama/CodeLlama-7b-hf --model-b-id DevQuasar-5/coma-7B-v0.1 \
    --target-side b --layer 16 --feature-id "$feature" --alpha "$alpha" \
    --intervention-mode traditional --token-scope last_token \
    --generation-backend paired_cached --input-jsonl "$root/input.jsonl" \
    --output-jsonl "$output" --max-new-tokens 512 --temperature 0.2 --top-p 0.95 \
    --seed 1000 --device-a cuda:0 --device-b cuda:0 --dtype float16 \
    --tokenizer-id meta-llama/CodeLlama-7b-hf >"$root/logs/f${feature}_${name}.log" 2>&1
}

for feature in 9608 7915; do
  run_arm "$feature" neg0p5 -0.5
  run_arm "$feature" neg1 -1
  run_arm "$feature" neg2 -2
  run_arm "$feature" neg3 -3
done
touch "$root/PROBE_COMPLETE"
