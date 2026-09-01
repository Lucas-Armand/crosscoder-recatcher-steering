#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering

root=runs/codellama_bm_first_token_ev_positive_alpha1_v1
input=runs/codellama_bm_repetition_10token_probe_v1/feature_5411/input.jsonl
mkdir -p "$root"/{generations,logs,audit}
cp -n "$input" "$root/input.jsonl"

run_arm() {
  local feature="$1" alpha="$2" name="$3"
  local dir="$root/generations/feature_$feature"
  local output="$dir/${name}.jsonl"
  mkdir -p "$dir"
  if [[ -f "$output" && "$(wc -l < "$output")" == 41 ]]; then
    return
  fi
  echo "[$(date -Iseconds)] feature=$feature alpha=$alpha"
  CUDA_VISIBLE_DEVICES=1 python tools/run_crosscoder_intervention.py \
    --checkpoint runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt \
    --model-a-id meta-llama/CodeLlama-7b-hf \
    --model-b-id DevQuasar-5/coma-7B-v0.1 \
    --target-side b --layer 16 --feature-id "$feature" --alpha "$alpha" \
    --intervention-mode traditional --token-scope last_token \
    --generation-backend paired_cached --input-jsonl "$root/input.jsonl" \
    --output-jsonl "$output" --max-new-tokens 512 \
    --temperature 0.2 --top-p 0.95 --seed 1000 \
    --device-a cuda:0 --device-b cuda:0 --dtype float16 \
    --tokenizer-id meta-llama/CodeLlama-7b-hf \
    >"$root/logs/f${feature}_${name}.log" 2>&1
}

# One shared zero arm verifies exact baseline reproduction under this run.
run_arm 10980 0 baseline
for feature in 10980 11596 10196 3211; do
  run_arm "$feature" 1 pos1
done

touch "$root/PROBE_COMPLETE"
