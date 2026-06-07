#!/usr/bin/env python3
"""Local HumanEval evaluator for repaired JSONL files produced by reprocess_outputs_minimal.py."""
import argparse
import json
import subprocess
import sys
import tempfile
import os
from pathlib import Path
from statistics import median

from datasets import load_dataset


def run_candidate(code: str, test_code: str, entry_point: str, timeout: int):
    script = f"""
import json, traceback, time
from typing import *
RESULT = {{'correct': False, 'error': None, 'time': None}}
try:
    exec({code!r}, globals())
    exec({test_code!r}, globals())
    t0 = time.perf_counter()
    check({entry_point})
    RESULT['time'] = time.perf_counter() - t0
    RESULT['correct'] = True
except Exception as e:
    RESULT['error'] = repr(e) + '\\n' + traceback.format_exc(limit=3)
print(json.dumps(RESULT))
"""
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as f:
        f.write(script)
        p = f.name
    try:
        c = subprocess.run([sys.executable, p], capture_output=True, text=True, timeout=timeout)
        if c.returncode != 0:
            return {'correct': False, 'error': f'returncode={c.returncode}\nSTDOUT={c.stdout}\nSTDERR={c.stderr}', 'time': None}
        return json.loads(c.stdout.splitlines()[-1])
    except subprocess.TimeoutExpired:
        return {'correct': False, 'error': 'timeout', 'time': None}
    finally:
        try: os.remove(p)
        except OSError: pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repaired-jsonl', required=True)
    ap.add_argument('--output-jsonl', required=True)
    ap.add_argument('--timeout', type=int, default=5)
    ap.add_argument('--field', choices=['candidate_code_repaired','candidate_code_original'], default='candidate_code_repaired')
    args = ap.parse_args()

    ds = load_dataset('openai/openai_humaneval', split='test')
    tests = {f'HumanEval/{i}': {'test': x['test'], 'entry_point': x['entry_point']} for i, x in enumerate(ds)}

    out_path = Path(args.output_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total = correct = 0
    with open(args.repaired_jsonl) as f, out_path.open('w') as out:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get('benchmark') != 'humanevalplus':
                continue
            task_id = row['task_id']
            if task_id not in tests:
                continue
            res = run_candidate(row.get(args.field, ''), tests[task_id]['test'], tests[task_id]['entry_point'], args.timeout)
            row[f'eval_{args.field}_correct'] = res.get('correct')
            row[f'eval_{args.field}_error'] = res.get('error')
            row[f'eval_{args.field}_time'] = res.get('time')
            out.write(json.dumps(row, ensure_ascii=False) + '\n')
            total += 1
            correct += int(bool(res.get('correct')))
    print('evaluated:', total, 'correct:', correct, 'rate:', correct / total if total else None)
    print('wrote:', out_path)


if __name__ == '__main__':
    main()
