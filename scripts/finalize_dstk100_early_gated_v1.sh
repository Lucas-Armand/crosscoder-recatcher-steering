#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering
run="runs/dstk100_early_gated_v1"
mkdir -p "$run/evaluations" "$run/finalizer_logs"
for sample in "$run"/postprocessed/samples_for_external_eval/*_samples.jsonl; do
  stem="$(basename "$sample" _samples.jsonl)"
  /home/lucas/venvs/bigcodebench015/bin/python tools/evaluate_bigcodebench_subset.py --samples "$sample" --output "$run/evaluations/${stem}_eval.json" --parallel 4 > "$run/finalizer_logs/eval_${stem}.log" 2>&1
done
touch "$run/PIPELINE_COMPLETE"
