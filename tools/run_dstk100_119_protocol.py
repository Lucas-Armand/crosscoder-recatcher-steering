#!/usr/bin/env python3
"""Reproduce the frozen DeepSeek 119-task protocol; never selects new controls."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'reproducibility/dstk100_119_v1'


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def dump_rows(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in content))
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['verify', 'baseline', 'sweep', 'curves', 'random'], required=True)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'runs/dstk100_119_reproduction_v1')
    parser.add_argument('--device', default='cuda:0')
    parser.add_argument('--eval-python', default='/home/lucas/venvs/bigcodebench015/bin/python')
    parser.add_argument('--worker-index', type=int, default=0)
    parser.add_argument('--num-workers', type=int, default=1)
    args = parser.parse_args()
    os.chdir(ROOT)
    assert 0 <= args.worker_index < args.num_workers
    manifest = json.loads((PACKAGE / 'manifest.json').read_text())
    if args.stage == 'verify':
        entries = json.loads((PACKAGE / 'checksums.json').read_text())
        for relative, expected in entries.items():
            path = ROOT / relative
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            assert digest.hexdigest() == expected, relative
        print(f'Verified {len(entries)} published files.')
        return
    original = rows(PACKAGE / 'inputs/cohort119.jsonl')
    assert len(original) == len({r['task_id'] for r in original}) == 119
    assert all(r['seed'] == 1000 + 100 * int(r['task_idx']) for r in original)
    out = args.output_dir.resolve()
    for folder in ('generations', 'evaluations', 'logs', 'postprocessed'):
        (out / folder).mkdir(parents=True, exist_ok=True)
    common = [sys.executable, str(ROOT / 'tools/run_crosscoder_intervention.py'),
              '--checkpoint', manifest['checkpoint']['path'],
              '--model-a-id', manifest['models']['a'], '--model-b-id', manifest['models']['b'],
              '--tokenizer-id', manifest['models']['a'], '--target-side', 'a', '--layer', '16',
              '--intervention-mode', 'traditional', '--token-scope', 'last_token',
              '--generation-backend', 'paired_cached', '--max-new-tokens', '512',
              '--temperature', '0.2', '--top-p', '0.95', '--seed', '1000',
              '--device-a', args.device, '--dtype', 'nf4', '--trust-remote-code']

    def generate(name, fid, alpha):
        output = out / 'generations' / f'bigcodebench__{name}_results.jsonl'
        previous = rows(output) if output.exists() else []
        by_id = {r['task_id']: r for r in previous}
        assert len(previous) == len(by_id)
        assert set(by_id).issubset({r['task_id'] for r in original})
        for row in previous:
            assert row['feature_id'] == fid and row['alpha'] == alpha
            assert row['generation_seed'] == 1000 + 100 * int(row['task_idx'])
        pending = [r for r in original if r['task_id'] not in by_id]
        pending_input = out / 'logs' / f'{name}_pending_input.jsonl'
        pending_output = out / 'logs' / f'{name}_pending_results.jsonl'
        # Recover atomically saved rows from an interrupted pending batch.
        if pending_output.exists():
            recovered = rows(pending_output)
            for row in recovered:
                assert row['feature_id'] == fid and row['alpha'] == alpha
                assert row['generation_seed'] == 1000 + 100 * int(row['task_idx'])
                assert row['task_id'] in {r['task_id'] for r in original}
                by_id[row['task_id']] = row
            pending = [r for r in original if r['task_id'] not in by_id]
            dump_rows(output, [by_id[r['task_id']] for r in original if r['task_id'] in by_id])
        if pending:
            dump_rows(pending_input, pending)
            # The underlying runner writes a new atomic checkpoint after every task.
            command = [*common, '--feature-id', str(fid), '--alpha', str(alpha),
                       '--input-jsonl', str(pending_input), '--output-jsonl', str(pending_output)]
            with (out / 'logs' / f'{name}.log').open('a') as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
            by_id.update({r['task_id']: r for r in rows(pending_output)})
            dump_rows(output, [by_id[r['task_id']] for r in original])
        assert len(rows(output)) == 119
        return output

    def evaluate(name, raw):
        from reprocess_outputs_minimal import process_raw_jsonl
        process_raw_jsonl(raw, out / 'postprocessed', False)
        result = out / 'evaluations' / f'bigcodebench__{name}_eval.json'
        if not result.exists():
            sample = out / 'postprocessed/samples_for_external_eval' / f'bigcodebench__{name}_samples.jsonl'
            command = [args.eval_python, 'tools/evaluate_bigcodebench_subset.py',
                       '--samples', str(sample), '--output', str(result), '--parallel', '4']
            with (out / 'logs' / f'{name}_eval.log').open('a') as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        payload = json.loads(result.read_text())
        assert payload['n_tasks'] == 119 and payload['version'] == '0.1.5'
        return payload

    gate = out / 'BASELINE_GATE.json'
    if args.stage == 'baseline':
        raw = generate('baseline_alpha0', 0, 0)
        observed = {r['task_id']: r for r in rows(raw)}
        exact = sum(observed[r['task_id']]['raw_completion'].encode() == r['raw_completion'].encode() for r in original)
        assert exact == 119, f'Raw baseline failed: {exact}/119'
        evaluated = evaluate('baseline_alpha0', raw)
        payload = {'byte_exact': exact, 'n': 119, 'official_passed': evaluated['passed'],
                   'passed': exact == 119 and evaluated['passed'] == 0}
        gate.write_text(json.dumps(payload, indent=2) + '\n')
        assert payload['passed'], 'Official baseline must remain 0/119'
        print(json.dumps(payload))
        return
    assert gate.exists() and json.loads(gate.read_text())['passed'], 'Run --stage baseline first'
    if args.stage == 'sweep':
        arms = [(c['feature_id'], c['alpha']) for c in manifest['sweep']['candidates']]
    elif args.stage == 'curves':
        arms = [(c['feature_id'], (1 if c['alpha'] > 0 else -1) * magnitude)
                for c in manifest['selected_top5'] for magnitude in (1, 2, 4, 5)]
    else:
        arms = [(int(fid), sign * magnitude) for fid, sign in manifest['random_controls']['features'].items()
                for magnitude in (5, 1, 2, 3, 4)]
    for i, (fid, alpha) in enumerate(arms):
        if i % args.num_workers != args.worker_index:
            continue
        name = f'f{fid}_{"pos" if alpha > 0 else "neg"}{abs(alpha)}'
        raw = generate(name, fid, alpha)
        result = evaluate(name, raw)
        print(json.dumps({'stage': args.stage, 'feature': fid, 'alpha': alpha,
                          'passed': result['passed'], 'n': result['n_tasks']}), flush=True)


if __name__ == '__main__':
    main()
