#!/usr/bin/env python3
"""Materialize exact evaluated-token masks as immutable NPZ sidecars."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

from crosscoder_common import (
    derive_legacy_evaluated_token_mask,
    index_activation_files,
    load_layer,
    normalize_task_id,
    read_jsonl,
)
from run_roc_auc_feature_screening import load_historical_tokenizer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("manifests/paper_v1.json"))
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--activation-root", type=Path, action="append", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--layer", type=int, default=16)
    return parser.parse_args()


def find_index(roots: list[Path], benchmark: str, model: str):
    for root in roots:
        try:
            return index_activation_files(root / benchmark, model)
        except FileNotFoundError:
            continue
    raise FileNotFoundError(f"no activations for {benchmark}/{model}")


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text())
    summary = []
    failures = []
    for benchmark in manifest["benchmarks"]:
        for model, model_name in manifest["models"].items():
            stem = f"{benchmark}__{model}"
            raw_rows = {
                normalize_task_id(row["task_id"]): row
                for row in read_jsonl(args.dataset_root / "raw_results" / f"{stem}_results.jsonl")
            }
            processed_rows = {
                normalize_task_id(row["task_id"]): row
                for row in read_jsonl(args.dataset_root / "results" / f"{stem}_results.jsonl")
            }
            index = find_index(args.activation_root, benchmark, model)
            tokenizer = load_historical_tokenizer(model_name)
            counts = Counter()
            for key, activation_path in sorted(index.items()):
                task_id = str(key.task_idx)
                try:
                    if task_id not in raw_rows or task_id not in processed_rows:
                        raise KeyError("task missing from raw or processed results")
                    rows = len(load_layer(activation_path, args.layer))
                    mask, provenance = derive_legacy_evaluated_token_mask(
                        activation_path, rows, raw_rows[task_id],
                        processed_rows[task_id], tokenizer,
                    )
                    relative = Path(benchmark) / model / f"{activation_path.stem}.evaluated_tokens.npz"
                    destination = args.output_root / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    np.savez_compressed(
                        destination,
                        evaluated_token_mask=mask,
                        task_idx=np.int64(key.task_idx),
                        gen_idx=np.int64(key.gen_idx),
                        benchmark=np.asarray(benchmark),
                        model=np.asarray(model),
                        activation_filename=np.asarray(activation_path.name),
                        provenance_json=np.asarray(json.dumps(provenance, sort_keys=True)),
                    )
                    counts["materialized"] += 1
                    counts["selected_tokens"] += int(mask.sum())
                    counts["nonprefix"] += int(not provenance["literal_prefix"])
                except Exception as exc:
                    counts["failed"] += 1
                    failures.append({
                        "benchmark": benchmark, "model": model,
                        "task_idx": key.task_idx, "activation": str(activation_path),
                        "error": f"{type(exc).__name__}: {exc}",
                    })
            summary.append({"benchmark": benchmark, "model": model, **counts})
            print(summary[-1], flush=True)
    report = {"status": "PASS" if not failures else "FAIL", "summary": summary, "failures": failures}
    (args.output_root / "mask_materialization_report.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
