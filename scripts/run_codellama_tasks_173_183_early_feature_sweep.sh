#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering

root=runs/codellama_bm_tasks_173_183_early_feature_sweep_v1
source_root=runs/codellama_bm_tasks_173_183_exclusive_feature_probe_v1
mkdir -p "$root"/{probe,full,logs}
cp -n "$source_root/input.jsonl" "$root/input.jsonl"
cp -n "$source_root/generations/baseline.jsonl" "$root/probe/baseline.jsonl"

base_only=(9291 12780 16058 3503 13479 1727 15041 14631 8545 5716 1551 2224 11396 4529 13499 8928 1346 8496 1895 12132 1970 9075 8965 4033)
merged_only=(7299 7758 6491 10040 6901 2371 13912 3225 13080 3044 4634 14821 942 12405 6051 577 2695 13204 14129 4709 2228 3255 15163 9948 6839 12491 507)

run_arm() {
  local feature="$1" alpha="$2" name="$3" max_tokens="$4" output_dir="$5"
  local output="$root/$output_dir/${name}.jsonl"
  if [[ -f "$output" && "$(wc -l < "$output")" == 2 ]]; then return; fi
  echo "[$(date -Iseconds)] phase=$output_dir name=$name feature=$feature alpha=$alpha"
  CUDA_VISIBLE_DEVICES=1 python tools/run_crosscoder_intervention.py \
    --checkpoint runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt \
    --model-a-id meta-llama/CodeLlama-7b-hf \
    --model-b-id DevQuasar-5/coma-7B-v0.1 \
    --target-side b --layer 16 --feature-id "$feature" --alpha "$alpha" \
    --intervention-mode traditional --token-scope last_token \
    --generation-backend paired_cached --input-jsonl "$root/input.jsonl" \
    --output-jsonl "$output" --max-new-tokens "$max_tokens" \
    --temperature 0.2 --top-p 0.95 --seed 1000 \
    --device-a cuda:0 --device-b cuda:0 --dtype float16 \
    --tokenizer-id meta-llama/CodeLlama-7b-hf \
    >"$root/logs/${output_dir}_${name}.log" 2>&1
}

for feature in "${base_only[@]}"; do
  for magnitude in 1 2 3 4 5; do
    run_arm "$feature" "$magnitude" "base_only_f${feature}_pos${magnitude}" 30 probe
  done
done
for feature in "${merged_only[@]}"; do
  for magnitude in 1 2 3 4 5; do
    run_arm "$feature" "-$magnitude" "merged_only_f${feature}_neg${magnitude}" 30 probe
  done
done
touch "$root/PROBE_COMPLETE"

python tools/analyze_codellama_tasks_173_183_early_feature_probe.py \
  >"$root/probe_analysis.log" 2>&1

while IFS=, read -r arm side feature alpha changed_count changed_tasks; do
  [[ "$arm" == "arm" ]] && continue
  [[ -z "$arm" ]] && continue
  run_arm "$feature" "$alpha" "$arm" 512 full
done < "$root/selected_for_full.csv"

touch "$root/FULL_COMPLETE"
