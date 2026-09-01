#!/usr/bin/env bash
set -euo pipefail

cd /home/lucas/crosscoder-recatcher-steering

run="runs/dstk100_f12883_limited_v1"
expected_rows=119
timestamp="$(date +%Y%m%d_%H%M%S)"

mkdir -p \
  "$run/generations" \
  "$run/logs" \
  "$run/postprocessed" \
  "$run/evaluations" \
  "$run/finalizer_logs" \
  "$run/audit"

archive_failed_artifact() {
  local arm_name="$1"
  local artifact="$2"
  if [[ -e "$artifact" ]]; then
    local audit_dir="$run/audit/${arm_name}_resume_${timestamp}"
    mkdir -p "$audit_dir"
    cp -p "$artifact" "$audit_dir/"
  fi
}

jsonl_row_count() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo 0
    return
  fi
  wc -l < "$path"
}

common=(
  --checkpoint runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt
  --model-a-id deepseek-ai/deepseek-coder-6.7b-base
  --model-b-id JetBrains/deepseek-coder-6.7B-kexer
  --target-side a
  --layer 16
  --feature-id 12883
  --intervention-mode topk_gated_suppression
  --token-scope last_token
  --generation-backend paired_cached
  --top-k 100
  --rms-epsilon 1e-6
  --input-jsonl "$run/input.jsonl"
  --max-new-tokens 512
  --temperature 0.2
  --top-p 0.95
  --seed 1000
  --device-a cuda:0
  --device-b cuda:1
  --dtype nf4
  --reference-dtype float16
  --tokenizer-id deepseek-ai/deepseek-coder-6.7b-base
  --trust-remote-code
)

run_arm_if_missing() {
  local arm_name="$1"
  local alpha="$2"
  local output="$run/generations/bigcodebench__f12883_alpha_${arm_name}_results.jsonl"
  local log_path="$run/logs/${arm_name}.log"
  local row_count
  row_count="$(jsonl_row_count "$output")"

  if [[ "$row_count" == "$expected_rows" ]]; then
    echo "[$(date -Iseconds)] arm ${arm_name} already complete (${row_count}/${expected_rows})"
    return
  fi

  archive_failed_artifact "$arm_name" "$log_path"
  archive_failed_artifact "$arm_name" "$output"

  rm -f "$output"
  .venv/bin/python tools/run_crosscoder_intervention.py "${common[@]}" \
    --alpha "$alpha" \
    --output-jsonl "$output" >"$log_path" 2>&1

  row_count="$(jsonl_row_count "$output")"
  if [[ "$row_count" != "$expected_rows" ]]; then
    echo "arm ${arm_name} finished with ${row_count}/${expected_rows} rows" >&2
    exit 1
  fi
}


run_arm_if_missing "neg0p5" "-0.5"
run_arm_if_missing "neg1" "-1"
run_arm_if_missing "neg2" "-2"

.venv/bin/python tools/reprocess_outputs_minimal.py \
  --raw-results-dir "$run/generations" \
  --output-dir "$run/postprocessed" \
  >"$run/finalizer_logs/reprocess.log" 2>&1

for sample in "$run"/postprocessed/samples_for_external_eval/*_samples.jsonl; do
  stem="$(basename "$sample" _samples.jsonl)"
  /home/lucas/venvs/bigcodebench015/bin/python tools/evaluate_bigcodebench_subset.py \
    --samples "$sample" \
    --output "$run/evaluations/${stem}_eval.json" \
    --parallel 4 \
    >"$run/finalizer_logs/eval_${stem}.log" 2>&1
done

touch "$run/PIPELINE_COMPLETE"
