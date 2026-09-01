#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering

run="runs/codellama_bm_f27_lowdose_and_reverse_v1"
mkdir -p "$run"/{generations,logs,postprocessed,evaluations,shams}
cp -n runs/codellama_bm_wrong_logic_50_first10_top5_canonical_v1/input.jsonl "$run/regression_input.jsonl"
cp -n runs/codellama_bm_f27_continuous_controls_v1/shams/*.npz "$run/shams/"

.venv/bin/python - <<'PY'
import csv,json
from pathlib import Path
trans=Path('reports/codellama_base_merged_topk100_v1_validation/transition_populations.csv')
source=Path('/tmp/crosscoder_postprocess_and_eval_v4/out/results_repaired/bigcodebench__codellama_base_repaired.jsonl')
wanted={r['task_id'] for r in csv.DictReader(trans.open()) if r['benchmark']=='bigcodebench' and r['transition']=='improvement'}
rows=[]
for line in source.open():
 r=json.loads(line)
 if r.get('task_id') in wanted:
  rows.append({'benchmark':'bigcodebench','task_id':r['task_id'],'task_idx':r['task_idx'],'entry_point':r['entry_point'],'prompt':r['prompt'],'original_prompt':r['prompt'],'seed':1000+int(r['task_idx'])})
rows.sort(key=lambda x:x['task_idx'])
assert len(rows)==len(wanted)==4,(len(rows),len(wanted))
Path('runs/codellama_bm_f27_lowdose_and_reverse_v1/reverse_input.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
PY

generate() {
  local side="$1" input="$2" feature="$3" name="$4" alpha="$5" expected="$6"; shift 6
  local out="$run/generations/bigcodebench__${name}_results.jsonl"
  [[ -f "$out" && "$(wc -l < "$out")" == "$expected" ]] && return
  CUDA_VISIBLE_DEVICES=0 .venv/bin/python tools/run_crosscoder_intervention.py \
    --checkpoint runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt \
    --model-a-id meta-llama/CodeLlama-7b-hf --model-b-id DevQuasar-5/coma-7B-v0.1 \
    --target-side "$side" --layer 16 --feature-id "$feature" --alpha "$alpha" \
    --intervention-mode traditional --token-scope last_token --generation-backend hf_generate \
    --input-jsonl "$input" --output-jsonl "$out" --max-new-tokens 512 \
    --temperature 0.2 --top-p 0.95 --seed 1000 --device-${side} cuda:0 --dtype nf4 \
    --tokenizer-id meta-llama/CodeLlama-7b-hf "$@" >"$run/logs/${name}.log" 2>&1
  [[ "$(wc -l < "$out")" == "$expected" ]]
}

for alpha in 1 2; do
  for feature in 27 13132 9430 6230; do
    generate b "$run/regression_input.jsonl" "$feature" "f${feature}_pos${alpha}" "$alpha" 50
  done
  for seed in 2701 2702 2703; do
    generate b "$run/regression_input.jsonl" 27 "sham${seed}_pos${alpha}" "$alpha" 50 \
      --per-example-direction-npz "$run/shams/sham_seed${seed}.npz" --preserve-per-example-direction-norm
  done
done

for alpha in 1 2 3 4 5; do
  generate a "$run/reverse_input.jsonl" 27 "f27_base_reverse_neg${alpha}" "-${alpha}" 4
done
touch "$run/GENERATIONS_COMPLETE"

.venv/bin/python tools/reprocess_outputs_minimal.py --raw-results-dir "$run/generations" --output-dir "$run/postprocessed" >"$run/logs/reprocess.log" 2>&1
for sample in "$run"/postprocessed/samples_for_external_eval/*_samples.jsonl; do
  stem="$(basename "$sample" _samples.jsonl)"
  /home/lucas/venvs/bigcodebench015/bin/python tools/evaluate_bigcodebench_subset.py --samples "$sample" --output "$run/evaluations/${stem}_eval.json" --parallel 4 >"$run/logs/eval_${stem}.log" 2>&1
done
touch "$run/EVALUATION_COMPLETE"
