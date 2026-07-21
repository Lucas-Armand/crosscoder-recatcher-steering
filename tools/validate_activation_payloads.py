#!/usr/bin/env python3
"""Download and validate selected canonical activation NPZ payloads read-only."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from build_canonical_crosscoder_activations import validate_canonical_file


def run(command: list[str]) -> str:
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "command failed")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--task-idx", type=int, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()

    pattern = f"__task_{args.task_idx:04d}__"
    listing = run(["gcloud", "storage", "ls", "--recursive", f"{args.prefix.rstrip('/')}/**"])
    objects = sorted(
        line.strip()
        for line in listing.splitlines()
        if line.startswith("gs://") and line.endswith(".npz") and pattern in line
    )

    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="crosscoder_activation_validation_") as directory:
        root = Path(directory)
        for index, object_uri in enumerate(objects):
            destination = root / f"{index:04d}.npz"
            row: dict[str, object] = {"uri": object_uri, "status": "PASS"}
            try:
                run(["gcloud", "storage", "cp", object_uri, str(destination)])
                validate_canonical_file(destination)
                row["size_bytes"] = destination.stat().st_size
            except Exception as exc:  # report every payload without hiding the object
                row["status"] = "FAIL"
                row["error"] = f"{type(exc).__name__}: {exc}"
            results.append(row)

    payload = {
        "prefix": args.prefix,
        "task_idx": args.task_idx,
        "objects": len(objects),
        "passed": sum(row["status"] == "PASS" for row in results),
        "failed": sum(row["status"] == "FAIL" for row in results),
        "results": results,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("objects", "passed", "failed")}, indent=2))
    return 1 if payload["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
