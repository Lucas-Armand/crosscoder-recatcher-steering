#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-full}"
ACTIVATION_ROOTS="${ACTIVATION_ROOTS:-${ACTIVATION_ROOT:-}}"
: "${ACTIVATION_ROOTS:?Set ACTIVATION_ROOT or colon-separated ACTIVATION_ROOTS}"
CHECKPOINT_ROOT="${CHECKPOINT_ROOT:?Set CHECKPOINT_ROOT to materialized checkpoints}"
LABELS_CSV="${LABELS_CSV:-reports/paper_v1_v4_evaluation_labels.csv}"
DATASET="${DATASET:-gs://data-intelligence-bucket/tests/recatcher_crosscoder_humaneval/crosscoder_final_dataset_v1_postprocessed_extraction_v4}"
OUTPUT_ROOT="${OUTPUT_ROOT:-reports/differential_pr_auc_feature_screening}"
SEED="${SEED:-42}"

args=(
  --manifest manifests/paper_v1_extraction_v4.json
  --checkpoint-root "$CHECKPOINT_ROOT"
  --labels-csv "$LABELS_CSV"
  --dataset "$DATASET"
  --output-root "$OUTPUT_ROOT"
  --seed "$SEED"
  --device "${DEVICE:-cuda}"
)
read -r -a percentiles <<< "${PERCENTILES:-50 60 70 80 90 95 99}"
args+=(--percentiles "${percentiles[@]}")
IFS=: read -r -a activation_roots <<< "$ACTIVATION_ROOTS"
for activation_root in "${activation_roots[@]}"; do
  args+=(--activation-root "$activation_root")
done

case "$MODE" in
  smoke) args+=(--smoke-test) ;;
  full) args+=(--permutations "${PERMUTATIONS:-200}") ;;
  *) echo "Usage: $0 [smoke|full]" >&2; exit 2 ;;
esac

"${PYTHON:-.venv/bin/python}" tools/run_differential_pr_auc_screening.py "${args[@]}"
