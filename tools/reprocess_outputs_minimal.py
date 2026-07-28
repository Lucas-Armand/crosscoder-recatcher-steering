#!/usr/bin/env python3
"""
Minimal deterministic parse-fix pass for generated code.

Design principles:
- Do not select variants.
- Do not trim the function body.
- Do not regenerate or invent code.
- Preserve raw candidate_code and record exactly which deterministic fixes were applied.

Default repairs target issues observed in this project:
1. Byte-level markers that may be visible in decoded text: Ġ, Ċ, ĉ.
2. Markdown fences when the whole response is fenced.
3. CodeLlama indentation artifact: lines starting with exactly 3 spaces are shifted to 4 spaces.

Glued-token DeepSeek outputs are not fixed by default because we discovered they can come from
incorrect tokenizer loading. Rerun generation with the tokenizer guard instead. An optional
--enable-glued-fix exists only for qualitative exploration.
"""
import argparse
import ast
import csv
import json
import re
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from code_extraction import extract_python_candidate


@dataclass
class RepairRow:
    benchmark: str
    model_label: str
    task_idx: int
    task_id: str
    source_zip: str
    source_file: str
    compile_ok_original: bool
    compile_error_original: Optional[str]
    compile_ok_repaired: bool
    compile_error_repaired: Optional[str]
    changed: bool
    rules_applied: list
    suspicious_repair: bool
    original_len: int
    repaired_len: int
    candidate_code_original: str
    candidate_code_repaired: str
    raw_completion: str = ""
    prompt: str = ""
    entry_point: Optional[str] = None
    extraction_strategy: str = "legacy_zip_candidate"
    extraction_language: str = "unknown"
    extraction_generated_spans: list = None
    extraction_generated_text: str = ""
    extraction_candidate_count: int = 1
    extraction_ambiguous: bool = False


def infer_benchmark_model(zip_path: Path):
    stem = zip_path.stem
    parts = stem.split('__', 1)
    if len(parts) != 2:
        return 'unknown', stem
    return parts[0], parts[1]


def infer_task_idx(filename: str) -> int:
    m = re.search(r'task_(\d+)', filename)
    return int(m.group(1)) if m else -1


def infer_task_id(filename: str, benchmark: str, task_idx: int) -> str:
    if benchmark == 'humanevalplus':
        return f'HumanEval/{task_idx}'
    if benchmark == 'bigcodebench':
        return f'BigCodeBench/{task_idx}'
    return f'{benchmark}/{task_idx}'


def compile_check(code: str):
    try:
        compile(code, '<candidate>', 'exec')
        return True, None
    except Exception as e:
        return False, f'{type(e).__name__}: {e}'


def normalize_visible_bpe_markers(code: str):
    rules = []
    out = code
    for src, dst, name in [('Ċ', '\n', 'visible_newline_marker'), ('ĉ', '\t', 'visible_tab_marker'), ('Ġ', ' ', 'visible_space_marker')]:
        if src in out:
            out = out.replace(src, dst)
            rules.append(name)
    return out, rules


def strip_whole_markdown_fence(code: str):
    text = code.strip()
    if not text.startswith('```'):
        return code, []
    parts = text.split('```')
    if len(parts) >= 3:
        inner = parts[1]
        if inner.startswith('python'):
            inner = inner[len('python'):].lstrip('\n')
        return inner.rstrip() + '\n', ['strip_whole_markdown_fence']
    return code, []


def fix_three_space_indent(code: str):
    # Only local whitespace normalization: exactly 3 leading spaces followed by non-space -> 4 spaces.
    fixed = re.sub(r'(?m)^( {3})(\S)', r'    \2', code)
    return fixed, ['three_space_indent_to_four'] if fixed != code else []


def optional_glued_fix(code: str):
    # Exploratory only; disabled by default. Handles common exact patterns without changing identifiers broadly.
    rules = []
    replacements = {
        'returnNone': 'return None',
        'returnTrue': 'return True',
        'returnFalse': 'return False',
        'returnmax_string': 'return max_string',
        'deflongest': 'def longest',
        'fromtypingimport': 'from typing import ',
        'ifnot': 'if not ',
        'forstringin': 'for string in ',
    }
    out = code
    for a, b in replacements.items():
        if a in out:
            out = out.replace(a, b)
            rules.append(f'glued:{a}->{b}')
    return out, rules


def count_nonempty_body_lines(code: str) -> int:
    try:
        tree = ast.parse(code)
    except Exception:
        return -1
    funcs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if not funcs:
        return 0
    f = funcs[0]
    count = 0
    for node in f.body:
        if isinstance(node, ast.Expr) and isinstance(getattr(node, 'value', None), ast.Constant) and isinstance(node.value.value, str):
            continue
        count += 1
    return count


def minimal_repair(code: str, enable_glued_fix=False):
    rules = []
    original = code
    current, r = normalize_visible_bpe_markers(code); rules += r
    current, r = strip_whole_markdown_fence(current); rules += r
    ok, _ = compile_check(current)
    if not ok:
        candidate, r = fix_three_space_indent(current)
        ok2, _ = compile_check(candidate)
        if ok2 or candidate != current:
            current = candidate
            rules += r
    if enable_glued_fix:
        ok, _ = compile_check(current)
        if not ok:
            candidate, r = optional_glued_fix(current)
            current = candidate
            rules += r
    return current, rules


def process_zip(zip_path: Path, out_dir: Path, enable_glued_fix: bool):
    benchmark, model_label = infer_benchmark_model(zip_path)
    repaired_dir = out_dir / 'results_repaired'
    repaired_dir.mkdir(parents=True, exist_ok=True)
    repaired_jsonl = repaired_dir / f'{benchmark}__{model_label}_repaired.jsonl'
    repaired_zip_dir = out_dir / 'repaired_zips'
    repaired_zip_dir.mkdir(parents=True, exist_ok=True)
    repaired_zip = repaired_zip_dir / f'{benchmark}__{model_label}_repaired.zip'
    samples_dir = out_dir / 'samples_for_external_eval'
    samples_dir.mkdir(parents=True, exist_ok=True)
    samples_path = samples_dir / f'{benchmark}__{model_label}_samples.jsonl'

    rows = []
    with zipfile.ZipFile(zip_path) as zf, \
         zipfile.ZipFile(repaired_zip, 'w', compression=zipfile.ZIP_DEFLATED) as outzip, \
         repaired_jsonl.open('w') as jf, \
         samples_path.open('w') as sf:
        for name in sorted(zf.namelist()):
            if not name.endswith('.py'):
                continue
            code = zf.read(name).decode('utf-8', errors='replace')
            task_idx = infer_task_idx(Path(name).name)
            task_id = infer_task_id(Path(name).name, benchmark, task_idx)
            ok0, err0 = compile_check(code)
            fixed, rules = minimal_repair(code, enable_glued_fix=enable_glued_fix)
            ok1, err1 = compile_check(fixed)
            body0 = count_nonempty_body_lines(code)
            body1 = count_nonempty_body_lines(fixed)
            suspicious = (body0 > 0 and body1 >= 0 and body1 < body0) or (len(fixed) < 0.8 * len(code) and len(code) > 200)
            row = RepairRow(
                benchmark=benchmark,
                model_label=model_label,
                task_idx=task_idx,
                task_id=task_id,
                source_zip=str(zip_path),
                source_file=name,
                compile_ok_original=ok0,
                compile_error_original=err0,
                compile_ok_repaired=ok1,
                compile_error_repaired=err1,
                changed=(fixed != code),
                rules_applied=rules,
                suspicious_repair=suspicious,
                original_len=len(code),
                repaired_len=len(fixed),
                candidate_code_original=code,
                candidate_code_repaired=fixed,
            )
            d = asdict(row)
            jf.write(json.dumps(d, ensure_ascii=False) + '\n')
            out_name = Path(name).name.replace('.py', '__repaired.py')
            outzip.writestr(out_name, fixed)
            # Samples for external evaluators. HumanEval/EvalPlus usually consumes completion;
            # BigCodeBench accepts solution/completion depending on mode. We provide both.
            sf.write(json.dumps({'task_id': task_id, 'completion': fixed, 'solution': fixed, 'model_label': model_label, 'benchmark': benchmark}, ensure_ascii=False) + '\n')
            rows.append(row)

    return rows, repaired_jsonl


def process_raw_jsonl(path: Path, out_dir: Path, enable_glued_fix: bool):
    stem = path.name.removesuffix("_results.jsonl")
    benchmark, model_label = stem.split("__", 1)
    repaired_dir = out_dir / "results_repaired"
    samples_dir = out_dir / "samples_for_external_eval"
    repaired_dir.mkdir(parents=True, exist_ok=True)
    samples_dir.mkdir(parents=True, exist_ok=True)
    repaired_jsonl = repaired_dir / f"{stem}_repaired.jsonl"
    samples_path = samples_dir / f"{stem}_samples.jsonl"
    rows = []
    with path.open(encoding="utf-8") as source, repaired_jsonl.open("w") as jf, samples_path.open("w") as sf:
        for line in source:
            if not line.strip():
                continue
            raw = json.loads(line)
            extraction = extract_python_candidate(
                str(raw["prompt"]), str(raw.get("raw_completion", "")),
                raw.get("entry_point"), raw.get("candidate_code"),
            )
            code = extraction.code
            ok0, err0 = compile_check(code)
            fixed, rules = minimal_repair(code, enable_glued_fix=enable_glued_fix)
            ok1, err1 = compile_check(fixed)
            row = RepairRow(
                benchmark=benchmark, model_label=model_label,
                task_idx=int(raw["task_idx"]), task_id=str(raw["task_id"]),
                source_zip="", source_file=str(path),
                compile_ok_original=ok0, compile_error_original=err0,
                compile_ok_repaired=ok1, compile_error_repaired=err1,
                changed=(fixed != code), rules_applied=rules,
                suspicious_repair=False, original_len=len(code), repaired_len=len(fixed),
                candidate_code_original=code, candidate_code_repaired=fixed,
                raw_completion=str(raw.get("raw_completion", "")),
                prompt=str(raw["prompt"]), entry_point=raw.get("entry_point"),
                extraction_strategy=extraction.strategy,
                extraction_language=extraction.language,
                extraction_generated_spans=[list(span) for span in extraction.generated_spans],
                extraction_generated_text=extraction.generated_text,
                extraction_candidate_count=extraction.candidate_count,
                extraction_ambiguous=extraction.ambiguous,
            )
            data = asdict(row)
            jf.write(json.dumps(data, ensure_ascii=False) + "\n")
            sf.write(json.dumps({
                "task_id": row.task_id, "completion": fixed, "solution": fixed,
                "model_label": model_label, "benchmark": benchmark,
                "extraction_strategy": extraction.strategy,
                "extraction_generated_spans": data["extraction_generated_spans"],
            }, ensure_ascii=False) + "\n")
            rows.append(row)
    return rows, repaired_jsonl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--zip-dir', help='Legacy mode: directory with benchmark__model.zip files.')
    ap.add_argument('--raw-results-dir', help='Preferred v4 mode: extract directly from prompt + raw_completion JSONL.')
    ap.add_argument('--output-dir', required=True)
    ap.add_argument('--enable-glued-fix', action='store_true', help='Exploratory only; not recommended for final metrics.')
    args = ap.parse_args()

    if bool(args.zip_dir) == bool(args.raw_results_dir):
        ap.error("provide exactly one of --zip-dir or --raw-results-dir")
    zip_dir = Path(args.zip_dir) if args.zip_dir else None
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    all_rows = []
    if args.raw_results_dir:
        for path in sorted(Path(args.raw_results_dir).glob('*_results.jsonl')):
            rows, out = process_raw_jsonl(path, out_dir, args.enable_glued_fix)
            all_rows.extend(rows)
            print('processed', path.name, '->', out, 'rows=', len(rows))
    else:
        for z in sorted(zip_dir.glob('*.zip')):
            rows, out = process_zip(z, out_dir, args.enable_glued_fix)
            all_rows.extend(rows)
            print('processed', z.name, '->', out, 'rows=', len(rows))

    summary_path = out_dir / 'repair_summary.csv'
    with summary_path.open('w', newline='') as f:
        fields = ['benchmark','model_label','n','compile_ok_original','compile_ok_repaired','changed','suspicious_repair']
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        groups = {}
        for r in all_rows:
            groups.setdefault((r.benchmark, r.model_label), []).append(r)
        for (b,m), rows in sorted(groups.items()):
            w.writerow({
                'benchmark': b,
                'model_label': m,
                'n': len(rows),
                'compile_ok_original': sum(r.compile_ok_original for r in rows),
                'compile_ok_repaired': sum(r.compile_ok_repaired for r in rows),
                'changed': sum(r.changed for r in rows),
                'suspicious_repair': sum(r.suspicious_repair for r in rows),
            })
    print('summary:', summary_path)


if __name__ == '__main__':
    main()
