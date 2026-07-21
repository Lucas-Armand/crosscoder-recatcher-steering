#!/usr/bin/env bash
set -euo pipefail

cd "${REPO_ROOT:-$HOME/crosscoder-recatcher-steering}"

FEATURES_NPZ="${FEATURES_NPZ:-runs/test_corrected_screen/features.npz}"
EXAMPLES_CSV="${EXAMPLES_CSV:-runs/test_corrected_screen/examples.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-runs/feature_relevance_analysis/test_corrected_screen}"

PERMUTATIONS="${PERMUTATIONS:-1000}"
BOOTSTRAPS="${BOOTSTRAPS:-300}"
CV_REPEATS="${CV_REPEATS:-10}"
CV_FOLDS="${CV_FOLDS:-5}"
TOP_K="${TOP_K:-50}"
CANDIDATE_POOL="${CANDIDATE_POOL:-500}"

mkdir -p "$OUTPUT_DIR"

python tools/analyze_feature_relevance.py \
  --features-npz "$FEATURES_NPZ" \
  --examples-csv "$EXAMPLES_CSV" \
  --output-dir "$OUTPUT_DIR" \
  --top-k "$TOP_K" \
  --candidate-pool "$CANDIDATE_POOL" \
  --permutations "$PERMUTATIONS" \
  --bootstraps "$BOOTSTRAPS" \
  --cv-repeats "$CV_REPEATS" \
  --cv-folds "$CV_FOLDS" \
  2>&1 | tee "$OUTPUT_DIR/run.log"
