#!/usr/bin/env python3
"""
Train an explicitly sparse TopK CrossCoder from strictly paired activation NPZ files.

Expected activation layout:

  <activation_root>/<benchmark>/<model>/<file>.npz

Each .npz should contain arrays like:

  input_ids
  layer_08
  layer_16
  layer_24

The script matches activation files from two models by task/gen identifiers found
in the filename, for example:

  deepseek_base__bigcodebench__task_0000__gen_00__BigCodeBench_0.npz
  deepseek_merged__bigcodebench__task_0000__gen_00__BigCodeBench_0.npz

Matched key:

  task_0000__gen_00

Important methodological note:
If your activation tensors only contain generated-token activations, token positions
across models may not be semantically aligned because each model may generate
different text. This script is useful as a first reproducible baseline, but for a
strict paired CrossCoder you should capture activations for the same text in both
models, ideally prompt tokens or a fixed reference completion.

Example:

  python tools/train_crosscoder_from_npz.py \
    --activation-root /tmp/crosscoder_postprocess_and_eval_v3/out/selected_layer_activations \
    --benchmarks humanevalplus bigcodebench \
    --model-a deepseek_base \
    --model-b deepseek_merged \
    --layer 16 \
    --latent-dim 16384 \
    --batch-size 2048 \
    --steps 20000 \
    --lr 1e-4 \
    --l1-coef 1e-3 \
    --output-dir runs/crosscoder_deepseek_base_vs_merged_layer16
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


PAIR_RE = re.compile(r"task_(\d+)__gen_(\d+)")


@dataclass
class TrainConfig:
    activation_root: str
    benchmarks: List[str]
    model_a: str
    model_b: str
    layer: str
    latent_dim: int
    batch_size: int
    tokens_per_pair: int
    steps: int
    lr: float
    l1_coef: float
    top_k: int
    weight_decay: float
    seed: int
    device: str
    dtype: str
    max_pairs: Optional[int]
    val_frac: float
    eval_every: int
    save_every: int
    num_workers_note: str
    output_dir: str
    normalize_loss: bool
    decoder_unit_norm: bool
    pairing_mode: str


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train a sparse CrossCoder from paired .npz activations.")

    p.add_argument("--activation-root", required=True, help="Root containing selected_layer_activations/<benchmark>/<model>.")
    p.add_argument("--benchmarks", nargs="+", default=["humanevalplus", "bigcodebench"])
    p.add_argument("--model-a", required=True)
    p.add_argument("--model-b", required=True)
    p.add_argument("--layer", required=True, help="Layer id or key, e.g. 16 or layer_16.")
    p.add_argument("--output-dir", required=True)

    p.add_argument("--latent-dim", type=int, default=16384)
    p.add_argument("--batch-size", type=int, default=2048)
    p.add_argument("--tokens-per-pair", type=int, default=128, help="Max token rows sampled from each matched file pair per visit.")
    p.add_argument("--steps", type=int, default=20000)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--l1-coef", type=float, default=1e-3)
    p.add_argument("--top-k", type=int, default=100, help="Exact maximum active latents per token.")
    p.add_argument("--weight-decay", type=float, default=0.0)

    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    p.add_argument("--dtype", choices=["float32", "float16", "bfloat16"], default="float32")

    p.add_argument("--max-pairs", type=int, default=None)
    p.add_argument("--val-frac", type=float, default=0.02)
    p.add_argument("--eval-every", type=int, default=500)
    p.add_argument("--save-every", type=int, default=2000)

    p.add_argument(
        "--pairing-mode",
        choices=["same_position", "random_independent"],
        default="same_position",
        help=(
            "same_position samples the same token indices from both tensors after truncating to min length. "
            "random_independent samples token rows independently from each tensor in the matched file pair."
        ),
    )
    p.add_argument("--no-normalize-loss", action="store_true", help="Disable reconstruction loss normalization by batch activation energy.")
    p.add_argument("--no-decoder-unit-norm", action="store_true", help="Disable decoder feature normalization after optimizer steps.")

    return p.parse_args()


def canonical_layer_key(layer: str) -> str:
    layer = str(layer)
    if layer.startswith("layer_"):
        return layer
    return f"layer_{int(layer):02d}"


def pair_key_from_path(path: Path) -> Optional[str]:
    m = PAIR_RE.search(path.name)
    if not m:
        return None
    return f"task_{int(m.group(1)):04d}__gen_{int(m.group(2)):02d}"


def list_npz_files(root: Path, benchmark: str, model: str) -> Dict[str, Path]:
    d = root / benchmark / model
    if not d.exists():
        raise FileNotFoundError(f"Activation directory not found: {d}")

    out: Dict[str, Path] = {}
    for p in sorted(d.glob("*.npz")):
        key = pair_key_from_path(p)
        if key is None:
            continue
        # Keep the first if duplicates exist.
        out.setdefault(key, p)
    return out


def find_pairs(root: Path, benchmarks: Sequence[str], model_a: str, model_b: str, max_pairs: Optional[int]) -> List[Tuple[str, str, Path, Path]]:
    pairs: List[Tuple[str, str, Path, Path]] = []

    for bench in benchmarks:
        a = list_npz_files(root, bench, model_a)
        b = list_npz_files(root, bench, model_b)

        common = sorted(set(a) & set(b))
        print(f"[{bench}] {model_a}: {len(a)} files | {model_b}: {len(b)} files | matched: {len(common)}")

        for key in common:
            pairs.append((bench, key, a[key], b[key]))

    if not pairs:
        raise RuntimeError("No matched activation file pairs found.")

    if max_pairs is not None:
        pairs = pairs[:max_pairs]

    return pairs


def load_layer_array(path: Path, layer_key: str) -> np.ndarray:
    with np.load(path, allow_pickle=True) as z:
        if layer_key not in z:
            keys = sorted(z.files)
            raise KeyError(f"{layer_key} not found in {path}. Available keys: {keys}")
        arr = z[layer_key].copy()

    if arr.ndim != 2:
        raise ValueError(f"Expected 2D activation array in {path}:{layer_key}, got shape={arr.shape}")

    return arr


def sample_rows(
    arr_a: np.ndarray,
    arr_b: np.ndarray,
    n: int,
    mode: str,
    rng: random.Random,
) -> Tuple[np.ndarray, np.ndarray]:
    len_a = int(arr_a.shape[0])
    len_b = int(arr_b.shape[0])

    if len_a == 0 or len_b == 0:
        raise ValueError(f"Empty activation array: len_a={len_a}, len_b={len_b}")

    if mode == "same_position":
        m = min(len_a, len_b)
        k = min(n, m)
        idx = rng.sample(range(m), k=k) if m > k else list(range(m))
        return arr_a[idx], arr_b[idx]

    if mode == "random_independent":
        k = min(n, len_a, len_b)
        idx_a = [rng.randrange(len_a) for _ in range(k)]
        idx_b = [rng.randrange(len_b) for _ in range(k)]
        return arr_a[idx_a], arr_b[idx_b]

    raise ValueError(mode)


class ActivationPairBatcher:
    def __init__(
        self,
        pairs: Sequence[Tuple[str, str, Path, Path]],
        layer_key: str,
        batch_size: int,
        tokens_per_pair: int,
        pairing_mode: str,
        seed: int,
        dtype: torch.dtype,
        device: torch.device,
    ) -> None:
        self.pairs = list(pairs)
        self.layer_key = layer_key
        self.batch_size = int(batch_size)
        self.tokens_per_pair = int(tokens_per_pair)
        self.pairing_mode = pairing_mode
        self.rng = random.Random(seed)
        self.dtype = dtype
        self.device = device

        self._buffer_a: List[np.ndarray] = []
        self._buffer_b: List[np.ndarray] = []
        self._array_cache: Dict[Path, np.ndarray] = {}

    def _load(self, path: Path) -> np.ndarray:
        if path not in self._array_cache:
            self._array_cache[path] = load_layer_array(path, self.layer_key)
        return self._array_cache[path]

    def _fill_buffer_once(self) -> None:
        # Some activation files may contain zero generated-token activations,
        # for example arrays with shape (0, hidden_dim). These files are valid
        # artifacts but cannot contribute training rows, so we skip them.
        max_attempts = max(100, len(self.pairs) * 2)

        for _ in range(max_attempts):
            bench, key, path_a, path_b = self.rng.choice(self.pairs)
            arr_a = self._load(path_a)
            arr_b = self._load(path_b)

            if int(arr_a.shape[0]) == 0 or int(arr_b.shape[0]) == 0:
                continue

            try:
                rows_a, rows_b = sample_rows(
                    arr_a=arr_a,
                    arr_b=arr_b,
                    n=self.tokens_per_pair,
                    mode=self.pairing_mode,
                    rng=self.rng,
                )
            except ValueError:
                continue

            if rows_a.shape[0] == 0 or rows_b.shape[0] == 0:
                continue

            self._buffer_a.append(rows_a.astype(np.float32, copy=False))
            self._buffer_b.append(rows_b.astype(np.float32, copy=False))
            return

        raise RuntimeError(
            f"Could not sample a non-empty activation pair after {max_attempts} attempts. "
            f"Check layer={self.layer_key}, pairing_mode={self.pairing_mode}, and activation files."
        )

    def next_batch(self) -> Tuple[torch.Tensor, torch.Tensor]:
        n_buffer = sum(x.shape[0] for x in self._buffer_a)

        while n_buffer < self.batch_size:
            self._fill_buffer_once()
            n_buffer = sum(x.shape[0] for x in self._buffer_a)

        a = np.concatenate(self._buffer_a, axis=0)
        b = np.concatenate(self._buffer_b, axis=0)

        batch_a = a[: self.batch_size]
        batch_b = b[: self.batch_size]

        rest_a = a[self.batch_size :]
        rest_b = b[self.batch_size :]

        self._buffer_a = [rest_a] if rest_a.shape[0] else []
        self._buffer_b = [rest_b] if rest_b.shape[0] else []

        ta = torch.from_numpy(batch_a).to(device=self.device, dtype=self.dtype, non_blocking=True)
        tb = torch.from_numpy(batch_b).to(device=self.device, dtype=self.dtype, non_blocking=True)

        return ta, tb


class CrossCoder(nn.Module):
    def __init__(self, dim_a: int, dim_b: int, latent_dim: int, top_k: int) -> None:
        super().__init__()
        self.dim_a = int(dim_a)
        self.dim_b = int(dim_b)
        self.latent_dim = int(latent_dim)
        self.top_k = int(top_k)
        if not 0 < self.top_k <= self.latent_dim:
            raise ValueError(f"top_k must be in [1, {self.latent_dim}]")

        self.encoder = nn.Linear(self.dim_a + self.dim_b, self.latent_dim)
        self.decoder_a = nn.Linear(self.latent_dim, self.dim_a)
        self.decoder_b = nn.Linear(self.latent_dim, self.dim_b)

        self.reset_parameters()

    def reset_parameters(self) -> None:
        nn.init.kaiming_uniform_(self.encoder.weight, a=math.sqrt(5))
        nn.init.zeros_(self.encoder.bias)

        nn.init.normal_(self.decoder_a.weight, mean=0.0, std=0.02)
        nn.init.normal_(self.decoder_b.weight, mean=0.0, std=0.02)
        nn.init.zeros_(self.decoder_a.bias)
        nn.init.zeros_(self.decoder_b.bias)

    def encode(self, x_a: torch.Tensor, x_b: torch.Tensor) -> torch.Tensor:
        x = torch.cat([x_a, x_b], dim=-1)
        dense = F.relu(self.encoder(x))
        values, indices = torch.topk(dense, k=self.top_k, dim=-1, sorted=False)
        return torch.zeros_like(dense).scatter(-1, indices, values)

    def forward(self, x_a: torch.Tensor, x_b: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        z = self.encode(x_a, x_b)
        rec_a = self.decoder_a(z)
        rec_b = self.decoder_b(z)
        return rec_a, rec_b, z

    @torch.no_grad()
    def normalize_decoder_features(self, eps: float = 1e-8) -> None:
        # Decoder weight shapes:
        # decoder_a.weight: [dim_a, latent_dim]
        # decoder_b.weight: [dim_b, latent_dim]
        wa = self.decoder_a.weight.data
        wb = self.decoder_b.weight.data

        norms = torch.sqrt((wa ** 2).sum(dim=0) + (wb ** 2).sum(dim=0) + eps)
        norms = torch.clamp(norms, min=eps)

        self.decoder_a.weight.data = wa / norms.unsqueeze(0)
        self.decoder_b.weight.data = wb / norms.unsqueeze(0)


def split_train_val(
    pairs: Sequence[Tuple[str, str, Path, Path]],
    val_frac: float,
    seed: int,
) -> Tuple[List[Tuple[str, str, Path, Path]], List[Tuple[str, str, Path, Path]]]:
    rng = random.Random(seed)
    pairs = list(pairs)
    groups = sorted({(bench, key.split("__gen_")[0]) for bench, key, _, _ in pairs})
    rng.shuffle(groups)
    n_val_groups = int(round(len(groups) * val_frac))
    n_val_groups = max(1, n_val_groups) if len(groups) >= 10 and val_frac > 0 else n_val_groups
    val_groups = set(groups[:n_val_groups])
    val = [p for p in pairs if (p[0], p[1].split("__gen_")[0]) in val_groups]
    train = [p for p in pairs if (p[0], p[1].split("__gen_")[0]) not in val_groups]

    if not train:
        train = pairs
        val = []

    return train, val


def infer_dims(pair: Tuple[str, str, Path, Path], layer_key: str) -> Tuple[int, int]:
    _, _, pa, pb = pair
    a = load_layer_array(pa, layer_key)
    b = load_layer_array(pb, layer_key)
    return int(a.shape[1]), int(b.shape[1])


def reconstruction_loss(
    x_a: torch.Tensor,
    x_b: torch.Tensor,
    rec_a: torch.Tensor,
    rec_b: torch.Tensor,
    normalize_loss: bool,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    mse_a = F.mse_loss(rec_a.float(), x_a.float())
    mse_b = F.mse_loss(rec_b.float(), x_b.float())

    if normalize_loss:
        denom_a = x_a.float().pow(2).mean().detach().clamp_min(1e-8)
        denom_b = x_b.float().pow(2).mean().detach().clamp_min(1e-8)
        mse_a_norm = mse_a / denom_a
        mse_b_norm = mse_b / denom_b
    else:
        mse_a_norm = mse_a
        mse_b_norm = mse_b

    return mse_a_norm + mse_b_norm, mse_a, mse_b


@torch.no_grad()
def evaluate(
    model: CrossCoder,
    batcher: ActivationPairBatcher,
    batches: int,
    normalize_loss: bool,
    l1_coef: float,
) -> Dict[str, float]:
    model.eval()

    total_loss = 0.0
    total_mse_a = 0.0
    total_mse_b = 0.0
    total_l1 = 0.0
    total_l0 = 0.0
    total_tokens = 0

    for _ in range(batches):
        x_a, x_b = batcher.next_batch()
        rec_a, rec_b, z = model(x_a, x_b)

        recon_norm, mse_a_raw, mse_b_raw = reconstruction_loss(x_a, x_b, rec_a, rec_b, normalize_loss)
        l1 = z.float().mean()
        loss = recon_norm + l1_coef * l1

        total_loss += float(loss.item()) * x_a.shape[0]
        total_mse_a += float(mse_a_raw.item()) * x_a.shape[0]
        total_mse_b += float(mse_b_raw.item()) * x_a.shape[0]
        total_l1 += float(l1.item()) * x_a.shape[0]
        total_l0 += float((z > 0).float().sum(dim=-1).mean().item()) * x_a.shape[0]
        total_tokens += int(x_a.shape[0])

    model.train()

    return {
        "val_loss": total_loss / max(total_tokens, 1),
        "val_mse_a_raw": total_mse_a / max(total_tokens, 1),
        "val_mse_b_raw": total_mse_b / max(total_tokens, 1),
        "val_l1": total_l1 / max(total_tokens, 1),
        "val_l0": total_l0 / max(total_tokens, 1),
    }


def save_checkpoint(
    output_dir: Path,
    model: CrossCoder,
    optimizer: torch.optim.Optimizer,
    step: int,
    config: TrainConfig,
    metrics: Dict[str, float],
    name: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / name

    payload = {
        "step": step,
        "config": asdict(config),
        "metrics": metrics,
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
    }
    torch.save(payload, path)
    return path


def append_metrics_csv(path: Path, row: Dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()

    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def main() -> None:
    args = parse_args()

    layer_key = canonical_layer_key(args.layer)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    if args.device.startswith("cuda") and torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    device = torch.device(args.device)

    dtype_map = {
        "float32": torch.float32,
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
    }
    dtype = dtype_map[args.dtype]

    config = TrainConfig(
        activation_root=args.activation_root,
        benchmarks=list(args.benchmarks),
        model_a=args.model_a,
        model_b=args.model_b,
        layer=layer_key,
        latent_dim=args.latent_dim,
        batch_size=args.batch_size,
        tokens_per_pair=args.tokens_per_pair,
        steps=args.steps,
        lr=args.lr,
        l1_coef=args.l1_coef,
        top_k=args.top_k,
        weight_decay=args.weight_decay,
        seed=args.seed,
        device=str(device),
        dtype=args.dtype,
        max_pairs=args.max_pairs,
        val_frac=args.val_frac,
        eval_every=args.eval_every,
        save_every=args.save_every,
        num_workers_note="This script intentionally uses a simple lazy single-process loader for NPZ files.",
        output_dir=str(output_dir),
        normalize_loss=not args.no_normalize_loss,
        decoder_unit_norm=not args.no_decoder_unit_norm,
        pairing_mode=args.pairing_mode,
    )

    (output_dir / "config.json").write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")

    activation_root = Path(args.activation_root)
    pairs = find_pairs(
        root=activation_root,
        benchmarks=args.benchmarks,
        model_a=args.model_a,
        model_b=args.model_b,
        max_pairs=args.max_pairs,
    )

    train_pairs, val_pairs = split_train_val(pairs, val_frac=args.val_frac, seed=args.seed)

    print(f"Total matched pairs: {len(pairs)}")
    print(f"Train pairs: {len(train_pairs)}")
    print(f"Val pairs: {len(val_pairs)}")
    print(f"Layer: {layer_key}")

    dim_a, dim_b = infer_dims(train_pairs[0], layer_key)
    print(f"Activation dims: {args.model_a}={dim_a}, {args.model_b}={dim_b}")

    model = CrossCoder(dim_a=dim_a, dim_b=dim_b, latent_dim=args.latent_dim, top_k=args.top_k).to(device=device)

    if dtype in {torch.float16, torch.bfloat16}:
        model = model.to(dtype=dtype)

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.lr,
        weight_decay=args.weight_decay,
    )

    train_batcher = ActivationPairBatcher(
        pairs=train_pairs,
        layer_key=layer_key,
        batch_size=args.batch_size,
        tokens_per_pair=args.tokens_per_pair,
        pairing_mode=args.pairing_mode,
        seed=args.seed + 1,
        dtype=dtype,
        device=device,
    )

    val_batcher = None
    if val_pairs:
        val_batcher = ActivationPairBatcher(
            pairs=val_pairs,
            layer_key=layer_key,
            batch_size=args.batch_size,
            tokens_per_pair=args.tokens_per_pair,
            pairing_mode=args.pairing_mode,
            seed=args.seed + 2,
            dtype=dtype,
            device=device,
        )

    metrics_csv = output_dir / "metrics.csv"

    print("Starting training...")
    start = time.time()

    model.train()

    for step in range(1, args.steps + 1):
        x_a, x_b = train_batcher.next_batch()

        rec_a, rec_b, z = model(x_a, x_b)

        recon_norm, mse_a_raw, mse_b_raw = reconstruction_loss(
            x_a=x_a,
            x_b=x_b,
            rec_a=rec_a,
            rec_b=rec_b,
            normalize_loss=not args.no_normalize_loss,
        )
        l1 = z.float().mean()
        loss = recon_norm + args.l1_coef * l1

        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()

        if not args.no_decoder_unit_norm:
            model.normalize_decoder_features()

        l0 = (z > 0).float().sum(dim=-1).mean()

        if step == 1 or step % 50 == 0:
            elapsed = time.time() - start
            print(
                f"step={step:06d} "
                f"loss={loss.item():.6f} "
                f"mse_a={mse_a_raw.item():.6f} "
                f"mse_b={mse_b_raw.item():.6f} "
                f"l1={l1.item():.6f} "
                f"l0={l0.item():.2f} "
                f"elapsed={elapsed/60:.1f}m",
                flush=True,
            )

        if val_batcher is not None and (step == 1 or step % args.eval_every == 0):
            val = evaluate(
                model=model,
                batcher=val_batcher,
                batches=10,
                normalize_loss=not args.no_normalize_loss,
                l1_coef=args.l1_coef,
            )
            row = {
                "step": step,
                "train_loss": float(loss.item()),
                "train_mse_a_raw": float(mse_a_raw.item()),
                "train_mse_b_raw": float(mse_b_raw.item()),
                "train_l1": float(l1.item()),
                "train_l0": float(l0.item()),
                **val,
                "elapsed_seconds": float(time.time() - start),
            }
            append_metrics_csv(metrics_csv, row)
            print("VAL", json.dumps(row, sort_keys=True), flush=True)

        if step % args.save_every == 0:
            ckpt = save_checkpoint(
                output_dir=output_dir,
                model=model,
                optimizer=optimizer,
                step=step,
                config=config,
                metrics={
                    "train_loss": float(loss.item()),
                    "train_mse_a_raw": float(mse_a_raw.item()),
                    "train_mse_b_raw": float(mse_b_raw.item()),
                    "train_l1": float(l1.item()),
                    "train_l0": float(l0.item()),
                },
                name=f"checkpoint_step_{step:06d}.pt",
            )
            print(f"Saved checkpoint: {ckpt}", flush=True)

    final_ckpt = save_checkpoint(
        output_dir=output_dir,
        model=model,
        optimizer=optimizer,
        step=args.steps,
        config=config,
        metrics={},
        name="final.pt",
    )
    print(f"Saved final checkpoint: {final_ckpt}")
    print(f"Metrics CSV: {metrics_csv}")
    print("Done.")


if __name__ == "__main__":
    main()
