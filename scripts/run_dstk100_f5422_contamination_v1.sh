#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering
run=runs/dstk100_f5422_test_contamination_v1
mkdir -p "$run"/{generations,logs,postprocessed,evaluations,finalizer_logs}
python - <<'PY'
import csv,json
from pathlib import Path
repo=Path('/home/lucas/crosscoder-recatcher-steering')
cases={r['task_id'] for r in csv.DictReader(open(repo/'reports/dstk100_transition_failure_analysis_v1/transition_failure_cases.csv')) if r['benchmark']=='bigcodebench' and r['transition']=='improvement' and r['primary_failure_category']=='generated_test_import_contamination'}
src=Path('/tmp/crosscoder_postprocess_and_eval_v4/out/results_repaired/bigcodebench__deepseek_base_repaired.jsonl')
rows=[json.loads(x) for x in src.read_text().splitlines()]
out=[]
for r in rows:
 if r['task_id'] not in cases or int(r.get('gen_idx',r.get('generation_idx',0)))!=0: continue
 idx=int(r['task_id'].split('/')[-1]);r['gen_idx']=0;r['seed']=1000+idx*100;out.append(r)
assert len(out)==119,len(out)
p=repo/'runs/dstk100_f5422_test_contamination_v1/input.jsonl';p.write_text(''.join(json.dumps(r)+'\n' for r in sorted(out,key=lambda x:int(x['task_id'].split('/')[-1]))))
PY
common=(--checkpoint runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt --model-a-id deepseek-ai/deepseek-coder-6.7b-base --model-b-id JetBrains/deepseek-coder-6.7B-kexer --target-side a --layer 16 --feature-id 5422 --intervention-mode topk_gated_suppression --token-scope last_token --generation-backend paired_cached --top-k 100 --rms-epsilon 1e-6 --input-jsonl "$run/input.jsonl" --max-new-tokens 512 --temperature 0.2 --top-p 0.95 --seed 1000 --device-a cuda:0 --device-b cuda:1 --dtype nf4 --reference-dtype float16 --tokenizer-id deepseek-ai/deepseek-coder-6.7b-base --trust-remote-code)
arm(){ local n=$1 a=$2;.venv/bin/python tools/run_crosscoder_intervention.py "${common[@]}" --alpha "$a" --output-jsonl "$run/generations/bigcodebench__f5422_alpha_${n}_results.jsonl" >"$run/logs/${n}.log" 2>&1; }
arm zero 0
python - <<'PY'
import json
from pathlib import Path
r=Path('runs/dstk100_f5422_test_contamination_v1');a=[json.loads(x) for x in (r/'input.jsonl').read_text().splitlines()];b=[json.loads(x) for x in (r/'generations/bigcodebench__f5422_alpha_zero_results.jsonl').read_text().splitlines()];checks=[{'task_id':x['task_id'],'exact_raw_completion':x['raw_completion']==y['raw_completion']} for x,y in zip(a,b)];(r/'BASELINE_REPRODUCTION.json').write_text(json.dumps(checks,indent=2)+'\n');assert len(checks)==119 and all(x['exact_raw_completion'] for x in checks)
PY
arm neg0p5 -0.5
arm neg1 -1
arm neg2 -2
arm neg3 -3
arm pos1 +1
.venv/bin/python tools/reprocess_outputs_minimal.py --raw-results-dir "$run/generations" --output-dir "$run/postprocessed" >"$run/finalizer_logs/reprocess.log" 2>&1
for sample in "$run"/postprocessed/samples_for_external_eval/*_samples.jsonl; do stem=$(basename "$sample" _samples.jsonl);/home/lucas/venvs/bigcodebench015/bin/python tools/evaluate_bigcodebench_subset.py --samples "$sample" --output "$run/evaluations/${stem}_eval.json" --parallel 4 >"$run/finalizer_logs/eval_${stem}.log" 2>&1;done
touch "$run/PIPELINE_COMPLETE"
