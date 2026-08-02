#!/usr/bin/env python3
"""Decompose a reference steering direction into local model-difference subspaces."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np


def unit(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    return vector / norm if norm else np.zeros_like(vector)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-directions", type=Path, required=True)
    parser.add_argument("--local-direction-dir", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    reference_archive = np.load(args.reference_directions)
    task_ids = reference_archive["task_ids"].astype(str)
    matches = np.flatnonzero(task_ids == args.task_id)
    if len(matches) != 1:
        raise ValueError(f"Expected one reference for {args.task_id}; found {len(matches)}")
    reference = unit(reference_archive["directions"][matches[0]].astype(np.float64))
    safe = args.task_id.replace("/", "_")

    def load(name: str) -> np.ndarray:
        archive = np.load(args.local_direction_dir / f"{safe}__{name}.npz")
        return unit(archive["directions"][0].astype(np.float64))

    own = load("different_own_text")
    basis_names = [
        f"pc{pc}_{source}"
        for source in ("deepseek_base", "deepseek_finetuned")
        for pc in range(1, 6)
    ]
    basis_matrix = np.column_stack([load(name) for name in basis_names])
    q, _ = np.linalg.qr(basis_matrix)

    projection_own = np.dot(reference, own) * own
    residual_own = reference - projection_own
    projection_pc_span = q @ (q.T @ reference)
    residual_pc_span = reference - projection_pc_span
    outputs = {
        "reference_discriminant": reference,
        "projection_different_own_text": unit(projection_own),
        "residual_different_own_text": unit(residual_own),
        "projection_local_pc1_to_pc5_span": unit(projection_pc_span),
        "residual_local_pc1_to_pc5_span": unit(residual_pc_span),
        # Magnitude-preserving components are causal ablations: for each
        # subspace, projection_scaled + residual_scaled == reference.
        "projection_different_own_text_scaled": projection_own,
        "residual_different_own_text_scaled": residual_own,
        "projection_local_pc1_to_pc5_span_scaled": projection_pc_span,
        "residual_local_pc1_to_pc5_span_scaled": residual_pc_span,
    }
    for name, direction in outputs.items():
        np.savez_compressed(
            args.output_dir / f"{safe}__{name}.npz",
            task_ids=np.asarray([args.task_id]),
            directions=direction[None].astype(np.float32),
        )

    rows = [
        {
            "task_id": args.task_id,
            "subspace": "different_own_text",
            "projection_norm": float(np.linalg.norm(projection_own)),
            "squared_reference_fraction": float(np.dot(projection_own, projection_own)),
            "residual_norm": float(np.linalg.norm(residual_own)),
        },
        {
            "task_id": args.task_id,
            "subspace": "local_pc1_to_pc5_both_texts",
            "projection_norm": float(np.linalg.norm(projection_pc_span)),
            "squared_reference_fraction": float(np.dot(projection_pc_span, projection_pc_span)),
            "residual_norm": float(np.linalg.norm(residual_pc_span)),
        },
    ]
    with (args.output_dir / "decomposition_metrics.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
