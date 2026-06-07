#!/usr/bin/env bash
set -euo pipefail

# Reproducible runner with optional GCS sync.
# No bucket or credential is hard-coded. Configure via env vars or .env.local.
#
# Required for sync:
#   export REPRO_BUCKET='gs://your-bucket/path/to/experiment'
# Optional:
#   export EXP='full_table_6models_2benchmarks_layers_8_16_24_max512'
#   export ROOT_BASE='recatcher_crosscoder_humaneval'
#   export MODEL_MAP_JSON='{"deepseek_base":"deepseek-ai/deepseek-coder-6.7b-base",...}'

if [[ -f .env.local ]]; then
  set -a
  source .env.local
  set +a
fi

EXP="${EXP:-full_table_6models_2benchmarks_layers_8_16_24_max512}"
ROOT_BASE="${ROOT_BASE:-recatcher_crosscoder_humaneval}"
ROOT="${ROOT_BASE}/${EXP}"
BUCKET="${REPRO_BUCKET:-}"
LOG_DIR="logs_${EXP}"
TRACKER_DIR="${TRACKER_DIR:-/tmp/gsutil-tracker}"

mkdir -p "$LOG_DIR" "$TRACKER_DIR"
export TMPDIR="${TMPDIR:-/tmp}"

mkdir -p "${ROOT}/results" \
         "${ROOT}/metadata" \
         "${ROOT}/samples_for_external_eval" \
         "${ROOT}/selected_layer_activations"

MODEL_MAP_JSON="${MODEL_MAP_JSON:-$(cat configs/model_map.template.json)}"

show_counts() {
  echo "============================================================"
  echo "Local result counts"
  echo "============================================================"
  wc -l "${ROOT}/results/"*.jsonl 2>/dev/null || true
}

dedup_results() {
  echo "============================================================"
  echo "Deduplicating local JSONL results"
  echo "============================================================"
  python tools/dedup_results.py --results-dir "${ROOT}/results"
}

sync_to_bucket() {
  if [[ -z "${BUCKET}" ]]; then
    echo "REPRO_BUCKET not set; skipping bucket sync."
    return 0
  fi

  echo "============================================================"
  echo "Syncing to bucket configured by REPRO_BUCKET"
  echo "============================================================"

  gsutil -m -o "GSUtil:resumable_tracker_dir=${TRACKER_DIR}" rsync -r "${ROOT}/results" "${BUCKET}/results"
  gsutil -m -o "GSUtil:resumable_tracker_dir=${TRACKER_DIR}" rsync -r "${ROOT}/metadata" "${BUCKET}/metadata"
  gsutil -m -o "GSUtil:resumable_tracker_dir=${TRACKER_DIR}" rsync -r "${ROOT}/samples_for_external_eval" "${BUCKET}/samples_for_external_eval"
  gsutil -m -o "GSUtil:resumable_tracker_dir=${TRACKER_DIR}" rsync -r -x '.*\.tmp\.npz$' \
    "${ROOT}/selected_layer_activations" "${BUCKET}/selected_layer_activations"

  gsutil du -sh "${BUCKET}" || true
}

clean_local_activations() {
  if [[ "${CLEAN_LOCAL_ACTIVATIONS:-1}" == "1" ]]; then
    echo "============================================================"
    echo "Cleaning local activations after sync"
    echo "============================================================"
    rm -rf "${ROOT}/selected_layer_activations"/*
    mkdir -p "${ROOT}/selected_layer_activations"
  fi
  df -h /home/jupyter 2>/dev/null || df -h || true
  du -sh "${ROOT}" || true
}

run_block() {
  local BENCH="$1"
  local MODEL="$2"
  local MAX_TASKS="${3:-}"
  local TAG="${BENCH}__${MODEL}"

  if [[ -n "${MAX_TASKS}" ]]; then
    TAG="${TAG}__max${MAX_TASKS}"
  else
    TAG="${TAG}__full"
  fi

  local RUN_LOG="${LOG_DIR}/${TAG}.log"

  echo
  echo "################################################################################"
  echo "Running benchmark=${BENCH} model=${MODEL} max_tasks=${MAX_TASKS:-FULL}"
  echo "################################################################################"

  CMD=(
    python run_recatcher_benchmarks.py
    --benchmarks "${BENCH}"
    --models "${MODEL}"
    --model-map-json "${MODEL_MAP_JSON}"
    --selected-layer-ids 8 16 24
    --num-generations "${NUM_GENERATIONS:-1}"
    --max-new-tokens "${MAX_NEW_TOKENS:-512}"
    --experiment-name "${EXP}"
  )

  if [[ "${NO_ACTIVATIONS:-0}" == "1" ]]; then
    CMD+=(--no-activations)
  fi

  if [[ -n "${MAX_TASKS}" ]]; then
    CMD+=(--max-tasks "${MAX_TASKS}")
  fi

  "${CMD[@]}" 2>&1 | tee -a "${RUN_LOG}"

  dedup_results
  show_counts
  sync_to_bucket
  clean_local_activations
}

if [[ $# -lt 2 ]]; then
  cat <<'USAGE'
Usage:
  ./run_with_bucket_sync.sh <benchmark> <model_alias> [max_tasks]

Examples:
  ./run_with_bucket_sync.sh humanevalplus deepseek_base 20
  ./run_with_bucket_sync.sh bigcodebench codellama_base

Configure bucket sync with REPRO_BUCKET. If unset, only local files are produced.
USAGE
  exit 1
fi

run_block "$@"
