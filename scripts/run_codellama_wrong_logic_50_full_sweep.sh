#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering

root=runs/codellama_bm_wrong_logic_50_full_sweep_v1
mkdir -p "$root"/{generations,logs}
python tools/prepare_codellama_wrong_logic_50_input.py

run_arm() {
  local gpu="$1" feature="$2" alpha="$3" name="$4"
  local output="$root/generations/${name}.jsonl"
  if [[ -f "$output" && "$(wc -l < "$output")" == 50 ]]; then return; fi
  echo "[$(date -Iseconds)] gpu=$gpu name=$name feature=$feature alpha=$alpha"
  CUDA_VISIBLE_DEVICES="$gpu" python tools/run_crosscoder_intervention.py \
    --checkpoint runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt \
    --model-a-id meta-llama/CodeLlama-7b-hf --model-b-id DevQuasar-5/coma-7B-v0.1 \
    --target-side b --layer 16 --feature-id "$feature" --alpha "$alpha" \
    --intervention-mode traditional --token-scope last_token \
    --generation-backend paired_cached --input-jsonl "$root/input.jsonl" \
    --output-jsonl "$output" --max-new-tokens 512 \
    --temperature 0.2 --top-p 0.95 --seed 1000 \
    --device-a cuda:0 --device-b cuda:0 --dtype float16 \
    --tokenizer-id meta-llama/CodeLlama-7b-hf >"$root/logs/${name}.log" 2>&1
}

(
  run_arm 0 12132 0 baseline
  for feature in 12132 1346 1895 8545 8965; do
    for alpha in 3 4 5; do run_arm 0 "$feature" "$alpha" "f${feature}_pos${alpha}"; done
  done
) & p0=$!
(
  for feature in 13912 14821 2228 3044 6901; do
    for magnitude in 3 4 5; do run_arm 1 "$feature" "-$magnitude" "f${feature}_neg${magnitude}"; done
  done
) & p1=$!
wait "$p0" "$p1"
touch "$root/GENERATIONS_COMPLETE"
