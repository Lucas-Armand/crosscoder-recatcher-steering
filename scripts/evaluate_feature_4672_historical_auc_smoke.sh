#!/usr/bin/env bash
set -euo pipefail

cd "${REPO_ROOT:-$HOME/crosscoder-recatcher-steering}"
run_dir="runs/steering_historical_auc_feature_4672"

for tag in zero neg_0p10_p99 neg_0p25_p99 neg_0p50_p99 neg_1p00_p99; do
  model_label="deepseek_base__feature_4672__alpha_${tag}"
  eval_root="${run_dir}/evaluation/${tag}"
  bash scripts/prepare_and_postprocess_generation.sh \
    "${run_dir}/generations/alpha_${tag}.jsonl" \
    humanevalplus "$model_label" "$eval_root"
  .venv/bin/python tools/evaluate_humaneval_local.py \
    --repaired-jsonl "${eval_root}/postprocessed/results_repaired/humanevalplus__${model_label}_repaired.jsonl" \
    --output-jsonl "${eval_root}/results.jsonl" \
    --timeout 5 \
    --field candidate_code_repaired
done
