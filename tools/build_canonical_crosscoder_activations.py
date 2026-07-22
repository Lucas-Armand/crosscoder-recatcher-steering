#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np


LAYERS = ("layer_08", "layer_16", "layer_24")
REQUIRED_KEYS = {"input_ids", *LAYERS}
ALIGNMENT_KEYS = (
    "token_char_spans",
    "evaluated_token_mask",
    "evaluated_generated_char_spans",
)
EXPECTED_HIDDEN_SIZE = 4096

DEFAULT_BENCHMARKS = ("humanevalplus", "bigcodebench")
DEFAULT_MODELS = (
    "codellama_base",
    "codellama_finetuned",
    "codellama_merged",
    "deepseek_base",
    "deepseek_finetuned",
    "deepseek_merged",
)


@dataclass
class Result:
    source_uri: str
    destination_uri: str
    relative_path: str
    status: str
    source_size_bytes: int | None = None
    output_size_bytes: int | None = None
    source_layer_dtypes: str | None = None
    rows: int | None = None
    hidden_size: int | None = None
    duration_seconds: float | None = None
    error: str | None = None


def run_command(
    command: list[str],
    *,
    capture_output: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        capture_output=capture_output,
        check=check,
    )


def list_bucket_files(prefix: str) -> list[str]:
    result = run_command(
        [
            "gcloud",
            "storage",
            "ls",
            "--recursive",
            f"{prefix.rstrip('/')}/**",
        ]
    )

    return sorted(
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().endswith(".npz")
    )


def remote_exists(uri: str) -> bool:
    result = subprocess.run(
        ["gcloud", "storage", "ls", uri],
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def remote_size(uri: str) -> int | None:
    result = subprocess.run(
        ["gcloud", "storage", "ls", "--long", uri],
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        return None

    for line in result.stdout.splitlines():
        fields = line.split()

        if not fields:
            continue

        try:
            return int(fields[0])
        except ValueError:
            continue

    return None


def normalize_layer(array: np.ndarray) -> np.ndarray:
    if array.dtype == object:
        try:
            converted = np.asarray(
                array.tolist(),
                dtype=np.float32,
            )
        except (TypeError, ValueError):
            converted = np.stack(
                [
                    np.asarray(value, dtype=np.float32)
                    for value in array
                ],
                axis=0,
            )
    else:
        converted = np.asarray(array, dtype=np.float32)

    return np.ascontiguousarray(
        converted,
        dtype=np.float32,
    )


def convert_file(source: Path, destination: Path) -> tuple[str, int, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)

    with np.load(source, allow_pickle=True) as data:
        missing = REQUIRED_KEYS - set(data.files)

        if missing:
            raise ValueError(
                f"Missing keys: {sorted(missing)}"
            )

        input_ids = np.asarray(
            data["input_ids"],
            dtype=np.int64,
        )

        if input_ids.ndim != 1:
            raise ValueError(
                f"input_ids must be 1D, got {input_ids.shape}"
            )

        if input_ids.size == 0:
            raise ValueError("input_ids is empty")

        output: dict[str, np.ndarray] = {
            "input_ids": input_ids,
        }
        for key in ALIGNMENT_KEYS:
            if key in data.files:
                output[key] = np.asarray(data[key])

        source_dtypes: list[str] = []
        row_counts: list[int] = []

        for layer in LAYERS:
            original = data[layer]
            source_dtypes.append(
                f"{layer}:{original.dtype}"
            )

            converted = normalize_layer(original)

            if converted.ndim != 2:
                raise ValueError(
                    f"{layer} must be 2D, got {converted.shape}"
                )

            if converted.shape[1] != EXPECTED_HIDDEN_SIZE:
                raise ValueError(
                    f"{layer} hidden size is "
                    f"{converted.shape[1]}, expected "
                    f"{EXPECTED_HIDDEN_SIZE}"
                )

            if converted.shape[0] == 0:
                raise ValueError(f"{layer} has zero rows")

            if not np.isfinite(converted).all():
                raise ValueError(
                    f"{layer} contains NaN or Inf"
                )

            row_counts.append(converted.shape[0])
            output[layer] = converted

    if len(set(row_counts)) != 1:
        raise ValueError(
            f"Layer row counts differ: {row_counts}"
        )

    temporary = destination.with_suffix(".tmp.npz")

    try:
        np.savez_compressed(
            temporary,
            **output,
        )

        validate_canonical_file(temporary)

        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)

    return (
        ",".join(source_dtypes),
        row_counts[0],
        EXPECTED_HIDDEN_SIZE,
    )


def validate_canonical_file(path: Path) -> None:
    with np.load(path, allow_pickle=False) as data:
        missing = REQUIRED_KEYS - set(data.files)

        if missing:
            raise ValueError(
                f"Converted file missing keys: {sorted(missing)}"
            )

        input_ids = data["input_ids"]

        if input_ids.dtype != np.int64:
            raise ValueError(
                f"input_ids dtype is {input_ids.dtype}, expected int64"
            )

        if input_ids.ndim != 1 or input_ids.size == 0:
            raise ValueError(
                f"Invalid input_ids shape: {input_ids.shape}"
            )

        if "evaluated_token_mask" in data.files:
            mask = data["evaluated_token_mask"]
            if mask.ndim != 1 or len(mask) != len(input_ids):
                raise ValueError("evaluated_token_mask must align one-to-one with input_ids")
        if "token_char_spans" in data.files:
            spans = data["token_char_spans"]
            if spans.shape != (len(input_ids), 2):
                raise ValueError("token_char_spans must have shape [tokens, 2]")

        row_counts: list[int] = []

        for layer in LAYERS:
            array = data[layer]

            if array.dtype != np.float32:
                raise ValueError(
                    f"{layer} dtype is {array.dtype}, expected float32"
                )

            if array.ndim != 2:
                raise ValueError(
                    f"{layer} must be 2D, got {array.shape}"
                )

            if array.shape[1] != EXPECTED_HIDDEN_SIZE:
                raise ValueError(
                    f"{layer} hidden size is "
                    f"{array.shape[1]}, expected "
                    f"{EXPECTED_HIDDEN_SIZE}"
                )

            if array.shape[0] == 0:
                raise ValueError(f"{layer} has zero rows")

            if not np.isfinite(array).all():
                raise ValueError(
                    f"{layer} contains NaN or Inf"
                )

            row_counts.append(array.shape[0])

        if len(set(row_counts)) != 1:
            raise ValueError(
                f"Layer row counts differ: {row_counts}"
            )


def append_csv(path: Path, result: Result) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    row = asdict(result)
    write_header = not path.exists()

    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(row.keys()),
        )

        if write_header:
            writer.writeheader()

        writer.writerow(row)
        handle.flush()
        os.fsync(handle.fileno())


def relative_from_source(
    source_uri: str,
    source_root: str,
) -> str:
    prefix = source_root.rstrip("/") + "/"

    if not source_uri.startswith(prefix):
        raise ValueError(
            f"URI is outside source root: {source_uri}"
        )

    return source_uri[len(prefix):]


def build_source_list(
    source_bucket: str,
    benchmarks: Iterable[str],
    models: Iterable[str],
) -> list[str]:
    files: list[str] = []

    for benchmark in benchmarks:
        for model in models:
            prefix = (
                f"{source_bucket.rstrip('/')}/"
                f"{benchmark}/{model}"
            )

            group_files = list_bucket_files(prefix)

            print(
                f"{benchmark:18s} "
                f"{model:24s} "
                f"{len(group_files):6d} files",
                flush=True,
            )

            files.extend(group_files)

    return sorted(files)


def upload_file(source: Path, destination_uri: str) -> None:
    run_command(
        [
            "gcloud",
            "storage",
            "cp",
            str(source),
            destination_uri,
        ],
        capture_output=False,
    )


def write_manifest(
    path: Path,
    *,
    source_bucket: str,
    destination_bucket: str,
    files: list[str],
    benchmarks: list[str],
    models: list[str],
) -> None:
    manifest = {
        "source_bucket": source_bucket,
        "destination_bucket": destination_bucket,
        "total_source_files": len(files),
        "benchmarks": benchmarks,
        "models": models,
        "layer_keys": list(LAYERS),
        "layer_dtype": "float32",
        "input_ids_dtype": "int64",
        "hidden_size": EXPECTED_HIDDEN_SIZE,
        "allow_pickle_required_for_destination": False,
        "created_at_unix": time.time(),
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a canonical float32 CrossCoder activation "
            "dataset from NPZ files stored in Google Cloud Storage."
        )
    )

    parser.add_argument(
        "--source-bucket",
        required=True,
    )
    parser.add_argument(
        "--destination-bucket",
        required=True,
    )
    parser.add_argument(
        "--work-root",
        default="/tmp/crosscoder_canonical_builder",
    )
    parser.add_argument(
        "--benchmarks",
        nargs="+",
        default=list(DEFAULT_BENCHMARKS),
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=list(DEFAULT_MODELS),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace destination objects that already exist.",
    )
    parser.add_argument(
        "--keep-local",
        action="store_true",
        help="Keep downloaded and converted files after upload.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List work without downloading, converting, or uploading.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N files.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    work_root = Path(args.work_root)
    downloads_root = work_root / "downloads"
    converted_root = work_root / "converted"
    logs_root = work_root / "logs"

    csv_path = logs_root / "conversion_results.csv"
    manifest_path = logs_root / "build_manifest.json"

    files = build_source_list(
        args.source_bucket,
        args.benchmarks,
        args.models,
    )

    if args.limit is not None:
        files = files[: args.limit]

    print(f"\nTotal selected files: {len(files)}")

    write_manifest(
        manifest_path,
        source_bucket=args.source_bucket,
        destination_bucket=args.destination_bucket,
        files=files,
        benchmarks=args.benchmarks,
        models=args.models,
    )

    succeeded = 0
    skipped = 0
    failed = 0

    for index, source_uri in enumerate(files, start=1):
        relative = relative_from_source(
            source_uri,
            args.source_bucket,
        )

        destination_uri = (
            f"{args.destination_bucket.rstrip('/')}/"
            f"{relative}"
        )

        print(
            f"\n[{index}/{len(files)}] {relative}",
            flush=True,
        )

        if not args.overwrite and remote_exists(destination_uri):
            print("  SKIP destination already exists")
            skipped += 1

            append_csv(
                csv_path,
                Result(
                    source_uri=source_uri,
                    destination_uri=destination_uri,
                    relative_path=relative,
                    status="skipped_exists",
                ),
            )
            continue

        if args.dry_run:
            print(f"  DRY RUN -> {destination_uri}")
            continue

        start = time.monotonic()

        local_source = downloads_root / relative
        local_output = converted_root / relative

        local_source.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        local_output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            print("  downloading", flush=True)
            run_command(
                [
                    "gcloud",
                    "storage",
                    "cp",
                    source_uri,
                    str(local_source),
                ],
                capture_output=False,
            )

            source_size = local_source.stat().st_size

            print("  converting and validating", flush=True)
            source_dtypes, rows, hidden_size = convert_file(
                local_source,
                local_output,
            )

            output_size = local_output.stat().st_size

            print("  uploading", flush=True)
            upload_file(
                local_output,
                destination_uri,
            )

            destination_size = remote_size(destination_uri)

            if (
                destination_size is not None
                and destination_size != output_size
            ):
                raise RuntimeError(
                    "Uploaded object size differs from local output: "
                    f"local={output_size}, remote={destination_size}"
                )

            duration = time.monotonic() - start

            print(
                f"  OK "
                f"{source_size / 1024**2:.2f} MiB -> "
                f"{output_size / 1024**2:.2f} MiB "
                f"in {duration:.1f}s",
                flush=True,
            )

            append_csv(
                csv_path,
                Result(
                    source_uri=source_uri,
                    destination_uri=destination_uri,
                    relative_path=relative,
                    status="ok",
                    source_size_bytes=source_size,
                    output_size_bytes=output_size,
                    source_layer_dtypes=source_dtypes,
                    rows=rows,
                    hidden_size=hidden_size,
                    duration_seconds=round(duration, 3),
                ),
            )

            succeeded += 1

        except Exception as exc:
            duration = time.monotonic() - start
            failed += 1

            print(
                f"  ERROR: {type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )

            append_csv(
                csv_path,
                Result(
                    source_uri=source_uri,
                    destination_uri=destination_uri,
                    relative_path=relative,
                    status="error",
                    duration_seconds=round(duration, 3),
                    error=f"{type(exc).__name__}: {exc}",
                ),
            )

            if not args.continue_on_error:
                raise

        finally:
            if not args.keep_local:
                local_source.unlink(missing_ok=True)
                local_output.unlink(missing_ok=True)

    print("\n" + "=" * 80)
    print(f"Succeeded: {succeeded}")
    print(f"Skipped:   {skipped}")
    print(f"Failed:    {failed}")
    print(f"CSV log:   {csv_path}")
    print(f"Manifest:  {manifest_path}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
