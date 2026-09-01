#!/usr/bin/env bash
set -euo pipefail

cd /home/lucas/crosscoder-recatcher-steering

run="runs/dstk100_continuous_f6404_f10168_f13801_v1"
source_input="runs/dstk100_f6404_test_contamination_general_v1/input.jsonl"
expected_rows=80
features=(6404 10168 13801)
alphas=(-1 -2 -3 -4 -5)
names=(neg1 neg2 neg3 neg4 neg5)

mkdir -p "$run"/{generations,logs,postprocessed,evaluations,finalizer_logs,audit}
cp -n "$source_input" "$run/input.jsonl"

run_arm() {
  local feature="$1" name="$2" alpha="$3"
  local output="$run/generations/bigcodebench__f${feature}_continuous_${name}_results.jsonl"
  local log="$run/logs/f${feature}_${name}.log"
  local rows=0
  [[ -f "$output" ]] && rows="$(wc -l < "$output")"
  if [[ "$rows" == "$expected_rows" ]]; then
    echo "feature=$feature arm=$name already complete"
    return
  fi
  if [[ -e "$output" || -e "$log" ]]; then
    local stamp archive
    stamp="$(date +%Y%m%d_%H%M%S)"
    archive="$run/audit/f${feature}_${name}_$stamp"
    mkdir -p "$archive"
    [[ -e "$output" ]] && mv "$output" "$archive/"
    [[ -e "$log" ]] && mv "$log" "$archive/"
  fi
  echo "[$(date -Iseconds)] feature=$feature alpha=$alpha"
  CUDA_VISIBLE_DEVICES=1 .venv/bin/python tools/run_crosscoder_intervention.py \
    --checkpoint runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt \
    --model-a-id deepseek-ai/deepseek-coder-6.7b-base \
    --model-b-id JetBrains/deepseek-coder-6.7B-kexer \
    --target-side a --layer 16 --feature-id "$feature" --alpha "$alpha" \
    --intervention-mode traditional --token-scope last_token \
    --generation-backend hf_generate --input-jsonl "$run/input.jsonl" \
    --output-jsonl "$output" --max-new-tokens 512 \
    --temperature 0.2 --top-p 0.95 --seed 1000 \
    --device-a cuda:0 --dtype nf4 \
    --tokenizer-id deepseek-ai/deepseek-coder-6.7b-base --trust-remote-code \
    >"$log" 2>&1
  [[ "$(wc -l < "$output")" == "$expected_rows" ]]
}

for feature in "${features[@]}"; do
  for i in "${!alphas[@]}"; do
    run_arm "$feature" "${names[$i]}" "${alphas[$i]}"
  done
done

.venv/bin/python tools/reprocess_outputs_minimal.py \
  --raw-results-dir "$run/generations" --output-dir "$run/postprocessed" \
  >"$run/finalizer_logs/reprocess.log" 2>&1

for sample in "$run"/postprocessed/samples_for_external_eval/*_samples.jsonl; do
  stem="$(basename "$sample" _samples.jsonl)"
  /home/lucas/venvs/bigcodebench015/bin/python tools/evaluate_bigcodebench_subset.py \
    --samples "$sample" --output "$run/evaluations/${stem}_eval.json" --parallel 4 \
    >"$run/finalizer_logs/eval_${stem}.log" 2>&1
done

touch "$run/PIPELINE_COMPLETE"
