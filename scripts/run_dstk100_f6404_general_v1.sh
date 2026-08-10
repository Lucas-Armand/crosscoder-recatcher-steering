#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering
run="runs/dstk100_f6404_test_contamination_general_v1"
mkdir -p "$run/generations" "$run/logs" "$run/evaluations" "$run/postprocessed" "$run/finalizer_logs"
common=(
  --checkpoint runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt
  --model-a-id deepseek-ai/deepseek-coder-6.7b-base
  --model-b-id JetBrains/deepseek-coder-6.7B-kexer
  --target-side a --layer 16 --feature-id 6404
  --intervention-mode topk_gated_suppression
  --token-scope last_token --generation-backend paired_cached
  --top-k 100 --rms-epsilon 1e-6
  --input-jsonl "$run/input.jsonl"
  --max-new-tokens 512 --temperature 0.2 --top-p 0.95
  --seed 1000 --device-a cuda:0 --device-b cuda:1
  --dtype nf4 --reference-dtype float16
  --tokenizer-id deepseek-ai/deepseek-coder-6.7b-base --trust-remote-code
)
run_arm() {
  local name="$1" alpha="$2"
  .venv/bin/python tools/run_crosscoder_intervention.py "${common[@]}" --alpha "$alpha" \
    --output-jsonl "$run/generations/bigcodebench__${name}_results.jsonl" \
    > "$run/logs/${name}.log" 2>&1
}
run_arm baseline_alpha0 0
.venv/bin/python - <<'PY'
import json
from pathlib import Path
run=Path("runs/dstk100_f6404_test_contamination_general_v1")
expected=[json.loads(x) for x in (run/"input.jsonl").read_text().splitlines()]
observed=[json.loads(x) for x in (run/"generations/bigcodebench__baseline_alpha0_results.jsonl").read_text().splitlines()]
checks=[{"task_id":x["task_id"],"exact_raw_completion":x["raw_completion"]==y["raw_completion"]} for x,y in zip(expected,observed)]
(run/"BASELINE_REPRODUCTION.json").write_text(json.dumps(checks,indent=2)+"\n")
if len(checks)!=len(expected) or not all(x["exact_raw_completion"] for x in checks):
    raise SystemExit("baseline reproduction gate failed")
PY
run_arm f6404_alpha_neg0p5 -0.5
run_arm f6404_alpha_neg1 -1
run_arm f6404_alpha_neg2 -2
.venv/bin/python tools/reprocess_outputs_minimal.py --raw-results-dir "$run/generations" --output-dir "$run/postprocessed" > "$run/finalizer_logs/reprocess.log" 2>&1
for sample in "$run"/postprocessed/results_repaired/*_repaired.jsonl; do
  stem="$(basename "$sample" _repaired.jsonl)"
  /home/lucas/venvs/bigcodebench015/bin/python tools/evaluate_bigcodebench_subset.py --samples "$sample" --output "$run/evaluations/${stem}_eval.json" --parallel 4 > "$run/finalizer_logs/eval_${stem}.log" 2>&1
done
touch "$run/PIPELINE_COMPLETE"
