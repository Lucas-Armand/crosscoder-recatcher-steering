#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering

run="runs/dstk100_f10168_continuous_controls_v1"
input="runs/dstk100_continuous_f6404_f10168_f13801_v1/input.jsonl"
mkdir -p "$run"/{generations,logs,shams,audit}
cp -n "$input" "$run/input.jsonl"

CUDA_VISIBLE_DEVICES=1 .venv/bin/python - <<'PY'
import json, numpy as np, torch
from pathlib import Path
run=Path("runs/dstk100_f10168_continuous_controls_v1")
ck=torch.load("runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt",map_location="cpu",weights_only=False)
d=ck["model_state_dict"]["decoder_a.weight"][:,10168].float()
tasks=[json.loads(x)["task_id"] for x in (run/"input.jsonl").open()]
for seed in (1016801,1016802,1016803):
    p=run/"shams"/f"sham_seed{seed}.npz"
    if p.exists(): continue
    g=torch.Generator().manual_seed(seed)
    v=torch.randn(d.shape,generator=g)
    v=v-(v@d)/(d@d)*d
    v=v/v.norm()*d.norm()
    np.savez(p,task_ids=np.asarray(tasks),directions=v.numpy()[None,:].repeat(len(tasks),axis=0))
PY

common=(
  --checkpoint runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt
  --model-a-id deepseek-ai/deepseek-coder-6.7b-base
  --model-b-id JetBrains/deepseek-coder-6.7B-kexer
  --target-side a --layer 16 --intervention-mode traditional --token-scope last_token
  --generation-backend hf_generate --input-jsonl "$run/input.jsonl"
  --max-new-tokens 512 --temperature 0.2 --top-p 0.95 --seed 1000
  --device-a cuda:0 --dtype nf4 --tokenizer-id deepseek-ai/deepseek-coder-6.7b-base
  --trust-remote-code
)

run_arm() {
  local feature="$1" name="$2" alpha="$3"; shift 3
  local out="$run/generations/bigcodebench__${name}_results.jsonl"
  [[ -f "$out" && "$(wc -l < "$out")" == 80 ]] && return
  echo "[$(date -Iseconds)] $name alpha=$alpha"
  CUDA_VISIBLE_DEVICES=1 .venv/bin/python tools/run_crosscoder_intervention.py \
    "${common[@]}" --feature-id "$feature" --alpha "$alpha" "$@" \
    --output-jsonl "$out" >"$run/logs/${name}.log" 2>&1
  [[ "$(wc -l < "$out")" == 80 ]]
}

run_arm 10168 f10168_inverse_pos1 1
for seed in 1016801 1016802 1016803; do
  for alpha in 1 2 3 4 5; do
    run_arm 10168 "sham${seed}_neg${alpha}" "-${alpha}" \
      --per-example-direction-npz "$run/shams/sham_seed${seed}.npz" \
      --preserve-per-example-direction-norm
  done
done
for alpha in 1 2 3 4 5; do
  run_arm 9537 "f9537_neg${alpha}" "-${alpha}"
done
touch "$run/GENERATIONS_COMPLETE"
