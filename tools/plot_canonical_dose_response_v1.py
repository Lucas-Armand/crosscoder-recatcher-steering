#!/usr/bin/env python3
"""Plot the frozen direct target-versus-random dose curves; no model execution."""
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator, PercentFormatter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/dose_response_section66_20261015'


def read(path):
    return json.loads(path.read_text())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ds = ROOT / 'reproducibility/dstk100_119_v1/tables'
    cl_source = ROOT / 'reports/prospective_direct_controls_20260902/summary.json'
    cl = read(cl_source)['codellama']
    assert cl['n'] == 50 and cl['baseline_passed'] == 0
    gate_path = ROOT / 'runs/prospective_direct_controls_20260901_codellama/ALPHA0_GATE.json'
    gate = read(gate_path)
    assert gate['passed'] and gate['byte_exact'] == gate['expected'] == 50
    data = {'DeepSeek': {'n': 119, 'target': read(ds / 'target_curves.json'),
                         'random': read(ds / 'random_curves.json')},
            'CodeLlama': {'n': 50, 'target': [], 'random': []}}
    for row in cl['arms']:
        if row['kind'] in ('target', 'random'):
            data['CodeLlama'][row['kind']].append({'feature_id': row['id'], 'alpha': row['alpha'],
                'n': 50, 'passed': row['passed'], 'pass_tasks': row['pass_tasks'],
                'raw_changed': row['raw_changed'], 'evaluated_code_changed': row['extracted_changed']})
    expected = {'DeepSeek': {'target': {4810:-1, 2468:-1, 2621:-1, 10539:-1, 6895:1},
                             'random': {15173:-1, 6023:1, 605:1}},
                'CodeLlama': {'target': {7692:-1, 10818:-1, 5642:-1, 11596:-1, 4309:-1},
                              'random': {14260:-1, 2947:1, 3698:1}}}
    for model, datum in data.items():
        for kind in ('target', 'random'):
            records = datum[kind]
            assert len(records) == (25 if kind == 'target' else 15)
            seen = {(r['feature_id'], abs(r['alpha'])) for r in records}
            assert seen == {(fid, mag) for fid in expected[model][kind] for mag in (1,2,3,4,5)}
            for row in records:
                assert row['n'] == datum['n'] and 0 <= row['passed'] <= row['evaluated_code_changed'] <= row['n']
                assert len(set(row['pass_tasks'])) == row['passed']
                assert (1 if row['alpha'] > 0 else -1) == expected[model][kind][row['feature_id']]
    # Check the CodeLlama target alpha-three points directly against the sweep evaluations.
    cl_sweep = ROOT / 'runs/focused_subtype_codellama_alpha3_canonical_v1'
    for row in data['CodeLlama']['target']:
        if abs(row['alpha']) == 3:
            path = cl_sweep / 'evaluations' / f'bigcodebench__f{row["feature_id"]}_neg3_eval.json'
            evaluation = read(path)
            passed = sorted(k for k, vals in evaluation['eval'].items() if any(x['correct'] for x in vals))
            assert evaluation['n_tasks'] == 50 and evaluation['passed'] == row['passed']
            assert passed == sorted(row['pass_tasks'])
    (OUT / 'curves.json').write_text(json.dumps(data, indent=2) + '\n')
    with (OUT / 'curves.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['model','kind','feature_id','alpha','n','passed','raw_changed','evaluated_code_changed'])
        writer.writeheader()
        for model, datum in data.items():
            for kind in ('target', 'random'):
                for row in datum[kind]:
                    writer.writerow({'model': model, 'kind': kind,
                        **{k: row[k] for k in ('feature_id','alpha','n','passed','raw_changed','evaluated_code_changed')}})
    plt.rcParams.update({'font.family':'DejaVu Sans', 'pdf.fonttype':42, 'svg.fonttype':'none',
                         'font.size':11, 'axes.labelsize':12, 'axes.titlesize':12, 'xtick.labelsize':11,
                         'ytick.labelsize':11, 'legend.fontsize':9.5})
    target_colors = ['#5E3C99','#1B9E77','#D95F02','#377EB8','#CC79A7']
    markers = ['o','s','^','D','v']
    for metric, filename, ylabel in [('passed','official_corrections','Tasks corrected (%)'),
                                       ('evaluated_code_changed','evaluated_code_changes','Changed evaluated code (%)')]:
        fig, axs = plt.subplots(1, 2, figsize=(8.6, 5.4))
        for ax, (model, datum) in zip(axs, data.items()):
            ax.axvline(3, color='#A0A0A0', ls=':', lw=1, zorder=0)
            for kind in ('target', 'random'):
                for index, (fid, sign) in enumerate(expected[model][kind].items()):
                    records = sorted((r for r in datum[kind] if r['feature_id'] == fid), key=lambda r: abs(r['alpha']))
                    values = [0] + [r[metric] * 100 / datum['n'] for r in records]
                    label = f'{fid} ({"+" if sign > 0 else "−"})' + (' R' if kind == 'random' else '')
                    ax.plot([0,1,2,3,4,5], values, label=label,
                            color=target_colors[index] if kind == 'target' else ['#252525','#777777','#AAAAAA'][index],
                            marker=markers[index] if kind == 'target' else ['x','+','*'][index],
                            linestyle='-' if kind == 'target' else '--', linewidth=1.6, markersize=5)
            ax.set_title(f'{model} {"base" if model == "DeepSeek" else "merged"} (n={datum["n"]})',
                         color='#7654CF' if model == 'DeepSeek' else '#C66B10', pad=10)
            ax.set_xlabel(r'Steering magnitude $|\alpha|$')
            ax.set_xticks(range(6));ax.set_xlim(-.12,5.15);ax.set_ylabel(ylabel)
            if metric == 'passed':
                ax.set_ylim(-.3,13)
                ax.yaxis.set_major_formatter(PercentFormatter(100))
            else:
                ax.set_ylim(-1,65);ax.yaxis.set_major_formatter(PercentFormatter(100))
            ax.grid(axis='y', alpha=.25)
            ax.spines[['top','right']].set_visible(False)
            ax.legend(loc='upper center', bbox_to_anchor=(.5,-.23), ncol=2, frameon=False,
                      columnspacing=.9, handlelength=2.1)
        fig.subplots_adjust(left=.08, right=.99, top=.88, bottom=.34, wspace=.39)
        for suffix in ('pdf','svg','png'):
            fig.savefig(OUT / f'{filename}.{suffix}', dpi=240, facecolor='white', bbox_inches='tight', pad_inches=.12)
        plt.close(fig)
    summaries = {}
    for model, datum in data.items():
        by_dose = {}
        for mag in (1,2,3,4,5):
            by_dose[mag] = {}
            for kind in ('target','random'):
                rs = [r for r in datum[kind] if abs(r['alpha']) == mag]
                values = sorted(r['passed'] for r in rs)
                by_dose[mag][kind] = {'passes':values,'median':values[len(values)//2],
                    'mean':sum(values)/len(values),'maximum':max(values),
                    'changed_code_range':[min(r['evaluated_code_changed'] for r in rs),max(r['evaluated_code_changed'] for r in rs)]}
        summaries[model] = {'n':datum['n'],'by_dose':by_dose}
    (OUT / 'summary.json').write_text(json.dumps(summaries, indent=2) + '\n')
    inputs = [ds/'target_curves.json',ds/'random_curves.json',cl_source,gate_path]
    audit = {'status':'validated','arms':80,'no_generation_executed':True,
             'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
             'checks':['All 80 arms have expected model, feature, sign, dose and cohort size.',
                       'All correction counts equal distinct official pass task IDs.',
                       'CodeLlama selected alpha-three task outcomes match the canonical sweep.',
                       'Changed counts refer to extracted evaluated code, not raw output.',
                       'Only the current 119-task DeepSeek results are used; historical 80-task targets excluded.']}
    (OUT / 'audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    print(json.dumps({m: v['by_dose'][5] for m,v in summaries.items()}, indent=2))


if __name__ == '__main__':
    main()
