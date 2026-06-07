#!/usr/bin/env python3
"""
Streaming CrossCoder training script.

This version does NOT preload all activation tokens into RAM.

Instead, every training batch is built on demand:
  1. choose paired activation files randomly
  2. download/load the .npz pair if needed
  3. sample random token positions inside those files
  4. build the batch and train

This makes it possible to train with all files and, over many steps,
sample broadly from all tokens without loading the full benchmark into memory.

Example smoke test:

python train_crosscoders_streaming.py \
  --benchmark bigcodebench \
  --base-model codellama_base \
  --target-model codellama_finetuned \
  --expansion-factor 8 \
  --batch-size 2 \
  --train-steps 30 \
  --max-files 20

Example larger streaming run over all files:

python train_crosscoders_streaming.py \
  --benchmark bigcodebench \
  --base-model codellama_base \
  --target-model codellama_finetuned \
  --expansion-factor 8 \
  --batch-size 2 \
  --train-steps 5000 \
  --max-files -1 \
  --array-cache-size 4 \
  --upload-to-gcs
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import os
import random
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# ============================================================
# CLI arguments
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train a tied CrossCoder from paired activation .npz files using streaming batches."
    )

    parser.add_argument(
        "--exp",
        type=str,
        default="full_table_6models_2benchmarks_layers_8_16_24_max512",
        help="Experiment folder name inside the GCS bucket.",
    )
    parser.add_argument(
        "--bucket-root",
        type=str,
        default="gs://YOUR_BUCKET/YOUR_PREFIX",
        help="Root GCS bucket path.",
    )
    parser.add_argument(
        "--benchmark",
        type=str,
        required=True,
        choices=["bigcodebench", "humanevalplus"],
        help="Benchmark name.",
    )
    parser.add_argument(
        "--base-model",
        type=str,
        required=True,
        help="Base model label inside selected_layer_activations.",
    )
    parser.add_argument(
        "--target-model",
        type=str,
        required=True,
        help="Target model label inside selected_layer_activations.",
    )
    parser.add_argument(
        "--layers",
        type=int,
        nargs="+",
        default=[8, 16, 24],
        help="Layer numbers to concatenate. Example: --layers 8 16 24.",
    )

    # Dataset / streaming controls
    parser.add_argument(
        "--max-files",
        type=int,
        default=-1,
        help="Maximum number of paired files to use. Use -1 for all paired files.",
    )
    parser.add_argument(
        "--array-cache-size",
        type=int,
        default=4,
        help=(
            "Number of paired activation arrays kept in RAM by the streaming sampler. "
            "Higher is faster but uses more RAM."
        ),
    )
    parser.add_argument(
        "--keep-local-cache",
        action="store_true",
        help=(
            "Keep downloaded .npz files in --cache-dir. Faster if rerunning, but can use lots of disk. "
            "By default files are deleted after loading arrays into RAM cache."
        ),
    )
    parser.add_argument(
        "--warmup-files",
        type=int,
        default=0,
        help="Optionally preload this many file pairs into the RAM array cache before training.",
    )

    # Training controls
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--train-steps", type=int, default=30)
    parser.add_argument(
        "--expansion-factor",
        type=int,
        default=8,
        help="latent_dim = input_dim * expansion_factor.",
    )
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--l1-coef", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument(
        "--optimizer",
        choices=["sgd"],
        default="sgd",
        help="SGD is used to keep memory low for very large tied CrossCoders.",
    )

    # IO controls
    parser.add_argument(
        "--cache-dir",
        type=str,
        default="/tmp/crosscoder_cache_streaming",
        help="Local temp cache directory for downloaded .npz activation files.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./crosscoder_outputs_streaming",
        help="Local output directory for checkpoints and metrics.",
    )
    parser.add_argument(
        "--save-checkpoint",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Save model checkpoint at end. Use --no-save-checkpoint for timing-only runs.",
    )
    parser.add_argument(
        "--upload-to-gcs",
        action="store_true",
        help="If set, upload the output folder to GCS after training.",
    )
    parser.add_argument(
        "--gcs-output-root",
        type=str,
        default=None,
        help="Optional GCS output root. If omitted, uses bucket-root/exp/crosscoder_training_streaming.",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=5,
        help="Print and store training metrics every N steps.",
    )

    return parser.parse_args()


# ============================================================
# Shell helpers
# ============================================================

def run_cmd(cmd: str) -> str:
    return subprocess.check_output(["bash", "-lc", cmd], text=True)


def gsutil_cp(uri: str, local_path: Path) -> None:
    if local_path.exists():
        return
    local_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(["gsutil", "cp", uri, str(local_path)], stdout=subprocess.DEVNULL)


def gsutil_rsync(local_dir: Path, gcs_dir: str) -> None:
    subprocess.check_call(["gsutil", "-m", "rsync", "-r", str(local_dir), gcs_dir])


# ============================================================
# Dataset helpers
# ============================================================

def task_key_from_name(name: str) -> Optional[Tuple[int, int]]:
    """
    Expected filename pattern:

      model__benchmark__task_0000__gen_00__BigCodeBench_0.npz

    Returns:
      (task_idx, generation_idx)
    """
    match = re.search(r"__task_(\d+)__gen_(\d+)__", name)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def list_npz_map(bucket: str, benchmark: str, model_label: str) -> Dict[Tuple[int, int], str]:
    path = f"{bucket}/selected_layer_activations/{benchmark}/{model_label}/*.npz"
    out = run_cmd(f"gsutil ls '{path}' 2>/dev/null | grep -v '\\.tmp\\.npz$' || true")
    mapping: Dict[Tuple[int, int], str] = {}

    for uri in out.splitlines():
        name = uri.rstrip("/").split("/")[-1]
        key = task_key_from_name(name)
        if key is not None:
            mapping[key] = uri

    return mapping


def layer_key(layer_number: int) -> str:
    return f"layer_{layer_number:02d}"


def load_concat_layers(npz_path: Path, layer_keys: List[str]) -> np.ndarray:
    z = np.load(npz_path, allow_pickle=True)
    arrays: List[np.ndarray] = []

    for key in layer_keys:
        if key not in z:
            raise KeyError(
                f"Layer key {key!r} not found in {npz_path}. "
                f"Available keys: {list(z.keys())}"
            )
        arrays.append(z[key].astype(np.float16, copy=False))

    return np.ascontiguousarray(np.concatenate(arrays, axis=1), dtype=np.float16)


def rms_normalize(x: torch.Tensor, eps: float = 1e-6) -> torch.Tensor:
    rms = torch.sqrt(torch.mean(x.float() ** 2, dim=-1, keepdim=True) + eps)
    return x / rms.to(x.dtype)


def numpy_to_torch_cpu(arr: np.ndarray) -> torch.Tensor:
    """
    Robust NumPy -> Torch conversion.

    Some torch/numpy ABI combinations can fail with torch.from_numpy even when
    the object is a numpy.ndarray. DLPack is a useful fallback.
    """
    arr = np.ascontiguousarray(arr, dtype=np.float16)
    try:
        return torch.from_numpy(arr)
    except TypeError as exc:
        print("torch.from_numpy failed, falling back to DLPack:", repr(exc))
        return torch.utils.dlpack.from_dlpack(arr)


class PairedActivationStreamer:
    """
    Random-access streaming sampler over paired activation files.

    It keeps a small LRU cache of loaded paired arrays in RAM:
      key -> (x_base_tokens, x_target_tokens)

    If --keep-local-cache is False, downloaded .npz files are deleted after
    loading arrays into the RAM cache. This keeps disk usage bounded.
    """

    def __init__(
        self,
        bucket: str,
        benchmark: str,
        base_model: str,
        target_model: str,
        layer_keys: List[str],
        cache_dir: Path,
        max_files: int = -1,
        array_cache_size: int = 4,
        keep_local_cache: bool = False,
        seed: int = 123,
    ):
        self.bucket = bucket
        self.benchmark = benchmark
        self.base_model = base_model
        self.target_model = target_model
        self.layer_keys = layer_keys
        self.cache_dir = cache_dir
        self.array_cache_size = int(max(array_cache_size, 0))
        self.keep_local_cache = keep_local_cache
        self.rng = random.Random(seed)

        print("Listing activation files from GCS...")
        self.base_map = list_npz_map(bucket, benchmark, base_model)
        self.target_map = list_npz_map(bucket, benchmark, target_model)

        common_keys = sorted(set(self.base_map) & set(self.target_map))
        if max_files is not None and max_files >= 0:
            common_keys = common_keys[:max_files]

        self.keys = common_keys
        self.array_cache: "collections.OrderedDict[Tuple[int, int], Tuple[np.ndarray, np.ndarray]]" = (
            collections.OrderedDict()
        )

        print("base files:", len(self.base_map))
        print("target files:", len(self.target_map))
        print("paired files:", len(set(self.base_map) & set(self.target_map)))
        print("using paired files:", len(self.keys))

        if not self.keys:
            raise RuntimeError("No paired activation files found.")

    def _local_paths(self, key: Tuple[int, int]) -> Tuple[Path, Path]:
        base_uri = self.base_map[key]
        target_uri = self.target_map[key]
        base_local = self.cache_dir / self.base_model / base_uri.split("/")[-1]
        target_local = self.cache_dir / self.target_model / target_uri.split("/")[-1]
        return base_local, target_local

    def _download_pair(self, key: Tuple[int, int]) -> Tuple[Path, Path]:
        base_uri = self.base_map[key]
        target_uri = self.target_map[key]
        base_local, target_local = self._local_paths(key)

        gsutil_cp(base_uri, base_local)
        gsutil_cp(target_uri, target_local)

        return base_local, target_local

    def _delete_local_pair(self, base_local: Path, target_local: Path) -> None:
        if self.keep_local_cache:
            return
        for path in [base_local, target_local]:
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    def load_pair_arrays(self, key: Tuple[int, int]) -> Tuple[np.ndarray, np.ndarray]:
        if key in self.array_cache:
            xb, xt = self.array_cache.pop(key)
            self.array_cache[key] = (xb, xt)
            return xb, xt

        base_local, target_local = self._download_pair(key)

        xb = load_concat_layers(base_local, self.layer_keys)
        xt = load_concat_layers(target_local, self.layer_keys)

        n = min(len(xb), len(xt))
        if n == 0:
            raise RuntimeError(f"Empty paired activation arrays for key={key}")

        xb = xb[:n]
        xt = xt[:n]

        self._delete_local_pair(base_local, target_local)

        if self.array_cache_size > 0:
            self.array_cache[key] = (xb, xt)
            while len(self.array_cache) > self.array_cache_size:
                self.array_cache.popitem(last=False)

        return xb, xt

    def sample_batch_np(self, batch_size: int) -> Tuple[np.ndarray, np.ndarray, List[Tuple[int, int]]]:
        xb_rows: List[np.ndarray] = []
        xt_rows: List[np.ndarray] = []
        sampled_keys: List[Tuple[int, int]] = []

        for _ in range(batch_size):
            # Retry a few times in case a pathological file is empty/corrupt.
            last_exc: Optional[Exception] = None
            for _attempt in range(5):
                key = self.rng.choice(self.keys)
                try:
                    xb_arr, xt_arr = self.load_pair_arrays(key)
                    n = min(len(xb_arr), len(xt_arr))
                    token_idx = self.rng.randrange(n)
                    xb_rows.append(xb_arr[token_idx])
                    xt_rows.append(xt_arr[token_idx])
                    sampled_keys.append(key)
                    last_exc = None
                    break
                except Exception as exc:
                    last_exc = exc
            if last_exc is not None:
                raise RuntimeError("Could not sample a valid activation pair") from last_exc

        xb_batch = np.ascontiguousarray(np.stack(xb_rows, axis=0), dtype=np.float16)
        xt_batch = np.ascontiguousarray(np.stack(xt_rows, axis=0), dtype=np.float16)
        return xb_batch, xt_batch, sampled_keys

    def warmup(self, n_files: int) -> None:
        if n_files <= 0 or self.array_cache_size <= 0:
            return
        n = min(n_files, len(self.keys))
        print(f"Warming RAM array cache with {n} paired files...")
        for i, key in enumerate(self.keys[:n], start=1):
            self.load_pair_arrays(key)
            print(f"  warmup [{i}/{n}] key={key}")


# ============================================================
# Model
# ============================================================

class TiedCrossCoder(nn.Module):
    """
    Tied CrossCoder.

    Encoder:
      z = relu(x_base @ D_base.T + x_target @ D_target.T + b_enc)

    Decoder:
      xhat_base = z @ D_base + b_base
      xhat_target = z @ D_target + b_target

    This tied version avoids separate encoder matrices and is much smaller
    than a fully untied CrossCoder.
    """

    def __init__(self, input_dim: int, latent_dim: int, dtype: torch.dtype = torch.float16):
        super().__init__()

        scale = 1.0 / math.sqrt(input_dim)

        self.D_base = nn.Parameter(torch.empty(latent_dim, input_dim, dtype=dtype))
        self.D_target = nn.Parameter(torch.empty(latent_dim, input_dim, dtype=dtype))
        self.b_enc = nn.Parameter(torch.zeros(latent_dim, dtype=dtype))
        self.b_base = nn.Parameter(torch.zeros(input_dim, dtype=dtype))
        self.b_target = nn.Parameter(torch.zeros(input_dim, dtype=dtype))

        nn.init.normal_(self.D_base, mean=0.0, std=scale)
        nn.init.normal_(self.D_target, mean=0.0, std=scale)

    def forward(self, xb: torch.Tensor, xt: torch.Tensor):
        z = F.relu(F.linear(xb, self.D_base) + F.linear(xt, self.D_target) + self.b_enc)
        xb_hat = F.linear(z, self.D_base.t(), self.b_base)
        xt_hat = F.linear(z, self.D_target.t(), self.b_target)
        return xb_hat, xt_hat, z


def estimate_tied_params(input_dim: int, latent_dim: int) -> int:
    return 2 * latent_dim * input_dim + latent_dim + 2 * input_dim


# ============================================================
# Training
# ============================================================

def main() -> None:
    args = parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    bucket = f"{args.bucket_root}/{args.exp}"
    layer_keys = [layer_key(layer) for layer in args.layers]

    run_name = (
        f"{args.benchmark}__"
        f"{args.target_model}_vs_{args.base_model}__"
        f"layers_{'_'.join(map(str, args.layers))}__"
        f"x{args.expansion_factor}__"
        f"streaming"
    )

    cache_dir = Path(args.cache_dir) / run_name
    output_dir = Path(args.output_dir) / run_name
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    print("=" * 80)
    print("Streaming CrossCoder training")
    print("=" * 80)
    print("run_name:", run_name)
    print("device:", device)
    if device == "cuda":
        print("gpu:", torch.cuda.get_device_name(0))
    print("bucket:", bucket)
    print("benchmark:", args.benchmark)
    print("base_model:", args.base_model)
    print("target_model:", args.target_model)
    print("layers:", layer_keys)
    print("max_files:", args.max_files)
    print("array_cache_size:", args.array_cache_size)
    print("keep_local_cache:", args.keep_local_cache)
    print()

    streamer = PairedActivationStreamer(
        bucket=bucket,
        benchmark=args.benchmark,
        base_model=args.base_model,
        target_model=args.target_model,
        layer_keys=layer_keys,
        cache_dir=cache_dir,
        max_files=args.max_files,
        array_cache_size=args.array_cache_size,
        keep_local_cache=args.keep_local_cache,
        seed=args.seed,
    )

    streamer.warmup(args.warmup_files)

    # Infer input_dim by sampling one batch.
    infer_start = time.perf_counter()
    xb0_np, xt0_np, keys0 = streamer.sample_batch_np(batch_size=1)
    infer_seconds = time.perf_counter() - infer_start

    input_dim = int(xb0_np.shape[1])
    latent_dim = input_dim * args.expansion_factor
    n_params = estimate_tied_params(input_dim, latent_dim)

    print()
    print("Inferred input_dim:", input_dim)
    print("latent_dim:", latent_dim)
    print("first_sample_key:", keys0[0])
    print("first_sample_seconds:", round(infer_seconds, 2))
    print("estimated parameters:", f"{n_params:,}")
    print("estimated fp16 weights:", f"{n_params * 2 / 1024**3:.2f} GiB")
    print("note: gradients add roughly another copy during training.")

    model = TiedCrossCoder(input_dim=input_dim, latent_dim=latent_dim, dtype=dtype).to(device)
    optimizer = torch.optim.SGD(model.parameters(), lr=args.lr)

    if device == "cuda":
        torch.cuda.empty_cache()
        print("cuda allocated after model:", round(torch.cuda.memory_allocated() / 1024**3, 2), "GiB")
        print("cuda reserved after model:", round(torch.cuda.memory_reserved() / 1024**3, 2), "GiB")

    metrics_path = output_dir / "metrics.jsonl"
    summary_path = output_dir / "summary.json"
    config_path = output_dir / "config.json"

    with config_path.open("w") as f:
        json.dump(vars(args), f, indent=2)

    print()
    print("Starting training...")

    train_start = time.perf_counter()
    history: List[dict] = []

    for step in range(1, args.train_steps + 1):
        if device == "cuda":
            torch.cuda.synchronize()
        step_start = time.perf_counter()

        xb_np, xt_np, sampled_keys = streamer.sample_batch_np(args.batch_size)

        xb = numpy_to_torch_cpu(xb_np).to(device, dtype=dtype, non_blocking=True)
        xt = numpy_to_torch_cpu(xt_np).to(device, dtype=dtype, non_blocking=True)

        xb = rms_normalize(xb)
        xt = rms_normalize(xt)

        optimizer.zero_grad(set_to_none=True)

        xb_hat, xt_hat, z = model(xb, xt)

        recon_loss = F.mse_loss(xb_hat.float(), xb.float()) + F.mse_loss(xt_hat.float(), xt.float())
        l1_loss = z.float().abs().mean()
        loss = recon_loss + args.l1_coef * l1_loss

        loss.backward()
        optimizer.step()

        if device == "cuda":
            torch.cuda.synchronize()
        step_seconds = time.perf_counter() - step_start

        metrics = {
            "step": step,
            "loss": float(loss.detach().cpu()),
            "recon_loss": float(recon_loss.detach().cpu()),
            "l1_loss": float(l1_loss.detach().cpu()),
            "step_seconds": float(step_seconds),
            "sampled_keys": sampled_keys,
        }

        if device == "cuda":
            metrics["cuda_allocated_gib"] = torch.cuda.memory_allocated() / 1024**3
            metrics["cuda_reserved_gib"] = torch.cuda.memory_reserved() / 1024**3

        history.append(metrics)

        if step == 1 or step % args.log_every == 0:
            with metrics_path.open("a") as f:
                f.write(json.dumps(metrics) + "\n")

            msg = (
                f"step={step:04d}/{args.train_steps} "
                f"loss={metrics['loss']:.6f} "
                f"recon={metrics['recon_loss']:.6f} "
                f"l1={metrics['l1_loss']:.6f} "
                f"step_s={metrics['step_seconds']:.3f}"
            )
            if device == "cuda":
                msg += (
                    f" | alloc={metrics['cuda_allocated_gib']:.2f}GiB"
                    f" reserved={metrics['cuda_reserved_gib']:.2f}GiB"
                )
            print(msg)

    train_seconds = time.perf_counter() - train_start

    checkpoint_path = output_dir / "model.pt"
    if args.save_checkpoint:
        torch.save(
            {
                "model_state_dict": model.state_dict(),
                "input_dim": input_dim,
                "latent_dim": latent_dim,
                "layer_keys": layer_keys,
                "base_model": args.base_model,
                "target_model": args.target_model,
                "benchmark": args.benchmark,
                "expansion_factor": args.expansion_factor,
                "tied": True,
                "streaming": True,
            },
            checkpoint_path,
        )

    summary = {
        "run_name": run_name,
        "benchmark": args.benchmark,
        "base_model": args.base_model,
        "target_model": args.target_model,
        "layers": args.layers,
        "layer_keys": layer_keys,
        "max_files": args.max_files,
        "array_cache_size": args.array_cache_size,
        "keep_local_cache": args.keep_local_cache,
        "batch_size": args.batch_size,
        "train_steps": args.train_steps,
        "expansion_factor": args.expansion_factor,
        "input_dim": input_dim,
        "latent_dim": latent_dim,
        "estimated_params": n_params,
        "train_seconds": train_seconds,
        "seconds_per_step": train_seconds / args.train_steps,
        "examples_per_second": (args.train_steps * args.batch_size) / train_seconds,
        "final_loss": history[-1]["loss"],
        "final_recon_loss": history[-1]["recon_loss"],
        "final_l1_loss": history[-1]["l1_loss"],
        "checkpoint_saved": bool(args.save_checkpoint),
        "checkpoint_path": str(checkpoint_path) if args.save_checkpoint else None,
        "metrics_path": str(metrics_path),
        "config_path": str(config_path),
    }

    with summary_path.open("w") as f:
        json.dump(summary, f, indent=2)

    print()
    print("=" * 80)
    print("DONE")
    print("=" * 80)
    print("output_dir:", output_dir)
    print("summary:", summary_path)
    print("metrics:", metrics_path)
    print("config:", config_path)
    if args.save_checkpoint:
        print("checkpoint:", checkpoint_path)
    print("train_steps:", args.train_steps)
    print("train_seconds:", round(train_seconds, 2))
    print("seconds_per_step:", round(train_seconds / args.train_steps, 3))
    print("examples_per_second:", round((args.train_steps * args.batch_size) / train_seconds, 3))
    print("final_loss:", history[-1]["loss"])

    if args.upload_to_gcs:
        if args.gcs_output_root:
            gcs_output_root = args.gcs_output_root
        else:
            gcs_output_root = f"{bucket}/crosscoder_training_streaming"
        gcs_output_dir = f"{gcs_output_root}/{run_name}"

        print()
        print("Uploading outputs to:", gcs_output_dir)
        gsutil_rsync(output_dir, gcs_output_dir)
        print("Upload finished.")


if __name__ == "__main__":
    main()
