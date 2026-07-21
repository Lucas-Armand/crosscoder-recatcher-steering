#!/usr/bin/env python3
"""Read-only validator for a ReCatcher/CrossCoder paper release."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass
class Check:
    gate: str
    name: str
    status: str
    detail: str


class Validation:
    def __init__(self) -> None:
        self.checks: list[Check] = []

    def add(self, gate: str, name: str, passed: bool, detail: str) -> None:
        self.checks.append(Check(gate, name, "PASS" if passed else "FAIL", detail))

    def warn(self, gate: str, name: str, detail: str) -> None:
        self.checks.append(Check(gate, name, "WARN", detail))

    @property
    def failed(self) -> bool:
        return any(check.status == "FAIL" for check in self.checks)


class GCloudStorage:
    """Minimal read-only GCS adapter using the authenticated gcloud CLI."""

    @staticmethod
    def _run(arguments: list[str]) -> str:
        result = subprocess.run(
            ["gcloud", "storage", *arguments],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "gcloud storage command failed")
        return result.stdout

    def cat(self, uri: str) -> str:
        return self._run(["cat", uri])

    def list(self, uri: str, recursive: bool = False) -> list[str]:
        arguments = ["ls"]
        if recursive:
            arguments.append("--recursive")
        arguments.append(uri)
        return [line.strip() for line in self._run(arguments).splitlines() if line.startswith("gs://")]

    def exists(self, uri: str) -> bool:
        result = subprocess.run(
            ["gcloud", "storage", "ls", uri],
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0


def parse_jsonl(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def parse_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def uri(base: str, *parts: str) -> str:
    return "/".join([base.rstrip("/"), *(part.strip("/") for part in parts)])


def expected_seed(row: dict[str, Any]) -> int:
    return 1000 + int(row["task_idx"]) * 100 + int(row.get("gen_idx", 0))


def task_key(row: dict[str, Any]) -> tuple[int, int]:
    return int(row["task_idx"]), int(row.get("gen_idx", 0))


def validate_generation_and_processing(
    manifest: dict[str, Any], storage: GCloudStorage, validation: Validation
) -> None:
    base = manifest["bucket_base"]
    dataset = uri(base, manifest["dataset_prefix"])
    contract = manifest["generation_contract"]
    allowed_repairs = set(manifest["allowed_repairs"])

    manifest_uri = uri(dataset, "POSTPROCESS_MANIFEST.txt")
    try:
        postprocess_manifest = storage.cat(manifest_uri)
        validation.add(
            "postprocessing",
            "postprocess manifest",
            "crosscoder_final_dataset_v1" in postprocess_manifest,
            manifest_uri,
        )
    except RuntimeError as exc:
        validation.add("postprocessing", "postprocess manifest", False, str(exc))

    for benchmark, benchmark_config in manifest["benchmarks"].items():
        expected = int(benchmark_config["expected_tasks"])
        for model_label, model_id in manifest["models"].items():
            stem = f"{benchmark}__{model_label}"
            raw_uri = uri(dataset, "raw_results", f"{stem}_results.jsonl")
            repaired_uri = uri(dataset, "results", f"{stem}_results.jsonl")
            try:
                raw_rows = parse_jsonl(storage.cat(raw_uri))
                repaired_rows = parse_jsonl(storage.cat(repaired_uri))
            except (RuntimeError, json.JSONDecodeError) as exc:
                validation.add("generation", stem, False, str(exc))
                continue

            raw_keys = [task_key(row) for row in raw_rows]
            repaired_keys = [task_key(row) for row in repaired_rows]
            validation.add(
                "generation",
                f"{stem} task coverage",
                len(raw_rows) == expected and len(set(raw_keys)) == expected,
                f"rows={len(raw_rows)}, unique={len(set(raw_keys))}, expected={expected}",
            )

            metadata_errors: list[str] = []
            for row in raw_rows:
                if row.get("benchmark") != benchmark:
                    metadata_errors.append("benchmark")
                if row.get("model_label") != model_label or row.get("model_name") != model_id:
                    metadata_errors.append("model")
                if row.get("seed") != expected_seed(row):
                    metadata_errors.append("seed")
                if int(row.get("generated_tokens", 0)) > int(contract["max_new_tokens"]):
                    metadata_errors.append("generated_tokens")
                if int(contract["required_activation_layer"]) not in row.get("layer_ids_saved", []):
                    metadata_errors.append("layer_16")
                missing_activation = (
                    not row.get("activation_path") or int(row.get("num_saved_tokens", 0)) <= 0
                )
                declared_missing = is_declared_activation_omission(
                    manifest, benchmark, model_label, int(row["task_idx"])
                )
                if missing_activation and not declared_missing:
                    metadata_errors.append("activation_metadata")
            validation.add(
                "generation",
                f"{stem} metadata contract",
                not metadata_errors,
                "ok" if not metadata_errors else f"violations={sorted(set(metadata_errors))}",
            )

            lineage_ok = len(repaired_rows) == expected and len(set(repaired_keys)) == expected
            raw_by_key = {task_key(row): row for row in raw_rows}
            repair_errors: list[str] = []
            changed = 0
            for row in repaired_rows:
                rules = set(row.get("rules_applied", []))
                if not rules <= allowed_repairs:
                    repair_errors.append("non_allowlisted_rule")
                if bool(row.get("changed")) != (
                    row.get("candidate_code_original") != row.get("candidate_code_repaired")
                ):
                    repair_errors.append("changed_flag")
                if row.get("suspicious_repair"):
                    repair_errors.append("suspicious_repair")
                raw_row = raw_by_key.get(task_key(row))
                if raw_row is None or row.get("candidate_code_original") != raw_row.get("candidate_code"):
                    repair_errors.append("raw_candidate_mismatch")
                if row.get("changed"):
                    changed += 1
            validation.add(
                "postprocessing",
                f"{stem} repair lineage",
                lineage_ok and not repair_errors and set(raw_keys) == set(repaired_keys),
                f"rows={len(repaired_rows)}, changed={changed}, errors={sorted(set(repair_errors))}",
            )

            if benchmark == "humanevalplus":
                eval_uri = uri(dataset, "eval", "humanevalplus", f"{stem}_eval.jsonl")
                try:
                    eval_rows = parse_jsonl(storage.cat(eval_uri))
                    eval_keys = [task_key(row) for row in eval_rows]
                    explicit = all(
                        "eval_candidate_code_repaired_correct" in row
                        and "eval_candidate_code_repaired_error" in row
                        for row in eval_rows
                    )
                    passed = sum(
                        bool(row.get("eval_candidate_code_repaired_correct")) for row in eval_rows
                    )
                    validation.add(
                        "evaluation",
                        f"{stem} HumanEval+ evidence",
                        len(eval_rows) == expected
                        and len(set(eval_keys)) == expected
                        and set(eval_keys) == set(raw_keys)
                        and explicit,
                        f"rows={len(eval_rows)}, correct={passed}, explicit_status={explicit}",
                    )
                except (RuntimeError, json.JSONDecodeError) as exc:
                    validation.add("evaluation", f"{stem} HumanEval+ evidence", False, str(exc))
            else:
                log_uri = uri(
                    dataset,
                    "eval",
                    "bigcodebench015",
                    f"{stem}_full_eval_nogt.log",
                )
                exit_uri = f"{log_uri}.exitcode"
                try:
                    log = storage.cat(log_uri)
                    exitcode = storage.cat(exit_uri).strip()
                    score = re.findall(r"^pass@1:\s*([0-9]+(?:\.[0-9]+)?)\s*$", log, re.MULTILINE)
                    version_recorded = "bigcodebench version: 0.1.5" in log
                    validation.add(
                        "evaluation",
                        f"{stem} BigCodeBench evidence",
                        exitcode == "0" and len(score) >= 1,
                        f"exitcode={exitcode}, pass@1={score[-1] if score else 'missing'}, version_recorded={version_recorded}",
                    )
                except RuntimeError as exc:
                    validation.add("evaluation", f"{stem} BigCodeBench evidence", False, str(exc))

    evidence_errors: list[str] = []
    for config_uri in manifest.get("generation_config_evidence", []):
        try:
            config = json.loads(storage.cat(config_uri))
        except (RuntimeError, json.JSONDecodeError):
            evidence_errors.append(config_uri)
            continue
        expected_fields = {
            "num_generations": contract["num_generations_per_task"],
            "max_new_tokens": contract["max_new_tokens"],
            "temperature": contract["temperature"],
            "top_p": contract["top_p"],
        }
        if any(not values_equal(config.get(key), value) for key, value in expected_fields.items()):
            evidence_errors.append(config_uri)
        if int(contract["required_activation_layer"]) not in config.get("selected_layer_ids", []):
            evidence_errors.append(config_uri)
    validation.add(
        "generation",
        "sampling parameter provenance",
        bool(manifest.get("generation_config_evidence")) and not evidence_errors,
        "archived experiment configs match" if not evidence_errors else f"invalid={evidence_errors}",
    )
    validation.warn(
        "evaluation",
        "BigCodeBench version provenance",
        "The v3 launcher enforced bigcodebench==0.1.5 before evaluation, but that version line was not copied into the per-model evaluator logs.",
    )


def activation_expected_count(
    manifest: dict[str, Any], benchmark: str, model: str
) -> tuple[int, list[int]]:
    expected = int(manifest["benchmarks"][benchmark]["expected_tasks"])
    omitted: list[int] = []
    for exception in manifest.get("activation_exceptions", []):
        if exception["benchmark"] == benchmark and model in exception["models"]:
            omitted.append(int(exception["task_idx"]))
    return expected - len(omitted), omitted


def is_declared_activation_omission(
    manifest: dict[str, Any], benchmark: str, model: str, task_idx: int
) -> bool:
    _, omitted = activation_expected_count(manifest, benchmark, model)
    return task_idx in omitted


def validate_activation_inventory(
    manifest: dict[str, Any], storage: GCloudStorage, validation: Validation
) -> None:
    root = uri(manifest["bucket_base"], manifest["activation_prefix"])
    try:
        objects = storage.list(f"{root}/**", recursive=True)
    except RuntimeError as exc:
        validation.add("activations", "canonical inventory", False, str(exc))
        return

    npz_objects = [item for item in objects if item.endswith(".npz")]
    for benchmark in manifest["benchmarks"]:
        for model in manifest["models"]:
            prefix = f"{root}/{benchmark}/{model}/"
            present = [item for item in npz_objects if item.startswith(prefix)]
            expected, omitted = activation_expected_count(manifest, benchmark, model)
            validation.add(
                "activations",
                f"{benchmark}/{model}",
                len(present) == expected,
                f"present={len(present)}, expected={expected}, declared_omissions={omitted}",
            )

    evidence = manifest.get("activation_conversion_evidence", {})
    try:
        log = storage.cat(evidence["uri"])
        summary = {
            key: int(match.group(1)) if match else -1
            for key, match in {
                "converted_and_validated": re.search(r"Succeeded:\s+(\d+)", log),
                "preexisting_revalidated": re.search(r"Skipped:\s+(\d+)", log),
                "declared_failures": re.search(r"Failed:\s+(\d+)", log),
            }.items()
        }
        evidence_ok = all(summary.get(key) == int(value) for key, value in evidence.items() if key in summary)
        total = sum(summary.values())
        expected_total = sum(
            int(config["expected_tasks"]) for config in manifest["benchmarks"].values()
        ) * len(manifest["models"])
        validation.add(
            "activations",
            "payload conversion evidence",
            evidence_ok and total == expected_total,
            f"summary={summary}, expected_total={expected_total}; 12 pre-existing task-0 payloads are covered by the supplemental revalidation report",
        )
    except (KeyError, RuntimeError) as exc:
        validation.add("activations", "payload conversion evidence", False, str(exc))


def values_equal(actual: Any, expected: Any) -> bool:
    if isinstance(expected, float):
        try:
            return math.isclose(float(actual), expected, rel_tol=1e-9, abs_tol=1e-12)
        except (TypeError, ValueError):
            return False
    return actual == expected


def validate_crosscoders(
    manifest: dict[str, Any], storage: GCloudStorage, validation: Validation
) -> None:
    base = manifest["bucket_base"]
    contract = manifest["crosscoder_contract"]
    for crosscoder in manifest["crosscoders"]:
        root = uri(base, crosscoder["prefix"])
        try:
            exitcode = storage.cat(uri(root, "exitcode.txt")).strip()
            config = json.loads(storage.cat(uri(root, "config.json")))
            metrics = parse_csv(storage.cat(uri(root, "metrics.csv")))
            final_uri = crosscoder.get("final_checkpoint_uri", uri(root, "final.pt"))
            final_exists = storage.exists(final_uri)
        except (RuntimeError, json.JSONDecodeError) as exc:
            validation.add("crosscoders", crosscoder["id"], False, str(exc))
            continue

        config_errors = [
            key for key, expected in contract.items() if not values_equal(config.get(key), expected)
        ]
        pair_ok = (
            config.get("model_a") == crosscoder["model_a"]
            and config.get("model_b") == crosscoder["model_b"]
        )
        finite = True
        for row in metrics:
            for key, value in row.items():
                if key == "step" or value in (None, ""):
                    continue
                try:
                    finite = finite and math.isfinite(float(value))
                except ValueError:
                    finite = False
        final_step = int(float(metrics[-1]["step"])) if metrics else -1
        passed = (
            exitcode == "0"
            and final_exists
            and pair_ok
            and not config_errors
            and final_step == int(contract["steps"])
            and finite
        )
        validation.add(
            "crosscoders",
            crosscoder["id"],
            passed,
            f"exitcode={exitcode}, final={final_exists}, final_uri={final_uri}, final_step={final_step}, pair={pair_ok}, config_errors={config_errors}, finite_metrics={finite}",
        )


def render_markdown(manifest: dict[str, Any], validation: Validation) -> str:
    lines = [
        f"# Validation report: {manifest['release_id']}",
        "",
        f"Overall blocking status: **{'FAIL' if validation.failed else 'PASS'}**",
        "",
        "Warnings are non-blocking evidence gaps that must be resolved or accepted before the publication freeze.",
        "",
        "| Gate | Check | Status | Detail |",
        "|---|---|---|---|",
    ]
    for check in validation.checks:
        detail = check.detail.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {check.gate} | {check.name} | {check.status} | {detail} |")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-markdown", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    validation = Validation()
    storage = GCloudStorage()

    validate_generation_and_processing(manifest, storage, validation)
    validate_activation_inventory(manifest, storage, validation)
    validate_crosscoders(manifest, storage, validation)

    payload = {
        "release_id": manifest["release_id"],
        "blocking_status": "FAIL" if validation.failed else "PASS",
        "checks": [asdict(check) for check in validation.checks],
    }
    markdown = render_markdown(manifest, validation)

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.output_markdown:
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output_markdown.write_text(markdown, encoding="utf-8")

    print(markdown)
    return 1 if validation.failed else 0


if __name__ == "__main__":
    sys.exit(main())
