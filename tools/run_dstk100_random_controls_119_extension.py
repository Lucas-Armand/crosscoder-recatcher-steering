#!/usr/bin/env python3
"""Extend the frozen 80-task random-latent controls to the missing 39 tasks."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

REPO = Path('/home/lucas/crosscoder-recatcher-steering')
RUN = Path('runs/dstk100_random_controls_119_extension_v1')
OLD = Path('runs/prospective_direct_controls_20260901_deepseek')
FULL = Path('runs/dstk100_focused_subtype_multialpha_top5_119_v1/input.jsonl')
CHECKPOINT = Path('runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt')
SIGNS = {15173: -1, 6023: 1, 605: 1}
MAGS = (5, 1, 2, 3, 4)  # Prioritize the dose requested for the comparison.
PYTHON = REPO / '.venv/bin/python'
EVAL_PYTHON = '/home/lucas/venvs/bigcodebench015/bin/python'


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
    temp.replace(path)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def prepare():
    full = read_rows(FULL)
    original = json.loads((OLD / 'EXPERIMENT_MANIFEST.json').read_text())
    old_input = Path(original['cohort_input'])
    old = read_rows(old_input)
    old_by_id = {row['task_id']: row for row in old}
    assert len(full) == 119 and len(old_by_id) == 80
    assert len({r['task_id'] for r in full}) == 119
    assert set(old_by_id).issubset({r['task_id'] for r in full})
    assert {int(k): v for k, v in original['random_latents'].items()} == SIGNS
    assert json.loads((OLD / 'ALPHA0_GATE.json').read_text())['passed']
    assert json.loads(Path('runs/dstk100_alpha0_repro119_v1/audit/BASELINE_REPRODUCTION.json').read_text())['byte_exact_all']
    for row in full:
        assert row['seed'] == 1000 + 100 * int(row['task_idx'])
        if row['task_id'] in old_by_id:
            for field in ('prompt', 'raw_completion', 'seed', 'task_idx', 'entry_point'):
                assert row[field] == old_by_id[row['task_id']][field], (row['task_id'], field)
    missing = [row for row in full if row['task_id'] not in old_by_id]
    assert len(missing) == 39
    for folder in ('generations', 'logs', 'evaluations', 'combined_generations', 'combined_evaluations'):
        (RUN / folder).mkdir(parents=True, exist_ok=True)
    for fid, sign in SIGNS.items():
        for mag in MAGS:
            name = f'random_f{fid}_{sign * mag:+d}'
            archived = read_rows(OLD / 'generations' / f'bigcodebench__{name}_results.jsonl')
            assert {r['task_id'] for r in archived} == set(old_by_id)
            old_eval = json.loads((OLD / 'evaluations' / f'bigcodebench__{name}_eval.json').read_text())
            assert old_eval['n_tasks'] == 80 and old_eval['version'] == '0.1.5'
            for row in archived:
                assert row['generation_seed'] == old_by_id[row['task_id']]['seed']
                assert row['alpha'] == sign * mag and row['feature_id'] == fid
                for key, expected in {'temperature_config': 0.2, 'top_p_config': 0.95,
                                      'max_new_tokens_config': 512, 'model_dtype_config': 'nf4',
                                      'generation_backend': 'paired_cached', 'target_side': 'a',
                                      'token_scope': 'last_token', 'intervention_mode': 'traditional'}.items():
                    assert row[key] == expected, (name, key, row[key])
    manifest = {
        'experiment': 'DSTK100 random latent controls: frozen 80 + missing 39',
        'original_run': str(OLD), 'full_input': str(FULL), 'old_tasks': 80,
        'new_tasks': 39, 'combined_tasks': 119, 'random_latents': SIGNS,
        'selection': 'Reuse the exact previously sampled IDs and signs; no resampling.',
        'magnitudes': [1, 2, 3, 4, 5], 'execution_order': list(MAGS),
        'additional_steered_generations': 585, 'fresh_alpha0_generations': 39,
        'generation': original['generation'], 'intervention': original['intervention'],
        'seed_rule': original['seed_rule'], 'missing_task_ids': [r['task_id'] for r in missing],
        'gpu_uuid': 'GPU-b254e6d2-3821-d871-cffc-72e7751f86aa',
        'workers': 2, 'baseline_gate': 'Fresh alpha=0 exact raw bytes, seed and task IDs; 0/39 official passes.',
        'reuse': 'Archived 80 generations and official evaluations remain untouched; combine with new 39.',
        'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'sha256': {str(path): sha(path) for path in (FULL, old_input, CHECKPOINT,
                    Path('tools/run_crosscoder_intervention.py'), Path('tools/code_extraction.py'),
                    Path('tools/evaluate_bigcodebench_subset.py'))},
    }
    manifest_path = RUN / 'EXPERIMENT_MANIFEST.json'
    if manifest_path.exists():
        assert json.loads(manifest_path.read_text()) == manifest, 'Existing run configuration differs'
    else:
        dump(manifest_path, manifest)
        write_rows(RUN / 'input_missing39.jsonl', missing)
    return missing


def generate(name, fid, alpha):
    output = RUN / 'generations' / f'bigcodebench__{name}_results.jsonl'
    wanted = read_rows(RUN / 'input_missing39.jsonl')
    existing = read_rows(output) if output.exists() else []
    by_id = {row['task_id']: row for row in existing}
    assert len(existing) == len(by_id)
    assert set(by_id).issubset({r['task_id'] for r in wanted})
    for row in existing:
        assert row['feature_id'] == fid and row['alpha'] == alpha
        assert row['generation_seed'] == 1000 + 100 * int(row['task_idx'])
    pending = [row for row in wanted if row['task_id'] not in by_id]
    if pending:
        pending_input = RUN / 'logs' / f'{name}_pending.jsonl'
        pending_output = RUN / 'logs' / f'{name}_pending_results.jsonl'
        write_rows(pending_input, pending)
        command = [str(PYTHON), 'tools/run_crosscoder_intervention.py',
                   '--checkpoint', str(CHECKPOINT), '--model-a-id', 'deepseek-ai/deepseek-coder-6.7b-base',
                   '--model-b-id', 'JetBrains/deepseek-coder-6.7B-kexer',
                   '--tokenizer-id', 'deepseek-ai/deepseek-coder-6.7b-base', '--target-side', 'a',
                   '--layer', '16', '--intervention-mode', 'traditional', '--token-scope', 'last_token',
                   '--generation-backend', 'paired_cached', '--input-jsonl', str(pending_input),
                   '--max-new-tokens', '512', '--temperature', '0.2', '--top-p', '0.95',
                   '--seed', '1000', '--device-a', 'cuda:0', '--dtype', 'nf4', '--trust-remote-code',
                   '--feature-id', str(fid), '--alpha', str(alpha), '--output-jsonl', str(pending_output)]
        dump(RUN / 'logs' / f'{name}_command.json', {'argv': command})
        with (RUN / 'logs' / f'{name}.log').open('a') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        generated = read_rows(pending_output)
        assert len(generated) == len(pending)
        by_id.update({r['task_id']: r for r in generated})
        write_rows(output, [by_id[row['task_id']] for row in wanted])
    return output


def evaluate(name, raw, combined=False):
    from reprocess_outputs_minimal import process_raw_jsonl
    post_dir = RUN / ('combined_postprocessed' if combined else 'postprocessed')
    process_raw_jsonl(raw, post_dir, False)
    samples = post_dir / 'samples_for_external_eval' / f'bigcodebench__{name}_samples.jsonl'
    result = RUN / 'evaluations' / f'bigcodebench__{name}_eval.json'
    if not result.exists():
        with (RUN / 'logs' / f'{name}_eval.log').open('a') as log:
            subprocess.run([EVAL_PYTHON, 'tools/evaluate_bigcodebench_subset.py', '--samples', str(samples),
                            '--output', str(result), '--parallel', '4'], stdout=log,
                           stderr=subprocess.STDOUT, check=True)
    return json.loads(result.read_text())


def combine(name, new_raw, new_eval):
    full = read_rows(FULL)
    old_raw = read_rows(OLD / 'generations' / f'bigcodebench__{name}_results.jsonl')
    additional = read_rows(new_raw)
    by_id = {row['task_id']: row for row in old_raw + additional}
    assert len(by_id) == 119 and len(old_raw) + len(additional) == 119
    combined_raw = RUN / 'combined_generations' / f'bigcodebench__{name}_results.jsonl'
    write_rows(combined_raw, [by_id[row['task_id']] for row in full])
    from reprocess_outputs_minimal import process_raw_jsonl
    process_raw_jsonl(combined_raw, RUN / 'combined_postprocessed', False)
    old_eval = json.loads((OLD / 'evaluations' / f'bigcodebench__{name}_eval.json').read_text())
    assert set(old_eval['eval']).isdisjoint(new_eval['eval'])
    merged = {**old_eval['eval'], **new_eval['eval']}
    assert len(merged) == 119
    samples = read_rows(RUN / 'combined_postprocessed' / 'samples_for_external_eval' / f'bigcodebench__{name}_samples.jsonl')
    for sample in samples:
        assert merged[sample['task_id']][0]['solution'] == sample['solution'], 'Extraction differs from archived evaluation'
    payload = {**new_eval, 'n_tasks': 119, 'passed': old_eval['passed'] + new_eval['passed'],
               'eval': dict(sorted(merged.items())), 'provenance': {'archived_tasks': 80, 'new_tasks': 39,
               'archived_eval': str(OLD / 'evaluations' / f'bigcodebench__{name}_eval.json'),
               'new_eval': str(RUN / 'evaluations' / f'bigcodebench__{name}_eval.json')}}
    dump(RUN / 'combined_evaluations' / f'bigcodebench__{name}_eval.json', payload)
    print(json.dumps({'arm': name, 'old80_passed': old_eval['passed'],
                      'new39_passed': new_eval['passed'], 'combined119_passed': payload['passed']}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--worker-index', type=int, choices=(0, 1), default=0)
    args = parser.parse_args()
    os.chdir(REPO)
    if args.prepare:
        prepare()
        print('Prepared 15 arms x 39 missing tasks; 80 archived tasks reused.')
        return
    rows = read_rows(RUN / 'input_missing39.jsonl')
    gate_path = RUN / 'ALPHA0_GATE.json'
    if args.worker_index == 0 and not gate_path.exists():
        baseline = generate('baseline_alpha0', 0, 0)
        generated = {row['task_id']: row for row in read_rows(baseline)}
        exact = sum(generated[row['task_id']]['raw_completion'].encode() == row['raw_completion'].encode() for row in rows)
        assert exact == 39, f'Baseline byte reproduction failed: {exact}/39'
        baseline_eval = evaluate('baseline_alpha0', baseline)
        gate = {'expected': 39, 'byte_exact': exact, 'official_passed': baseline_eval['passed'],
                'passed': exact == 39 and baseline_eval['passed'] == 0}
        dump(gate_path, gate)
    while not gate_path.exists():
        time.sleep(3)
    assert json.loads(gate_path.read_text())['passed'], 'Baseline gate failed'
    arms = [(fid, sign * mag) for mag in MAGS for fid, sign in SIGNS.items()]
    for index, (fid, alpha) in enumerate(arms):
        if index % 2 != args.worker_index:
            continue
        name = f'random_f{fid}_{alpha:+d}'
        print(f'Starting {name}', flush=True)
        raw = generate(name, fid, alpha)
        new_eval = evaluate(name, raw)
        combine(name, raw, new_eval)
    (RUN / f'WORKER_{args.worker_index}_COMPLETE').touch()
    if all((RUN / f'WORKER_{i}_COMPLETE').exists() for i in (0, 1)):
        (RUN / 'EVALUATION_COMPLETE').touch()


if __name__ == '__main__':
    main()
