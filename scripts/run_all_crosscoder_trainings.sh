#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# Run CrossCoder training jobs from ReCatcher/CrossCoder activation NPZ files.
#
# What this script does:
#   1. For each model pair:
#      - downloads only the activation folders needed for that pair;
#      - trains CrossCoders for each requested layer;
#      - uploads checkpoints/metrics/configs to GCS;
#      - deletes the downloaded local activations for that pair.
#
# It does NOT delete anything from GCS.
#
# Requirements:
#   - tools/train_crosscoder_from_npz.py must exist.
#   - gsutil must be configured.
#   - The activation GCS prefix must have:
#       selected_layer_activations/<benchmark>/<model>/*.npz
#
# Example:
#   ./scripts/run_all_crosscoder_trainings.sh
#
# Smoke:
#   STEPS=100 LATENT_DIM=1024 BATCH_SIZE=512 BENCHMARKS_STR="humanevalplus" \
#   PAIRS_STR="deepseek_base:deepseek_merged" LAYERS_STR="16" \
#   ./scripts/run_all_crosscoder_trainings.sh
# ============================================================================


# ----------------------------------------------------------------------------
# Source/destination
# ----------------------------------------------------------------------------

SRC_EXP="${SRC_EXP:-crosscoder_final_dataset_v1_postprocessed_minimal_v3}"
BUCKET_BASE="${BUCKET_BASE:-gs://data-intelligence-bucket/tests/recatcher_crosscoder_humaneval}"

ACTIVATION_GCS="${ACTIVATION_GCS:-${BUCKET_BASE}/${SRC_EXP}/selected_layer_activations}"

TRAINING_EXP="${TRAINING_EXP:-crosscoder_training_v1}"
TRAINING_GCS="${TRAINING_GCS:-${BUCKET_BASE}/${TRAINING_EXP}}"

# Local scratch used for downloaded activations.
WORK_ROOT="${WORK_ROOT:-/tmp/crosscoder_training_work}"
LOCAL_ACT="${LOCAL_ACT:-${WORK_ROOT}/selected_layer_activations}"

# Local output root. These runs are uploaded after each job.
LOCAL_RUNS_ROOT="${LOCAL_RUNS_ROOT:-runs/crosscoder_training_v1}"


# ----------------------------------------------------------------------------
# Training configuration
# ----------------------------------------------------------------------------

BENCHMARKS_STR="${BENCHMARKS_STR:-humanevalplus bigcodebench}"

# Default: train within-family pairs.
# You can override this with:
#   PAIRS_STR="deepseek_base:deepseek_merged codellama_base:codellama_merged"
PAIRS_STR="${PAIRS_STR:-deepseek_base:deepseek_finetuned deepseek_base:deepseek_merged deepseek_finetuned:deepseek_merged codellama_base:codellama_finetuned codellama_base:codellama_merged codellama_finetuned:codellama_merged}"

# Selected layers from the generation run.
LAYERS_STR="${LAYERS_STR:-8 16 24}"

LATENT_DIM="${LATENT_DIM:-16384}"
BATCH_SIZE="${BATCH_SIZE:-2048}"
TOKENS_PER_PAIR="${TOKENS_PER_PAIR:-128}"
STEPS="${STEPS:-20000}"
LR="${LR:-1e-4}"
L1_COEF="${L1_COEF:-1e-3}"
WEIGHT_DECAY="${WEIGHT_DECAY:-0.0}"
VAL_FRAC="${VAL_FRAC:-0.02}"
EVAL_EVERY="${EVAL_EVERY:-500}"
SAVE_EVERY="${SAVE_EVERY:-2000}"

PAIRING_MODE="${PAIRING_MODE:-same_position}"

# Use cuda if available unless overridden by the inner script.
DEVICE="${DEVICE:-cuda}"
DTYPE="${DTYPE:-float32}"

# If MAX_PAIRS is empty, it is not passed.
MAX_PAIRS="${MAX_PAIRS:-}"

# Cleanup downloaded activations after each model pair.
CLEANUP_ACTIVATIONS="${CLEANUP_ACTIVATIONS:-1}"

# Upload each completed training run to GCS.
UPLOAD_RUNS="${UPLOAD_RUNS:-1}"

# Skip a job if final.pt already exists locally or in GCS.
SKIP_IF_DONE="${SKIP_IF_DONE:-1}"

# Stop everything on the first failed training job.
FAIL_FAST="${FAIL_FAST:-1}"

# Optional venv activation.
# Example:
#   TRAIN_VENV="$HOME/venvs/crosscoder"
TRAIN_VENV="${TRAIN_VENV:-}"


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

log() {
  echo
  echo "[$(date -Is)] $*"
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing command: $1"
}

safe_name() {
  echo "$1" | sed 's#[/:]#_#g'
}

activation_count() {
  local dir="$1"
  if [[ -d "$dir" ]]; then
    find "$dir" -type f -name "*.npz" | wc -l
  else
    echo 0
  fi
}

gcs_exists() {
  local path="$1"
  gsutil -q stat "$path" >/dev/null 2>&1
}

download_model_activations() {
  local benchmark="$1"
  local model="$2"

  local src="${ACTIVATION_GCS}/${benchmark}/${model}"
  local dst_parent="${LOCAL_ACT}/${benchmark}"

  mkdir -p "$dst_parent"

  if [[ -d "${dst_parent}/${model}" ]]; then
    local n
    n="$(activation_count "${dst_parent}/${model}")"
    if [[ "$n" -gt 0 ]]; then
      log "Local activations already exist for ${benchmark}/${model}: ${n} files"
      return 0
    fi
  fi

  log "Downloading activations: ${benchmark}/${model}"
  log "From: ${src}"
  log "To:   ${dst_parent}/"

  gsutil -m cp -r "$src" "$dst_parent/"

  local n
  n="$(activation_count "${dst_parent}/${model}")"
  if [[ "$n" -eq 0 ]]; then
    die "Downloaded zero NPZ files for ${benchmark}/${model}"
  fi

  log "Downloaded ${n} NPZ files for ${benchmark}/${model}"
}

download_pair_activations() {
  local model_a="$1"
  local model_b="$2"

  for benchmark in $BENCHMARKS_STR; do
    download_model_activations "$benchmark" "$model_a"
    download_model_activations "$benchmark" "$model_b"
  done
}

cleanup_pair_activations() {
  local model_a="$1"
  local model_b="$2"

  if [[ "$CLEANUP_ACTIVATIONS" != "1" ]]; then
    log "Skipping local activation cleanup because CLEANUP_ACTIVATIONS=${CLEANUP_ACTIVATIONS}"
    return 0
  fi

  log "Deleting local downloaded activations for pair ${model_a} vs ${model_b}"

  for benchmark in $BENCHMARKS_STR; do
    rm -rf "${LOCAL_ACT}/${benchmark}/${model_a}"
    rm -rf "${LOCAL_ACT}/${benchmark}/${model_b}"
  done
}

write_manifest() {
  local out_dir="$1"
  local model_a="$2"
  local model_b="$3"
  local layer="$4"

  mkdir -p "$out_dir"

  cat > "${out_dir}/TRAINING_MANIFEST.txt" <<EOF
created_at=$(date -Is)

source_experiment=${SRC_EXP}
activation_gcs=${ACTIVATION_GCS}
training_gcs=${TRAINING_GCS}

model_a=${model_a}
model_b=${model_b}
layer=${layer}
benchmarks=${BENCHMARKS_STR}

latent_dim=${LATENT_DIM}
batch_size=${BATCH_SIZE}
tokens_per_pair=${TOKENS_PER_PAIR}
steps=${STEPS}
lr=${LR}
l1_coef=${L1_COEF}
weight_decay=${WEIGHT_DECAY}
val_frac=${VAL_FRAC}
eval_every=${EVAL_EVERY}
save_every=${SAVE_EVERY}
pairing_mode=${PAIRING_MODE}
device=${DEVICE}
dtype=${DTYPE}

methodological_note=If activations are generated-token activations, token positions across models may not be semantically aligned because each model generated different text. These runs should be treated as a first reproducible baseline unless activations are later collected on shared text.
EOF
}

should_skip_job() {
  local out_dir="$1"
  local gcs_dir="$2"

  if [[ "$SKIP_IF_DONE" != "1" ]]; then
    return 1
  fi

  if [[ -f "${out_dir}/final.pt" ]]; then
    log "Skipping because local final.pt exists: ${out_dir}/final.pt"
    return 0
  fi

  if gcs_exists "${gcs_dir}/final.pt"; then
    log "Skipping because GCS final.pt exists: ${gcs_dir}/final.pt"
    return 0
  fi

  return 1
}

upload_run() {
  local out_dir="$1"
  local gcs_dir="$2"

  if [[ "$UPLOAD_RUNS" != "1" ]]; then
    log "Skipping upload because UPLOAD_RUNS=${UPLOAD_RUNS}"
    return 0
  fi

  log "Uploading training run"
  log "From: ${out_dir}"
  log "To:   ${gcs_dir}"

  gsutil -m cp -r "${out_dir}"/* "${gcs_dir}/"
}

run_one_training() {
  local model_a="$1"
  local model_b="$2"
  local layer="$3"

  local pair_name
  pair_name="$(safe_name "${model_a}_vs_${model_b}")"

  local run_name="${pair_name}_layer${layer}_lat${LATENT_DIM}_steps${STEPS}"
  local out_dir="${LOCAL_RUNS_ROOT}/${run_name}"
  local gcs_dir="${TRAINING_GCS}/${run_name}"

  log "======================================================================"
  log "TRAINING ${model_a} vs ${model_b} | layer ${layer}"
  log "Output: ${out_dir}"
  log "GCS:    ${gcs_dir}"
  log "======================================================================"

  if should_skip_job "$out_dir" "$gcs_dir"; then
    return 0
  fi

  write_manifest "$out_dir" "$model_a" "$model_b" "$layer"

  local cmd=(
    python tools/train_crosscoder_from_npz.py
    --activation-root "$LOCAL_ACT"
    --benchmarks $BENCHMARKS_STR
    --model-a "$model_a"
    --model-b "$model_b"
    --layer "$layer"
    --latent-dim "$LATENT_DIM"
    --batch-size "$BATCH_SIZE"
    --tokens-per-pair "$TOKENS_PER_PAIR"
    --steps "$STEPS"
    --lr "$LR"
    --l1-coef "$L1_COEF"
    --weight-decay "$WEIGHT_DECAY"
    --val-frac "$VAL_FRAC"
    --eval-every "$EVAL_EVERY"
    --save-every "$SAVE_EVERY"
    --pairing-mode "$PAIRING_MODE"
    --device "$DEVICE"
    --dtype "$DTYPE"
    --output-dir "$out_dir"
  )

  if [[ -n "$MAX_PAIRS" ]]; then
    cmd+=(--max-pairs "$MAX_PAIRS")
  fi

  log "Command:"
  printf ' %q' "${cmd[@]}"
  echo

  mkdir -p "$out_dir"

  set +e
  "${cmd[@]}" 2>&1 | tee "${out_dir}/train.log"
  local status="${PIPESTATUS[0]}"
  set -e

  echo "$status" > "${out_dir}/exitcode.txt"

  if [[ "$status" -ne 0 ]]; then
    log "Training failed with exit code ${status}: ${model_a} vs ${model_b}, layer ${layer}"

    if [[ "$UPLOAD_RUNS" == "1" ]]; then
      gsutil -m cp -r "${out_dir}"/* "${gcs_dir}/" || true
    fi

    if [[ "$FAIL_FAST" == "1" ]]; then
      exit "$status"
    fi

    return "$status"
  fi

  if [[ ! -f "${out_dir}/final.pt" ]]; then
    log "WARNING: training exited successfully but final.pt was not found: ${out_dir}/final.pt"
  fi

  upload_run "$out_dir" "$gcs_dir"
}

run_pair() {
  local model_a="$1"
  local model_b="$2"

  log "######################################################################"
  log "PAIR ${model_a} vs ${model_b}"
  log "######################################################################"

  download_pair_activations "$model_a" "$model_b"

  local status=0

  for layer in $LAYERS_STR; do
    if ! run_one_training "$model_a" "$model_b" "$layer"; then
      status=$?
      log "Layer job failed: ${model_a} vs ${model_b}, layer ${layer}"
      if [[ "$FAIL_FAST" == "1" ]]; then
        cleanup_pair_activations "$model_a" "$model_b"
        exit "$status"
      fi
    fi
  done

  cleanup_pair_activations "$model_a" "$model_b"

  return "$status"
}


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

need_cmd gsutil
need_cmd python

if [[ ! -f tools/train_crosscoder_from_npz.py ]]; then
  die "Missing tools/train_crosscoder_from_npz.py"
fi

if [[ -n "$TRAIN_VENV" ]]; then
  log "Activating TRAIN_VENV=${TRAIN_VENV}"
  # shellcheck source=/dev/null
  source "${TRAIN_VENV}/bin/activate"
fi

mkdir -p "$WORK_ROOT" "$LOCAL_ACT" "$LOCAL_RUNS_ROOT"

log "Starting CrossCoder training runner"
log "ACTIVATION_GCS=${ACTIVATION_GCS}"
log "TRAINING_GCS=${TRAINING_GCS}"
log "WORK_ROOT=${WORK_ROOT}"
log "LOCAL_ACT=${LOCAL_ACT}"
log "LOCAL_RUNS_ROOT=${LOCAL_RUNS_ROOT}"
log "BENCHMARKS_STR=${BENCHMARKS_STR}"
log "PAIRS_STR=${PAIRS_STR}"
log "LAYERS_STR=${LAYERS_STR}"
log "CLEANUP_ACTIVATIONS=${CLEANUP_ACTIVATIONS}"
log "UPLOAD_RUNS=${UPLOAD_RUNS}"

cat > "${LOCAL_RUNS_ROOT}/RUNNER_MANIFEST.txt" <<EOF
created_at=$(date -Is)

source_experiment=${SRC_EXP}
activation_gcs=${ACTIVATION_GCS}
training_gcs=${TRAINING_GCS}

benchmarks=${BENCHMARKS_STR}
pairs=${PAIRS_STR}
layers=${LAYERS_STR}

latent_dim=${LATENT_DIM}
batch_size=${BATCH_SIZE}
tokens_per_pair=${TOKENS_PER_PAIR}
steps=${STEPS}
lr=${LR}
l1_coef=${L1_COEF}
weight_decay=${WEIGHT_DECAY}
val_frac=${VAL_FRAC}
eval_every=${EVAL_EVERY}
save_every=${SAVE_EVERY}
pairing_mode=${PAIRING_MODE}
device=${DEVICE}
dtype=${DTYPE}

cleanup_activations=${CLEANUP_ACTIVATIONS}
upload_runs=${UPLOAD_RUNS}
skip_if_done=${SKIP_IF_DONE}
fail_fast=${FAIL_FAST}
EOF

if [[ "$UPLOAD_RUNS" == "1" ]]; then
  gsutil cp "${LOCAL_RUNS_ROOT}/RUNNER_MANIFEST.txt" "${TRAINING_GCS}/RUNNER_MANIFEST.txt"
fi

for pair in $PAIRS_STR; do
  model_a="${pair%%:*}"
  model_b="${pair##*:}"

  if [[ "$model_a" == "$model_b" || -z "$model_a" || -z "$model_b" ]]; then
    die "Invalid pair: ${pair}. Expected format model_a:model_b"
  fi

  run_pair "$model_a" "$model_b"
done

log "All requested CrossCoder trainings finished."
log "Local runs: ${LOCAL_RUNS_ROOT}"
log "GCS runs:   ${TRAINING_GCS}"
