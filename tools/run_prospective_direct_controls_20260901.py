#!/usr/bin/env python3
"""Prospective direct-only controls for the current focused top-5 features."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import time
from pathlib import Path

import numpy as np
import torch


REPO = Path("/home/lucas/crosscoder-recatcher-steering")
MAGS = [1, 2, 3, 4, 5]
CFG = {
    "deepseek": {
        "run": "runs/prospective_direct_controls_20260901_deepseek",
        "n": 80,
        "input": "runs/focused_subtype_dstk100_alpha3_canonical_v1/input.jsonl",
        "checkpoint": "runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt",
        "model_a": "deepseek-ai/deepseek-coder-6.7b-base",
        "model_b": "JetBrains/deepseek-coder-6.7B-kexer",
        "tokenizer": "deepseek-ai/deepseek-coder-6.7b-base",
        "side": "a",
        "backend": "paired_cached",
        "trust": True,
        "targets": {2468: -1, 2621: -1, 1078: 1, 14175: 1, 15235: -1},
        "screen_summary": "reports/focused_subtype_screening_dstk100_contamination_v1/run_summary.json",
        "random_seed": 2026090101,
        "sham_seeds": [2026090111, 2026090112, 2026090113],
    },
    "codellama": {
        "run": "runs/prospective_direct_controls_20260901_codellama",
        "n": 50,
        "input": "runs/focused_subtype_codellama_alpha3_canonical_v1/input.jsonl",
        "checkpoint": "runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt",
        "model_a": "meta-llama/CodeLlama-7b-hf",
        "model_b": "DevQuasar-5/coma-7B-v0.1",
        "tokenizer": "meta-llama/CodeLlama-7b-hf",
        "side": "b",
        "backend": "hf_generate",
        "trust": False,
        "targets": {4309: -1, 5642: -1, 7692: -1, 10818: -1, 11596: -1},
        "screen_summary": "reports/focused_subtype_screening_codellama_wrong_logic_v1/run_summary.json",
        "random_seed": 2026090102,
        "sham_seeds": [2026090121, 2026090122, 2026090123],
    },
}


def line_count(path: Path) -> int:
    return sum(1 for _ in path.open()) if path.exists() else -1


def load_rows(path: Path, expected: int):
    rows = [json.loads(line) for line in path.open()]
    assert len(rows) == expected
    assert all(int(r["seed"]) == 1000 + 100 * int(r["task_idx"]) for r in rows)
    return rows


def exclusions(c):
    excluded = set(c["targets"])
    summary = json.loads(Path(c["screen_summary"]).read_text())
    for cell in summary["cells"]:
        excluded.update(cell["top10"])
    # Exclude every latent that has already appeared in a generated steering arm.
    pattern = re.compile(r"f(\d+)(?:_|\b)")
    for path in Path("runs").glob("**/*.jsonl"):
        match = pattern.search(path.name)
        if match:
            excluded.add(int(match.group(1)))
    return excluded


def prepare(family, c, rows):
    run = Path(c["run"])
    for name in ("generations", "logs", "controls"):
        (run / name).mkdir(parents=True, exist_ok=True)
    manifest_path = run / "EXPERIMENT_MANIFEST.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        random_features = {int(k): int(v) for k, v in manifest["random_latents"].items()}
    else:
        excluded = exclusions(c)
        rng = random.Random(c["random_seed"])
        candidates = [fid for fid in range(16384) if fid not in excluded]
        selected = rng.sample(candidates, 3)
        random_features = {fid: rng.choice([-1, 1]) for fid in selected}
        manifest = {
            "experiment": "prospective_direct_controls",
            "version": "2026-09-01_v1",
            "family": family,
            "status": "preregistered_before_generation",
            "scope": "direct only; no inverse arms",
            "cohort_input": c["input"],
            "cohort_size": c["n"],
            "seed_rule": "1000 + 100 * task_idx",
            "generation": {
                "temperature": 0.2,
                "top_p": 0.95,
                "max_new_tokens": 512,
                "dtype": "nf4",
                "backend": c["backend"],
            },
            "intervention": {
                "layer": 16,
                "mode": "traditional",
                "token_scope": "last_token",
                "target_side": c["side"],
                "magnitudes": MAGS,
            },
            "current_top5_and_predicted_sign": c["targets"],
            "random_seed": c["random_seed"],
            "random_latents": random_features,
            "random_selection": (
                "uniform feature IDs sampled before outcomes; excludes current targets, "
                "focused top-10 nomination pool, and every feature ID found in prior generation filenames"
            ),
            "shams": [
                {
                    "id": i,
                    "seed": seed,
                    "construction": (
                        "Gaussian direction orthogonal to exact current top-5 decoder span on direct side; "
                        "scaled to median top-5 decoder norm"
                    ),
                }
                for i, seed in enumerate(c["sham_seeds"], 1)
            ],
            "gate": "fresh alpha=0 must reproduce all input raw completions byte-for-byte",
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    state = torch.load(c["checkpoint"], map_location="cpu", weights_only=False)["model_state_dict"]
    decoder = state[f"decoder_{c['side']}.weight"].float()
    target_matrix = torch.stack([decoder[:, fid] for fid in c["targets"]], dim=1)
    q = torch.linalg.qr(target_matrix, mode="reduced").Q
    median_norm = torch.median(torch.linalg.vector_norm(target_matrix, dim=0))
    task_ids = np.asarray([r["task_id"] for r in rows])
    sham_paths = []
    sham_audit = []
    for index, seed in enumerate(c["sham_seeds"], 1):
        generator = torch.Generator().manual_seed(seed)
        vector = torch.randn(target_matrix.shape[0], generator=generator)
        vector = vector - q @ (q.T @ vector)
        vector = vector / vector.norm() * median_norm
        path = run / "controls" / f"sham{index}_{c['side']}.npz"
        np.savez(path, task_ids=task_ids,
                 directions=vector.numpy()[None, :].repeat(len(rows), axis=0))
        sham_paths.append(path)
        sham_audit.append({
            "id": index,
            "seed": seed,
            "norm": float(vector.norm()),
            "max_abs_cosine_to_targets": float(torch.max(torch.abs(
                (target_matrix.T @ vector) /
                (torch.linalg.vector_norm(target_matrix, dim=0) * vector.norm())
            ))),
        })
    (run / "controls" / "SHAM_GEOMETRY_AUDIT.json").write_text(
        json.dumps({"median_target_norm": float(median_norm), "shams": sham_audit}, indent=2) + "\n"
    )
    return run, random_features, sham_paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", choices=CFG, required=True)
    parser.add_argument("--gpu", required=True)
    parser.add_argument("--worker-index", type=int, default=0)
    parser.add_argument("--num-workers", type=int, default=1)
    args = parser.parse_args()
    assert 0 <= args.worker_index < args.num_workers
    os.chdir(REPO)
    c = CFG[args.family]
    rows = load_rows(Path(c["input"]), c["n"])
    run, random_features, sham_paths = prepare(args.family, c, rows)

    common = [
        ".venv/bin/python", "tools/run_crosscoder_intervention.py",
        "--checkpoint", c["checkpoint"],
        "--model-a-id", c["model_a"], "--model-b-id", c["model_b"],
        "--tokenizer-id", c["tokenizer"], "--target-side", c["side"],
        "--layer", "16", "--intervention-mode", "traditional",
        "--token-scope", "last_token", "--generation-backend", c["backend"],
        "--input-jsonl", c["input"], "--max-new-tokens", "512",
        "--temperature", "0.2", "--top-p", "0.95", "--seed", "1000",
        f"--device-{c['side']}", f"cuda:{args.gpu}", "--dtype", "nf4",
    ]
    if c["trust"]:
        common.append("--trust-remote-code")

    def generate(name, fid, alpha, extra=()):
        output = run / "generations" / f"bigcodebench__{name}_results.jsonl"
        if line_count(output) == c["n"]:
            return output
        command = [*common, "--feature-id", str(fid), "--alpha", str(alpha),
                   "--output-jsonl", str(output), *extra]
        with (run / "logs" / f"{name}.log").open("w") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        assert line_count(output) == c["n"]
        return output

    # Worker zero owns the unique gate; other shards wait for it.
    gate_path = run / "ALPHA0_GATE.json"
    if args.worker_index == 0:
        baseline = generate("baseline_alpha0", 0, 0)
        generated = [json.loads(line) for line in baseline.open()]
        exact = sum(a["raw_completion"] == b["raw_completion"] for a, b in zip(rows, generated))
        gate = {"expected": c["n"], "byte_exact": exact, "passed": exact == c["n"]}
        gate_path.write_text(json.dumps(gate, indent=2) + "\n")
    else:
        while not gate_path.exists():
            time.sleep(5)
        gate = json.loads(gate_path.read_text())
    if not gate["passed"]:
        raise RuntimeError(f"alpha=0 gate failed: {gate['byte_exact']}/{c['n']} byte-exact")

    arms = []
    for fid, sign in random_features.items():
        for magnitude in MAGS:
            arms.append((f"random_f{fid}_{sign*magnitude:+d}", fid, sign * magnitude, ()))
    for index, sham_path in enumerate(sham_paths, 1):
        for magnitude in MAGS:
            arms.append((
                f"sham{index}_{magnitude:+d}", 0, magnitude,
                ("--per-example-direction-npz", str(sham_path),
                 "--preserve-per-example-direction-norm"),
            ))
    for arm_index, (name, fid, alpha, extra) in enumerate(arms):
        if arm_index % args.num_workers == args.worker_index:
            generate(name, fid, alpha, extra)
    (run / f"WORKER_{args.worker_index}_COMPLETE").touch()
    if all((run / f"WORKER_{i}_COMPLETE").exists() for i in range(args.num_workers)):
        (run / "GENERATIONS_COMPLETE").touch()


if __name__ == "__main__":
    main()
