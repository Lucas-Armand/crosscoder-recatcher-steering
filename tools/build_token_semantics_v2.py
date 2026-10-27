"""Token-only feature interpretation from frozen offline activations; no inference."""
import ast
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from analyze_4309_behavior_hypothesis_v1 import function, statements, descendants
from plot_section67_clouds_overlap_v1 import cloud

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'reports/section67_semantic_temporal_20261019_v1'
OUT = ROOT / 'reports/feature_token_semantics_20261027_v1'
TAX = ROOT / 'reports/codellama_base_merged_topk100_v1_regression_taxonomy/regression_failure_cases.csv'

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    arrays = np.load(SRC / 'codellama_feature_activations.npz')
    tax = {r['task_id']: r for r in csv.DictReader(TAX.open()) if r['benchmark'] == 'bigcodebench'}
    tasks = json.loads((ROOT / 'reports/codellama4309_temporal_return_visuals_20261019_v1/first_activation_contexts.json').read_text())
    records = []
    census = Counter()
    for tid in sorted(tasks, key=lambda x: int(x.split('/')[-1])):
        code = tax[tid]['merged_code']
        f = function(code)
        return_lines = {n.end_lineno for s in statements(f) for n in descendants(s) if isinstance(n, ast.Return)}
        allnodes = list(ast.walk(ast.parse(code)))
        lines = code.splitlines(keepends=True)
        starts = np.cumsum([0] + [len(s) for s in lines[:-1]])
        key = tid.split('/')[-1] + '__codellama_merged'
        z, offsets = arrays[key + '__z'], arrays[key + '__offsets']
        for idx, (lo, hi) in enumerate(offsets):
            lo, hi = int(lo), int(hi)
            span = code[lo:hi]
            newline_positions = [lo + k for k, c in enumerate(span) if c == '\n']
            return_end = any(code.count('\n', 0, p) + 1 in return_lines for p in newline_positions)
            family = 'Return-ending newline' if return_end else 'Other newline' if newline_positions else 'Non-newline'
            census[(family, 'all')] += 1
            if z[idx] <= 0:
                continue
            census[(family, 'active')] += 1
            if not newline_positions:
                continue
            assert len(newline_positions) == 1, 'Explicitly handle multi-newline tokens before pooling'
            line_number = code.count('\n', 0, newline_positions[0]) + 1
            line = lines[line_number - 1].rstrip('\r\n')
            stripped = line.strip()
            if return_end:
                category = 'Return statement'
            elif not stripped:
                category = 'Blank line'
            elif stripped.startswith('#'):
                category = 'Comment'
            elif stripped.endswith(':'):
                category = 'Block header'
            else:
                ending = [n for n in allnodes if isinstance(n, ast.stmt) and getattr(n, 'end_lineno', None) == line_number]
                if any(isinstance(n, ast.Raise) for n in ending):
                    category = 'Raise statement'
                elif any(isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)) for n in ending):
                    category = 'Assignment'
                else:
                    category = 'Other line'
            records.append(dict(task_id=tid, token_index=idx, token_text=span,
                start_char=lo, end_char=hi, line_number=line_number, line_text=line,
                preceding_line_category=category, activation=float(z[idx])))
    assert [census[(k, 'active')] for k in ['Return-ending newline', 'Other newline', 'Non-newline']] == [49, 92, 53]
    assert [census[(k, 'all')] for k in ['Return-ending newline', 'Other newline', 'Non-newline']] == [51, 327, 4320]
    categories = Counter(r['preceding_line_category'] for r in records)
    assert len(records) == 141 and categories['Return statement'] == 49
    summary = dict(n_tasks=50, active_newline_occurrences=len(records),
        active_newline_line_categories=dict(categories),
        fraction_active_newlines_after_return=49/141,
        token_census=[dict(category=k, total=census[(k, 'all')], active=census[(k, 'active')])
            for k in ['Return-ending newline', 'Other newline', 'Non-newline']],
        definitions=['Each active captured newline token is assigned once to the physical line it ends.',
            'Return statements use AST end lines inside task_func, excluding nested function definitions.',
            'Return may be conditional: this does not imply the last return of the function.',
            'Other categories use lexical blank/comment/header checks, then AST Raise/Assign end lines.',
            'Clouds use up to 40 token IDs active in at least 3 tasks, sized by square root of activation mass.',
            'Pooled token counts are descriptive, not independent statistical replications.'], new_inference=False)
    plt.rcParams.update({'font.size': 10, 'pdf.fonttype': 42, 'svg.fonttype': 'none'})
    fig, axs = plt.subplots(2, 2, figsize=(11.6, 7.5), gridspec_kw={'height_ratios': [1.1, 1]})
    layouts = {}
    for ax, source, title, color in [
        (axs[0, 0], 'deepseek_base', '(a) DeepSeek 4810 · base text · 119 tasks', '#7654cf'),
        (axs[0, 1], 'codellama_merged', '(b) CodeLlama 4309 · merged text · 50 tasks', '#d67a16')]:
        ax.set_axis_off()
        ax.set_title(title, color=color, fontsize=11)
    fig.subplots_adjust(left=.13, right=.98, top=.93, bottom=.12, wspace=.48, hspace=.35)
    for ax, source, color in [(axs[0,0], 'deepseek_base', '#7654cf'), (axs[0,1], 'codellama_merged', '#d67a16')]:
        stats = list(csv.DictReader((SRC / f'{source}_token_statistics.csv').open()))
        layouts[source] = cloud(ax, stats, color, 42)
        total_mass = sum(float(r['activation_sum']) for r in stats)
        newline_mass = sum(float(r['activation_sum']) for r in stats if '\n' in r['token'])
        summary[source] = dict(total_activation_mass=total_mass, newline_activation_mass=newline_mass,
            newline_mass_fraction=newline_mass/total_mass)
    ax = axs[1, 0]
    order = ['Return statement'] + [k for k, _ in categories.most_common() if k != 'Return statement']
    values = [categories[k] for k in order]
    ax.barh(range(len(order)), [100*v/141 for v in values], color=['#b9550c']+['#efa454']*(len(order)-1))
    ax.set_yticks(range(len(order)), order, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0, 50)
    for i, v in enumerate(values):
        ax.text(100*v/141+.8, i, f'{v}/141 ({100*v/141:.1f}%)', va='center', fontsize=8)
    ax.set_xlabel('Share of active newline tokens (%)', fontsize=9)
    ax.set_title('(c) Which lines end at an active newline?', fontsize=10, color='#d67a16')
    ax.grid(axis='x', alpha=.15)
    ax = axs[1, 1]
    rr = summary['token_census']
    rates = [100*r['active']/r['total'] for r in rr]
    ax.bar(range(3), rates, color=['#b9550c', '#efa454', '#f7cf9c'], width=.6)
    for i, (r, v) in enumerate(zip(rr, rates)):
        ax.text(i, v+2, f"{r['active']}/{r['total']}\n{v:.1f}%", ha='center', fontsize=9)
    ax.set_xticks(range(3), ['Return-ending\nnewline', 'Other\nnewline', 'Non-newline'], fontsize=9)
    ax.set_ylim(0, 114)
    ax.set_ylabel('Tokens with positive activation (%)', fontsize=9)
    ax.set_title('(d) How often does each token category activate?', fontsize=10, color='#d67a16')
    ax.grid(axis='y', alpha=.15)
    fig.text(.5, .025, 'Clouds: activation-weighted token IDs, support ≥3 tasks; NEWLINE and SPACE are visible aliases.\nPanels (c–d): all 50 original failing merged texts; pooled occurrences, not task percentages.', ha='center', fontsize=9)
    for ext in ['pdf', 'png', 'svg']:
        fig.savefig(OUT / f'token_clouds_and_line_contexts.{ext}', dpi=300, bbox_inches='tight', facecolor='white')
    for name, obj in [('SUMMARY.json', summary), ('active_newline_contexts.json', records), ('cloud_layout.json', layouts)]:
        (OUT/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n')
    inputs = [TAX, SRC/'codellama_feature_activations.npz', SRC/'deepseek_base_token_statistics.csv', SRC/'codellama_merged_token_statistics.csv']
    (OUT/'DATA_MANIFEST.json').write_text(json.dumps(dict(new_inference=False,
        sources=[dict(path=str(p.relative_to(ROOT)), sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in inputs]), indent=2)+'\n')
    print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    main()
