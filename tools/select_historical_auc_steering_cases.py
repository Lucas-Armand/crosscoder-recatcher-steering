#!/usr/bin/env python3
"""Select high-activation pass/fail cases for historical-style steering."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from audit_evaluation_pipeline import Source, jsonl
from crosscoder_common import (
    load_checkpoint_encoder,
    load_layer,
    normalize_task_id,
    write_jsonl,
)
from run_differential_pr_auc_screening import (
    exact_mask,
    load_result_maps,
    maximum_positive_contribution,
)
from run_pr_auc_feature_screening import (
    discover_activation_index,
    load_historical_tokenizer,
    read_labels,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--activation-root", type=Path, action="append", required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--labels-csv", type=Path, required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--crosscoder-id", required=True)
    parser.add_argument("--benchmark", default="humanevalplus")
    parser.add_argument("--feature-id", type=int, required=True)
    parser.add_argument("--failures", type=int, default=20)
    parser.add_argument("--controls", type=int, default=20)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--output-jsonl", type=Path, required=True)
    parser.add_argument("--metadata-json", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text())
    crosscoder = next(
        item for item in manifest["crosscoders"] if item["id"] == args.crosscoder_id
    )
    base_model = crosscoder["model_a"]
    layer = int(str(manifest["crosscoder_contract"]["layer"]).split("_")[-1])
    labels = read_labels(args.labels_csv)
    index = discover_activation_index(args.activation_root, args.benchmark, base_model)
    weight, _, _ = load_checkpoint_encoder(args.checkpoint)
    hidden_size = load_layer(next(iter(index.values())), layer).shape[1]
    weight_a = torch.from_numpy(weight[:, :hidden_size]).to(args.device).float()
    tokenizer = load_historical_tokenizer(manifest["models"][base_model])
    source = Source(args.dataset)
    try:
        raw, repaired = load_result_maps(source, args.benchmark, base_model)
    except (FileNotFoundError, RuntimeError):
        stem = f"{args.benchmark}__{base_model}"
        repaired_rows = jsonl(source.read(f"results/{stem}_results.jsonl"))
        repaired = {
            normalize_task_id(row["task_id"]): row for row in repaired_rows
        }
        if len(repaired) != len(repaired_rows):
            raise ValueError("duplicate repaired task IDs")
        # This fallback is safe only when exact masks are embedded in each NPZ.
        # exact_mask will fail rather than fabricate alignment if one is absent.
        raw = repaired

    result_rows = repaired
    rows = []
    token_values = []
    skipped = []
    for key, label in labels.items():
        model, benchmark, task_id, generation = key
        if model != base_model or benchmark != args.benchmark:
            continue
        try:
            matches = [
                activation_key for activation_key in index
                if str(activation_key.task_idx) == task_id
                and activation_key.gen_idx == generation
            ]
            if len(matches) != 1:
                raise ValueError(f"activation matches={len(matches)}")
            activation_key = matches[0]
            array = load_layer(index[activation_key], layer)
            mask, _, _ = exact_mask(
                index[activation_key], array, len(array), task_id,
                raw, repaired, tokenizer,
            )
            score = maximum_positive_contribution(
                array, mask, weight_a, args.device
            )[args.feature_id]
            selected = np.asarray(array[-len(mask):][mask], dtype=np.float32)
            with torch.inference_mode():
                values = torch.nn.functional.linear(
                    torch.from_numpy(selected).to(args.device),
                    weight_a[args.feature_id:args.feature_id + 1],
                ).squeeze(-1).clamp_min_(0).cpu().numpy()
            token_values.append(values[values > 0])
            row = dict(result_rows[task_id])
            row.update({
                "historical_label": "failure" if int(label) == 1 else "pass_control",
                "historical_failure": int(label),
                "feature_id": args.feature_id,
                "historical_feature_score": float(score),
                "seed": 1000 + int(task_id),
            })
            rows.append(row)
        except Exception as exc:
            skipped.append({"task_id": task_id, "reason": f"{type(exc).__name__}: {exc}"})

    failures = sorted(
        (row for row in rows if row["historical_failure"] == 1),
        key=lambda row: row["historical_feature_score"], reverse=True,
    )[:args.failures]
    controls = sorted(
        (row for row in rows if row["historical_failure"] == 0),
        key=lambda row: row["historical_feature_score"], reverse=True,
    )[:args.controls]
    selected_rows = failures + controls
    positives = np.concatenate(token_values) if token_values else np.empty(0)
    if not len(positives):
        raise ValueError(
            "no positive evaluated-token contributions; "
            f"first skips={json.dumps(skipped[:5])}"
        )
    p99 = float(np.percentile(positives, 99))
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_jsonl, selected_rows)
    metadata = {
        "crosscoder_id": args.crosscoder_id,
        "base_model": base_model,
        "benchmark": args.benchmark,
        "layer": layer,
        "feature_id": args.feature_id,
        "score": "max positive base-side encoder contribution over evaluated_tokens",
        "scale": "p99 positive base-side encoder contribution over evaluated_tokens",
        "p99_scale": p99,
        "n_failures": len(failures),
        "n_controls": len(controls),
        "failure_task_ids": [row["task_id"] for row in failures],
        "control_task_ids": [row["task_id"] for row in controls],
        "skipped": skipped,
    }
    args.metadata_json.write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
