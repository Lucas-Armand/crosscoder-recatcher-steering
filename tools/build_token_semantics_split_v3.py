#!/usr/bin/env python3
"""Split token clouds and a single newline-context chart; saved data only."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from plot_section67_clouds_overlap_v1 import cloud

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'reports/section67_semantic_temporal_20261019_v1'
PRIOR = ROOT / 'reports/feature_token_semantics_20261027_v1'
OUT = ROOT / 'reports/feature_token_semantics_20261102_v2'
FIG = OUT / 'emse-submission/crosscoder_case_studies/figures'

def save(fig, name):
    for ext in ['png', 'pdf', 'svg']:
        fig.savefig(FIG / f'{name}.{ext}', dpi=300, bbox_inches='tight', facecolor='white')
    plt.close(fig)

def main():
    FIG.mkdir(parents=True, exist_ok=True)
    contexts = json.loads((PRIOR/'active_newline_contexts.json').read_text())
    previous = json.loads((PRIOR/'SUMMARY.json').read_text())
    categories = Counter(r['preceding_line_category'] for r in contexts)
    assert len(contexts) == 141
    assert dict(categories) == previous['active_newline_line_categories']
    assert categories['Return statement'] == 49 and categories['Raise statement'] == 28
    natural = list(csv.DictReader((SRC/'natural_timing.csv').open()))
    for source, n in [('deepseek_base',119), ('codellama_merged',50)]:
        ids = [r['task_id'] for r in natural if r['source_text']==source]
        assert len(ids)==len(set(ids))==n
    plt.rcParams.update({'font.size':10, 'pdf.fonttype':42, 'svg.fonttype':'none'})
    fig, axs = plt.subplots(1,2,figsize=(11.2,3.6))
    fig.subplots_adjust(left=.025,right=.975,top=.85,bottom=.13,wspace=.14)
    layouts = {}
    inputs = [PRIOR/'SUMMARY.json', PRIOR/'active_newline_contexts.json', SRC/'natural_timing.csv']
    for ax, source, title, color in [
        (axs[0],'deepseek_base','(a) DeepSeek 4810 · base text · 119 tasks','#7654cf'),
        (axs[1],'codellama_merged','(b) CodeLlama 4309 · merged text · 50 tasks','#d67a16')]:
        ax.set_axis_off(); ax.set_title(title,color=color,fontsize=11,pad=12)
        path=SRC/f'{source}_token_statistics.csv'; inputs.append(path)
        stats=list(csv.DictReader(path.open()))
        assert all(r['source_text']==source for r in stats)
        layouts[source]=cloud(ax,stats,color,42)
        eligible={str(r['token_id']) for r in stats if int(r['active_task_support'])>=3}
        assert all(str(r['token_id']) in eligible for r in layouts[source])
    fig.text(.5,.025,'Within-feature font scaling by activation mass · token support ≥3 tasks\nNEWLINE / SPACE are visible token aliases; a middle dot denotes a space.',ha='center',fontsize=8)
    save(fig,'feature_token_clouds')
    order=['Return statement','Raise statement','Block header','Assignment','Blank line','Other line']
    values=[categories[k] for k in order]
    fig,ax=plt.subplots(figsize=(7.4,3.7))
    ax.barh(range(len(order)),[100*v/141 for v in values],color=['#b9550c','#ce6a13','#de852a','#e99b45','#f1b56d','#f7cf9c'])
    ax.set_yticks(range(len(order)),order,fontsize=10); ax.invert_yaxis()
    for i,v in enumerate(values):
        ax.text(100*v/141+.7,i,f'{v}/141 ({100*v/141:.1f}%)',va='center',fontsize=9)
    ax.set_xlim(0,48);ax.set_xlabel('Share of active newline occurrences (%)')
    ax.set_title('CodeLlama 4309: lines ending at active newline tokens',color='#d67a16',fontsize=11,pad=12)
    ax.grid(axis='x',alpha=.15)
    fig.text(.5,.025,'Original failing merged programs · 50-task cohort · 141 active newline occurrences',ha='center',fontsize=8)
    fig.subplots_adjust(left=.23,right=.98,top=.84,bottom=.18)
    save(fig,'codellama_active_newline_contexts')
    summary=dict(focal_sources={'deepseek':'119 original failing base programs','codellama':'50 original failing merged programs'},
        active_newline_occurrences=141,active_newline_line_categories=dict(categories),
        newline_activation_mass_fraction=previous['codellama_merged']['newline_mass_fraction'],
        chart_denominator='141 positive-activation newline occurrences, pooled across the fixed 50-task merged cohort',
        cloud_support='at least three tasks; up to 40 strongest token IDs; independent within-feature font scaling',
        includes_passing_base_comparison=False,includes_conditional_activation_rate_chart=False,new_inference=False,
        caveats=['Return end lines are AST-derived and may correspond to conditional returns, not the final return.',
            'Block headers and blank lines are lexical contexts, not executed statements.',
            'Pooled occurrences are descriptive; repeated occurrences within a task are not independent observations.'])
    assert round(100*summary['newline_activation_mass_fraction'],1)==80.8
    for name,obj in [('SUMMARY.json',summary),('cloud_layout.json',layouts)]:
        (OUT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
    (OUT/'DATA_MANIFEST.json').write_text(json.dumps(dict(new_inference=False,sources=[dict(
        path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in inputs]),indent=2)+'\n')
    (OUT/'VALIDATION.json').write_text(json.dumps(dict(validated=True,cohorts_checked=True,
        newline_counts_match_previous_analysis=True,one_bar_denominator=141,
        deepseek_color='#7654cf',codellama_palette='orange only',new_inference=False),indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
