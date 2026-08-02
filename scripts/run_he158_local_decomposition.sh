#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering
components=(
  projection_different_own_text_scaled
  residual_different_own_text_scaled
  projection_local_pc1_to_pc5_span_scaled
  residual_local_pc1_to_pc5_span_scaled
)
for component in "${components[@]}"; do
  out="runs/local_task_mechanisms/deepseek_base_finetuned_layer16/he158_steering/generations/${component}_pos6.jsonl"
  log="runs/local_task_mechanisms/deepseek_base_finetuned_layer16/he158_steering/logs/${component}_pos6.log"
  .venv/bin/python tools/run_crosscoder_intervention.py \
    --checkpoint runs/crosscoder_training_v1/deepseek_base_vs_deepseek_finetuned_layer16_lat16384_steps20000/final.pt \
    --model-a-id deepseek-ai/deepseek-coder-6.7b-base \
    --model-b-id JetBrains/deepseek-coder-6.7B-kexer \
    --target-side a --layer 16 --feature-id 0 \
    --per-example-direction-npz "runs/local_task_mechanisms/deepseek_base_finetuned_layer16/he158_decomposition/HumanEval_158__${component}.npz" \
    --alpha 6 --intervention-mode traditional --token-scope last_token \
    --input-jsonl runs/local_task_mechanisms/deepseek_base_finetuned_layer16/he158_steering/input.jsonl \
    --output-jsonl "$out" --max-new-tokens 512 --temperature 0.2 --top-p 0.95 \
    --generation-backend hf_generate --seed 16800 --device-a cuda:0 --device-b cuda:1 \
    --dtype nf4 --trust-remote-code --tokenizer-id deepseek-ai/deepseek-coder-6.7b-base \
    >"$log" 2>&1
done
