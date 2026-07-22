#!/usr/bin/env python3
"""
Run code-generation benchmarks and save results/activations in the same
incremental JSONL + NPZ organization used by the notebook.

Main goals:
- Select the least occupied NVIDIA GPU automatically.
- Resume from existing JSONL rows.
- Save rows compatible with the existing notebook schema.
- Support smoke tests through CLI parameters.
- Prepare runs for HumanEval+/HumanEval-style and BigCodeBench-style tasks.
- Run multiple model aliases sequentially without keeping multiple models in memory.

Example smoke test:
    python run_recatcher_benchmarks.py \
      --benchmarks humanevalplus \
      --models deepseek_original \
      --max-tasks 2 \
      --num-generations 1 \
      --no-activations \
      --experiment-name smoke_test

Example full run:
    python run_recatcher_benchmarks.py \
      --benchmarks humanevalplus bigcodebench \
      --models codellama_original codellama_merged deepseek_original deepseek_merged \
      --num-generations 10 \
      --selected-layer-ids 8 16 24 \
      --experiment-name recatcher_table_v1
"""

from __future__ import annotations

import argparse
import ast
import difflib
import datetime
import gc
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


# Heavy ML imports are intentionally delayed until after CUDA_VISIBLE_DEVICES is set.
np = None
pd = None
torch = None
AutoTokenizer = None
AutoModelForCausalLM = None
BitsAndBytesConfig = None
set_seed = None
load_dataset = None
tqdm = None


DEFAULT_MODELS: Dict[str, str] = {
    # Adjust these aliases if your exact ReCatcher models are different.
    "codellama_original": "meta-llama/CodeLlama-7b-hf",
    "codellama_merged": "codellama-7b-merged-llama2-7b",  # pass --model-map-json to override
    "deepseek_original": "deepseek-ai/deepseek-coder-6.7b-base",
    "deepseek_merged": "ori-ai-fabric/ds-trinity-7b-v1",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate/evaluate benchmark completions and capture selected layer activations."
    )

    parser.add_argument(
        "--benchmarks",
        nargs="+",
        default=["humanevalplus"],
        choices=["humanevalplus", "humaneval", "bigcodebench"],
        help="Benchmarks to run.",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=["deepseek_original", "deepseek_merged"],
        help=(
            "Model aliases or Hugging Face model names. Known aliases: "
            + ", ".join(DEFAULT_MODELS.keys())
        ),
    )
    parser.add_argument(
        "--model-map-json",
        type=str,
        default=None,
        help=(
            "Optional JSON dict to override/add model aliases, e.g. "
            "{\"codellama_merged\":\"your-org/your-model\"}"
        ),
    )

    parser.add_argument("--root-dir", type=str, default="recatcher_crosscoder_humaneval")
    parser.add_argument("--experiment-name", type=str, default="humaneval_bigcodebench_4models_selected3layers_v1")

    parser.add_argument("--max-tasks", type=int, default=None, help="Use a small value for smoke tests.")
    parser.add_argument("--task-idx", type=int, default=None, help="Run only one benchmark task index, useful for smoke tests/debugging.")
    parser.add_argument("--num-generations", type=int, default=10)

    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--top-p", type=float, default=0.95)

    parser.add_argument("--perf-repeats", type=int, default=1)
    parser.add_argument("--perf-timeout-seconds", type=int, default=5)

    parser.add_argument("--max-length-for-activations", type=int, default=1536)
    parser.add_argument("--selected-layer-ids", nargs="*", type=int, default=[8, 16, 24])
    parser.add_argument("--save-all-layers", action="store_true")
    parser.add_argument("--save-prompt-tokens", action="store_true")
    parser.add_argument("--activation-save-format", choices=["npz", "npz_compressed"], default="npz")
    parser.add_argument("--no-activations", action="store_true", help="Skip activation capture for a fast smoke test.")

    parser.add_argument("--gpu", type=int, default=None, help="Physical GPU id. If omitted, choose least occupied GPU.")
    parser.add_argument(
        "--gpu-policy",
        choices=["free_memory", "used_memory"],
        default="free_memory",
        help="How to choose the automatic GPU.",
    )

    parser.add_argument("--load-in-4bit", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--attn-implementation", type=str, default="eager")
    parser.add_argument("--trust-remote-code", action=argparse.BooleanOptionalAction, default=True)

    parser.add_argument(
        "--compat-notebook-names",
        action="store_true",
        help=(
            "For a single benchmark and labels deepseek_original/deepseek_merged, also use "
            "base_results.jsonl and merged_results.jsonl naming style."
        ),
    )

    parser.add_argument("--dry-run", action="store_true", help="Print plan and exit.")
    return parser.parse_args()


def query_nvidia_smi() -> List[Dict[str, Any]]:
    cmd = [
        "nvidia-smi",
        "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        out = subprocess.check_output(cmd, text=True)
    except Exception as exc:
        print(f"Could not run nvidia-smi: {exc}", file=sys.stderr)
        return []

    rows = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 6:
            continue
        idx, name, total, used, free, util = parts
        rows.append(
            {
                "index": int(idx),
                "name": name,
                "memory_total_mb": int(total),
                "memory_used_mb": int(used),
                "memory_free_mb": int(free),
                "gpu_util_percent": int(util),
            }
        )
    return rows


def choose_gpu(policy: str = "free_memory") -> Optional[int]:
    gpus = query_nvidia_smi()
    if not gpus:
        return None

    if policy == "free_memory":
        chosen = max(gpus, key=lambda r: (r["memory_free_mb"], -r["gpu_util_percent"]))
    else:
        chosen = min(gpus, key=lambda r: (r["memory_used_mb"], r["gpu_util_percent"]))

    print("GPU status:")
    for g in gpus:
        marker = " <-- selected" if g["index"] == chosen["index"] else ""
        print(
            f"  GPU {g['index']}: {g['name']} | "
            f"used={g['memory_used_mb']}MiB free={g['memory_free_mb']}MiB "
            f"util={g['gpu_util_percent']}%{marker}"
        )

    return int(chosen["index"])


def import_runtime_dependencies() -> None:
    global np, pd, torch, AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig, set_seed, load_dataset, tqdm

    import numpy as _np
    import pandas as _pd
    import torch as _torch
    from datasets import load_dataset as _load_dataset
    from tqdm.auto import tqdm as _tqdm
    from transformers import (
        AutoModelForCausalLM as _AutoModelForCausalLM,
        AutoTokenizer as _AutoTokenizer,
        BitsAndBytesConfig as _BitsAndBytesConfig,
        PreTrainedTokenizerFast as _PreTrainedTokenizerFast,
        set_seed as _set_seed,
    )

    np = _np
    pd = _pd
    torch = _torch
    AutoTokenizer = _AutoTokenizer
    AutoModelForCausalLM = _AutoModelForCausalLM
    BitsAndBytesConfig = _BitsAndBytesConfig
    globals()["PreTrainedTokenizerFast"] = _PreTrainedTokenizerFast
    set_seed = _set_seed
    load_dataset = _load_dataset
    tqdm = _tqdm

    print("torch:", torch.__version__)
    print("torch cuda build:", torch.version.cuda)
    print("cuda available:", torch.cuda.is_available())
    print("visible cuda device count:", torch.cuda.device_count())
    if torch.cuda.is_available():
        print("visible cuda device name:", torch.cuda.get_device_name(0))


def now_utc_iso() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def format_seconds(seconds: float) -> str:
    seconds = float(seconds)
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.2f}min"
    return f"{minutes / 60:.2f}h"


def append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"Warning: skipping malformed JSONL line {line_no} in {path}: {exc}")
    return rows


def sanitize_task_id(task_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(task_id))


def make_run_id(model_label: str, benchmark: str, task_idx: int, gen_idx: int) -> str:
    return f"{model_label}__{benchmark}__task_{task_idx:04d}__gen_{gen_idx:02d}"


def strip_markdown_fences(text: str) -> str:
    text = text.replace("```python", "```")
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            candidates = parts[1::2]
            return max(candidates, key=len).strip("\n")
    return text.strip("\n")


def truncate_completion(completion: str) -> str:
    markers = [
        "\n\nif __name__",
        "\nif __name__",
        "\n\n# Test",
        "\n# Test",
        "\n\n# test",
        "\n# test",
        "\n\nprint(",
        "\nprint(",
        "\n\nassert ",
        "\nassert ",
        "\n\nExplanation:",
        "\nExplanation:",
        "\n\nThe function",
        "\nThe function",
        "\n\nThis function",
        "\nThis function",
        "\n```",
    ]
    cut = len(completion)
    for marker in markers:
        idx = completion.find(marker)
        if idx != -1:
            cut = min(cut, idx)

    for pattern in ["\n\ndef ", "\n\n\ndef "]:
        idx = completion.find(pattern)
        if idx != -1:
            cut = min(cut, idx)

    return completion[:cut].rstrip() + "\n"


def make_candidate_code(prompt: str, completion: str, entry_point: Optional[str]) -> str:
    cleaned = truncate_completion(strip_markdown_fences(completion))

    if entry_point:
        function_marker = f"def {entry_point}"
        idx = cleaned.find(function_marker)
        if idx != -1:
            return cleaned[idx:].rstrip() + "\n"

    return prompt.rstrip() + "\n" + cleaned.rstrip() + "\n"


def quick_syntax_check(code: str) -> Tuple[bool, Optional[str]]:
    try:
        ast.parse(code)
        return True, None
    except Exception as exc:
        return False, repr(exc)


def run_candidate_in_subprocess(
    candidate_code: str,
    test_code: Optional[str],
    entry_point: Optional[str],
    repeats: int = 1,
    timeout: int = 5,
) -> Dict[str, Any]:
    if not test_code or not entry_point:
        return {
            "correct": None,
            "times": [],
            "error": "No local test_code/entry_point available. Use official external evaluator for this benchmark.",
        }

    script = f"""
import json
import time
import traceback
import math
import statistics
from typing import *

RESULT = {{"correct": False, "times": [], "error": None}}

try:
    exec({candidate_code!r}, globals())
    exec({test_code!r}, globals())

    check({entry_point})

    times = []
    for _ in range({int(repeats)}):
        t0 = time.perf_counter()
        check({entry_point})
        t1 = time.perf_counter()
        times.append(t1 - t0)

    RESULT["correct"] = True
    RESULT["times"] = times

except Exception as e:
    RESULT["correct"] = False
    RESULT["times"] = []
    RESULT["error"] = repr(e) + "\\n" + traceback.format_exc(limit=3)

print(json.dumps(RESULT))
"""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(script)
        path = f.name

    try:
        completed = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()

        if completed.returncode != 0:
            return {
                "correct": False,
                "times": [],
                "error": f"returncode={completed.returncode}\nSTDOUT={stdout}\nSTDERR={stderr}",
            }

        if not stdout:
            return {
                "correct": False,
                "times": [],
                "error": f"empty stdout\nSTDERR={stderr}",
            }

        return json.loads(stdout.splitlines()[-1])

    except subprocess.TimeoutExpired:
        return {"correct": False, "times": [], "error": "timeout"}

    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def normalize_problem(raw: Dict[str, Any], benchmark: str, idx: int) -> Dict[str, Any]:
    task_id = raw.get("task_id") or raw.get("id") or raw.get("complete_task_id") or f"{benchmark}/{idx}"

    prompt = (
        raw.get("prompt")
        or raw.get("complete_prompt")
        or raw.get("instruct_prompt")
        or raw.get("question")
        or raw.get("description")
    )

    if prompt is None:
        raise ValueError(f"Could not find prompt for {benchmark} task {task_id}. Keys: {sorted(raw.keys())}")

    entry_point = raw.get("entry_point") or raw.get("canonical_entry_point")
    test_code = raw.get("test") or raw.get("test_code") or raw.get("tests")

    return {
        "benchmark": benchmark,
        "task_idx": idx,
        "task_id": str(task_id),
        "prompt": str(prompt),
        "test": test_code,
        "entry_point": entry_point,
        "raw_keys": sorted(raw.keys()),
    }


def load_benchmark(benchmark: str, max_tasks: Optional[int], task_idx: Optional[int] = None) -> List[Dict[str, Any]]:
    examples: List[Dict[str, Any]] = []

    if benchmark in {"humaneval", "humanevalplus"}:
        # For local per-row execution, openai/openai_humaneval gives prompt/test/entry_point.
        # For HumanEval+ rigor, this script also writes EvalPlus-style sample files;
        # run the official EvalPlus evaluator on those samples after generation.
        ds = load_dataset("openai/openai_humaneval", split="test")
        examples = [normalize_problem(dict(x), benchmark, i) for i, x in enumerate(ds)]

    elif benchmark == "bigcodebench":
        load_errors = []
        candidates = [
            ("bigcode/bigcodebench", "v0.1.2"),
            ("bigcode/bigcodebench", "complete"),
            ("bigcode/bigcodebench", "default"),
        ]
        for name, split in candidates:
            try:
                ds = load_dataset(name, split=split)
                examples = [normalize_problem(dict(x), benchmark, i) for i, x in enumerate(ds)]
                break
            except Exception as exc:
                load_errors.append(f"{name}:{split}: {exc}")

        if not examples:
            try:
                from bigcodebench.data import get_bigcodebench  # type: ignore

                data = get_bigcodebench()
                if isinstance(data, dict):
                    iterable = list(data.values())
                else:
                    iterable = list(data)
                examples = [normalize_problem(dict(x), benchmark, i) for i, x in enumerate(iterable)]
            except Exception as exc:
                load_errors.append(f"bigcodebench.data.get_bigcodebench: {exc}")

        if not examples:
            raise RuntimeError("Could not load BigCodeBench. Tried:\n" + "\n".join(load_errors))

    else:
        raise ValueError(f"Unsupported benchmark: {benchmark}")

    if max_tasks is not None:
        examples = examples[:max_tasks]

    if task_idx is not None:
        examples = [ex for ex in examples if int(ex["task_idx"]) == int(task_idx)]
        if not examples:
            raise ValueError(f"Requested --task-idx {task_idx}, but no such task is available after max_tasks filtering for {benchmark}.")

    print(f"Loaded {len(examples)} examples for {benchmark}")
    if examples:
        print(f"First {benchmark} task:", examples[0]["task_id"], "keys:", examples[0]["raw_keys"])
    return examples


def get_selected_layer_ids(num_layers_available: int, args: argparse.Namespace) -> List[int]:
    if args.no_activations:
        return []

    if args.save_all_layers:
        return list(range(num_layers_available))

    if args.selected_layer_ids:
        invalid = [x for x in args.selected_layer_ids if x < 0 or x >= num_layers_available]
        if invalid:
            raise ValueError(
                f"Invalid selected layer IDs {invalid}. "
                f"The model returned {num_layers_available} hidden-state entries."
            )
        return list(args.selected_layer_ids)

    return sorted(
        {
            num_layers_available // 4,
            num_layers_available // 2,
            (3 * num_layers_available) // 4,
        }
    )



def is_deepseek_family(model_name: str) -> bool:
    """Heuristic for model repos that should use the byte-level fast tokenizer path."""
    name = model_name.lower()
    return any(x in name for x in ["deepseek", "ds-trinity", "trinity", "kexer"])


def assert_tokenizer_preserves_code_whitespace(tokenizer, model_name: str) -> None:
    """
    Guard against a subtle tokenizer-loading failure observed with DeepSeek-family models.

    Failure mode: AutoTokenizer may instantiate a Llama tokenizer path that tokenizes code as
    `from` + `ty` + `ping` and decodes it as `fromtyping`, removing spaces/newlines.
    This contaminates both the prompt and the generation. We abort early if round-trip fails.
    """
    probe = "from typing import List, Optional\n\n\ndef f(x: int) -> int:\n    if x > 0:\n        return x\n    return None\n"
    ids = tokenizer(probe, add_special_tokens=False)["input_ids"]
    decoded = tokenizer.decode(
        ids,
        skip_special_tokens=False,
        clean_up_tokenization_spaces=False,
    )
    required = ["from typing", "def f", "return x", "return None", "\n"]
    missing = [x for x in required if x not in decoded]
    if missing:
        raise RuntimeError(
            f"Tokenizer whitespace round-trip failed for {model_name}.\n"
            f"Missing: {missing}\n"
            f"Original: {probe!r}\n"
            f"Decoded:  {decoded!r}\n"
            "Use a tokenizer path that loads tokenizer.json through PreTrainedTokenizerFast."
        )


def load_tokenizer_safe(model_name: str, args: argparse.Namespace):
    """
    Load tokenizer with a strict whitespace round-trip check.

    DeepSeek Coder tokenizers are byte-level BPE tokenizers. In this project we observed
    AutoTokenizer loading them through an incompatible Llama tokenizer route, removing
    whitespace in code prompts. For DeepSeek-family repos, force PreTrainedTokenizerFast.
    """
    from transformers import PreTrainedTokenizerFast

    if is_deepseek_family(model_name):
        tokenizer = PreTrainedTokenizerFast.from_pretrained(
            model_name,
            trust_remote_code=args.trust_remote_code,
            bos_token="<｜begin▁of▁sentence｜>",
            eos_token="<｜end▁of▁sentence｜>",
            pad_token="<｜end▁of▁sentence｜>",
        )
    else:
        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            trust_remote_code=args.trust_remote_code,
            use_fast=True,
        )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"

    assert_tokenizer_preserves_code_whitespace(tokenizer, model_name)
    print("Tokenizer loaded safely:", tokenizer.__class__.__name__, "is_fast=", getattr(tokenizer, "is_fast", None))
    return tokenizer


def load_quantized_model(model_name: str, args: argparse.Namespace, run_dir: Path):
    print("Loading model:", model_name)

    tokenizer = load_tokenizer_safe(model_name, args)

    compute_dtype = torch.float16
    kwargs = {
        "torch_dtype": compute_dtype,
        "low_cpu_mem_usage": True,
        "trust_remote_code": args.trust_remote_code,
        "attn_implementation": args.attn_implementation,
    }

    if args.load_in_4bit:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )
        kwargs["quantization_config"] = bnb_config

    offload_dir = run_dir / "offload" / model_name.replace("/", "__")
    offload_dir.mkdir(parents=True, exist_ok=True)

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        device_map={"": 0},  # physical GPU is controlled by CUDA_VISIBLE_DEVICES
        offload_folder=str(offload_dir),
        **kwargs,
    )
    model.eval()

    print("Model loaded.")
    print("Model device:", next(model.parameters()).device)
    return model, tokenizer


def generation_kwargs(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "max_new_tokens": args.max_new_tokens,
        "do_sample": True,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "use_cache": True,
    }


def fallback_generation_kwargs(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "max_new_tokens": args.max_new_tokens,
        "do_sample": False,
        "remove_invalid_values": True,
        "renormalize_logits": True,
        "use_cache": True,
    }


def normalize_decoded_text(text: str) -> str:
    """
    Fix byte-level BPE artifacts that may appear with some code tokenizers,
    especially when decoded text contains visible Ġ/Ċ markers.
    """
    if not text:
        return text

    replacements = {
        "Ċ": "\n",
        "ĉ": "\t",
        "Ġ": " ",
    }

    for src, dst in replacements.items():
        text = text.replace(src, dst)

    return text


def generate_completion(model, tokenizer, prompt: str, seed: int, args: argparse.Namespace) -> Dict[str, Any]:
    set_seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=1024,
    ).to(model.device)

    inputs = {k: v.to(model.device) for k, v in inputs.items() if k != "token_type_ids"}

    prompt_tokens = int(inputs["input_ids"].shape[1])
    start = time.perf_counter()

    try:
        output_ids = model.generate(
            **inputs,
            **generation_kwargs(args),
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
        mode = "sample"
    except RuntimeError as exc:
        print("Sampling failed. Falling back to greedy decoding.")
        print("Original error:", repr(exc))
        torch.cuda.empty_cache()
        output_ids = model.generate(
            **inputs,
            **fallback_generation_kwargs(args),
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
        mode = "greedy_fallback"

    seconds = time.perf_counter() - start
    generated_ids = output_ids[0, prompt_tokens:]
                             
    completion = tokenizer.decode(
        generated_ids,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )
    completion = normalize_decoded_text(completion)
                   
    generated_tokens = int(generated_ids.shape[0])

    return {
        "completion": completion,
        "prompt_tokens": prompt_tokens,
        "generated_tokens": generated_tokens,
        "total_tokens": int(output_ids.shape[1]),
        "generation_seconds": float(seconds),
        "tokens_per_second": float(generated_tokens / seconds) if seconds > 0 else None,
        "generation_mode": mode,
    }



def capture_activations(
    model,
    tokenizer,
    full_text: str,
    prompt: str,
    evaluated_candidate: str,
    args: argparse.Namespace,
) -> Optional[Dict[str, Any]]:
    if args.no_activations:
        return None

    with torch.no_grad():
        encoded_full = tokenizer(
            full_text,
            return_tensors="pt",
            truncation=True,
            max_length=args.max_length_for_activations,
            return_offsets_mapping=True,
        ).to(model.device)

        offsets = encoded_full.pop("offset_mapping")[0].detach().cpu().numpy()

        encoded_full = {
            k: v.to(model.device)
            for k, v in encoded_full.items()
            if k != "token_type_ids"
        }

        encoded_prompt = tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=args.max_length_for_activations,
        )

        prompt_len = int(encoded_prompt["input_ids"].shape[1])
        outputs = model(**encoded_full, output_hidden_states=True, use_cache=False)

        hidden_states = outputs.hidden_states
        input_ids = encoded_full["input_ids"][0].detach().cpu().numpy()
        seq_len = int(input_ids.shape[0])
        start_pos = 0 if args.save_prompt_tokens else min(prompt_len, seq_len)
        generated_char_start = len(prompt.rstrip() + "\n")
        retained_spans = []
        matcher = difflib.SequenceMatcher(a=full_text, b=evaluated_candidate, autojunk=False)
        for block in matcher.get_matching_blocks():
            lo = max(block.a, generated_char_start)
            hi = block.a + block.size
            if hi > lo:
                retained_spans.append((lo, hi))
        evaluated_token_mask = np.asarray([
            end > begin and any(end > lo and begin < hi for lo, hi in retained_spans)
            for begin, end in offsets
        ], dtype=np.bool_)
        layer_ids = get_selected_layer_ids(len(hidden_states), args)

        layer_arrays = {}
        for layer_idx in layer_ids:
            hidden = hidden_states[layer_idx]
            layer_name = f"layer_{layer_idx:02d}"
            arr = (
                hidden[0, start_pos:, :]
                .detach()
                .to(torch.float16)
                .cpu()
                .numpy()
                .astype(np.float16)
            )
            layer_arrays[layer_name] = arr

        result = {
            "layer_arrays": layer_arrays,
            "input_ids": input_ids[start_pos:],
            "token_char_spans": offsets[start_pos:].astype(np.int64, copy=False),
            "evaluated_token_mask": evaluated_token_mask[start_pos:],
            "evaluated_generated_char_spans": np.asarray(retained_spans, dtype=np.int64).reshape(-1, 2),
            "prompt_len": prompt_len,
            "start_pos": start_pos,
            "seq_len": seq_len,
            "num_saved_tokens": seq_len - start_pos,
            "num_layers_available": len(hidden_states),
            "num_layers_saved": len(layer_ids),
            "layer_ids_saved": layer_ids,
        }

        del outputs
        del hidden_states
        torch.cuda.empty_cache()
        return result


def save_activation_file(path: Path, activation_output: Dict[str, Any], fmt: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    arrays = {
        "input_ids": activation_output["input_ids"],
        "token_char_spans": activation_output["token_char_spans"],
        "evaluated_token_mask": activation_output["evaluated_token_mask"],
        "evaluated_generated_char_spans": activation_output["evaluated_generated_char_spans"],
        **activation_output["layer_arrays"],
    }

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    if fmt == "npz":
        np.savez(tmp_path, **arrays)
    elif fmt == "npz_compressed":
        np.savez_compressed(tmp_path, **arrays)
    else:
        raise ValueError(f"Unsupported activation format: {fmt}")

    # numpy appends .npz if suffix is not exactly .npz
    actual_tmp = Path(str(tmp_path) + ".npz") if not tmp_path.exists() else tmp_path
    actual_tmp.replace(path)


def result_path_for(
    results_dir: Path,
    benchmark: str,
    model_label: str,
    args: argparse.Namespace,
) -> Path:
    if args.compat_notebook_names and len(args.benchmarks) == 1:
        if model_label == "deepseek_original":
            return results_dir / "base_results.jsonl"
        if model_label == "deepseek_merged":
            return results_dir / "merged_results.jsonl"

    return results_dir / f"{benchmark}__{model_label}_results.jsonl"


def evalplus_sample_path(samples_dir: Path, benchmark: str, model_label: str) -> Path:
    return samples_dir / f"{benchmark}__{model_label}_samples.jsonl"


def run_one_model_on_benchmark(
    model,
    tokenizer,
    model_label: str,
    model_name: str,
    benchmark: str,
    examples: List[Dict[str, Any]],
    args: argparse.Namespace,
    run_dir: Path,
    results_dir: Path,
    activation_dir: Path,
    metadata_dir: Path,
    samples_dir: Path,
) -> None:
    results_path = result_path_for(results_dir, benchmark, model_label, args)
    timing_path = metadata_dir / "timing_log.jsonl"
    samples_path = evalplus_sample_path(samples_dir, benchmark, model_label)

    existing_rows = read_jsonl(results_path)
    completed = set()

    for row in existing_rows:
        rid = row.get("run_id")
        if not rid:
            continue

        # Important:
        # We consider a run complete if it is present in the JSONL.
        # Activations may have been moved to GCS and deleted locally to save disk.
        completed.add(rid)

    print(f"[{benchmark} / {model_label}] existing complete rows: {len(completed)}")

    model_activation_dir = activation_dir / benchmark / model_label
    model_activation_dir.mkdir(parents=True, exist_ok=True)

    total_expected = len(examples) * args.num_generations
    session_start = time.perf_counter()
    completed_this_session = 0

    progress = tqdm(examples, desc=f"{benchmark}:{model_label}")
    for task_idx, ex in enumerate(progress):
        task_id = ex["task_id"]
        prompt = ex["prompt"]
        test_code = ex.get("test")
        entry_point = ex.get("entry_point")

        for gen_idx in range(args.num_generations):
            run_id = make_run_id(model_label, benchmark, task_idx, gen_idx)
            if run_id in completed:
                continue

            run_start = time.perf_counter()
            seed = 1000 + task_idx * 100 + gen_idx

            gen_out = generate_completion(model, tokenizer, prompt, seed, args)
            completion = gen_out["completion"]

            syntax_start = time.perf_counter()
            candidate_code = make_candidate_code(prompt, completion, entry_point)
            syntax_ok, syntax_error = quick_syntax_check(candidate_code)
            syntax_seconds = time.perf_counter() - syntax_start

            eval_start = time.perf_counter()
            if syntax_ok:
                eval_result = run_candidate_in_subprocess(
                    candidate_code=candidate_code,
                    test_code=test_code,
                    entry_point=entry_point,
                    repeats=args.perf_repeats,
                    timeout=args.perf_timeout_seconds,
                )
            else:
                eval_result = {"correct": False, "times": [], "error": syntax_error}
            evaluation_seconds = time.perf_counter() - eval_start

            full_text = prompt.rstrip() + "\n" + completion.rstrip() + "\n"

            activation_path = None
            activation_output = None
            activation_forward_seconds = 0.0
            activation_save_seconds = 0.0

            if not args.no_activations:
                task_safe = sanitize_task_id(task_id)
                activation_path = model_activation_dir / f"{run_id}__{task_safe}.npz"

                activation_forward_start = time.perf_counter()
                activation_output = capture_activations(
                    model, tokenizer, full_text, prompt, candidate_code, args
                )
                activation_forward_seconds = time.perf_counter() - activation_forward_start

                activation_save_start = time.perf_counter()
                save_activation_file(activation_path, activation_output, args.activation_save_format)
                activation_save_seconds = time.perf_counter() - activation_save_start

            total_run_seconds = time.perf_counter() - run_start

            row = {
                # Existing notebook-compatible columns
                "run_id": run_id,
                "model_label": model_label,
                "model_name": model_name,
                "task_idx": task_idx,
                "task_id": task_id,
                "gen_idx": gen_idx,
                "seed": seed,
                "entry_point": entry_point,
                "prompt": prompt,
                "raw_completion": completion,
                "candidate_code": candidate_code,
                "syntax_ok": bool(syntax_ok),
                "correct": eval_result.get("correct"),
                "times": eval_result.get("times", []),
                "median_time": float(np.median(eval_result["times"])) if eval_result.get("times") else None,
                "error": eval_result.get("error"),
                "prompt_tokens": int(gen_out["prompt_tokens"]),
                "generated_tokens": int(gen_out["generated_tokens"]),
                "total_tokens": int(gen_out["total_tokens"]),
                "generation_mode": gen_out["generation_mode"],
                "tokens_per_second": gen_out["tokens_per_second"],
                "generation_seconds": float(gen_out["generation_seconds"]),
                "syntax_seconds": float(syntax_seconds),
                "evaluation_seconds": float(evaluation_seconds),
                "activation_forward_seconds": float(activation_forward_seconds),
                "activation_save_seconds": float(activation_save_seconds),
                "total_run_seconds": float(total_run_seconds),
                "activation_path": str(activation_path) if activation_path else None,
                "activation_dtype": "float16",
                "save_prompt_tokens": bool(args.save_prompt_tokens),
                "prompt_len": int(activation_output["prompt_len"]) if activation_output else None,
                "seq_len": int(activation_output["seq_len"]) if activation_output else None,
                "start_pos": int(activation_output["start_pos"]) if activation_output else None,
                "num_saved_tokens": int(activation_output["num_saved_tokens"]) if activation_output else None,
                "num_layers_available": int(activation_output["num_layers_available"]) if activation_output else None,
                "num_layers_saved": int(activation_output["num_layers_saved"]) if activation_output else None,
                "layer_ids_saved": activation_output["layer_ids_saved"] if activation_output else [],
                # New columns for the multi-benchmark/multi-model experiment
                "benchmark": benchmark,
                "created_at": now_utc_iso(),
                "physical_gpu": os.environ.get("PHYSICAL_CUDA_DEVICE"),
                "visible_cuda_device": 0 if torch.cuda.is_available() else None,
            }

            append_jsonl(results_path, row)

            # Sample file compatible with external benchmark evaluators.
            append_jsonl(
                samples_path,
                {
                    "task_id": task_id,
                    "completion": completion,
                    "solution": candidate_code,
                    "run_id": run_id,
                    "model_label": model_label,
                    "model_name": model_name,
                    "benchmark": benchmark,
                },
            )

            timing_row = {
                k: row[k]
                for k in [
                    "created_at",
                    "run_id",
                    "benchmark",
                    "model_label",
                    "model_name",
                    "task_idx",
                    "task_id",
                    "gen_idx",
                    "seed",
                    "prompt_tokens",
                    "generated_tokens",
                    "total_tokens",
                    "generation_mode",
                    "tokens_per_second",
                    "syntax_ok",
                    "correct",
                    "generation_seconds",
                    "syntax_seconds",
                    "evaluation_seconds",
                    "activation_forward_seconds",
                    "activation_save_seconds",
                    "total_run_seconds",
                    "num_saved_tokens",
                    "num_layers_available",
                    "num_layers_saved",
                    "layer_ids_saved",
                    "physical_gpu",
                ]
            }
            append_jsonl(timing_path, timing_row)

            completed.add(run_id)
            completed_this_session += 1

            elapsed = time.perf_counter() - session_start
            mean_time = elapsed / max(completed_this_session, 1)
            remaining = total_expected - len(completed)
            eta = remaining * mean_time

            print(
                f"[{benchmark}/{model_label}] {task_id} gen={gen_idx} "
                f"syntax={syntax_ok} correct={row['correct']} "
                f"mode={row['generation_mode']} tokens={row['generated_tokens']} "
                f"tok/s={row['tokens_per_second']} layers={row['layer_ids_saved']} "
                f"gen={format_seconds(row['generation_seconds'])} "
                f"eval={format_seconds(row['evaluation_seconds'])} "
                f"act={format_seconds(row['activation_forward_seconds'] + row['activation_save_seconds'])} "
                f"total={format_seconds(row['total_run_seconds'])} eta_model={format_seconds(eta)}"
            )


def save_config(args: argparse.Namespace, model_map: Dict[str, str], run_dir: Path, metadata_dir: Path) -> None:
    metadata_dir.mkdir(parents=True, exist_ok=True)
    config = vars(args).copy()
    config["model_map"] = model_map
    config["created_at"] = now_utc_iso()
    config["cuda_visible_devices"] = os.environ.get("CUDA_VISIBLE_DEVICES")
    config["physical_cuda_device"] = os.environ.get("PHYSICAL_CUDA_DEVICE")

    path = metadata_dir / "experiment_config.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print("Saved config:", path)


def resolve_model_map(args: argparse.Namespace) -> Dict[str, str]:
    model_map = dict(DEFAULT_MODELS)
    if args.model_map_json:
        model_map.update(json.loads(args.model_map_json))
    return model_map


def resolve_model_name(model_arg: str, model_map: Dict[str, str]) -> Tuple[str, str]:
    if model_arg in model_map:
        return model_arg, model_map[model_arg]

    # Treat unknown values as direct HF model names.
    label = model_arg.replace("/", "__")
    return label, model_arg


def main() -> None:
    args = parse_args()

    selected_gpu = args.gpu if args.gpu is not None else choose_gpu(args.gpu_policy)
    if selected_gpu is not None:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(selected_gpu)
        os.environ["PHYSICAL_CUDA_DEVICE"] = str(selected_gpu)
        print(f"Using physical GPU {selected_gpu}; inside PyTorch it will appear as cuda:0.")
    else:
        print("No GPU selected. The script will continue, but model loading may fail or run on CPU.")

    model_map = resolve_model_map(args)

    root_dir = Path(args.root_dir)
    run_dir = root_dir / args.experiment_name
    results_dir = run_dir / "results"
    activation_dir = run_dir / "selected_layer_activations"
    metadata_dir = run_dir / "metadata"
    samples_dir = run_dir / "samples_for_external_eval"
    backup_dir = run_dir / "backups"

    for d in [results_dir, activation_dir, metadata_dir, samples_dir, backup_dir]:
        d.mkdir(parents=True, exist_ok=True)

    print("Run directory:", run_dir)
    print("Results directory:", results_dir)
    print("Activation directory:", activation_dir)
    print("Samples directory:", samples_dir)
    print("Benchmarks:", args.benchmarks)
    print("Models:", args.models)

    if args.dry_run:
        print("Dry run only. Resolved model names:")
        for m in args.models:
            label, name = resolve_model_name(m, model_map)
            print(f"  {label}: {name}")
        return

    import_runtime_dependencies()
    save_config(args, model_map, run_dir, metadata_dir)

    benchmark_cache = {
        benchmark: load_benchmark(benchmark, args.max_tasks, args.task_idx)
        for benchmark in args.benchmarks
    }

    for model_arg in args.models:
        model_label, model_name = resolve_model_name(model_arg, model_map)

        model, tokenizer = load_quantized_model(model_name, args, run_dir)

        try:
            for benchmark, examples in benchmark_cache.items():
                run_one_model_on_benchmark(
                    model=model,
                    tokenizer=tokenizer,
                    model_label=model_label,
                    model_name=model_name,
                    benchmark=benchmark,
                    examples=examples,
                    args=args,
                    run_dir=run_dir,
                    results_dir=results_dir,
                    activation_dir=activation_dir,
                    metadata_dir=metadata_dir,
                    samples_dir=samples_dir,
                )
        finally:
            del model
            del tokenizer
            gc.collect()
            if torch is not None and torch.cuda.is_available():
                torch.cuda.empty_cache()

    print("Done.")
    print("Results:", results_dir)
    print("Activations:", activation_dir)
    print("External-eval samples:", samples_dir)


if __name__ == "__main__":
    main()
