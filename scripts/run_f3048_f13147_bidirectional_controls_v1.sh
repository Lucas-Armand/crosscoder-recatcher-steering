#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering

magnitudes=(0.5 1 2 3 4 5 6)

run_pipeline() {
  local family="$1"
  if [[ "$family" == dstk ]]; then
    local run="runs/dstk100_f3048_bidirectional_controls_v1" n=80 gpu=0 target=3048
    local input="runs/dstk100_continuous_f6404_f10168_f13801_v1/input.jsonl"
    local checkpoint="runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt"
    local model_a="deepseek-ai/deepseek-coder-6.7b-base" model_b="JetBrains/deepseek-coder-6.7B-kexer"
    local tokenizer="deepseek-ai/deepseek-coder-6.7b-base"
    local alternatives=(13801 15669 7828)
    local seeds=(304801 304802 304803)
    local own_side=a reverse_side=b own_sign=-1 reverse_sign=1 trust=(--trust-remote-code)
  else
    local run="runs/codellama_bm_f13147_bidirectional_controls_v1" n=50 gpu=1 target=13147
    local input="runs/codellama_bm_wrong_logic_50_first10_top5_canonical_v1/input.jsonl"
    local checkpoint="runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt"
    local model_a="meta-llama/CodeLlama-7b-hf" model_b="DevQuasar-5/coma-7B-v0.1"
    local tokenizer="meta-llama/CodeLlama-7b-hf"
    local alternatives=(15471 7353 2825)
    local seeds=(1314701 1314702 1314703)
    local own_side=b reverse_side=a own_sign=-1 reverse_sign=1 trust=()
  fi

  mkdir -p "$run"/{generations,logs,shams,postprocessed,evaluations,audit}
  cp -n "$input" "$run/input.jsonl"

  CUDA_VISIBLE_DEVICES="$gpu" .venv/bin/python - "$checkpoint" "$run" "$target" "$own_side" "${seeds[@]}" <<'PY'
import json,numpy as np,sys,torch
from pathlib import Path
checkpoint,run,target,side,*seeds=sys.argv[1:]
run=Path(run); target=int(target)
ck=torch.load(checkpoint,map_location="cpu",weights_only=False)["model_state_dict"]
d=ck[f"decoder_{side}.weight"][:,target].float()
tasks=[json.loads(x)["task_id"] for x in (run/"input.jsonl").open()]
for seed in map(int,seeds):
    g=torch.Generator().manual_seed(seed); v=torch.randn(d.shape,generator=g)
    v=v-(v@d)/(d@d)*d; v=v/v.norm()*d.norm()
    np.savez(run/"shams"/f"sham_seed{seed}.npz",task_ids=np.asarray(tasks),directions=v.numpy()[None,:].repeat(len(tasks),axis=0))
PY

  run_arm() {
    local side="$1" feature="$2" name="$3" alpha="$4"; shift 4
    local out="$run/generations/bigcodebench__${name}_results.jsonl"
    [[ -f "$out" && "$(wc -l < "$out")" == "$n" ]] && return
    echo "[$(date -Iseconds)] $family $name alpha=$alpha"
    CUDA_VISIBLE_DEVICES="$gpu" .venv/bin/python tools/run_crosscoder_intervention.py \
      --checkpoint "$checkpoint" --model-a-id "$model_a" --model-b-id "$model_b" \
      --target-side "$side" --layer 16 --feature-id "$feature" --alpha "$alpha" \
      --intervention-mode traditional --token-scope last_token --generation-backend hf_generate \
      --input-jsonl "$run/input.jsonl" --output-jsonl "$out" --max-new-tokens 512 \
      --temperature 0.2 --top-p 0.95 --seed 1000 --device-${side} cuda:0 --dtype nf4 \
      --tokenizer-id "$tokenizer" "${trust[@]}" "$@" >"$run/logs/${name}.log" 2>&1
    [[ "$(wc -l < "$out")" == "$n" ]]
  }

  run_arm "$own_side" "$target" "${family}_own_alpha0" 0
  run_arm "$reverse_side" "$target" "${family}_reverse_alpha0" 0
  for mag in "${magnitudes[@]}"; do
    run_arm "$own_side" "$target" "f${target}_own_neg${mag}" "-${mag}"
    run_arm "$reverse_side" "$target" "f${target}_reverse_pos${mag}" "$mag"
  done
  for seed in "${seeds[@]}"; do
    for mag in "${magnitudes[@]}"; do
      run_arm "$own_side" "$target" "sham${seed}_neg${mag}" "-${mag}" \
        --per-example-direction-npz "$run/shams/sham_seed${seed}.npz" --preserve-per-example-direction-norm
    done
  done
  for feature in "${alternatives[@]}"; do
    for mag in "${magnitudes[@]}"; do
      run_arm "$own_side" "$feature" "f${feature}_control_neg${mag}" "-${mag}"
    done
  done

  touch "$run/GENERATIONS_COMPLETE"
  .venv/bin/python tools/reprocess_outputs_minimal.py --raw-results-dir "$run/generations" --output-dir "$run/postprocessed" >"$run/logs/reprocess.log" 2>&1
  for sample in "$run"/postprocessed/samples_for_external_eval/*_samples.jsonl; do
    local stem; stem="$(basename "$sample" _samples.jsonl)"
    local eval="$run/evaluations/${stem}_eval.json"
    [[ -f "$eval" ]] && continue
    /home/lucas/venvs/bigcodebench015/bin/python tools/evaluate_bigcodebench_subset.py \
      --samples "$sample" --output "$eval" --parallel 4 >"$run/logs/eval_${stem}.log" 2>&1
  done
  touch "$run/PIPELINE_COMPLETE"
}

run_pipeline "$1"
