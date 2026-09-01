#!/usr/bin/env bash
set -euo pipefail
cd /home/lucas/crosscoder-recatcher-steering

run27="runs/codellama_bm_f27_symmetric_base50_v1"
run10168="runs/dstk100_f10168_symmetric_ft80_v1"
mkdir -p "$run27"/{generations,logs,postprocessed,evaluations} "$run10168"/{generations,logs,postprocessed,evaluations}
cp -n runs/codellama_bm_wrong_logic_50_first10_top5_canonical_v1/input.jsonl "$run27/input.jsonl"
cp -n runs/dstk100_continuous_f6404_f10168_f13801_v1/input.jsonl "$run10168/input.jsonl"

generate27() {
  local name="$1" alpha="$2"
  local out="$run27/generations/bigcodebench__f27_base_${name}_results.jsonl"
  [[ -f "$out" && "$(wc -l < "$out")" == 50 ]] && return
  CUDA_VISIBLE_DEVICES=1 .venv/bin/python tools/run_crosscoder_intervention.py \
    --checkpoint runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt \
    --model-a-id meta-llama/CodeLlama-7b-hf --model-b-id DevQuasar-5/coma-7B-v0.1 \
    --target-side a --layer 16 --feature-id 27 --alpha "$alpha" \
    --intervention-mode traditional --token-scope last_token --generation-backend hf_generate \
    --input-jsonl "$run27/input.jsonl" --output-jsonl "$out" --max-new-tokens 512 \
    --temperature 0.2 --top-p 0.95 --seed 1000 --device-a cuda:0 --dtype nf4 \
    --tokenizer-id meta-llama/CodeLlama-7b-hf >"$run27/logs/${name}.log" 2>&1
  [[ "$(wc -l < "$out")" == 50 ]]
}

generate10168() {
  local name="$1" alpha="$2"
  local out="$run10168/generations/bigcodebench__f10168_ft_${name}_results.jsonl"
  [[ -f "$out" && "$(wc -l < "$out")" == 80 ]] && return
  CUDA_VISIBLE_DEVICES=1 .venv/bin/python tools/run_crosscoder_intervention.py \
    --checkpoint runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt \
    --model-a-id deepseek-ai/deepseek-coder-6.7b-base --model-b-id JetBrains/deepseek-coder-6.7B-kexer \
    --target-side b --layer 16 --feature-id 10168 --alpha "$alpha" \
    --intervention-mode traditional --token-scope last_token --generation-backend hf_generate \
    --input-jsonl "$run10168/input.jsonl" --output-jsonl "$out" --max-new-tokens 512 \
    --temperature 0.2 --top-p 0.95 --seed 1000 --device-b cuda:0 --dtype nf4 \
    --tokenizer-id deepseek-ai/deepseek-coder-6.7b-base --trust-remote-code >"$run10168/logs/${name}.log" 2>&1
  [[ "$(wc -l < "$out")" == 80 ]]
}

generate27 alpha0 0
for alpha in 1 2 3 4 5; do generate27 "neg${alpha}" "-${alpha}"; done
touch "$run27/GENERATIONS_COMPLETE"
.venv/bin/python tools/reprocess_outputs_minimal.py --raw-results-dir "$run27/generations" --output-dir "$run27/postprocessed" >"$run27/logs/reprocess.log" 2>&1
for sample in "$run27"/postprocessed/samples_for_external_eval/*_samples.jsonl; do
  stem="$(basename "$sample" _samples.jsonl)"
  /home/lucas/venvs/bigcodebench015/bin/python tools/evaluate_bigcodebench_subset.py --samples "$sample" --output "$run27/evaluations/${stem}_eval.json" --parallel 4 >"$run27/logs/eval_${stem}.log" 2>&1
done
touch "$run27/EVALUATION_COMPLETE"

generate10168 alpha0 0
for alpha in 1 2 3 4 5; do generate10168 "pos${alpha}" "$alpha"; done
touch "$run10168/GENERATIONS_COMPLETE"
.venv/bin/python tools/reprocess_outputs_minimal.py --raw-results-dir "$run10168/generations" --output-dir "$run10168/postprocessed" >"$run10168/logs/reprocess.log" 2>&1
for sample in "$run10168"/postprocessed/samples_for_external_eval/*_samples.jsonl; do
  stem="$(basename "$sample" _samples.jsonl)"
  /home/lucas/venvs/bigcodebench015/bin/python tools/evaluate_bigcodebench_subset.py --samples "$sample" --output "$run10168/evaluations/${stem}_eval.json" --parallel 4 >"$run10168/logs/eval_${stem}.log" 2>&1
done
touch "$run10168/EVALUATION_COMPLETE"
