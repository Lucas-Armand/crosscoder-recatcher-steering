#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering

run="runs/dstk100_f10168_reverse_regressions_v1"
mkdir -p "$run"/{generations,logs,postprocessed,evaluations}
.venv/bin/python - <<'PY'
import csv,json
from pathlib import Path
labels={}
for r in csv.DictReader(open('reports/paper_v1_v4_evaluation_labels.csv')):
 if r['benchmark']=='bigcodebench' and r['model'] in {'deepseek_base','deepseek_finetuned'}:
  labels[(r['model'],r['task_id'])]=int(r['label'])
wanted={t for (m,t),v in labels.items() if m=='deepseek_base' and v==0 and labels.get(('deepseek_finetuned',t))==1}
source=Path('/tmp/crosscoder_postprocess_and_eval_v4/out/results_repaired/bigcodebench__deepseek_finetuned_repaired.jsonl')
rows=[]
for line in source.open():
 r=json.loads(line)
 if r.get('task_id') in wanted:
  rows.append({'benchmark':'bigcodebench','task_id':r['task_id'],'task_idx':r['task_idx'],'entry_point':r['entry_point'],'prompt':r['prompt'],'original_prompt':r['prompt'],'seed':1000+int(r['task_idx'])})
rows.sort(key=lambda x:x['task_idx'])
assert len(rows)==len(wanted)==79,(len(rows),len(wanted))
Path('runs/dstk100_f10168_reverse_regressions_v1/input.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
PY

for alpha in 1 2 3 4 5; do
  out="$run/generations/bigcodebench__f10168_ft_reverse_pos${alpha}_results.jsonl"
  if [[ ! -f "$out" || "$(wc -l < "$out")" != 79 ]]; then
    CUDA_VISIBLE_DEVICES=1 .venv/bin/python tools/run_crosscoder_intervention.py \
      --checkpoint runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt \
      --model-a-id deepseek-ai/deepseek-coder-6.7b-base --model-b-id JetBrains/deepseek-coder-6.7B-kexer \
      --target-side b --layer 16 --feature-id 10168 --alpha "$alpha" \
      --intervention-mode traditional --token-scope last_token --generation-backend hf_generate \
      --input-jsonl "$run/input.jsonl" --output-jsonl "$out" --max-new-tokens 512 \
      --temperature 0.2 --top-p 0.95 --seed 1000 --device-b cuda:0 --dtype nf4 \
      --tokenizer-id deepseek-ai/deepseek-coder-6.7b-base --trust-remote-code >"$run/logs/pos${alpha}.log" 2>&1
  fi
  [[ "$(wc -l < "$out")" == 79 ]]
done
touch "$run/GENERATIONS_COMPLETE"
.venv/bin/python tools/reprocess_outputs_minimal.py --raw-results-dir "$run/generations" --output-dir "$run/postprocessed" >"$run/logs/reprocess.log" 2>&1
for sample in "$run"/postprocessed/samples_for_external_eval/*_samples.jsonl; do
  stem="$(basename "$sample" _samples.jsonl)"
  /home/lucas/venvs/bigcodebench015/bin/python tools/evaluate_bigcodebench_subset.py --samples "$sample" --output "$run/evaluations/${stem}_eval.json" --parallel 4 >"$run/logs/eval_${stem}.log" 2>&1
done
touch "$run/EVALUATION_COMPLETE"
