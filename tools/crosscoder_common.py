#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import torch


FILE_RE = re.compile(
    r"^(?P<model>.+?)__(?P<benchmark>humanevalplus|bigcodebench)__"
    r"task_(?P<task_idx>\d+)__gen_(?P<gen_idx>\d+)__"
)


@dataclass(frozen=True)
class ExampleKey:
    benchmark: str
    task_idx: int
    gen_idx: int


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"Expected object at {path}:{line_no}")
            rows.append(obj)
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def index_activation_files(root: Path, model: str) -> dict[ExampleKey, Path]:
    model_root_candidates = list(root.glob(f"*/{model}"))
    if not model_root_candidates:
        raise FileNotFoundError(
            f"No activation directories matching {root}/*/{model}"
        )

    index: dict[ExampleKey, Path] = {}
    for model_root in model_root_candidates:
        benchmark = model_root.parent.name
        for path in model_root.glob("*.npz"):
            match = FILE_RE.match(path.name)
            if not match:
                continue
            key = ExampleKey(
                benchmark=benchmark,
                task_idx=int(match.group("task_idx")),
                gen_idx=int(match.group("gen_idx")),
            )
            if key in index:
                raise ValueError(f"Duplicate activation key {key}: {path} and {index[key]}")
            index[key] = path
    return index


def result_key(row: dict[str, Any]) -> ExampleKey:
    return ExampleKey(
        benchmark=str(row["benchmark"]),
        task_idx=int(row["task_idx"]),
        gen_idx=int(row.get("gen_idx", 0)),
    )


def load_layer(path: Path, layer: int) -> np.ndarray:
    layer_key = f"layer_{layer:02d}"
    with np.load(path, allow_pickle=False) as data:
        if layer_key not in data:
            raise KeyError(f"{layer_key} missing from {path}")
        arr = np.asarray(data[layer_key], dtype=np.float32)
    if arr.ndim != 2:
        raise ValueError(f"{path}:{layer_key} must be 2D, got {arr.shape}")
    if arr.shape[0] == 0:
        raise ValueError(f"{path}:{layer_key} has zero token rows")
    if not np.isfinite(arr).all():
        raise ValueError(f"{path}:{layer_key} contains non-finite values")
    return arr


def load_checkpoint_encoder(checkpoint_path: Path) -> tuple[torch.Tensor, torch.Tensor, dict]:
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    state = checkpoint["model_state_dict"]
    weight = state["encoder.weight"].detach().float().cpu()
    bias = state["encoder.bias"].detach().float().cpu()
    config = dict(checkpoint.get("config", {}))
    return weight, bias, config


def aggregate_latents(z: torch.Tensor, aggregation: str) -> torch.Tensor:
    if aggregation == "max":
        return z.max(dim=0).values
    if aggregation == "mean":
        return z.mean(dim=0)
    if aggregation == "last":
        return z[-1]
    if aggregation == "mean_positive":
        return torch.where(z > 0, z, torch.zeros_like(z)).mean(dim=0)
    raise ValueError(f"Unsupported aggregation: {aggregation}")


def compute_latent_summary(
    activation_a: np.ndarray,
    activation_b: np.ndarray,
    encoder_weight: torch.Tensor,
    encoder_bias: torch.Tensor,
    aggregation: str,
    device: str,
) -> np.ndarray:
    token_count = min(len(activation_a), len(activation_b))
    if token_count <= 0:
        raise ValueError("No aligned token rows")

    a = torch.from_numpy(activation_a[-token_count:]).to(device=device, dtype=torch.float32)
    b = torch.from_numpy(activation_b[-token_count:]).to(device=device, dtype=torch.float32)
    x = torch.cat([a, b], dim=-1)

    weight = encoder_weight.to(device)
    bias = encoder_bias.to(device)
    with torch.inference_mode():
        z = torch.relu(torch.nn.functional.linear(x, weight, bias))
        summary = aggregate_latents(z, aggregation)
    return summary.cpu().numpy().astype(np.float32, copy=False)
