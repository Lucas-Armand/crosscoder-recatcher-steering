#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering
root=runs/codellama_bm_f9608_standard_30token_probe_v1
input=runs/codellama_bm_repetition_10token_probe_v1/feature_5411/input.jsonl
mkdir -p "$root"/{generations,logs,audit}
cp -n "$input" "$root/input.jsonl"

run_arm() {
  local gpu="$1" name="$2" alpha="$3"
  local output="$root/generations/${name}.jsonl"
  if [[ -f "$output" && "$(wc -l < "$output")" == 41 ]]; then return; fi
  echo "[$(date -Iseconds)] gpu=$gpu alpha=$alpha"
  CUDA_VISIBLE_DEVICES="$gpu" python tools/run_crosscoder_intervention.py \
    --checkpoint runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt \
    --model-a-id meta-llama/CodeLlama-7b-hf --model-b-id DevQuasar-5/coma-7B-v0.1 \
    --target-side b --layer 16 --feature-id 9608 --alpha "$alpha" \
    --intervention-mode traditional --token-scope last_token \
    --generation-backend paired_cached --input-jsonl "$root/input.jsonl" \
    --output-jsonl "$output" --max-new-tokens 30 --temperature 0.2 --top-p 0.95 \
    --seed 1000 --device-a cuda:0 --device-b cuda:0 --dtype float16 \
    --tokenizer-id meta-llama/CodeLlama-7b-hf >"$root/logs/${name}.log" 2>&1
}

(
  run_arm 0 zero 0
  run_arm 0 neg1 -1
  run_arm 0 neg3 -3
) & p0=$!
(
  run_arm 1 neg0p5 -0.5
  run_arm 1 neg2 -2
) & p1=$!
wait "$p0" "$p1"
touch "$root/PROBE_COMPLETE"
