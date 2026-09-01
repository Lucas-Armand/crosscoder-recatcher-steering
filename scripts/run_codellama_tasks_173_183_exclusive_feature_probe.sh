#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering

root=runs/codellama_bm_tasks_173_183_exclusive_feature_probe_v1
mkdir -p "$root"/{generations,logs}
.venv/bin/python tools/prepare_codellama_tasks_173_183_input.py

base_only=(13713 9291 10509 1525 15243 14980 2310 16060 9163 11244 2155 8393 2685 12062 4028 1970 3503 1687 6129 3350)
merged_only=(188 8131 855 13359 16088 4130 15875 9558 5903 6693 7274 6005)

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

run_arm 188 0 baseline
for feature in "${merged_only[@]}"; do
  run_arm "$feature" -1 "merged_only_f${feature}_neg1"
done
for feature in "${base_only[@]}"; do
  run_arm "$feature" 1 "base_only_f${feature}_pos1"
done
touch "$root/PROBE_COMPLETE"
