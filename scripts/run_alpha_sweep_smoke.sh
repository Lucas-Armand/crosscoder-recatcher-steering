#!/usr/bin/env bash
set -euo pipefail

cd "${REPO_ROOT:-$HOME/crosscoder-recatcher-steering}"

FEATURE_ID="${FEATURE_ID:?Set FEATURE_ID}"
MAX_EXAMPLES="${MAX_EXAMPLES:-2}"
MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-64}"

for alpha in -1 -0.75 -0.5 0 1; do
  echo "===== feature=$FEATURE_ID alpha=$alpha ====="
  FEATURE_ID="$FEATURE_ID" \
  ALPHA="$alpha" \
  MAX_EXAMPLES="$MAX_EXAMPLES" \
  MAX_NEW_TOKENS="$MAX_NEW_TOKENS" \
  ./scripts/run_intervention_smoke_example.sh
done
