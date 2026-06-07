#!/usr/bin/env python3

"""
Reusable CrossCoder training script.

Example usage:

python train_crosscoders.py \
  --benchmark bigcodebench \
  --base-model codellama_base \
  --target-model codellama_finetuned \
  --expansion-factor 8 \
  --max-files 20 \
  --tokens-per-file 16 \
  --batch-size 2 \
  --train-steps 30

To run a larger experiment, increase:
  --max-files
  --tokens-per-file
  --train-steps
"""

import os
import re
import json
import time
import math
import random
import argparse
import subprocess
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# ============================================================
# CLI arguments
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser()

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
        help="Layer numbers to concatenate.",
    )

    parser.add_argument(
        "--max-files",
        type=int,
        default=20,
        help="Maximum number of paired activation files to use.",
    )

    parser.add_argument(
        "--tokens-per-file",
        type=int,
        default=16,
        help="Number of random token positions sampled from each paired file.",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=2,
        help="Training batch size.",
    )

    parser.add_argument(
        "--train-steps",
        type=int,
        default=30,
        help="Number of training steps.",
    )

    parser.add_argument(
        "--expansion-factor",
        type=int,
        default=8,
        help="Latent dimension multiplier. latent_dim = input_dim * expansion_factor.",
    )

    parser.add_argument(
        "--lr",
        type=float,
        default=1e-3,
        help="Learning rate.",
    )

    parser.add_argument(
        "--l1-coef",
        type=float,
        default=1e-4,
        help="L1 sparsity coefficient.",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=123,
        help="Random seed.",
    )

    parser.add_argument(
        "--cache-dir",
        type=str,
        default="/tmp/crosscoder_cache",
        help="Local cache directory for downloaded .npz activation files.",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="./crosscoder_outputs",
        help="Local output directory for checkpoints and metrics.",
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
        help="Optional GCS output root. If omitted, uses bucket-root/exp/crosscoder_training.",
    )

    return parser.parse_args()


# ============================================================
# Shell helpers
# ============================================================

def run_cmd(cmd: str) -> str:
    return subprocess.check_output(["bash", "-lc", cmd], text=True)


def gsutil_cp(uri: str, local_path: Path):
    if local_path.exists():
        return

    local_path.parent.mkdir(parents=True, exist_ok=True)

    subprocess.check_call(
        ["gsutil", "cp", uri, str(local_path)],
        stdout=subprocess.DEVNULL,
    )


def gsutil_rsync(local_dir: Path, gcs_dir: str):
    subprocess.check_call(
        ["gsutil", "-m", "rsync", "-r", str(local_dir), gcs_dir]
    )


# ============================================================
# Dataset helpers
# ============================================================

def task_key_from_name(name: str):
    """
    Expected filename pattern:

    model__benchmark__task_0000__gen_00__BigCodeBench_0.npz

    Returns:
      (task_id, generation_id)
    """
    match = re.search(r"__task_(\d+)__gen_(\d+)__", name)

    if not match:
        return None

    return int(match.group(1)), int(match.group(2))


def list_npz_map(bucket: str, benchmark: str, model_label: str):
    path = f"{bucket}/selected_layer_activations/{benchmark}/{model_label}/*.npz"

    out = run_cmd(
        f"gsutil ls '{path}' 2>/dev/null | grep -v '\\.tmp\\.npz$' || true"
    )

    mapping = {}

    for uri in out.splitlines():
        name = uri.rstrip("/").split("/")[-1]
        key = task_key_from_name(name)

        if key is not None:
            mapping[key] = uri

    return mapping


def layer_key(layer_number: int) -> str:
    return f"layer_{layer_number:02d}"


def load_concat_layers(npz_path: Path, layer_keys):
    z = np.load(npz_path, allow_pickle=True)

    arrays = []

    for key in layer_keys:
        if key not in z:
            raise KeyError(
                f"Layer key {key!r} not found in {npz_path}. "
                f"Available keys: {list(z.keys())}"
            )

        arr = z[key].astype(np.float16)
        arrays.append(arr)

    return np.concatenate(arrays, axis=1)


def rms_normalize(x, eps=1e-6):
    rms = torch.sqrt(torch.mean(x.float() ** 2, dim=-1, keepdim=True) + eps)
    return x / rms.to(x.dtype)


# ============================================================
# Model
# ============================================================

class TiedCrossCoder(nn.Module):
    """
    Tied CrossCoder.

    Encoder:

      z = relu(
          x_base @ D_base.T
        + x_target @ D_target.T
        + b_enc
      )

    Decoder:

      xhat_base = z @ D_base + b_base
      xhat_target = z @ D_target + b_target

    This tied version avoids separate encoder matrices and is much smaller
    than a fully untied CrossCoder.
    """

    def __init__(self, input_dim: int, latent_dim: int, dtype=torch.float16):
        super().__init__()

        scale = 1.0 / math.sqrt(input_dim)

        self.D_base = nn.Parameter(
            torch.empty(latent_dim, input_dim, dtype=dtype)
        )

        self.D_target = nn.Parameter(
            torch.empty(latent_dim, input_dim, dtype=dtype)
        )

        self.b_enc = nn.Parameter(
            torch.zeros(latent_dim, dtype=dtype)
        )

        self.b_base = nn.Parameter(
            torch.zeros(input_dim, dtype=dtype)
        )

        self.b_target = nn.Parameter(
            torch.zeros(input_dim, dtype=dtype)
        )

        nn.init.normal_(self.D_base, mean=0.0, std=scale)
        nn.init.normal_(self.D_target, mean=0.0, std=scale)

    def forward(self, xb, xt):
        z = F.relu(
            F.linear(xb, self.D_base)
            + F.linear(xt, self.D_target)
            + self.b_enc
        )

        xb_hat = F.linear(z, self.D_base.t(), self.b_base)
        xt_hat = F.linear(z, self.D_target.t(), self.b_target)

        return xb_hat, xt_hat, z


def estimate_tied_params(input_dim: int, latent_dim: int):
    return 2 * latent_dim * input_dim + latent_dim + 2 * input_dim


# ============================================================
# Training
# ============================================================

def main():
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
        f"x{args.expansion_factor}"
    )

    cache_dir = Path(args.cache_dir) / run_name
    output_dir = Path(args.output_dir) / run_name

    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    print("=" * 80)
    print("CrossCoder training")
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
    print()

    # ------------------------------------------------------------
    # List paired files
    # ------------------------------------------------------------

    print("Listing activation files from GCS...")

    base_map = list_npz_map(bucket, args.benchmark, args.base_model)
    target_map = list_npz_map(bucket, args.benchmark, args.target_model)

    common_keys = sorted(set(base_map) & set(target_map))
    selected_keys = common_keys[: args.max_files]

    print("base files:", len(base_map))
    print("target files:", len(target_map))
    print("paired files:", len(common_keys))
    print("using paired files:", len(selected_keys))
    print()

    if not selected_keys:
        raise RuntimeError("No paired activation files found.")

    # ------------------------------------------------------------
    # Download and build token dataset
    # ------------------------------------------------------------

    base_tokens = []
    target_tokens = []

    download_start = time.perf_counter()

    for i, key in enumerate(selected_keys, start=1):
        base_uri = base_map[key]
        target_uri = target_map[key]

        base_local = cache_dir / args.base_model / base_uri.split("/")[-1]
        target_local = cache_dir / args.target_model / target_uri.split("/")[-1]

        gsutil_cp(base_uri, base_local)
        gsutil_cp(target_uri, target_local)

        xb = load_concat_layers(base_local, layer_keys)
        xt = load_concat_layers(target_local, layer_keys)

        n = min(len(xb), len(xt))

        if n == 0:
            continue

        sample_n = min(args.tokens_per_file, n)
        idx = np.random.choice(n, size=sample_n, replace=False)

        base_tokens.append(xb[idx])
        target_tokens.append(xt[idx])

        print(f"[{i}/{len(selected_keys)}] key={key} tokens={sample_n}")

    download_seconds = time.perf_counter() - download_start

    if not base_tokens or not target_tokens:
        raise RuntimeError("No token data was loaded.")

    x_base_np = np.concatenate(base_tokens, axis=0)
    x_target_np = np.concatenate(target_tokens, axis=0)

    assert x_base_np.shape == x_target_np.shape

    num_examples, input_dim = x_base_np.shape
    latent_dim = input_dim * args.expansion_factor

    print()
    print("dataset tokens:", num_examples)
    print("input_dim:", input_dim)
    print("latent_dim:", latent_dim)
    print("download/load seconds:", round(download_seconds, 2))

    x_base = torch.from_numpy(x_base_np)
    x_target = torch.from_numpy(x_target_np)

    # ------------------------------------------------------------
    # Create model
    # ------------------------------------------------------------

    n_params = estimate_tied_params(input_dim, latent_dim)

    print()
    print("estimated parameters:", f"{n_params:,}")
    print("estimated fp16 weights:", f"{n_params * 2 / 1024**3:.2f} GiB")
    print("note: gradients add roughly another copy during training.")

    model = TiedCrossCoder(
        input_dim=input_dim,
        latent_dim=latent_dim,
        dtype=dtype,
    ).to(device)

    # SGD keeps memory much lower than Adam.
    optimizer = torch.optim.SGD(model.parameters(), lr=args.lr)

    if device == "cuda":
        torch.cuda.empty_cache()
        print(
            "cuda allocated after model:",
            round(torch.cuda.memory_allocated() / 1024**3, 2),
            "GiB",
        )
        print(
            "cuda reserved after model:",
            round(torch.cuda.memory_reserved() / 1024**3, 2),
            "GiB",
        )

    # ------------------------------------------------------------
    # Training loop
    # ------------------------------------------------------------

    def sample_batch():
        idx = torch.randint(0, num_examples, (args.batch_size,))

        xb = x_base[idx].to(device, dtype=dtype, non_blocking=True)
        xt = x_target[idx].to(device, dtype=dtype, non_blocking=True)

        xb = rms_normalize(xb)
        xt = rms_normalize(xt)

        return xb, xt

    print()
    print("Starting training...")

    train_start = time.perf_counter()
    loss_history = []

    for step in range(1, args.train_steps + 1):
        step_start = time.perf_counter()

        xb, xt = sample_batch()

        optimizer.zero_grad(set_to_none=True)

        xb_hat, xt_hat, z = model(xb, xt)

        recon_loss = (
            F.mse_loss(xb_hat.float(), xb.float())
            + F.mse_loss(xt_hat.float(), xt.float())
        )

        l1_loss = z.float().abs().mean()
        loss = recon_loss + args.l1_coef * l1_loss

        loss.backward()
        optimizer.step()

        step_seconds = time.perf_counter() - step_start

        metrics = {
            "step": step,
            "loss": float(loss.detach().cpu()),
            "recon_loss": float(recon_loss.detach().cpu()),
            "l1_loss": float(l1_loss.detach().cpu()),
            "step_seconds": step_seconds,
        }

        if device == "cuda":
            metrics["cuda_allocated_gib"] = (
                torch.cuda.memory_allocated() / 1024**3
            )
            metrics["cuda_reserved_gib"] = (
                torch.cuda.memory_reserved() / 1024**3
            )

        loss_history.append(metrics)

        if step == 1 or step % 5 == 0:
            msg = (
                f"step={step:04d}/{args.train_steps} "
                f"loss={metrics['loss']:.6f} "
                f"recon={metrics['recon_loss']:.6f} "
                f"l1={metrics['l1_loss']:.6f} "
                f"step_s={metrics['step_seconds']:.2f}"
            )

            if device == "cuda":
                msg += (
                    f" | alloc={metrics['cuda_allocated_gib']:.2f}GiB"
                    f" reserved={metrics['cuda_reserved_gib']:.2f}GiB"
                )

            print(msg)

    train_seconds = time.perf_counter() - train_start

    # ------------------------------------------------------------
    # Save outputs
    # ------------------------------------------------------------

    checkpoint_path = output_dir / "model.pt"
    metrics_path = output_dir / "metrics.json"
    config_path = output_dir / "config.json"

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
        "tokens_per_file": args.tokens_per_file,
        "batch_size": args.batch_size,
        "train_steps": args.train_steps,
        "expansion_factor": args.expansion_factor,
        "input_dim": input_dim,
        "latent_dim": latent_dim,
        "num_examples": num_examples,
        "estimated_params": n_params,
        "download_seconds": download_seconds,
        "train_seconds": train_seconds,
        "seconds_per_step": train_seconds / args.train_steps,
        "examples_per_second": (
            args.train_steps * args.batch_size
        ) / train_seconds,
        "final_loss": loss_history[-1]["loss"],
    }

    with open(metrics_path, "w") as f:
        json.dump(
            {
                "summary": summary,
                "history": loss_history,
            },
            f,
            indent=2,
        )

    with open(config_path, "w") as f:
        json.dump(vars(args), f, indent=2)

    print()
    print("=" * 80)
    print("DONE")
    print("=" * 80)
    print("checkpoint:", checkpoint_path)
    print("metrics:", metrics_path)
    print("config:", config_path)
    print()
    print("train_steps:", args.train_steps)
    print("train_seconds:", round(train_seconds, 2))
    print("seconds_per_step:", round(train_seconds / args.train_steps, 3))
    print(
        "examples_per_second:",
        round((args.train_steps * args.batch_size) / train_seconds, 3),
    )
    print("final_loss:", loss_history[-1]["loss"])

    # ------------------------------------------------------------
    # Optional GCS upload
    # ------------------------------------------------------------

    if args.upload_to_gcs:
        if args.gcs_output_root:
            gcs_output_root = args.gcs_output_root
        else:
            gcs_output_root = f"{bucket}/crosscoder_training"

        gcs_output_dir = f"{gcs_output_root}/{run_name}"

        print()
        print("Uploading outputs to:", gcs_output_dir)
        gsutil_rsync(output_dir, gcs_output_dir)
        print("Upload finished.")


if __name__ == "__main__":
    main()
