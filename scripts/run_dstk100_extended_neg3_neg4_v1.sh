#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering
run=runs/dstk100_extended_controls_neg3_neg4_v1
source_run=runs/dstk100_f6404_test_contamination_general_v1
mkdir -p "$run/generations" "$run/logs" "$run/postprocessed" "$run/evaluations" "$run/finalizer_logs"
cp "$source_run/input.jsonl" "$run/input.jsonl"
cp "$source_run/sham_orthogonal_seed6404.npz" "$run/sham_orthogonal_seed6404.npz"
cp "$source_run/SHAM_DIRECTION.json" "$run/SHAM_DIRECTION.json"
common=(--checkpoint runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt --model-a-id deepseek-ai/deepseek-coder-6.7b-base --model-b-id JetBrains/deepseek-coder-6.7B-kexer --target-side a --layer 16 --intervention-mode topk_gated_suppression --token-scope last_token --generation-backend paired_cached --top-k 100 --rms-epsilon 1e-6 --input-jsonl "$run/input.jsonl" --max-new-tokens 512 --temperature 0.2 --top-p 0.95 --seed 1000 --device-a cuda:0 --device-b cuda:1 --dtype nf4 --reference-dtype float16 --tokenizer-id deepseek-ai/deepseek-coder-6.7b-base --trust-remote-code)
for alpha_spec in neg3:-3 neg4:-4; do
  alpha_name=${alpha_spec%%:*}; alpha=${alpha_spec#*:}
  for condition in f6404 sham f9388 f6757 f6509; do
    extra=()
    case "$condition" in
      f6404) fid=6404 ;;
      sham) fid=6404; extra=(--per-example-direction-npz "$run/sham_orthogonal_seed6404.npz" --preserve-per-example-direction-norm) ;;
      f9388) fid=9388 ;;
      f6757) fid=6757 ;;
      f6509) fid=6509 ;;
    esac
    name="${condition}_alpha_${alpha_name}"
    .venv/bin/python tools/run_crosscoder_intervention.py "${common[@]}" "${extra[@]}" --feature-id "$fid" --alpha "$alpha" --output-jsonl "$run/generations/bigcodebench__${name}_results.jsonl" > "$run/logs/${name}.log" 2>&1
  done
done
.venv/bin/python tools/reprocess_outputs_minimal.py --raw-results-dir "$run/generations" --output-dir "$run/postprocessed" > "$run/finalizer_logs/reprocess.log" 2>&1
for sample in "$run"/postprocessed/samples_for_external_eval/*_samples.jsonl; do
  stem=$(basename "$sample" _samples.jsonl)
  /home/lucas/venvs/bigcodebench015/bin/python tools/evaluate_bigcodebench_subset.py --samples "$sample" --output "$run/evaluations/${stem}_eval.json" --parallel 4 > "$run/finalizer_logs/eval_${stem}.log" 2>&1
done
touch "$run/PIPELINE_COMPLETE"
