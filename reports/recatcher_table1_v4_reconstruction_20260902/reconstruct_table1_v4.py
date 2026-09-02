#!/usr/bin/env python3
"""Reconstruct ReCatcher Table 1 General Logic and compare it with extraction/evaluation v4."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


MODELS = (
    "deepseek_base",
    "deepseek_finetuned",
    "codellama_base",
    "codellama_merged",
)
PAIRS = (
    ("deepseek_base", "deepseek_finetuned", "DeepSeek base--FT", 9.32),
    ("codellama_base", "codellama_merged", "CodeLlama base--merged", 6.71),
)
N_TASKS = 1140
N_EXPS = 10


def read_original(path: Path) -> dict[tuple[str, str, int], bool]:
    result = {}
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            exp = int(row["exp"].removeprefix("exp_"))
            result[(row["model"], row["task_id"], exp)] = bool(int(row["correct"]))
    return result


def evaluation_path(root: Path, model: str, exp: int) -> Path:
    name = f"bigcodebench__{model}_exp{exp}.json"
    if model == "codellama_merged":
        return root / "merged_parallel_eval" / name
    return root / "final_eval" / name


def read_v4(root: Path) -> dict[tuple[str, str, int], bool]:
    result = {}
    for model in MODELS:
        for exp in range(N_EXPS):
            payload = json.loads(evaluation_path(root, model, exp).read_text())
            for task_id, records in payload["eval"].items():
                result[(model, task_id, exp)] = bool(records[0]["correct"])
            # CodeLlama merged task 8 has an empty original continuation in every
            # experiment. Extraction v4 cannot emit a sample, so it is an explicit fail.
            if model == "codellama_merged":
                result[(model, "BigCodeBench/8", exp)] = False
    expected = len(MODELS) * N_TASKS * N_EXPS
    if len(result) != expected:
        raise RuntimeError(f"Expected {expected} v4 labels, found {len(result)}")
    return result


def transitions(labels, base: str, variant: str):
    counts = Counter()
    for exp in range(N_EXPS):
        for task_idx in range(N_TASKS):
            task = f"BigCodeBench/{task_idx}"
            a = labels[(base, task, exp)]
            b = labels[(variant, task, exp)]
            counts[(a, b)] += 1
    return {
        "both_fail": counts[(False, False)],
        "improvement": counts[(False, True)],
        "regression": counts[(True, False)],
        "both_pass": counts[(True, True)],
    }


def write_csv(path: Path, rows: list[dict]):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    original = read_original(args.root / "original_logic_labels.csv")
    v4 = read_v4(args.root)
    expected = len(MODELS) * N_TASKS * N_EXPS
    if len(original) != expected:
        raise RuntimeError(f"Expected {expected} original labels, found {len(original)}")

    model_rows = []
    for model in MODELS:
        keys = [(model, f"BigCodeBench/{task}", exp) for exp in range(N_EXPS) for task in range(N_TASKS)]
        old = sum(original[k] for k in keys)
        new = sum(v4[k] for k in keys)
        up = sum((not original[k]) and v4[k] for k in keys)
        down = sum(original[k] and (not v4[k]) for k in keys)
        model_rows.append({
            "model": model,
            "n": len(keys),
            "original_passes": old,
            "original_rate_pct": f"{100 * old / len(keys):.6f}",
            "v4_passes": new,
            "v4_rate_pct": f"{100 * new / len(keys):.6f}",
            "v4_minus_original_pp": f"{100 * (new - old) / len(keys):.6f}",
            "label_agreement": len(keys) - up - down,
            "agreement_pct": f"{100 * (len(keys) - up - down) / len(keys):.6f}",
            "original_fail_to_v4_pass": up,
            "original_pass_to_v4_fail": down,
        })

    pair_rows = []
    for base, variant, label, published in PAIRS:
        for evaluator_name, labels in (("Zenodo original labels", original), ("Extraction/evaluator v4", v4)):
            trans = transitions(labels, base, variant)
            base_passes = sum(labels[(base, f"BigCodeBench/{task}", exp)] for exp in range(N_EXPS) for task in range(N_TASKS))
            variant_passes = sum(labels[(variant, f"BigCodeBench/{task}", exp)] for exp in range(N_EXPS) for task in range(N_TASKS))
            delta = 100 * (variant_passes - base_passes) / (N_TASKS * N_EXPS)
            pair_rows.append({
                "pair": label,
                "evaluation": evaluator_name,
                "n": N_TASKS * N_EXPS,
                "base_passes": base_passes,
                "variant_passes": variant_passes,
                "delta_pp": f"{delta:.6f}",
                "published_table1_pp": f"{published:.2f}",
                **trans,
            })

    write_csv(args.output_dir / "model_summary.csv", model_rows)
    write_csv(args.output_dir / "pair_summary.csv", pair_rows)
    payload = {"model_summary": model_rows, "pair_summary": pair_rows}
    (args.output_dir / "summary.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
