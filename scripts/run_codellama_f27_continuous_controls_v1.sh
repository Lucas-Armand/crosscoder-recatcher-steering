#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering

run="runs/codellama_bm_f27_continuous_controls_v1"
input="runs/codellama_bm_wrong_logic_50_first10_top5_canonical_v1/input.jsonl"
mkdir -p "$run"/{generations,logs,shams,audit}
cp -n "$input" "$run/input.jsonl"

CUDA_VISIBLE_DEVICES=0 .venv/bin/python - <<'PY'
import json, numpy as np, torch
from pathlib import Path
run=Path("runs/codellama_bm_f27_continuous_controls_v1")
ck=torch.load("runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt",map_location="cpu",weights_only=False)
d=ck["model_state_dict"]["decoder_b.weight"][:,27].float()
tasks=[json.loads(x)["task_id"] for x in (run/"input.jsonl").open()]
for seed in (2701,2702,2703):
    p=run/"shams"/f"sham_seed{seed}.npz"
    if p.exists(): continue
    g=torch.Generator().manual_seed(seed)
    v=torch.randn(d.shape,generator=g)
    v=v-(v@d)/(d@d)*d
    v=v/v.norm()*d.norm()
    np.savez(p,task_ids=np.asarray(tasks),directions=v.numpy()[None,:].repeat(len(tasks),axis=0))
PY

common=(
  --checkpoint runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt
  --model-a-id meta-llama/CodeLlama-7b-hf --model-b-id DevQuasar-5/coma-7B-v0.1
  --target-side b --layer 16 --intervention-mode traditional --token-scope last_token
  --generation-backend hf_generate --input-jsonl "$run/input.jsonl"
  --max-new-tokens 512 --temperature 0.2 --top-p 0.95 --seed 1000
  --device-b cuda:0 --dtype nf4 --tokenizer-id meta-llama/CodeLlama-7b-hf
)

run_arm() {
  local name="$1" alpha="$2"; shift 2
  local out="$run/generations/bigcodebench__${name}_results.jsonl"
  [[ -f "$out" && "$(wc -l < "$out")" == 50 ]] && return
  echo "[$(date -Iseconds)] $name alpha=$alpha"
  CUDA_VISIBLE_DEVICES=0 .venv/bin/python tools/run_crosscoder_intervention.py \
    "${common[@]}" --feature-id 27 --alpha "$alpha" "$@" \
    --output-jsonl "$out" >"$run/logs/${name}.log" 2>&1
  [[ "$(wc -l < "$out")" == 50 ]]
}

run_arm f27_inverse_neg1 -1
for seed in 2701 2702 2703; do
  for alpha in 3 4 5; do
    run_arm "sham${seed}_pos${alpha}" "$alpha" \
      --per-example-direction-npz "$run/shams/sham_seed${seed}.npz" \
      --preserve-per-example-direction-norm
  done
done
touch "$run/GENERATIONS_COMPLETE"
