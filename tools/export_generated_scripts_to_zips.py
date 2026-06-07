#!/usr/bin/env python3
"""Export generated candidate_code from JSONL result files into per-run .py files inside zips."""
import argparse
import json
import zipfile
from pathlib import Path


def safe(s: str) -> str:
    return str(s).replace('/', '_').replace(' ', '_').replace(':', '_')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--results-dir', required=True, help='Directory containing benchmark__model_results.jsonl files.')
    ap.add_argument('--out-dir', required=True, help='Directory to write benchmark__model.zip files.')
    args = ap.parse_args()
    results_dir = Path(args.results_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for path in sorted(results_dir.glob('*.jsonl')):
        name = path.name.replace('_results.jsonl', '').replace('.jsonl', '')
        zip_path = out_dir / f'{name}.zip'
        n = 0
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            with path.open() as f:
                for line in f:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    task_idx = int(row.get('task_idx', n))
                    gen_idx = int(row.get('gen_idx', 0))
                    task_id = safe(row.get('task_id', f'task_{task_idx}'))
                    syntax = 'syntaxOK' if row.get('syntax_ok') else 'syntaxBAD'
                    correct = row.get('correct')
                    corr = 'correct' if correct is True else 'wrong' if correct is False else 'unknown'
                    filename = f'task_{task_idx:04d}__gen_{gen_idx:02d}__{task_id}__{syntax}__{corr}.py'
                    code = row.get('candidate_code') or ''
                    zf.writestr(filename, code)
                    n += 1
        print(zip_path, n)


if __name__ == '__main__':
    main()
