#!/usr/bin/env python3
"""Paper-discussion figures from the frozen section 6.7 analysis, magnitudes 0..5."""
from collections import defaultdict
import csv
import difflib
import json
from pathlib import Path
import textwrap
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/section67_semantic_temporal_20261019_v1'
COLORS={'deepseek':'#7654CF','codellama':'#D67A16'}
TITLES={'deepseek':'DeepSeek base · feature 4810 · n=119','codellama':'CodeLlama merged · feature 4309 · n=50'}

def csvread(name):return list(csv.DictReader((OUT/name).open()))
def number(v):return float(v) if v not in [None,'','None'] else None
def boolean(v):return v is True or str(v)=='True'
def save(fig,name):
    for suffix in ['pdf','png','svg']:fig.savefig(OUT/f'{name}.{suffix}',dpi=220,bbox_inches='tight',facecolor='white')
    plt.close(fig)
def setup(ax):
    ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.18)
def tokenlabel(token):return token.replace('\n','\\n').replace('\t','\\t').replace(' ','·') or '[empty]'

def main():
    plt.rcParams.update({'font.size':9,'axes.titlesize':11,'pdf.fonttype':42,'svg.fonttype':'none'})
    curves=csvread('curves.csv');timing=csvread('natural_timing.csv');steering=json.loads((OUT/'steering_cases.json').read_text())
    contexts=json.loads((OUT/'activation_contexts.json').read_text())
    for row in curves:
        for key in ['alpha','magnitude','passed','n','changed']:row[key]=float(row[key])
    # Primary curve: strongest target, all three random latents, all three negative shuffles.
    for metric,name,ylabel in [('passed','01_correctness_controls','Official fail-to-pass (%)'),('changed','02_code_changes_controls','Changed evaluated code (%)')]:
        fig,axs=plt.subplots(1,2,figsize=(11,5.1))
        for ax,family in zip(axs,COLORS):
            data=[r for r in curves if r['family']==family]
            for kind in ['random','shuffle','target']:
                identities=sorted({r['identity'] for r in data if r['kind']==kind})
                for j,identity in enumerate(identities):
                    rs=sorted([r for r in data if r['kind']==kind and r['identity']==identity and (kind!='shuffle' or r['alpha']<0)],key=lambda r:r['magnitude'])
                    assert len(rs)==5
                    color=COLORS[family] if kind=='target' else (['#20798C','#519DAA','#86BDC2'][j] if kind=='random' else ['#222222','#777777','#AAAAAA'][j])
                    label=f'Target {identity} (−)' if kind=='target' else (f'Random latent {identity} ({"+" if rs[0]["alpha"]>0 else "−"})' if kind=='random' else f'Shuffle {identity} (−)')
                    ax.plot([0]+[r['magnitude'] for r in rs],[0]+[100*r[metric]/r['n'] for r in rs],
                        color=color,lw=2.8 if kind=='target' else 1.25,ls='-' if kind=='target' else '--' if kind=='random' else ':',
                        marker='o' if kind=='target' else None,label=label,zorder=4 if kind=='target' else 2)
            ax.set_title(TITLES[family],color=COLORS[family]);ax.set_xlabel('Magnitude |α|');ax.set_xticks(range(6))
            ax.set_ylabel(ylabel);ax.yaxis.set_major_formatter(PercentFormatter(100));ax.set_ylim(bottom=-.3)
            if metric=='passed':ax.set_ylim(-.3,13)
            else:ax.set_ylim(-1,65)
            setup(ax);ax.legend(loc='upper center',bbox_to_anchor=(.5,-.2),ncol=2,frameon=False,fontsize=8)
        fig.suptitle('Selected feature versus random latent and norm-preserving shuffle controls',y=1.01)
        fig.subplots_adjust(wspace=.28,bottom=.34);save(fig,name)
    # All shuffles in both signs; target remains in its predicted (negative) direction.
    fig,axs=plt.subplots(1,2,figsize=(11,5.2))
    for ax,family in zip(axs,COLORS):
        data=[r for r in curves if r['family']==family]
        for index,color in zip(['1','2','3'],['#292929','#737373','#B1B1B1']):
            for sign in [-1,1]:
                rs=sorted([r for r in data if r['kind']=='shuffle' and r['identity']==index and r['alpha']*sign>0],key=lambda r:r['magnitude'])
                assert len(rs)==5
                ax.plot([0]+[r['magnitude'] for r in rs],[0]+[100*r['passed']/r['n'] for r in rs],
                        color=color,ls='-' if sign<0 else '--',marker='.' if sign<0 else 'x',label=f'Shuffle {index} ({"−" if sign<0 else "+"})')
        rs=sorted([r for r in data if r['kind']=='target'],key=lambda r:r['magnitude'])
        ax.plot([0]+[r['magnitude'] for r in rs],[0]+[100*r['passed']/r['n'] for r in rs],color=COLORS[family],lw=2.8,marker='o',label='Target (−)')
        ax.set_title(TITLES[family],color=COLORS[family]);ax.set_xticks(range(6));ax.set_xlabel('Magnitude |α|')
        ax.set_ylabel('Official fail-to-pass (%)');ax.set_ylim(-.3,13);ax.yaxis.set_major_formatter(PercentFormatter(100));setup(ax)
        ax.legend(loc='upper center',bbox_to_anchor=(.5,-.2),ncol=2,frameon=False,fontsize=8)
    fig.subplots_adjust(bottom=.34,wspace=.28);save(fig,'03_shuffle_both_signs')
    # Natural timing: box plots preserve inactive counts explicitly.
    fig,axs=plt.subplots(1,2,figsize=(11,4.5));summaries={}
    for ax,family in zip(axs,COLORS):
        rs=[r for r in timing if r['family']==family];sources=sorted({r['source_text'] for r in rs})
        if family=='deepseek':base,variant='deepseek_base','deepseek_finetuned';weak=base
        else:base,variant='codellama_base','codellama_merged';weak=variant
        series=[];labels=[];summaries[family]={}
        for source,title in [(base,'First activation · base text'),(variant,'First activation · variant text')]:
            source_rows=[r for r in rs if r['source_text']==source]
            values=[100*number(r['first_active_position']) for r in source_rows if number(r['first_active_position']) is not None]
            labels.append(f'{title}\nactive in {len(values)}/{len(source_rows)} tasks');series.append(values)
            before=sum(boolean(r['active_at_or_before_divergence']) for r in source_rows)
            summaries[family][source]=dict(n=len(source_rows),active_tasks=len(values),inactive_tasks=len(source_rows)-len(values),
                first_activation_median_pct=float(np.median(values)) if values else None,active_at_or_before_text_divergence=before)
        weakrows=[r for r in rs if r['source_text']==weak and not boolean(r['all_code_identical'])]
        series.append([100*number(r['model_divergence_position']) for r in weakrows]);labels.append('Base–variant first divergence\nposition in weak-model text')
        if family=='deepseek':
            marker=[100*number(r['contamination_marker_position']) for r in weakrows if number(r['contamination_marker_position']) is not None]
            series.append(marker);labels.append(f'First test/import marker\nheuristic · present in {len(marker)}/{len(weakrows)}')
        for j,vals in enumerate(series):
            if not vals:continue
            bp=ax.boxplot(vals,positions=[j],vert=False,widths=.42,patch_artist=True,showfliers=False)
            bp['boxes'][0].set_facecolor(COLORS[family] if j<2 else '#BBBBBB');bp['boxes'][0].set_alpha(.35)
            rng=np.random.default_rng(42+j);ax.scatter(vals,j+rng.uniform(-.14,.14,len(vals)),s=8,alpha=.35,c=COLORS[family] if j<2 else '#666666')
        ax.set_yticks(range(len(labels)),labels);ax.invert_yaxis();ax.set_xlim(-2,102);ax.xaxis.set_major_formatter(PercentFormatter(100))
        ax.set_xlabel('Position within evaluated generated tokens');ax.set_title(TITLES[family],color=COLORS[family]);ax.grid(axis='x',alpha=.2)
    fig.subplots_adjust(wspace=.9,left=.22);save(fig,'04_natural_timing_boxplots')
    # Feature magnitude by normalized token bins; every task contributes equally to the mean.
    fig,axs=plt.subplots(1,2,figsize=(11,3.3));bins=20
    for ax,family in zip(axs,COLORS):
        npz=np.load(OUT/f'{family}_feature_activations.npz');sources=['deepseek_base','deepseek_finetuned'] if family=='deepseek' else ['codellama_base','codellama_merged']
        matrix=[]
        for source in sources:
            taskmeans=[]
            for key in npz.files:
                if not key.endswith(f'__{source}__z'):continue
                z=npz[key];ix=np.minimum(bins-1,(np.arange(len(z))/max(1,len(z)-1)*bins).astype(int))
                taskmeans.append([float(z[ix==j].mean()) if np.any(ix==j) else np.nan for j in range(bins)])
            matrix.append(np.nanmean(taskmeans,axis=0))
        im=ax.imshow(matrix,aspect='auto',cmap='Purples' if family=='deepseek' else 'Oranges',extent=[0,100,1.5,-.5],vmin=0)
        ax.set_yticks([0,1],['Base text','Variant text']);ax.set_xlabel('Normalized evaluated-token position (%)')
        ax.set_title(TITLES[family],color=COLORS[family]);fig.colorbar(im,ax=ax,label='Mean TopK activation',shrink=.8)
    fig.subplots_adjust(wspace=.45);save(fig,'05_activation_position_profile')
    # Activating tokens: activation mass, support >=3 tasks; no correlation claim.
    fig,axs=plt.subplots(2,2,figsize=(11,8))
    top_tokens={}
    for column,family in enumerate(COLORS):
        sources=['deepseek_base','deepseek_finetuned'] if family=='deepseek' else ['codellama_base','codellama_merged']
        for row,source in enumerate(sources):
            ax=axs[row,column];stats=csvread(f'{source}_token_statistics.csv')
            selected=[r for r in stats if int(r['active_task_support'])>=3][:12]
            top_tokens[source]=selected
            denom=sum(float(r['activation_sum']) for r in stats)
            values=[100*float(r['activation_sum'])/denom for r in selected]
            labels=[f"{tokenlabel(r['token'])}  [tasks={r['active_task_support']}]" for r in selected]
            ax.barh(range(len(values)),values,color=COLORS[family],alpha=.8);ax.set_yticks(range(len(values)),labels)
            ax.invert_yaxis();ax.set_title(source);ax.set_xlabel('Share of total feature activation mass (%)');setup(ax)
    fig.suptitle('Activating tokens — focal cohorts only; token support ≥3 tasks',y=1.01)
    fig.subplots_adjust(wspace=.6,hspace=.35);save(fig,'06_top_activating_tokens')
    # Steering divergence: corrected versus changed-still-failing; unchanged not imputed at 100%.
    fig,axs=plt.subplots(1,2,figsize=(11,4.8))
    for ax,family in zip(axs,COLORS):
        for mag in range(1,6):
            rs=[r for r in steering if r['family']==family and abs(r['alpha'])==mag]
            for corrected,shift,color in [(False,-.15,'#999999'),(True,.15,COLORS[family])]:
                vals=[100*r['first_change_position'] for r in rs if r['changed'] and r['passed']==corrected]
                if vals:
                    b=ax.boxplot(vals,positions=[mag+shift],widths=.24,patch_artist=True,showfliers=False)
                    b['boxes'][0].set_facecolor(color);b['boxes'][0].set_alpha(.55)
                ax.text(mag+shift,104,str(len(vals)),ha='center',fontsize=8,color=color)
        ax.set_xticks(range(1,6));ax.set_xlim(.5,5.5);ax.set_ylim(-2,112);ax.set_xlabel('Magnitude |α|');ax.set_ylabel('First steering-induced change (%)')
        ax.set_title(TITLES[family],color=COLORS[family]);ax.yaxis.set_major_formatter(PercentFormatter(100));setup(ax)
    fig.text(.5,.01,'Colored: corrected · gray: changed but still failing · numbers above: tasks · unchanged outputs omitted, not placed at 100%',ha='center',fontsize=8)
    fig.subplots_adjust(bottom=.17,wspace=.3);save(fig,'07_steering_divergence_timing')
    (OUT/'summary.json').write_text(json.dumps(dict(natural_timing=summaries,top_tokens=top_tokens),indent=2,ensure_ascii=False)+'\n')
    # Every changed case has an inspectable diff; figures do not auto-invent semantic labels.
    caseorder=sorted([r for r in steering if abs(r['alpha'])==5 and r['changed']],key=lambda r:(r['family'],not r['passed'],r['task_id']))
    lines=['# Case inspection workbook — alpha -5','','Correctness comes from the official evaluator. Excerpts/diffs alone do not identify a complete causal mechanism.','']
    for r in caseorder:
        lines += [f"## {r['family']} / feature {r['feature']} / {r['task_id']} / {'PASS' if r['passed'] else 'FAIL'}",'',
            f"First changed position: {100*r['first_change_position']:.1f}%. Natural first activation: {r['natural_first_activation']}.",'','```diff']
        lines+=list(difflib.unified_diff(r['code_before'].splitlines(),r['code_after'].splitlines(),fromfile='baseline',tofile='alpha_minus5',lineterm=''))
        lines+=['```','']
    (OUT/'CASE_INSPECTION.md').write_text('\n'.join(lines)+'\n')
    contextlines=['# Natural activation context workbook','','Each context is from a saved natural code sequence, not a steering generation. TopK100 was applied jointly.','']
    for family in COLORS:
        for source in sorted({r['source_text'] for r in contexts if r['family']==family}):
            used=set();selected=[]
            for r in contexts:
                if r['source_text']==source and r['task_id'] not in used:
                    selected.append(r);used.add(r['task_id'])
                if len(selected)>=15:break
            contextlines += [f'## {source}','']
            for r in selected:
                contextlines += [f"### {r['task_id']} · token {r['token']!r} · activation {r['activation']:.3f} · position {100*r['position']:.1f}%",'','```python',r['context'],'```','']
    (OUT/'ACTIVATION_CONTEXTS.md').write_text('\n'.join(contextlines)+'\n')
    # Selected factual examples, with full versions available in the case workbook.
    chosen=[('deepseek','BigCodeBench/937','PASS: removed failing test-module import; solution body unchanged.'),
            ('deepseek','BigCodeBench/475','FAIL: test imports removed, but evaluator still reports missing locale.'),
            ('codellama','BigCodeBench/490','PASS: file-writing behavior restored; duplicate helper remains in output.'),
            ('codellama','BigCodeBench/878','FAIL: validation changes, but repeated checks remain and the task still fails.')]
    fig,axs=plt.subplots(2,2,figsize=(13,10.5))
    for ax,(family,tid,note) in zip(axs.flat,chosen):
        r=next(r for r in steering if r['family']==family and r['task_id']==tid and r['alpha']==-5)
        diff=list(difflib.unified_diff(r['code_before'].splitlines(),r['code_after'].splitlines(),lineterm='',n=2))[2:]
        # Focus on main-function repair rather than duplicated docstrings in /490.
        if tid=='BigCodeBench/490':
            end=next((i for i,s in enumerate(diff) if s.startswith('+def task_func_2')),len(diff))
            diff=diff[:end]+['[Additional duplicate task_func_2 omitted from this excerpt.]']
        display=[]
        for line in diff:
            wrapped=textwrap.wrap(line,width=68,replace_whitespace=False,drop_whitespace=False) or ['']
            display += [(s,'#A6E3A1' if line.startswith('+') else '#F38BA8' if line.startswith('-') else '#CDD6F4') for s in wrapped]
        if len(display)>25:display=display[:24]+[('[Excerpt ends here; complete diff in CASE_INSPECTION.md]','#9399B2')]
        ax.set_facecolor('#1E1E2E');ax.set_xticks([]);ax.set_yticks([])
        ax.set_title(f"{family.upper()} · {tid} · α=−5",color=COLORS[family],loc='left',pad=12)
        for j,(line,color) in enumerate(display):ax.text(.025,.96-j*.032,line,transform=ax.transAxes,va='top',fontfamily='monospace',fontsize=6.7,color=color)
        ax.text(.025,.07,textwrap.fill(note,70),transform=ax.transAxes,va='top',fontsize=8,color='#F9E2AF')
        natural='inactive' if r['natural_first_activation'] is None else f"{100*r['natural_first_activation']:.1f}%"
        ax.text(.025,.015,f"Baseline first activation: {natural} · first code change: {100*r['first_change_position']:.1f}%",transform=ax.transAxes,fontsize=7.5,color='#BAC2DE')
    fig.suptitle('Semantic case studies — corrected programs and changed-but-failing programs',y=.995)
    fig.subplots_adjust(wspace=.12,hspace=.2);save(fig,'08_case_studies')
    # Baseline natural timing does not necessarily precede unconditional steering effects.
    fig,axs=plt.subplots(1,2,figsize=(10,4.6))
    for ax,family in zip(axs,COLORS):
        rs=[r for r in steering if r['family']==family and r['alpha']==-5 and r['changed']]
        for passed in [False,True]:
            selected=[r for r in rs if r['passed']==passed and r['natural_first_activation'] is not None]
            ax.scatter([100*r['natural_first_activation'] for r in selected],[100*r['first_change_position'] for r in selected],
                color=COLORS[family] if passed else '#888888',marker='D' if passed else 'o',alpha=.8 if passed else .5,s=38 if passed else 20,
                label=f"{'Corrected' if passed else 'Changed, still failing'} (n={len(selected)})")
        ax.plot([0,100],[0,100],color='#AAAAAA',ls='--',lw=1);ax.set_xlim(-3,103);ax.set_ylim(-3,103)
        ax.set_xlabel('First natural activation on baseline text (%)');ax.set_ylabel('First steering-induced code change (%)')
        ax.set_title(TITLES[family],color=COLORS[family]);setup(ax);ax.legend(fontsize=8,loc='upper left')
        inactive=sum(not r['natural_active'] for r in rs)
        unmapped=sum(r['natural_active'] and not r['natural_first_position_mapped'] for r in rs)
        ax.text(.02,-.23,f'Changed outputs: naturally inactive={inactive}; unaligned active anchor={unmapped}',transform=ax.transAxes,fontsize=8)
        for r in rs:
            if r['task_id'] in (['BigCodeBench/937','BigCodeBench/475'] if family=='deepseek' else ['BigCodeBench/490','BigCodeBench/878']) and r['natural_first_activation'] is not None:
                ax.annotate('/'+r['task_id'].split('/')[-1],(100*r['natural_first_activation'],100*r['first_change_position']),xytext=(4,4),textcoords='offset points',fontsize=8)
    fig.text(.5,.005,'α=−5 · Below the diagonal: code changed before the feature first activated naturally. Steering here is unconditional.',ha='center',fontsize=8)
    fig.subplots_adjust(bottom=.25,wspace=.3);save(fig,'09_natural_vs_intervention_timing')
    print(json.dumps(summaries,indent=2))

if __name__=='__main__':main()
