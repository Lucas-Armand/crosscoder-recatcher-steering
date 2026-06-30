#!/usr/bin/env bash
set -euo pipefail

SRC_EXP="${SRC_EXP:-crosscoder_final_dataset_v1}"
DST_EXP="${DST_EXP:-crosscoder_final_dataset_v1_postprocessed_minimal_v3}"

BUCKET_BASE="${BUCKET_BASE:-gs://data-intelligence-bucket/tests/recatcher_crosscoder_humaneval}"

SRC="${SRC:-${BUCKET_BASE}/${SRC_EXP}}"
DST="${DST:-${BUCKET_BASE}/${DST_EXP}}"

WORK_ROOT="${WORK_ROOT:-/tmp/crosscoder_postprocess_and_eval_v3}"

HUMANEVAL_VENV="${HUMANEVAL_VENV:-$HOME/venvs/recatcher_humaneval}"
BIGCODEBENCH_VENV="${BIGCODEBENCH_VENV:-$HOME/venvs/bigcodebench015}"

BIGCODEBENCH_PARALLEL="${BIGCODEBENCH_PARALLEL:-16}"
GRACE_AFTER_SCORE_SECONDS="${GRACE_AFTER_SCORE_SECONDS:-20}"
HARD_TIMEOUT_SECONDS="${HARD_TIMEOUT_SECONDS:-1800}"

COPY_ACTIVATIONS="${COPY_ACTIVATIONS:-1}"
RUN_HUMANEVAL="${RUN_HUMANEVAL:-1}"
RUN_BIGCODEBENCH="${RUN_BIGCODEBENCH:-1}"

MODELS_STR="${MODELS_STR:-codellama_base codellama_finetuned codellama_merged deepseek_base deepseek_finetuned deepseek_merged}"
BENCHES_STR="${BENCHES_STR:-humanevalplus bigcodebench}"

is_gcs() {
  [[ "$1" == gs://* ]]
}

copy_file_from_src() {
  local src_file="$1"
  local dst_file="$2"

  if is_gcs "$src_file"; then
    gsutil cp "$src_file" "$dst_file"
  else
    cp "$src_file" "$dst_file"
  fi
}

upload_dir_to_dst() {
  local local_dir="$1"
  local dst_dir="$2"

  if is_gcs "$dst_dir"; then
    gsutil -m cp -r "${local_dir}/"* "${dst_dir}/"
  else
    mkdir -p "$dst_dir"
    cp -R "${local_dir}/"* "${dst_dir}/"
  fi
}

copy_activations_one() {
  local bench="$1"
  local model="$2"

  local src_act="${SRC}/selected_layer_activations/${bench}/${model}"
  local dst_act_parent="${DST}/selected_layer_activations/${bench}/"

  echo "--- Copying activations unchanged for ${bench}/${model}"

  if is_gcs "$SRC" && is_gcs "$DST"; then
    gsutil -m cp -r "$src_act" "$dst_act_parent" || {
      echo "WARNING: activation copy failed or folder missing for ${bench}/${model}"
    }
  elif ! is_gcs "$SRC" && ! is_gcs "$DST"; then
    mkdir -p "$dst_act_parent"
    cp -R "$src_act" "$dst_act_parent" || {
      echo "WARNING: activation copy failed or folder missing for ${bench}/${model}"
    }
  else
    echo "WARNING: mixed local/GCS activation copy skipped for ${bench}/${model}"
  fi
}

expected_count_for_bench() {
  local bench="$1"

  if [[ "$bench" == "humanevalplus" ]]; then
    echo 164
  elif [[ "$bench" == "bigcodebench" ]]; then
    echo 1140
  else
    echo ""
  fi
}

count_jsonl_lines() {
  local file="$1"
  python - "$file" <<'PY'
import sys
p = sys.argv[1]
n = 0
with open(p, "r", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            n += 1
print(n)
PY
}

has_real_bigcodebench_score() {
  local log_file="$1"
  grep -qE '^pass@1:[[:space:]]*[0-9]+(\.[0-9]+)?[[:space:]]*$' "$log_file"
}

run_until_score_then_grace() {
  local log_file="$1"
  local grace_seconds="$2"
  local hard_timeout_seconds="$3"
  shift 3

  : > "$log_file"

  echo "--- Running command with score monitor" | tee -a "$log_file"
  echo "--- Grace after final score: ${grace_seconds}s" | tee -a "$log_file"
  echo "--- Hard timeout: ${hard_timeout_seconds}s" | tee -a "$log_file"
  echo "--- Command: $*" | tee -a "$log_file"

  setsid "$@" > >(tee -a "$log_file") 2>&1 &
  local pid="$!"

  local start_time
  start_time="$(date +%s)"

  local score_seen=0
  local score_time=0
  local killed_after_score=0
  local hard_timeout_hit=0

  while kill -0 "$pid" 2>/dev/null; do
    local now
    now="$(date +%s)"

    # Only match real metric lines, never helper messages.
    if [[ "$score_seen" == "0" ]] && has_real_bigcodebench_score "$log_file"; then
      score_seen=1
      score_time="$now"
      echo "--- Detected final score line. Waiting ${grace_seconds}s for clean exit..." | tee -a "$log_file"
    fi

    if [[ "$score_seen" == "1" ]] && (( now - score_time >= grace_seconds )); then
      echo "--- Process still alive ${grace_seconds}s after final score. Terminating process group..." | tee -a "$log_file"
      kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
      sleep 5

      if kill -0 "$pid" 2>/dev/null; then
        echo "--- Process did not terminate after SIGTERM. Sending SIGKILL..." | tee -a "$log_file"
        kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
      fi

      killed_after_score=1
      break
    fi

    if (( now - start_time >= hard_timeout_seconds )); then
      echo "--- Hard timeout reached. Terminating process group..." | tee -a "$log_file"
      kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
      sleep 5

      if kill -0 "$pid" 2>/dev/null; then
        kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
      fi

      hard_timeout_hit=1
      break
    fi

    sleep 2
  done

  set +e
  wait "$pid"
  local status="$?"
  set -e

  if [[ "$killed_after_score" == "1" ]]; then
    echo "--- Treated as success because final score was already printed." | tee -a "$log_file"
    return 0
  fi

  if [[ "$hard_timeout_hit" == "1" ]]; then
    if has_real_bigcodebench_score "$log_file"; then
      echo "--- Hard timeout hit, but final score was printed. Treating as success." | tee -a "$log_file"
      return 0
    fi

    echo "--- Hard timeout hit before final score. Treating as failure." | tee -a "$log_file"
    return 124
  fi

  return "$status"
}

run_humaneval_one() {
  local repaired_jsonl="$1"
  local out_jsonl="$2"
  local log_file="$3"

  mkdir -p "$(dirname "$out_jsonl")"

  if [[ ! -d "$HUMANEVAL_VENV" ]]; then
    echo "ERROR: HUMANEVAL_VENV does not exist: $HUMANEVAL_VENV"
    exit 1
  fi

  set +e
  (
    source "${HUMANEVAL_VENV}/bin/activate"
    python tools/evaluate_humaneval_local.py \
      --repaired-jsonl "$repaired_jsonl" \
      --output-jsonl "$out_jsonl"
  ) 2>&1 | tee "$log_file"
  local status="${PIPESTATUS[0]}"
  set -e

  echo "$status" > "${log_file}.exitcode"

  if [[ "$status" -ne 0 ]]; then
    echo "ERROR: HumanEval+ failed: $log_file"
    exit "$status"
  fi
}

run_bigcodebench_one() {
  local samples="$1"
  local model="$2"
  local out_dir="$3"

  mkdir -p "$out_dir"

  local log_file="${out_dir}/bigcodebench__${model}_full_eval_nogt.log"
  local local_eval_json="${out_dir}/bigcodebench__${model}_eval_results.json"

  if [[ ! -f "$samples" ]]; then
    echo "ERROR: BigCodeBench samples not found: $samples"
    exit 1
  fi

  if [[ ! -d "$BIGCODEBENCH_VENV" ]]; then
    echo "ERROR: BIGCODEBENCH_VENV does not exist: $BIGCODEBENCH_VENV"
    exit 1
  fi

  # BigCodeBench writes cache next to the samples file.
  # Delete it so the run is non-interactive and fresh.
  local cache="${samples%.jsonl}_eval_results.json"
  rm -f "$cache" "$cache.bak"

  set +e
  (
    source "${BIGCODEBENCH_VENV}/bin/activate"

    python - <<'PY'
import importlib.metadata as md
version = md.version("bigcodebench")
print("bigcodebench version:", version)
if version != "0.1.5":
    raise SystemExit(f"Expected bigcodebench==0.1.5, got {version}")
PY

    run_until_score_then_grace \
      "$log_file" \
      "$GRACE_AFTER_SCORE_SECONDS" \
      "$HARD_TIMEOUT_SECONDS" \
      python -m bigcodebench.evaluate \
        --subset complete \
        --samples "$samples" \
        --parallel "$BIGCODEBENCH_PARALLEL" \
        --no-gt
  )
  local status="$?"
  set -e

  echo "$status" > "${log_file}.exitcode"

  if ! has_real_bigcodebench_score "$log_file"; then
    echo "ERROR: BigCodeBench finished without a real pass@1 score: $log_file"
    exit 1
  fi

  if [[ -f "$cache" ]]; then
    cp "$cache" "$local_eval_json"
  else
    echo "WARNING: BigCodeBench cache JSON not found: $cache"
  fi

  if [[ "$status" -ne 0 ]]; then
    echo "ERROR: BigCodeBench failed for ${model}: $log_file"
    exit "$status"
  fi
}

write_summary_csv() {
  local local_out="$1"
  local summary_csv="${local_out}/reports/model_benchmark_summary.csv"

  mkdir -p "${local_out}/reports"

  python - "$local_out" "$summary_csv" <<'PY'
import csv
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
out_csv = Path(sys.argv[2])

rows = []

samples_dir = root / "samples_for_external_eval"
eval_root = root / "eval"

def count_lines(path):
    if not path.exists():
        return ""
    return sum(1 for line in path.open("r", encoding="utf-8") if line.strip())

def truthy(x):
    return x is True or x == 1 or x == "true" or x == "True" or x == "passed"

# HumanEval+
hum_dir = eval_root / "humanevalplus"
for path in sorted(hum_dir.glob("humanevalplus__*_eval.jsonl")):
    model = path.name.replace("humanevalplus__", "").replace("_eval.jsonl", "")
    sample_path = samples_dir / f"humanevalplus__{model}_samples.jsonl"

    total = 0
    correct = 0

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            total += 1

            value = (
                row.get("eval_candidate_code_repaired_correct")
                if "eval_candidate_code_repaired_correct" in row else
                row.get("correct")
                if "correct" in row else
                row.get("passed")
            )
            correct += int(truthy(value))

    rows.append({
        "benchmark": "humanevalplus",
        "model": model,
        "n_samples": count_lines(sample_path),
        "n_eval_rows": total,
        "correct": correct,
        "pass_at_1": correct / total if total else "",
        "log_or_file": str(path),
    })

# BigCodeBench
bcb_dir = eval_root / "bigcodebench015"
for path in sorted(bcb_dir.glob("bigcodebench__*_full_eval_nogt.log")):
    model = path.name.replace("bigcodebench__", "").replace("_full_eval_nogt.log", "")
    sample_path = samples_dir / f"bigcodebench__{model}_samples.jsonl"

    text = path.read_text(encoding="utf-8", errors="replace")

    pass_at_1 = ""
    m = re.search(r"^pass@1:\s*([0-9]+(?:\.[0-9]+)?)\s*$", text, re.MULTILINE)
    if m:
        pass_at_1 = m.group(1)

    exitcode_path = Path(str(path) + ".exitcode")
    exitcode = exitcode_path.read_text().strip() if exitcode_path.exists() else ""

    rows.append({
        "benchmark": "bigcodebench",
        "model": model,
        "n_samples": count_lines(sample_path),
        "n_eval_rows": "",
        "correct": "",
        "pass_at_1": pass_at_1,
        "log_or_file": f"{path} exitcode={exitcode}",
    })

out_csv.parent.mkdir(parents=True, exist_ok=True)

with out_csv.open("w", newline="", encoding="utf-8") as f:
    fieldnames = [
        "benchmark",
        "model",
        "n_samples",
        "n_eval_rows",
        "correct",
        "pass_at_1",
        "log_or_file",
    ]
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

print(f"Wrote summary: {out_csv}")
for row in rows:
    print(row)
PY
}

echo "=== ReCatcher postprocess + evaluation from scratch ==="
echo "SRC: $SRC"
echo "DST: $DST"
echo "WORK_ROOT: $WORK_ROOT"
echo "MODELS: $MODELS_STR"
echo "BENCHES: $BENCHES_STR"
echo

echo "=== Safety ==="
echo "- This script deletes only local WORK_ROOT."
echo "- It never deletes the source bucket."
echo "- Use a fresh DST_EXP to avoid mixing old logs."
echo

rm -rf "$WORK_ROOT"
mkdir -p "$WORK_ROOT"

LOCAL_OUT="${WORK_ROOT}/out"
LOCAL_IN="${WORK_ROOT}/input"

mkdir -p \
  "${LOCAL_IN}" \
  "${LOCAL_OUT}/results" \
  "${LOCAL_OUT}/results_repaired" \
  "${LOCAL_OUT}/raw_results" \
  "${LOCAL_OUT}/samples_for_external_eval" \
  "${LOCAL_OUT}/eval/humanevalplus" \
  "${LOCAL_OUT}/eval/bigcodebench015" \
  "${LOCAL_OUT}/reports"

cat > "${LOCAL_OUT}/POSTPROCESS_MANIFEST.txt" <<EOF
source=${SRC}
destination=${DST}
created_at=$(date -Is)

This dataset is a minimal evaluation-ready copy.

Raw model outputs:
- preserved under raw_results/

Processed outputs:
- saved under results/
- detailed repaired rows under results_repaired/

Post-processing:
- uses tools/export_generated_scripts_to_zips.py
- uses tools/reprocess_outputs_minimal.py
- applies only conservative formatting/output cleanup

Activations:
- not modified
- copied unchanged if COPY_ACTIVATIONS=1

Evaluation:
- HumanEval+ env: ${HUMANEVAL_VENV}
- BigCodeBench env: ${BIGCODEBENCH_VENV}
- BigCodeBench version expected: 0.1.5
- BigCodeBench mode: --subset complete --no-gt
EOF

echo
echo "=== PHASE 1: post-process all results ==="

for bench in $BENCHES_STR; do
  for model in $MODELS_STR; do
    stem="${bench}__${model}"
    raw_name="${stem}_results.jsonl"
    repaired_name="${stem}_repaired.jsonl"

    one="${WORK_ROOT}/process_${stem}"

    echo
    echo "======================================================================"
    echo "PROCESSING ${stem}"
    echo "======================================================================"

    rm -rf "$one"
    mkdir -p "${one}/in_results" "${one}/zips_raw" "${one}/reprocessed"

    src_file="${SRC}/results/${raw_name}"
    local_raw="${one}/in_results/${raw_name}"

    copy_file_from_src "$src_file" "$local_raw"

    n_raw="$(count_jsonl_lines "$local_raw")"
    expected="$(expected_count_for_bench "$bench")"

    echo "--- Raw rows: ${n_raw}"

    if [[ -n "$expected" && "$n_raw" != "$expected" ]]; then
      echo "ERROR: expected ${expected} rows for ${stem}, got ${n_raw}"
      exit 1
    fi

    cp "$local_raw" "${LOCAL_OUT}/raw_results/${raw_name}"

    python tools/export_generated_scripts_to_zips.py \
      --results-dir "${one}/in_results" \
      --out-dir "${one}/zips_raw"

    python tools/reprocess_outputs_minimal.py \
      --zip-dir "${one}/zips_raw" \
      --output-dir "${one}/reprocessed"

    repaired_jsonl="${one}/reprocessed/results_repaired/${repaired_name}"

    if [[ ! -f "$repaired_jsonl" ]]; then
      echo "ERROR: repaired JSONL not found: ${repaired_jsonl}"
      exit 1
    fi

    n_repaired="$(count_jsonl_lines "$repaired_jsonl")"
    echo "--- Repaired rows: ${n_repaired}"

    if [[ "$n_repaired" != "$n_raw" ]]; then
      echo "ERROR: raw/repaired row count mismatch for ${stem}: ${n_raw} vs ${n_repaired}"
      exit 1
    fi

    cp "$repaired_jsonl" "${LOCAL_OUT}/results_repaired/${repaired_name}"
    cp "$repaired_jsonl" "${LOCAL_OUT}/results/${raw_name}"

    if [[ -f "${one}/reprocessed/repair_summary.csv" ]]; then
      cp "${one}/reprocessed/repair_summary.csv" \
        "${LOCAL_OUT}/reports/repair_summary__${stem}.csv"
    fi

    if [[ -d "${one}/reprocessed/samples_for_external_eval" ]]; then
      cp -r "${one}/reprocessed/samples_for_external_eval/"* \
        "${LOCAL_OUT}/samples_for_external_eval/" || true
    fi

    rm -rf "$one"
  done
done

if [[ "$COPY_ACTIVATIONS" == "1" ]]; then
  echo
  echo "=== PHASE 2: copy activations unchanged ==="

  for bench in $BENCHES_STR; do
    for model in $MODELS_STR; do
      copy_activations_one "$bench" "$model"
    done
  done
fi

echo
echo "=== PHASE 3: evaluate HumanEval+ ==="

if [[ "$RUN_HUMANEVAL" == "1" ]]; then
  for model in $MODELS_STR; do
    stem="humanevalplus__${model}"

    echo
    echo "======================================================================"
    echo "EVALUATING ${stem}"
    echo "======================================================================"

    run_humaneval_one \
      "${LOCAL_OUT}/results_repaired/${stem}_repaired.jsonl" \
      "${LOCAL_OUT}/eval/humanevalplus/${stem}_eval.jsonl" \
      "${LOCAL_OUT}/eval/humanevalplus/${stem}_eval.log"
  done
else
  echo "--- HumanEval+ skipped"
fi

echo
echo "=== PHASE 4: evaluate BigCodeBench ==="

if [[ "$RUN_BIGCODEBENCH" == "1" ]]; then
  for model in $MODELS_STR; do
    stem="bigcodebench__${model}"

    echo
    echo "======================================================================"
    echo "EVALUATING ${stem}"
    echo "======================================================================"

    run_bigcodebench_one \
      "${LOCAL_OUT}/samples_for_external_eval/${stem}_samples.jsonl" \
      "$model" \
      "${LOCAL_OUT}/eval/bigcodebench015"
  done
else
  echo "--- BigCodeBench skipped"
fi

echo
echo "=== PHASE 5: summary ==="

write_summary_csv "$LOCAL_OUT"

echo
echo "=== PHASE 6: upload/copy final output ==="

upload_dir_to_dst "$LOCAL_OUT" "$DST"

echo
echo "=== DONE ==="
echo "Local output:"
echo "$LOCAL_OUT"
echo
echo "Saved to:"
echo "$DST"
echo
echo "Summary:"
echo "${DST}/reports/model_benchmark_summary.csv"
