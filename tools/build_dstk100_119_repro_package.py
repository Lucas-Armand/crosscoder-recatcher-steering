#!/usr/bin/env python3
"""Audit existing outputs and publish the frozen 119-task package, without GPU work."""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'reproducibility/dstk100_119_v1'
FIGURES = ROOT / 'presentation/figures/dstk100_119_v1'
SCREEN = ROOT / 'reports/focused_subtype_screening_dstk100_contamination_119_v1'
GATE = ROOT / 'runs/dstk100_alpha0_repro119_v1'
SWEEP = ROOT / 'runs/dstk100_focused_subtype_alpha3_119_v1'
CURVES = ROOT / 'runs/dstk100_focused_subtype_multialpha_top5_119_v1'
RANDOM = ROOT / 'runs/dstk100_random_controls_119_extension_v1'
OLD_RANDOM = ROOT / 'runs/prospective_direct_controls_20260901_deepseek'
CELLS = ['association_global', 'association_local', 'paired_global', 'paired_local']


def read(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + '\n')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def arm_stats(run, stem, baseline, expected):
    evaluation = read(run / 'evaluations' / f'{stem}_eval.json')
    generated = rows(run / 'generations' / f'{stem}_results.jsonl')
    repaired = rows(run / 'postprocessed/results_repaired' / f'{stem}_repaired.jsonl')
    wanted = set(baseline)
    assert len(generated) == len(repaired) == evaluation['n_tasks'] == expected
    assert set(evaluation['eval']) == {r['task_id'] for r in generated} == wanted
    assert evaluation['version'] == '0.1.5'
    assert all(r['generation_seed'] == 1000 + 100 * int(r['task_idx']) for r in generated)
    passed = sorted(k for k, v in evaluation['eval'].items() if any(r['correct'] for r in v))
    assert len(passed) == evaluation['passed']
    return {'feature_id': generated[0]['feature_id'], 'alpha': generated[0]['alpha'],
            'n': expected, 'passed': len(passed), 'pass_tasks': passed,
            'raw_changed': sum(r['raw_completion'] != baseline[r['task_id']]['raw_completion'] for r in generated),
            'evaluated_code_changed': sum(r['candidate_code_repaired'] != baseline[r['task_id']]['code'] for r in repaired)}


def render_figures():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'svg.fonttype': 'none', 'pdf.fonttype': 42})
    ink, gray, teal = '#14243F', '#596579', '#139C9B'
    purple, orange = '#7654CF', '#E78B24'
    FIGURES.mkdir(parents=True, exist_ok=True)

    def setup(ax):
        ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')

    def card(ax, x, y, w, h, title, body, color):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.008,rounding_size=0.015',
                                   edgecolor='#CCD1D6', facecolor='white', linewidth=0.8))
        ax.plot([x + .008, x + w - .008], [y + h - .015] * 2, color=color, lw=3)
        ax.text(x + .012, y + h - .07, title, color=ink, fontsize=9, fontweight='bold', va='top')
        ax.text(x + .012, y + h - .19, body, color=gray, fontsize=8.5, va='top', linespacing=1.5)

    def method(ax):
        setup(ax)
        ax.text(.015, .97, 'FEATURE SCREENING: STABLE ERROR-FOCUSED CONTRASTS', color=ink,
                fontsize=12, weight='bold', va='top')
        content = [('3 SUMMARIES', 'max · mean\nactive fraction'),
                   ('PER TASK', 'Association: $s^V$\nPaired: $s^V-s^B$'),
                   ('OBSERVED EFFECT', 'mean focal group\n− mean comparison'),
                   ('200 PERMUTATIONS', 'shuffle subtype labels\nwithin the selected\ntransition population'),
                   ('E/V', 'observed effect\n÷ permutation SD')]
        for i, (title, body) in enumerate(content):
            x = .018 + i * .198
            card(ax, x, .32, .175, .50, title, body, teal if i < 4 else '#D5A120')
            if i < 4:
                ax.annotate('', xy=(x + .196, .54), xytext=(x + .178, .54),
                            arrowprops={'arrowstyle': '->', 'color': teal, 'lw': 1.5})
        ax.text(.018, .23, 'Support: ≥12 focal tasks (DeepSeek); ≥5 (CodeLlama)', fontsize=9, color=ink)
        ax.text(.018, .14, 'Retain the summary with largest |E/V| per feature; nominate top 10 per cell.', fontsize=9, color=ink)
        ax.text(.018, .05, 'Both signs are retained. E/V is a permutation signal-to-noise score, not a z-score or p-value.',
                fontsize=8.5, color=gray)

    def cells(ax):
        setup(ax)
        ax.text(.015, .97, 'FOUR ERROR-FOCUSED SCREENING CELLS PER MODEL', fontsize=12, color=ink,
                weight='bold', va='top')
        for x, model, color, pop, pool in [(.02, 'DEEPSEEK BASE → FINE-TUNED', purple,
            'Within 215 improvements\n119 contamination cases vs. 96 other improvements', 38),
            (.515, 'CODELLAMA BASE → MERGED', orange,
            'Within 291 regressions\n50 logic/runtime cases vs. 241 other regressions', 32)]:
            ax.text(x, .83, model, fontsize=10, color=color, weight='bold')
            ax.text(x, .77, pop, fontsize=9, color=gray, va='top', linespacing=1.5)
            for xx, design in [(x, 'ASSOCIATION'), (x + .235, 'PAIRED')]:
                for yy, scope in [(.40, 'GLOBAL'), (.19, 'LOCAL')]:
                    card(ax, xx, yy, .213, .17, design + ' · ' + scope, '', color)
            ax.text(x, .12, f'40 nominations → {pool} unique features', fontsize=9, color=color, weight='bold')
        ax.text(.018, .04, 'Local: ±10% around normalized first textual divergence; an anchor, not an annotated error boundary.',
                fontsize=8.5, color=gray)

    for name, draw, height in [('screening_method', method, 3.4), ('screening_cells', cells, 4.0)]:
        fig, ax = plt.subplots(figsize=(10, height))
        draw(ax); fig.subplots_adjust(left=.01, right=.99, top=.98, bottom=.02)
        for extension in ('svg', 'pdf', 'png'):
            fig.savefig(FIGURES / f'{name}.{extension}', dpi=240, facecolor='white')
        plt.close(fig)
    fig, axs = plt.subplots(2, 1, figsize=(10, 7.4), gridspec_kw={'height_ratios': [3.4, 4.0]})
    method(axs[0]); cells(axs[1]); fig.subplots_adjust(left=.01, right=.99, top=.98, bottom=.02, hspace=.13)
    for extension in ('svg', 'pdf', 'png'):
        fig.savefig(FIGURES / f'screening_method_and_cells.{extension}', dpi=240, facecolor='white')
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--results-root', type=Path, required=True)
    parser.add_argument('--skip-bundle', action='store_true')
    args = parser.parse_args()
    PACKAGE.mkdir(parents=True, exist_ok=True)
    for folder in ('inputs', 'metadata', 'tables', 'artifacts'):
        (PACKAGE / folder).mkdir(exist_ok=True)
    taxonomy = [r for r in csv.DictReader((ROOT / 'reports/dstk100_transition_failure_analysis_v1/transition_failure_cases.csv').open())
                if r['benchmark'] == 'bigcodebench' and r['transition'] == 'improvement']
    extracted = {side: {r['task_id']: r for r in rows(args.results_root / f'bigcodebench__deepseek_{side}_repaired.jsonl')}
                 for side in ('base', 'finetuned')}
    assert len(taxonomy) == 215
    assert all(extracted['base'][r['task_id']]['candidate_code_repaired'] == r['failing_code'] for r in taxonomy)
    assert all(extracted['finetuned'][r['task_id']]['candidate_code_repaired'] == r['passing_code'] for r in taxonomy)
    write(PACKAGE / 'metadata/screening_input_audit.json', {'transition_tasks': 215,
          'base_code_exact_to_taxonomy': 215, 'finetuned_code_exact_to_taxonomy': 215,
          'source_files': {f'bigcodebench__deepseek_{side}_repaired.jsonl': sha(args.results_root / f'bigcodebench__deepseek_{side}_repaired.jsonl')
                           for side in ('base', 'finetuned')}})
    gate = read(GATE / 'audit/BASELINE_REPRODUCTION.json')
    assert gate['n'] == gate['exact_reference'] == 119 and gate['byte_exact_all']
    assert read(RANDOM / 'ALPHA0_GATE.json') == {'expected': 39, 'byte_exact': 39, 'official_passed': 0, 'passed': True}
    assert all((p / 'EVALUATION_COMPLETE').exists() for p in (SWEEP, CURVES, RANDOM))
    sweep_manifest = read(SWEEP / 'EXPERIMENT_MANIFEST.json')
    candidates = sweep_manifest['candidates']
    assert len(candidates) == 38
    source_input = rows(SWEEP / 'input.jsonl')
    assert {r['task_id'] for r in source_input} == {r['task_id'] for r in rows(CURVES / 'input.jsonl')}
    assert len(source_input) == len({r['task_id'] for r in source_input}) == 119
    assert all(r['seed'] == 1000 + 100 * int(r['task_idx']) for r in source_input)
    shutil.copy2(SWEEP / 'input.jsonl', PACKAGE / 'inputs/cohort119.jsonl')
    baseline_raw = {r['task_id']: r for r in rows(SWEEP / 'generations/bigcodebench__baseline_alpha0_results.jsonl')}
    baseline_code = {r['task_id']: r['candidate_code_repaired'] for r in rows(SWEEP / 'postprocessed/results_repaired/bigcodebench__baseline_alpha0_repaired.jsonl')}
    for original in source_input:
        assert baseline_raw[original['task_id']]['raw_completion'] == original['raw_completion']
        baseline_raw[original['task_id']]['code'] = baseline_code[original['task_id']]
    assert read(SWEEP / 'evaluations/bigcodebench__baseline_alpha0_eval.json')['passed'] == 0
    stats = []
    frequency = Counter()
    for c in candidates:
        stem = f'bigcodebench__f{c["feature_id"]}_{"pos" if c["alpha"] > 0 else "neg"}3'
        result = arm_stats(SWEEP, stem, baseline_raw, 119)
        frequency.update(result['pass_tasks'])
        stats.append({**c, **result})
    stats.sort(key=lambda r: (-r['passed'], -r['abs_ev'], r['feature_id']))
    assert sum(r['passed'] for r in stats) == 174 and len(frequency) == 19
    top5 = stats[:5]
    assert [r['feature_id'] for r in top5] == [4810, 2468, 2621, 10539, 6895]
    curves = []
    for c in top5:
        for magnitude in (1, 2, 3, 4, 5):
            if magnitude == 3:
                result = next(r for r in stats if r['feature_id'] == c['feature_id'])
            else:
                stem = f'bigcodebench__f{c["feature_id"]}_{"pos" if c["alpha"] > 0 else "neg"}{magnitude}'
                result = arm_stats(CURVES, stem, baseline_raw, 119)
            curves.append(result)
    random = []
    for fid, sign in ((15173, -1), (6023, 1), (605, 1)):
        for magnitude in (1, 2, 3, 4, 5):
            name = f'bigcodebench__random_f{fid}_{sign * magnitude:+d}'
            evaluation = read(RANDOM / 'combined_evaluations' / f'{name}_eval.json')
            raw = rows(RANDOM / 'combined_generations' / f'{name}_results.jsonl')
            repaired = rows(RANDOM / 'combined_postprocessed/results_repaired' / f'{name}_repaired.jsonl')
            assert evaluation['n_tasks'] == len(raw) == len(repaired) == 119
            assert set(evaluation['eval']) == set(baseline_raw)
            assert all(r['generation_seed'] == baseline_raw[r['task_id']]['generation_seed'] for r in raw)
            random.append({'feature_id': fid, 'alpha': sign * magnitude, 'n': 119, 'passed': evaluation['passed'],
                'pass_tasks': sorted(k for k, v in evaluation['eval'].items() if any(r['correct'] for r in v)),
                'raw_changed': sum(r['raw_completion'] != baseline_raw[r['task_id']]['raw_completion'] for r in raw),
                'evaluated_code_changed': sum(r['candidate_code_repaired'] != baseline_code[r['task_id']] for r in repaired)})
    assert [r['passed'] for r in random if abs(r['alpha']) == 5] == [7, 6, 6]
    screening_rows = []
    for model, report in [('DeepSeek', SCREEN), ('CodeLlama', ROOT / 'reports/focused_subtype_screening_codellama_wrong_logic_v1')]:
        top = {cell: list(csv.DictReader((report / f'{cell}_absolute.csv').open()))[:10] for cell in CELLS}
        count = Counter(r['feature_id'] for values in top.values() for r in values)
        for cell, ranked in top.items():
            for row in ranked:
                screening_rows.append({'model': model, 'cell': cell, **row,
                                       'repeated_across_cells': count[row['feature_id']] > 1})
    write(PACKAGE / 'tables/screening_top10.json', screening_rows)
    from export_crosscoder_screening_table import generate as export_screening_table
    export_screening_table(ROOT)
    write(PACKAGE / 'tables/sweep.json', stats)
    write(PACKAGE / 'tables/target_curves.json', curves)
    write(PACKAGE / 'tables/random_curves.json', random)
    summary = {'baseline_passed': 0, 'n': 119, 'sweep_features': 38,
               'sweep_feature_task_corrections': 174, 'sweep_unique_corrected_tasks': 19,
               'features_correcting_any_task': sum(r['passed'] > 0 for r in stats),
               'task_susceptibility': frequency.most_common(), 'top5': top5,
               'target_alpha5': [r for r in curves if abs(r['alpha']) == 5],
               'random_alpha5': [r for r in random if abs(r['alpha']) == 5]}
    write(PACKAGE / 'results_summary.json', summary)
    checkpoint = ROOT / 'runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt'
    canonical = read(checkpoint.parent / 'CANONICAL_CHECKPOINT.json')
    assert canonical['canonical_step'] == 10000 and canonical['top_k'] == 100
    manifest = {'release_id': 'dstk100_119_v1', 'status': 'canonical_direct_protocol', 'date': '2026-10-13',
        'scope': 'DeepSeek BigCodeBench contamination improvements: all 119 taxonomy cases; direct interventions.',
        'supersedes_for_this_study': '80-task contamination subset; historical artifacts remain immutable.',
        'code_base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'models': {'a': 'deepseek-ai/deepseek-coder-6.7b-base', 'b': 'JetBrains/deepseek-coder-6.7B-kexer'},
        'checkpoint': {'path': str(checkpoint.relative_to(ROOT)), 'sha256': sha(checkpoint), 'canonical_step': 10000,
                       'artifact_manifest': 'manifests/dstk100_v1.json'},
        'cohort': {'positives': 119, 'comparison': 96, 'transition_population': 215,
                   'category': 'generated_test_import_contamination', 'taxonomy_validation': 'Original exploratory classification; no new annotation validation in this release.'},
        'screening': {**read(SCREEN / 'run_summary.json'), 'unique_candidates': 38,
                      'score_interpretation': 'Not a z-score, p-value or multiplicity-corrected significance claim.'},
        'generation': sweep_manifest['generation'], 'intervention': sweep_manifest['intervention'],
        'sweep': {'candidates': candidates, 'ranking': 'official corrections descending, absolute E/V descending, feature ID ascending'},
        'selected_top5': [{k: c[k] for k in ('feature_id', 'alpha', 'source_cells', 'summary', 'ev', 'abs_ev')} for c in top5],
        'random_controls': {'features': {'15173': -1, '6023': 1, '605': 1},
                            'selection': 'Exact IDs and signs frozen in the 2026-09-01 prospective selection; no outcome-based resampling.',
                            'construction': 'Reuse 80 archived tasks plus 39 new tasks per arm, with disjoint IDs and identical extraction.',
                            'magnitudes': [1, 2, 3, 4, 5]},
        'evaluation': {'extraction': 'tools/code_extraction.py and tools/reprocess_outputs_minimal.py',
                       'harness': 'tools/evaluate_bigcodebench_subset.py', 'bigcodebench_version': '0.1.5'},
        'external_activation_artifacts': 'gs://data-intelligence-bucket/tests/recatcher_crosscoder_humaneval/crosscoder_deepseek_base_finetuned_layer16_sametext_topk100_10k_v1/',
        'canonical_runs': [str(p.relative_to(ROOT)) for p in (GATE, SWEEP, CURVES, RANDOM)],
        'limitations': ['One generation seed per task; same-cohort exploratory selection and intervention.',
                        'Comparison with three frozen random latent directions, not a population-wide specificity test.',
                        'CodeLlama results remain the separately documented 50-task historical study.']}
    write(PACKAGE / 'manifest.json', manifest)
    pointer = ROOT / 'manifests/dstk100_119_v1.json'
    write(pointer, {'release_id': 'dstk100_119_v1', 'status': 'canonical_direct_protocol',
                    'manifest': 'reproducibility/dstk100_119_v1/manifest.json',
                    'manifest_sha256': sha(PACKAGE / 'manifest.json'),
                    'historical_manifests_modified': False})
    for name, source in [('raw_baseline_reproduction.json', GATE / 'audit/BASELINE_REPRODUCTION.json'),
                         ('extension_baseline_gate.json', RANDOM / 'ALPHA0_GATE.json'),
                         ('sweep_manifest.json', SWEEP / 'EXPERIMENT_MANIFEST.json'),
                         ('target_curve_manifest.json', CURVES / 'RUN_MANIFEST.json'),
                         ('random_extension_manifest.json', RANDOM / 'EXPERIMENT_MANIFEST.json'),
                         ('canonical_checkpoint.json', checkpoint.parent / 'CANONICAL_CHECKPOINT.json')]:
        shutil.copy2(source, PACKAGE / 'metadata' / name)
    versions = {name: importlib.metadata.version(name) for name in ('torch', 'transformers', 'numpy', 'bitsandbytes', 'matplotlib')}
    write(PACKAGE / 'metadata/runtime_versions.json', versions)
    render_figures()
    if not args.skip_bundle:
        inputs = [ROOT / 'reports/paper_v1_v4_evaluation_labels.csv',
                  ROOT / 'reports/dstk100_transition_failure_analysis_v1/transition_failure_cases.csv',
                  ROOT / 'runs/same_text_activations/deepseek_base_finetuned_layer16_rms/capture_manifest.json',
                  checkpoint.parent / 'config.json', checkpoint.parent / 'CANONICAL_CHECKPOINT.json']
        inputs += [p for p in SCREEN.iterdir() if p.suffix in ('.csv', '.json')]
        for run in (GATE, SWEEP, CURVES, RANDOM):
            for folder in ('generations', 'evaluations', 'postprocessed', 'combined_generations', 'combined_evaluations', 'combined_postprocessed', 'audit'):
                if (run / folder).exists():
                    inputs += [p for p in (run / folder).rglob('*') if p.is_file() and p.suffix in ('.json', '.jsonl')]
            inputs += [p for p in run.glob('*.json')] + [p for p in run.glob('input*.jsonl')]
        # Only the random latent outputs are archived from the historical 80-task run.
        inputs += [OLD_RANDOM / 'EXPERIMENT_MANIFEST.json', OLD_RANDOM / 'ALPHA0_GATE.json']
        for folder in ('generations', 'evaluations'):
            inputs += [p for p in (OLD_RANDOM / folder).iterdir() if 'random_f' in p.name or 'baseline_alpha0' in p.name]
        raw_hashes = {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(inputs))}
        write(PACKAGE / 'metadata/raw_artifact_checksums.json', raw_hashes)
        archive = PACKAGE / 'artifacts/canonical_outputs.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            for path in sorted(set(inputs)):
                tar.add(path, arcname=str(path.relative_to(ROOT)), recursive=False)
            for model in ('base', 'finetuned'):
                path = args.results_root / f'bigcodebench__deepseek_{model}_repaired.jsonl'
                assert path.exists()
                tar.add(path, arcname=f'reproducibility/dstk100_119_v1/restored_results/{path.name}', recursive=False)
        print('Raw archive bytes:', archive.stat().st_size)
    files = [p for p in PACKAGE.rglob('*') if p.is_file() and p.name != 'checksums.json']
    files += [p for p in FIGURES.iterdir() if p.is_file()]
    files.append(pointer)
    files += [ROOT / 'tools' / name for name in ('screen_focused_subtype_topk.py', 'run_dstk100_119_protocol.py',
              'run_dstk100_random_controls_119_extension.py', 'build_dstk100_119_repro_package.py', 'export_crosscoder_screening_table.py',
              'run_crosscoder_intervention.py', 'code_extraction.py', 'reprocess_outputs_minimal.py', 'evaluate_bigcodebench_subset.py')]
    write(PACKAGE / 'checksums.json', {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(files))})
    print(json.dumps({k: summary[k] for k in ('n', 'sweep_features', 'sweep_feature_task_corrections', 'sweep_unique_corrected_tasks')}, indent=2))


if __name__ == '__main__':
    main()
