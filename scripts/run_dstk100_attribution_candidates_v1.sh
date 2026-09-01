#!/usr/bin/env bash
set -euo pipefail

cd /home/lucas/crosscoder-recatcher-steering

input="runs/dstk100_f5422_test_contamination_v1/input.jsonl"
expected_rows=119
features=(10168 13801)
arm_names=(neg0p5 neg1 neg1p5 neg2 neg2p5 neg3)
alphas=(-0.5 -1 -1.5 -2 -2.5 -3)

for feature in "${features[@]}"; do
  run="runs/dstk100_f${feature}_causal_attribution_grid_v1"
  mkdir -p "$run"/{generations,logs,postprocessed,evaluations,finalizer_logs,audit}
  cp -n "$input" "$run/input.jsonl"

  common=(
    --checkpoint runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt
    --model-a-id deepseek-ai/deepseek-coder-6.7b-base
    --model-b-id JetBrains/deepseek-coder-6.7B-kexer
    --target-side a --layer 16 --feature-id "$feature"
    --intervention-mode topk_gated_suppression --token-scope last_token
    --generation-backend paired_cached --top-k 100 --rms-epsilon 1e-6
    --input-jsonl "$run/input.jsonl" --max-new-tokens 512
    --temperature 0.2 --top-p 0.95 --seed 1000
    --device-a cuda:0 --device-b cuda:1 --dtype nf4 --reference-dtype float16
    --tokenizer-id deepseek-ai/deepseek-coder-6.7b-base --trust-remote-code
  )

  for i in "${!arm_names[@]}"; do
    name="${arm_names[$i]}"
    alpha="${alphas[$i]}"
    output="$run/generations/bigcodebench__f${feature}_alpha_${name}_results.jsonl"
    log="$run/logs/${name}.log"
    rows=0
    [[ -f "$output" ]] && rows="$(wc -l < "$output")"
    if [[ "$rows" == "$expected_rows" ]]; then
      echo "feature=$feature arm=$name already complete"
      continue
    fi
    if [[ -e "$output" || -e "$log" ]]; then
      stamp="$(date +%Y%m%d_%H%M%S)"
      archive="$run/audit/${name}_$stamp"
      mkdir -p "$archive"
      [[ -e "$output" ]] && mv "$output" "$archive/"
      [[ -e "$log" ]] && mv "$log" "$archive/"
    fi
    echo "[$(date -Iseconds)] feature=$feature arm=$name alpha=$alpha"
    .venv/bin/python tools/run_crosscoder_intervention.py "${common[@]}" \
      --alpha "$alpha" --output-jsonl "$output" >"$log" 2>&1
    [[ "$(wc -l < "$output")" == "$expected_rows" ]]
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
done
