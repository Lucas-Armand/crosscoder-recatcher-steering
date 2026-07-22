#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-full}"
ACTIVATION_ROOT="${ACTIVATION_ROOT:?Set ACTIVATION_ROOT to canonical activation root}"
CHECKPOINT_ROOT="${CHECKPOINT_ROOT:?Set CHECKPOINT_ROOT to materialized paper-v1 checkpoints}"
LABELS_CSV="${LABELS_CSV:-reports/paper_v1_evaluation_labels.csv}"
OUTPUT_ROOT="${OUTPUT_ROOT:-reports/roc_auc_feature_screening}"
SEED="${SEED:-42}"

args=(
  --manifest manifests/paper_v1.json
  --activation-root "$ACTIVATION_ROOT"
  --checkpoint-root "$CHECKPOINT_ROOT"
  --labels-csv "$LABELS_CSV"
  --output-root "$OUTPUT_ROOT"
  --seed "$SEED"
)

case "$MODE" in
  smoke) args+=(--smoke-test) ;;
  full) args+=(--permutations "${PERMUTATIONS:-5000}") ;;
  *) echo "Usage: $0 [smoke|full]" >&2; exit 2 ;;
esac

python tools/run_roc_auc_feature_screening.py "${args[@]}"
