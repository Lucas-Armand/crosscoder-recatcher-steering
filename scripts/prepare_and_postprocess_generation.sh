#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 4 ]]; then
  echo "Usage: $0 INPUT_JSONL BENCHMARK MODEL_LABEL OUTPUT_ROOT" >&2
  exit 2
fi

INPUT_JSONL="$1"
BENCHMARK="$2"
MODEL_LABEL="$3"
OUTPUT_ROOT="$4"
STEM="${BENCHMARK}__${MODEL_LABEL}"

mkdir -p \
  "${OUTPUT_ROOT}/raw_results" \
  "${OUTPUT_ROOT}/zips_raw" \
  "${OUTPUT_ROOT}/postprocessed"

python tools/prepare_evaluation_input.py \
  --input-jsonl "$INPUT_JSONL" \
  --output-jsonl "${OUTPUT_ROOT}/raw_results/${STEM}_results.jsonl" \
  --benchmark "$BENCHMARK" \
  --model-label "$MODEL_LABEL"

python tools/export_generated_scripts_to_zips.py \
  --results-dir "${OUTPUT_ROOT}/raw_results" \
  --out-dir "${OUTPUT_ROOT}/zips_raw"

python tools/reprocess_outputs_minimal.py \
  --raw-results-dir "${OUTPUT_ROOT}/raw_results" \
  --output-dir "${OUTPUT_ROOT}/postprocessed"

echo "Prepared evaluator inputs under ${OUTPUT_ROOT}/postprocessed"
