#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch


ACTIVATION_FILENAME_RE = re.compile(
    r"^(?P<model>.+?)__"
    r"(?P<benchmark>humanevalplus|bigcodebench)__"
    r"task_(?P<task_idx>\d+)__"
    r"gen_(?P<gen_idx>\d+)__"
)


@dataclass(frozen=True, order=True)
class ExampleKey:
    benchmark: str
    task_idx: int
    gen_idx: int


def normalize_benchmark(value: Any) -> str:
    text = str(value).strip().lower()
    aliases = {
        "humaneval": "humanevalplus",
        "humaneval+": "humanevalplus",
        "evalplus": "humanevalplus",
        "bigcodebench_complete": "bigcodebench",
        "bigcodebench-complete": "bigcodebench",
    }
    return aliases.get(text, text)


def normalize_task_id(value: Any) -> str:
    text = str(value).strip()
    for prefix in (
        "BigCodeBench/",
        "BigCodeBench_",
        "HumanEval/",
        "HumanEval_",
    ):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    try:
        return str(int(text))
    except ValueError:
        return text


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(obj)
    return rows


def result_key(row: dict[str, Any]) -> ExampleKey:
    benchmark = normalize_benchmark(row.get("benchmark", ""))
    if "task_idx" in row and row["task_idx"] is not None:
        task_idx = int(row["task_idx"])
    elif "task_id" in row and row["task_id"] is not None:
        normalized = normalize_task_id(row["task_id"])
        try:
            task_idx = int(normalized)
        except ValueError as exc:
            raise ValueError(
                f"Cannot infer numeric task_idx from task_id={row['task_id']!r}"
            ) from exc
    else:
        raise KeyError("Result row must contain task_idx or task_id")

    gen_idx = int(row.get("gen_idx", row.get("generation_idx", 0)))
    return ExampleKey(benchmark=benchmark, task_idx=task_idx, gen_idx=gen_idx)


def index_activation_files(activation_root: Path, model: str) -> dict[ExampleKey, Path]:
    activation_root = Path(activation_root)
    if not activation_root.exists():
        raise FileNotFoundError(f"Activation root does not exist: {activation_root}")

    index: dict[ExampleKey, Path] = {}
    for path in activation_root.rglob("*.npz"):
        match = ACTIVATION_FILENAME_RE.match(path.name)
        if match is None or match.group("model") != model:
            continue
        key = ExampleKey(
            benchmark=normalize_benchmark(match.group("benchmark")),
            task_idx=int(match.group("task_idx")),
            gen_idx=int(match.group("gen_idx")),
        )
        if key in index:
            raise ValueError(
                f"Duplicate activation key for model {model}: {key}\n"
                f"  first:  {index[key]}\n  second: {path}"
            )
        index[key] = path

    if not index:
        raise FileNotFoundError(
            f"No activation files found for model={model!r} under {activation_root}"
        )
    return index


def load_layer(path: Path, layer: int) -> np.ndarray:
    layer_name = f"layer_{int(layer):02d}"
    with np.load(path, allow_pickle=False) as archive:
        if layer_name not in archive:
            raise KeyError(
                f"{path}: missing {layer_name}; available={sorted(archive.files)}"
            )
        array = np.asarray(archive[layer_name])

    if array.dtype == object:
        raise TypeError(
            f"{path}:{layer_name} has dtype=object; use canonical float32 activations"
        )
    array = np.asarray(array, dtype=np.float32)
    if array.ndim == 1:
        array = array[None, :]
    if array.ndim != 2:
        raise ValueError(
            f"{path}:{layer_name} expected 2D [tokens, hidden], got {array.shape}"
        )
    if array.shape[0] == 0:
        raise ValueError(f"{path}:{layer_name} has zero token rows")
    if not np.isfinite(array).all():
        raise ValueError(f"{path}:{layer_name} contains non-finite values")
    return array


def load_checkpoint_encoder(
    checkpoint_path: Path,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    checkpoint = torch.load(
        Path(checkpoint_path), map_location="cpu", weights_only=False
    )
    if not isinstance(checkpoint, dict):
        raise ValueError(f"{checkpoint_path}: expected checkpoint dict")

    state_dict = checkpoint.get("model_state_dict", checkpoint)
    for name in ("encoder.weight", "encoder.bias"):
        if name not in state_dict:
            raise KeyError(f"{checkpoint_path}: missing {name}")

    weight = state_dict["encoder.weight"].detach().cpu().float().numpy()
    bias = state_dict["encoder.bias"].detach().cpu().float().numpy()

    if weight.ndim != 2 or bias.ndim != 1 or weight.shape[0] != bias.shape[0]:
        raise ValueError(
            f"Invalid encoder shapes: weight={weight.shape}, bias={bias.shape}"
        )

    config = checkpoint.get("config", {})
    if not isinstance(config, dict):
        config = {"raw_config": config}
    return weight, bias, config


def _aggregate_latents(latent: torch.Tensor, aggregation: str) -> torch.Tensor:
    if aggregation == "max":
        return latent.max(dim=0).values
    if aggregation == "mean":
        return latent.mean(dim=0)
    if aggregation == "last":
        return latent[-1]
    if aggregation == "mean_positive":
        positive = latent > 0
        counts = positive.sum(dim=0)
        sums = torch.where(positive, latent, torch.zeros_like(latent)).sum(dim=0)
        return torch.where(
            counts > 0,
            sums / counts.clamp_min(1),
            torch.zeros_like(sums),
        )
    raise ValueError(f"Unknown aggregation: {aggregation}")


def compute_latent_summary(
    activation_a: np.ndarray,
    activation_b: np.ndarray,
    encoder_weight: np.ndarray,
    encoder_bias: np.ndarray,
    aggregation: str,
    device: str,
) -> np.ndarray:
    if activation_a.ndim != 2 or activation_b.ndim != 2:
        raise ValueError("Both activations must be 2D")
    if activation_a.shape[1] != activation_b.shape[1]:
        raise ValueError(
            f"Hidden size mismatch: a={activation_a.shape}, b={activation_b.shape}"
        )

    token_count = min(activation_a.shape[0], activation_b.shape[0])
    if token_count <= 0:
        raise ValueError("No overlapping token positions")

    paired = np.concatenate(
        [activation_a[-token_count:], activation_b[-token_count:]], axis=1
    ).astype(np.float32, copy=False)

    if paired.shape[1] != encoder_weight.shape[1]:
        raise ValueError(
            f"Encoder input width mismatch: paired={paired.shape[1]}, "
            f"encoder={encoder_weight.shape[1]}"
        )

    torch_device = torch.device(device)
    with torch.inference_mode():
        x = torch.from_numpy(paired).to(torch_device, dtype=torch.float32)
        weight = torch.from_numpy(encoder_weight).to(torch_device, dtype=torch.float32)
        bias = torch.from_numpy(encoder_bias).to(torch_device, dtype=torch.float32)
        latent = torch.relu(torch.nn.functional.linear(x, weight, bias))
        summary = _aggregate_latents(latent, aggregation)

    result = summary.detach().cpu().numpy().astype(np.float32, copy=False)
    if not np.isfinite(result).all():
        raise ValueError("Latent summary contains non-finite values")
    return result


def write_jsonl(
    path: Path,
    rows: Iterable[dict[str, Any]],
) -> None:
    """
    Write JSON objects as JSONL, replacing the destination atomically.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temporary_path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    allow_nan=False,
                )
            )
            handle.write("\n")

    temporary_path.replace(path)
