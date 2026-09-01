#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering
root=runs/codellama_bm_repetition_top10_standard_30token_v1
input=runs/codellama_bm_repetition_10token_probe_v1/feature_5411/input.jsonl
mkdir -p "$root"/{generations,logs,audit}
cp -n "$input" "$root/input.jsonl"
cp -n runs/codellama_bm_f9608_standard_30token_probe_v1/generations/zero.jsonl "$root/generations/baseline.jsonl"
mkdir -p "$root/generations/feature_9608"
for arm in neg0p5 neg1 neg2 neg3; do
  cp -n "runs/codellama_bm_f9608_standard_30token_probe_v1/generations/${arm}.jsonl" "$root/generations/feature_9608/${arm}.jsonl"
done

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
    --output-jsonl "$output" --max-new-tokens 30 --temperature 0.2 --top-p 0.95 \
    --seed 1000 --device-a cuda:0 --device-b cuda:0 --dtype float16 \
    --tokenizer-id meta-llama/CodeLlama-7b-hf >"$root/logs/f${feature}_${name}.log" 2>&1
}

run_feature() {
  local gpu="$1" feature="$2"
  run_arm "$gpu" "$feature" neg0p5 -0.5
  run_arm "$gpu" "$feature" neg1 -1
  run_arm "$gpu" "$feature" neg2 -2
  run_arm "$gpu" "$feature" neg3 -3
}

(
  for feature in 16263 13428 5566 2551 8313; do run_feature 0 "$feature"; done
) & p0=$!
(
  for feature in 7915 5411 2878 3680; do run_feature 1 "$feature"; done
) & p1=$!
wait "$p0" "$p1"
touch "$root/PROBE_COMPLETE"
