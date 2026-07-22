from pathlib import Path
import sys
import csv
import json
import subprocess

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from crosscoder_common import derive_legacy_evaluated_token_mask, load_evaluated_token_mask
from run_roc_auc_feature_screening import (
    auc_from_ranks,
    permutation_statistics,
    rank_columns,
)


def test_auc_is_tie_aware_and_failure_is_positive():
    values = np.array([[0.0], [1.0], [1.0], [2.0]], dtype=np.float32)
    labels = np.array([0, 0, 1, 1], dtype=np.int8)
    auc = auc_from_ranks(rank_columns(values), labels)
    assert auc[0] == pytest.approx(0.875)


def test_batched_permutations_match_scalar_reference(tmp_path):
    values = np.array(
        [[0, 3], [1, 2], [1, 1], [2, 0]], dtype=np.float32
    )
    labels = np.array([0, 0, 1, 1], dtype=np.int8)
    ranks = rank_columns(values)
    observed = auc_from_ranks(ranks, labels)
    actual = permutation_statistics(ranks, labels, observed, 7, 123, tmp_path)
    rng = np.random.default_rng(123)
    null = np.stack(
        [auc_from_ranks(ranks, rng.permutation(labels)) for _ in range(7)]
    )
    np.testing.assert_allclose(actual[0], null.mean(axis=0), atol=1e-7)
    np.testing.assert_allclose(actual[1], null.std(axis=0), atol=1e-7)


def test_legacy_activation_without_exact_mask_is_rejected(tmp_path):
    path = tmp_path / "legacy.npz"
    np.savez(path, input_ids=np.arange(3), layer_16=np.zeros((3, 2)))
    with pytest.raises(KeyError, match="exact evaluated-token alignment"):
        load_evaluated_token_mask(path, 3)


def test_mask_must_align_with_activation_rows(tmp_path):
    path = tmp_path / "bad.npz"
    np.savez(
        path,
        input_ids=np.arange(3),
        layer_16=np.zeros((3, 2)),
        evaluated_token_mask=np.ones(2, dtype=bool),
        token_char_spans=np.zeros((3, 2), dtype=np.int64),
    )
    with pytest.raises(ValueError, match="does not match activation rows"):
        load_evaluated_token_mask(path, 3)


class CharacterTokenizer:
    def __call__(self, text, **kwargs):
        limit = kwargs.get("max_length", len(text))
        text = text[:limit]
        return {
            "input_ids": [ord(char) for char in text],
            "offset_mapping": [(i, i + 1) for i in range(len(text))],
        }


def test_legacy_mask_is_derived_only_from_id_verified_raw_text(tmp_path):
    prompt = "def f():\n"
    completion = "    return 1\nEXPLANATION"
    full = prompt.rstrip() + "\n" + completion.rstrip() + "\n"
    path = tmp_path / "legacy.npz"
    np.savez(path, input_ids=np.array([ord(c) for c in full]))
    rows = len(completion.rstrip() + "\n")
    mask, provenance = derive_legacy_evaluated_token_mask(
        path,
        rows,
        {"prompt": prompt, "raw_completion": completion},
        {"candidate_code_original": prompt.rstrip() + "\n    return 1\n"},
        CharacterTokenizer(),
    )
    assert mask.sum() == len("    return 1")
    assert provenance["stored_id_equality"] is True
    assert provenance["literal_prefix"] is True


def test_legacy_mask_rejects_token_id_mismatch(tmp_path):
    path = tmp_path / "legacy.npz"
    np.savez(path, input_ids=np.array([999]))
    with pytest.raises(ValueError, match="stored-ID equality"):
        derive_legacy_evaluated_token_mask(
            path, 1, {"prompt": "", "raw_completion": "x"},
            {"candidate_code_original": "x"}, CharacterTokenizer(),
        )


def test_end_to_end_smoke_outputs(tmp_path):
    if not hasattr(torch, "tensor"):
        pytest.skip("end-to-end fixture requires the analysis environment with PyTorch")
    activations = tmp_path / "activations" / "humanevalplus"
    checkpoints = tmp_path / "checkpoints" / "toy_cc"
    activations.mkdir(parents=True)
    checkpoints.mkdir(parents=True)
    manifest = {
        "benchmarks": {"humanevalplus": {"expected_tasks": 4}},
        "crosscoder_contract": {"layer": "layer_16"},
        "crosscoders": [{"id": "toy_cc", "model_a": "toy_base", "model_b": "toy_tuned"}],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    labels_path = tmp_path / "labels.csv"
    with labels_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["model", "benchmark", "task_id", "generation_idx", "label"])
        writer.writeheader()
        for model in ("toy_base", "toy_tuned"):
            for task in range(4):
                writer.writerow({"model": model, "benchmark": "humanevalplus", "task_id": f"HumanEval/{task}", "generation_idx": 0, "label": task % 2})
    state = {
        "encoder.weight": torch.tensor([[1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.]]),
        "encoder.bias": torch.zeros(3),
    }
    torch.save({"model_state_dict": state, "config": {}}, checkpoints / "final.pt")
    for model in ("toy_base", "toy_tuned"):
        model_dir = activations / model
        model_dir.mkdir()
        for task in range(4):
            array = np.array([[task, 1.], [task + 1., 0.]], dtype=np.float32)
            np.savez(
                model_dir / f"{model}__humanevalplus__task_{task:04d}__gen_00__x.npz",
                input_ids=np.array([10, 11]), layer_16=array,
                evaluated_token_mask=np.array([True, True]),
                token_char_spans=np.array([[0, 1], [1, 2]]),
            )
    output = tmp_path / "report"
    script = Path(__file__).resolve().parents[1] / "tools" / "run_roc_auc_feature_screening.py"
    subprocess.run([
        sys.executable, str(script), "--manifest", str(manifest_path),
        "--activation-root", str(tmp_path / "activations"),
        "--checkpoint-root", str(tmp_path / "checkpoints"),
        "--labels-csv", str(labels_path), "--output-root", str(output),
        "--smoke-test",
    ], check=True)
    assert (output / "index.md").exists()
    assert len(list(output.glob("*/feature_statistics.csv"))) == 2
    assert len(list(output.glob("*/ranked_roc_auc_permutation_envelope.png"))) == 2
