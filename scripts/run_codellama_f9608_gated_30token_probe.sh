#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering
root=runs/codellama_bm_f9608_gated_30token_probe_v1
input=runs/codellama_bm_repetition_10token_probe_v1/feature_5411/input.jsonl
mkdir -p "$root"/{generations,logs,audit}
cp -n "$input" "$root/input.jsonl"
names=(zero neg0p5 neg1 neg2 neg3)
alphas=(0 -0.5 -1 -2 -3)
for i in "${!names[@]}"; do
  name="${names[$i]}"; alpha="${alphas[$i]}"
  output="$root/generations/${name}.jsonl"
  if [[ -f "$output" && "$(wc -l < "$output")" == 41 ]]; then continue; fi
  echo "[$(date -Iseconds)] alpha=$alpha"
  CUDA_VISIBLE_DEVICES=0,1 python tools/run_crosscoder_intervention.py \
    --checkpoint runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt \
    --model-a-id meta-llama/CodeLlama-7b-hf --model-b-id DevQuasar-5/coma-7B-v0.1 \
    --target-side b --layer 16 --feature-id 9608 --alpha "$alpha" \
    --intervention-mode topk_gated_suppression --token-scope last_token \
    --generation-backend paired_cached --top-k 100 --rms-epsilon 1e-6 \
    --input-jsonl "$root/input.jsonl" --output-jsonl "$output" \
    --max-new-tokens 30 --temperature 0.2 --top-p 0.95 --seed 1000 \
    --device-a cuda:0 --device-b cuda:1 --dtype float16 --reference-dtype float16 \
    --tokenizer-id meta-llama/CodeLlama-7b-hf >"$root/logs/${name}.log" 2>&1
done
touch "$root/PROBE_COMPLETE"
