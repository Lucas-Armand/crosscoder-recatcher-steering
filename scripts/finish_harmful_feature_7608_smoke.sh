#!/usr/bin/env bash
set -euo pipefail

cd "${REPO_ROOT:-$HOME/crosscoder-recatcher-steering}"
run_dir="runs/steering_harmful_feature_7608"
baseline_pid="${BASELINE_PID:-}"
if [[ -n "$baseline_pid" ]]; then
  while kill -0 "$baseline_pid" 2>/dev/null; do sleep 10; done
fi
test "$(wc -l < "$run_dir/baseline/alpha_0.jsonl")" -eq 10

bash scripts/prepare_and_postprocess_generation.sh \
  "$run_dir/baseline/alpha_0.jsonl" bigcodebench harmful7608_baseline \
  "$run_dir/baseline/evaluation"
/home/lucas/venvs/bigcodebench015/bin/python tools/evaluate_bigcodebench_subset.py \
  --samples "$run_dir/baseline/evaluation/postprocessed/samples_for_external_eval/bigcodebench__harmful7608_baseline_samples.jsonl" \
  --output "$run_dir/baseline/evaluation/subset_eval_results.json"

python tools/prepare_harmful_feature_steering_smoke.py \
  --candidate-tasks reports/differential_percentile_pr_auc_screening/candidate_task_examples.csv \
  --raw-results /tmp/crosscoder_postprocess_and_eval_v4/out/raw_results/bigcodebench__deepseek_finetuned_results.jsonl \
  --output-dir "$run_dir/selection" --baseline-eval "$run_dir/baseline/evaluation/subset_eval_results.json"

bash scripts/run_harmful_feature_7608_smoke.sh
mkdir -p "$run_dir/evaluations"
for generation in "$run_dir"/generations/*.jsonl; do
  stem="$(basename "$generation" .jsonl)"
  output="$run_dir/evaluations/$stem"
  bash scripts/prepare_and_postprocess_generation.sh \
    "$generation" bigcodebench "$stem" "$output"
  /home/lucas/venvs/bigcodebench015/bin/python tools/evaluate_bigcodebench_subset.py \
    --samples "$output/postprocessed/samples_for_external_eval/bigcodebench__${stem}_samples.jsonl" \
    --output "$output/subset_eval_results.json"
done
date -Is > "$run_dir/COMPLETE"
