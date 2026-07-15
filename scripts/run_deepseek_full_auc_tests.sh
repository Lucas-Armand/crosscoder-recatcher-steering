#!/usr/bin/env bash
set -euo pipefail

cd "${REPO_ROOT:-$HOME/crosscoder-recatcher-steering}"

ACTIVATION_ROOT="${ACTIVATION_ROOT:-/tmp/crosscoder_deepseek_activations}"
RESULT_ROOT="${RESULT_ROOT:-recatcher_crosscoder_humaneval/deepseek_rerun_1gen_max512/results}"
OUT_ROOT="${OUT_ROOT:-runs/crosscoder_failure_screening_deepseek}"
DEVICE="${DEVICE:-cuda}"

mkdir -p "$OUT_ROOT"

run_screen() {
  local checkpoint="$1"
  local model_a="$2"
  local model_b="$3"
  local target_model="$4"
  local tag="$5"
  shift 5

  echo
  echo "===== SCREENING: $tag ====="
  time python tools/screen_crosscoder_auc.py \
    --checkpoint "$checkpoint" \
    --activation-root "$ACTIVATION_ROOT" \
    --results-jsonl "$@" \
    --model-a "$model_a" \
    --model-b "$model_b" \
    --target-model "$target_model" \
    --layer 16 \
    --aggregation max \
    --device "$DEVICE" \
    --skip-errors \
    --output-dir "$OUT_ROOT/$tag"
}

FT_CKPT="runs/crosscoder_training_v1/deepseek_base_vs_deepseek_finetuned_layer16_lat16384_steps20000/final.pt"
MG_CKPT="runs/crosscoder_training_v1/deepseek_base_vs_deepseek_merged_layer16_lat16384_steps20000/final.pt"

# Base vs finetuned
run_screen "$FT_CKPT" deepseek_base deepseek_finetuned deepseek_finetuned \
  base_vs_finetuned_humaneval \
  "$RESULT_ROOT/humanevalplus__deepseek_finetuned_results.jsonl"

run_screen "$FT_CKPT" deepseek_base deepseek_finetuned deepseek_finetuned \
  base_vs_finetuned_bigcodebench \
  "$RESULT_ROOT/bigcodebench__deepseek_finetuned_results.jsonl"

run_screen "$FT_CKPT" deepseek_base deepseek_finetuned deepseek_finetuned \
  base_vs_finetuned_combined \
  "$RESULT_ROOT/humanevalplus__deepseek_finetuned_results.jsonl" \
  "$RESULT_ROOT/bigcodebench__deepseek_finetuned_results.jsonl"

# Base vs merged
run_screen "$MG_CKPT" deepseek_base deepseek_merged deepseek_merged \
  base_vs_merged_humaneval \
  "$RESULT_ROOT/humanevalplus__deepseek_merged_results.jsonl"

run_screen "$MG_CKPT" deepseek_base deepseek_merged deepseek_merged \
  base_vs_merged_bigcodebench \
  "$RESULT_ROOT/bigcodebench__deepseek_merged_results.jsonl"

run_screen "$MG_CKPT" deepseek_base deepseek_merged deepseek_merged \
  base_vs_merged_combined \
  "$RESULT_ROOT/humanevalplus__deepseek_merged_results.jsonl" \
  "$RESULT_ROOT/bigcodebench__deepseek_merged_results.jsonl"

python - <<'PY'
import csv
import json
from pathlib import Path

root = Path("runs/crosscoder_failure_screening_deepseek")
rows = []

for summary_path in sorted(root.glob("*/summary.json")):
    summary = json.loads(summary_path.read_text())
    tag = summary_path.parent.name
    top = summary.get("top_20", [])
    best = top[0] if top else {}
    rows.append({
        "run": tag,
        "n_examples": summary.get("n_examples"),
        "n_failures": summary.get("n_failures"),
        "failure_rate_percent": 100 * summary.get("failure_rate", 0),
        "n_skipped": summary.get("n_skipped"),
        "elapsed_seconds": summary.get("elapsed_seconds"),
        "best_feature": best.get("feature_id"),
        "best_auc": best.get("auc"),
        "best_predictive_auc": best.get("predictive_auc"),
        "best_direction": best.get("direction"),
    })

out = root / "screening_summary.csv"
with out.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

print()
print("===== SUMMARY =====")
for row in rows:
    print(
        f'{row["run"]:36s} '
        f'n={row["n_examples"]:4d} '
        f'fail={row["n_failures"]:4d} '
        f'failure={row["failure_rate_percent"]:6.2f}% '
        f'best_feature={str(row["best_feature"]):>5s} '
        f'best_pAUC={row["best_predictive_auc"]:.4f}'
    )
print(f"\nSaved: {out}")
PY
