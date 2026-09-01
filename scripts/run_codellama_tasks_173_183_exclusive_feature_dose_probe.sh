#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering

root=runs/codellama_bm_tasks_173_183_exclusive_feature_dose_probe_v1
source_root=runs/codellama_bm_tasks_173_183_exclusive_feature_probe_v1
mkdir -p "$root"/{generations,logs}
cp -n "$source_root/input.jsonl" "$root/input.jsonl"
cp -n "$source_root/generations/baseline.jsonl" "$root/generations/baseline.jsonl"

base_only=(13713 9291 10509 1525)
merged_only=(188 855 8131 16088)

run_arm() {
  local feature="$1" alpha="$2" name="$3"
  local output="$root/generations/${name}.jsonl"
  if [[ -f "$output" && "$(wc -l < "$output")" == 2 ]]; then return; fi
  echo "[$(date -Iseconds)] $name feature=$feature alpha=$alpha"
  CUDA_VISIBLE_DEVICES=1 python tools/run_crosscoder_intervention.py \
    --checkpoint runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt \
    --model-a-id meta-llama/CodeLlama-7b-hf \
    --model-b-id DevQuasar-5/coma-7B-v0.1 \
    --target-side b --layer 16 --feature-id "$feature" --alpha "$alpha" \
    --intervention-mode traditional --token-scope last_token \
    --generation-backend paired_cached --input-jsonl "$root/input.jsonl" \
    --output-jsonl "$output" --max-new-tokens 30 \
    --temperature 0.2 --top-p 0.95 --seed 1000 \
    --device-a cuda:0 --device-b cuda:0 --dtype float16 \
    --tokenizer-id meta-llama/CodeLlama-7b-hf \
    >"$root/logs/${name}.log" 2>&1
}

for feature in "${base_only[@]}"; do
  for magnitude in 2 3 4 5; do
    run_arm "$feature" "$magnitude" "base_only_f${feature}_pos${magnitude}"
  done
done
for feature in "${merged_only[@]}"; do
  for magnitude in 2 3 4 5; do
    run_arm "$feature" "-$magnitude" "merged_only_f${feature}_neg${magnitude}"
  done
done
touch "$root/PROBE_COMPLETE"
