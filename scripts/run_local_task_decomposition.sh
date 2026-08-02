#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering
task_id="${1:?Usage: $0 TASK_ID [ALPHA]}"
alpha="${2:-6}"
safe="${task_id//\//_}"
task_number="${task_id##*/}"
root="runs/local_task_mechanisms/deepseek_base_finetuned_layer16"
work="${root}/task_${task_number}_steering"
mkdir -p "$work/generations" "$work/logs"
python - "$task_id" "$work/input.jsonl" <<'PY'
import json,sys
task_id,out=sys.argv[1:]
source="runs/discriminant_direction_steering_smoke/input.jsonl"
rows=[json.loads(line) for line in open(source) if line.strip()]
matches=[row for row in rows if row["task_id"] == task_id]
if len(matches) != 1: raise SystemExit(f"expected one {task_id}; got {len(matches)}")
with open(out,"w") as handle: handle.write(json.dumps(matches[0])+"\n")
PY
components=(
  projection_different_own_text_scaled
  residual_different_own_text_scaled
  projection_local_pc1_to_pc5_span_scaled
  residual_local_pc1_to_pc5_span_scaled
)
for component in "${components[@]}"; do
  out="$work/generations/${component}_pos${alpha}.jsonl"
  log="$work/logs/${component}_pos${alpha}.log"
  .venv/bin/python tools/run_crosscoder_intervention.py \
    --checkpoint runs/crosscoder_training_v1/deepseek_base_vs_deepseek_finetuned_layer16_lat16384_steps20000/final.pt \
    --model-a-id deepseek-ai/deepseek-coder-6.7b-base \
    --model-b-id JetBrains/deepseek-coder-6.7B-kexer \
    --target-side a --layer 16 --feature-id 0 \
    --per-example-direction-npz "$root/task_${task_number}_decomposition/${safe}__${component}.npz" \
    --alpha "$alpha" --intervention-mode traditional --token-scope last_token \
    --input-jsonl "$work/input.jsonl" \
    --output-jsonl "$out" --max-new-tokens 512 --temperature 0.2 --top-p 0.95 \
    --generation-backend hf_generate --seed 16800 --device-a cuda:0 --device-b cuda:1 \
    --dtype nf4 --trust-remote-code --tokenizer-id deepseek-ai/deepseek-coder-6.7b-base \
    >"$log" 2>&1
done
