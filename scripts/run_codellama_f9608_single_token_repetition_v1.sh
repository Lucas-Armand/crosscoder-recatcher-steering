#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering
run="runs/codellama_bm_f9608_single_token_repetition_v1"
input="$run/gated_input.jsonl"
target_positions="$run/gated_target_positions.csv"
sham_positions="$run/gated_sham_positions.csv"
expected=17
features=(9608 5584 10733 10749)
names=(pos0p5 neg0p5 neg1 neg2 neg3)
alphas=(0.5 -0.5 -1 -2 -3)
mkdir -p "$run"/{generations,logs,audit}
common=(
  --checkpoint runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt
  --model-a-id meta-llama/CodeLlama-7b-hf
  --model-b-id DevQuasar-5/coma-7B-v0.1
  --target-side b --layer 16
  --intervention-mode traditional --token-scope last_token
  --no-special-tokens --input-jsonl "$input"
  --max-new-tokens 256 --temperature 0.2 --top-p 0.95
  --generation-backend paired_cached --seed 1000
  --device-a cuda:0 --device-b cuda:0 --dtype float16
  --tokenizer-id meta-llama/CodeLlama-7b-hf
)
run_arm() {
  local label="$1" feature="$2" alpha="$3" positions="$4"
  local out="$run/generations/${label}.jsonl" log="$run/logs/${label}.log"
  local rows=0
  [[ -f "$out" ]] && rows="$(wc -l < "$out")"
  if [[ "$rows" == "$expected" ]]; then echo "$label complete"; return; fi
  if [[ -e "$out" || -e "$log" ]]; then
    local stamp archive
    stamp="$(date +%Y%m%d_%H%M%S)"; archive="$run/audit/${label}_${stamp}"; mkdir -p "$archive"
    [[ -e "$out" ]] && mv "$out" "$archive/"
    [[ -e "$log" ]] && mv "$log" "$archive/"
  fi
  echo "[$(date -Iseconds)] $label feature=$feature alpha=$alpha"
  CUDA_VISIBLE_DEVICES=1 python tools/run_crosscoder_token_position.py "${common[@]}"     --feature-id "$feature" --alpha "$alpha"     --intervention-token-manifest "$positions" --output-jsonl "$out" >"$log" 2>&1
  [[ "$(wc -l < "$out")" == "$expected" ]]
}
for i in "${!names[@]}"; do
  run_arm "f9608_${names[$i]}" 9608 "${alphas[$i]}" "$target_positions"
done
for i in "${!names[@]}"; do
  run_arm "sham9608_${names[$i]}" 9608 "${alphas[$i]}" "$sham_positions"
done
for feature in 5584 10733 10749; do
  for i in "${!names[@]}"; do
    run_arm "random${feature}_${names[$i]}" "$feature" "${alphas[$i]}" "$target_positions"
  done
done
touch "$run/GRID_COMPLETE"
