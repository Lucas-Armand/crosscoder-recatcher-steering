#!/usr/bin/env python3
"""Split BigCodeBench sample JSONL and emit chunk commands using --selective_evaluate."""
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--samples', required=True)
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--chunk-size', type=int, default=100)
    ap.add_argument('--execution', default='local')
    ap.add_argument('--split', default='complete')
    ap.add_argument('--subset', default='full')
    ap.add_argument('--parallel', type=int, default=1)
    args = ap.parse_args()

    samples = Path(args.samples)
    out_dir = Path(args.out_dir)
    chunks_dir = out_dir / 'chunks'
    logs_dir = out_dir / 'logs'
    chunks_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    lines = [l for l in samples.read_text().splitlines() if l.strip()]
    commands = []
    for i in range(0, len(lines), args.chunk_size):
        chunk_lines = lines[i:i+args.chunk_size]
        ids = [json.loads(l)['task_id'] for l in chunk_lines]
        chunk_id = i // args.chunk_size
        chunk_path = chunks_dir / f'chunk_{chunk_id:03d}_{i:04d}_{i+len(chunk_lines)-1:04d}.jsonl'
        chunk_path.write_text('\n'.join(chunk_lines) + '\n')
        log = logs_dir / f'{chunk_path.stem}.log'
        selective = ','.join(ids)
        cmd = (
            f'python -m bigcodebench.evaluate {args.split} {args.subset} '
            f'--samples {chunk_path} --execution {args.execution} --parallel {args.parallel} '
            f'--selective_evaluate "{selective}" > {log} 2>&1'
        )
        commands.append(cmd)
    script = out_dir / 'run_chunks.sh'
    script.write_text('#!/usr/bin/env bash\nset -euo pipefail\n\n' + '\n\n'.join(commands) + '\n')
    script.chmod(0o755)
    print('lines:', len(lines), 'chunks:', len(commands))
    print('script:', script)


if __name__ == '__main__':
    main()
