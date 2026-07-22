#!/usr/bin/env python3
from __future__ import annotations

import json
import difflib
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


def load_evaluated_token_mask(path: Path, expected_rows: int) -> np.ndarray:
    """Load the exact, capture-time mask for generated tokens sent to evaluation."""
    with np.load(path, allow_pickle=False) as archive:
        if "evaluated_token_mask" not in archive:
            raise KeyError(
                f"{path}: missing evaluated_token_mask; exact evaluated-token alignment "
                "cannot be reconstructed from legacy activations"
            )
        mask = np.asarray(archive["evaluated_token_mask"], dtype=np.bool_)
        if "token_char_spans" not in archive:
            raise KeyError(f"{path}: missing token_char_spans alignment provenance")
        spans = np.asarray(archive["token_char_spans"])
    if mask.shape != (expected_rows,) or spans.shape != (expected_rows, 2):
        raise ValueError(
            f"{path}: alignment metadata does not match activation rows: "
            f"mask={mask.shape}, spans={spans.shape}, rows={expected_rows}"
        )
    if not mask.any():
        raise ValueError(f"{path}: evaluated_token_mask selects zero tokens")
    return mask


def derive_legacy_evaluated_token_mask(
    path: Path,
    expected_rows: int,
    raw_row: dict[str, Any],
    repaired_row: dict[str, Any],
    tokenizer: Any,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Exactly reconstruct a legacy mask, guarded by stored-ID equality.

    The original full text is tokenized, never the cleaned candidate. The
    reconstruction is accepted only if every resulting token ID equals the stored
    IDs. Literal matching then maps retained generated characters onto those proven
    token offsets.
    """
    with np.load(path, allow_pickle=False) as archive:
        stored_ids = np.asarray(archive["input_ids"], dtype=np.int64)
    prompt = str(raw_row["prompt"])
    completion = str(raw_row.get("raw_completion", raw_row.get("completion", "")))
    full_text = prompt.rstrip() + "\n" + completion.rstrip() + "\n"
    encoded = tokenizer(
        full_text,
        truncation=True,
        max_length=len(stored_ids),
        return_offsets_mapping=True,
    )
    rebuilt_ids = np.asarray(encoded["input_ids"], dtype=np.int64)
    offsets = np.asarray(encoded["offset_mapping"], dtype=np.int64)
    if rebuilt_ids.shape != stored_ids.shape or not np.array_equal(rebuilt_ids, stored_ids):
        mismatch = int(np.flatnonzero(rebuilt_ids != stored_ids)[0]) if rebuilt_ids.shape == stored_ids.shape and np.any(rebuilt_ids != stored_ids) else None
        raise ValueError(
            f"{path}: exact legacy alignment failed stored-ID equality: "
            f"stored={stored_ids.shape}, rebuilt={rebuilt_ids.shape}, first_mismatch={mismatch}"
        )
    if expected_rows > len(stored_ids):
        raise ValueError(f"{path}: activation rows exceed stored token IDs")

    candidate = str(repaired_row["candidate_code_original"])
    prompt_prefix = prompt.rstrip() + "\n"
    candidate_generated = candidate[len(prompt_prefix):] if candidate.startswith(prompt_prefix) else candidate
    candidate_generated = candidate_generated.rstrip()
    if not candidate_generated:
        raise ValueError(f"{path}: evaluated candidate contains no generated text")

    matcher = difflib.SequenceMatcher(
        a=completion, b=candidate_generated, autojunk=False
    )
    blocks = [block for block in matcher.get_matching_blocks() if block.size]
    matched_candidate_chars = sum(block.size for block in blocks)
    coverage = matched_candidate_chars / len(candidate_generated)
    if coverage < 0.999999:
        raise ValueError(
            f"{path}: evaluated generated text is not a literal selection from raw "
            f"completion (character coverage={coverage:.6f})"
        )

    generated_start = len(prompt.rstrip() + "\n")
    retained_spans = [
        (generated_start + block.a, generated_start + block.a + block.size)
        for block in blocks
    ]
    saved_offsets = offsets[-expected_rows:]
    mask = np.asarray(
        [
            end > begin and any(end > lo and begin < hi for lo, hi in retained_spans)
            for begin, end in saved_offsets
        ],
        dtype=np.bool_,
    )
    if not mask.any():
        raise ValueError(f"{path}: reconstructed legacy mask selects zero tokens")

    nonempty = candidate_generated.rstrip()
    prefix_literal = completion.startswith(nonempty)
    return mask, {
        "alignment_source": "legacy_stored_id_verified_literal_spans",
        "stored_id_equality": True,
        "matched_character_coverage": coverage,
        "literal_prefix": prefix_literal,
        "retained_span_count": len(retained_spans),
        "evaluated_tokens": int(mask.sum()),
    }


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
    token_mask: np.ndarray | None = None,
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
    if token_mask is not None:
        mask = np.asarray(token_mask, dtype=np.bool_)
        if mask.shape != (token_count,):
            raise ValueError(
                f"Token mask shape {mask.shape} does not match paired rows {token_count}"
            )
        paired = paired[mask]
        if paired.shape[0] == 0:
            raise ValueError("Token mask selects zero paired token positions")

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
