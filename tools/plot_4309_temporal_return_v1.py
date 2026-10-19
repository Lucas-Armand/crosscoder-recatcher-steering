#!/usr/bin/env python3
"""Saved-data-only timing and AST-labelled newline analysis for feature 4309."""
import ast,csv,json
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from analyze_4309_behavior_hypothesis_v1 import function,statements,descendants

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'reports/section67_semantic_temporal_20261019_v1'
OUT=ROOT/'reports/codellama4309_temporal_return_visuals_20261019_v1'
CATS=['newline_after_main_return','other_newline','non_newline']
LABELS=['Newline after task_func return','Other newline','Non-newline token']
COLORS=['#d67a16','#7654cf','#aaaaaa']
def save(fig,name):
    REVIEW.savefig(fig,bbox_inches='tight',facecolor='white')
    for ext in ['pdf','png','svg']:fig.savefig(OUT/f'{name}.{ext}',dpi=220,bbox_inches='tight',facecolor='white')
    plt.close(fig)

def main():
    global REVIEW
    OUT.mkdir(parents=True,exist_ok=True)
    REVIEW=PdfPages(OUT/'VISUAL_REVIEW.pdf')
    plt.rcParams.update({'font.size':10,'pdf.fonttype':42,'svg.fonttype':'none'})
    arrays=np.load(SRC/'codellama_feature_activations.npz')
    tax={r['task_id']:r for r in csv.DictReader((ROOT/'reports/codellama_base_merged_topk100_v1_regression_taxonomy/regression_failure_cases.csv').open()) if r['benchmark']=='bigcodebench'}
    timing=json.loads((ROOT/'reports/codellama4309_temporal_precedence_20261019_v1/task_temporal_relations.json').read_text())
    results=[];contexts={}
    for tid in sorted({r['task_id'] for r in timing},key=lambda x:int(x.split('/')[-1])):
        for source,field in [('codellama_base','base_code'),('codellama_merged','merged_code')]:
            code=tax[tid][field];f=function(code);nodes=[n for s in statements(f) for n in descendants(s)]
            return_lines={n.end_lineno for n in nodes if isinstance(n,ast.Return)}
            lines=code.splitlines(keepends=True);starts=np.cumsum([0]+[len(s) for s in lines[:-1]])
            newline_after_return={int(starts[n-1])+len(lines[n-1])-1 for n in return_lines if lines[n-1].endswith('\n')}
            key=tid.split('/')[-1]+'__'+source;z=arrays[key+'__z'];offsets=arrays[key+'__offsets'];active=np.flatnonzero(z>0)
            cats=[]
            for lo,hi in offsets:
                lo,hi=int(lo),int(hi);span=code[lo:hi]
                cats.append(CATS[0] if any(lo<=p<hi for p in newline_after_return) else CATS[1] if '\n' in span else CATS[2])
            for cat in CATS:
                mask=np.array([c==cat for c in cats]);results.append(dict(task_id=tid,source=source,category=cat,tokens=int(mask.sum()),active_tokens=int(((z>0)&mask).sum()),mass=float(z[mask].sum())))
            if source=='codellama_merged':
                first=int(active[0]) if len(active) else None
                char=int(offsets[first][0]) if first is not None else None
                line=code.count('\n',0,char)+1 if char is not None else None
                contexts[tid]=dict(first_category=cats[first] if first is not None else 'inactive',first_index=first,
                    line=line,activation=float(z[first]) if first is not None else None,
                    column=char-int(starts[line-1]) if char is not None else None,
                    token_span=code[int(offsets[first][0]):int(offsets[first][1])] if first is not None else None,
                    lines=[dict(number=n,text=lines[n-1].rstrip('\r\n'),first_active=n==line) for n in range(max(f.lineno,(line or f.lineno)-2),min(len(lines),(line or f.lineno)+1)+1)],
                    return_lines=sorted(return_lines))
    pooled=[]
    for source in ['codellama_base','codellama_merged']:
        ss=[r for r in results if r['source']==source];total=sum(r['mass'] for r in ss)
        for cat in CATS:
            rr=[r for r in ss if r['category']==cat];n=sum(r['tokens'] for r in rr);a=sum(r['active_tokens'] for r in rr);m=sum(r['mass'] for r in rr)
            pooled.append(dict(source=source,category=cat,tokens=n,active_tokens=a,mass=m,mass_fraction=m/total,activation_rate=a/n if n else None,tasks_active=sum(r['active_tokens']>0 for r in rr)))
    first_counts=dict(Counter(r['first_category'] for r in contexts.values()))
    summary=dict(first_activation_categories_merged=first_counts,pooled=pooled,
        definition='AST identifies task_func Return end lines, excluding nested functions; newline token span must cover the newline ending that statement. Other newline includes all other captured newline-containing tokens.',
        caveats=['A return may be conditional, not a final function exit; lexical AST category is not dynamic execution.',
            'Pooled token rates are descriptive and tasks are not independent token replications.',
            'Natural activations are shared same-text offline measurements; no prompt activations.',
            'Error regions are provisional or runtime sites, not validated earliest semantic errors.'])
    for name,obj in [('SUMMARY.json',summary),('task_token_categories.json',results),('first_activation_contexts.json',contexts)]:
        (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    # 1: evidence-tier separated temporal regions with a compact tally.
    order=['runtime_execution_sites','probable_line','probable_region','omission_region']
    tt=sorted(timing,key=lambda r:(order.index(r['evidence']),int(r['task_id'].split('/')[-1])))
    fig,(ax,bx)=plt.subplots(1,2,figsize=(14,13),gridspec_kw={'width_ratios':[3,1.4]})
    for i,r in enumerate(tt):
        ax.plot([100*r['error_region_start'],100*r['error_region_end']],[i,i],lw=5,color='#d67a16' if r['evidence']=='runtime_execution_sites' else '#bbbbbb',alpha=.65)
        if r['first_activation'] is not None:ax.scatter(100*r['first_activation'],i,color='#7654cf',s=24,marker='D' if r['passed'] else 'o')
        else:ax.text(102,i,'inactive' if not r['active'] else 'unmapped',fontsize=7,va='center')
    ax.set_yticks(range(50),[r['task_id'].replace('BigCodeBench','')+(' [PASS at -5]' if r['passed'] else '') for r in tt],fontsize=8)
    ax.invert_yaxis();ax.set_xlim(-2,120);ax.set_xticks([0,20,40,60,80,100]);ax.set_xlabel('Position in evaluated generated code (%)');ax.grid(axis='x',alpha=.15)
    k=0
    for tier in order:
        n=sum(r['evidence']==tier for r in tt)
        ax.axhline(k-.5,color='#777777',lw=.6);k+=n
    counts=Counter(r['relation'] for r in tt);keys=['before','same_token_or_within_region','after','not_observed_or_unmapped']
    bx.barh(range(4),[counts[k] for k in keys],color=['#2b8c78','#7654cf','#c66b10','#aaaaaa'])
    bx.set_yticks(range(4),['Before region','Within region','After region','Inactive / unmapped']);bx.invert_yaxis()
    for i,k in enumerate(keys):bx.text(counts[k]+.3,i,str(counts[k]),va='center')
    bx.set_xlabel('Tasks / 50');bx.set_xlim(0,32);bx.set_title('First activation vs. region')
    fig.suptitle('4309 timing in 50 failing merged outputs',fontsize=16)
    fig.text(.5,.025,'Purple: first natural activation · region: gray (proposed), orange (runtime site) · diamonds: two corrected tasks\nRows grouped: runtime sites / proposed lines / proposed intervals / omission regions. These are NOT validated error onsets.',ha='center',fontsize=9)
    fig.subplots_adjust(left=.12,right=.95,bottom=.08,wspace=.5);save(fig,'01_temporal_regions_50')
    # 2: enrichment, without confusing token mass with probability.
    fig,(ax,bx)=plt.subplots(1,2,figsize=(13,5.3))
    for source,label,y in [('codellama_base','Passing base text',0),('codellama_merged','Failing merged text',1)]:
        left=0
        for cat,col,lab in zip(CATS,COLORS,LABELS):
            r=next(r for r in pooled if r['source']==source and r['category']==cat);v=100*r['mass_fraction']
            ax.barh(y,v,left=left,color=col,label=lab if y==0 else None)
            if v>8:ax.text(left+v/2,y,f'{v:.1f}%',ha='center',va='center',color='white',fontsize=9)
            left+=v
    ax.set_yticks([0,1],['Passing base text','Failing merged text']);ax.set_xlim(0,100);ax.set_xlabel('Share of total activation mass (%)');ax.legend(loc='upper center',bbox_to_anchor=(.5,-.2),fontsize=8)
    xx=np.arange(3)
    for i,source in enumerate(['codellama_base','codellama_merged']):
        rr=[next(r for r in pooled if r['source']==source and r['category']==c) for c in CATS]
        bx.bar(xx+(i-.5)*.36,[100*r['activation_rate'] for r in rr],width=.35,label='Base text' if i==0 else 'Merged text',color='#777777' if i==0 else '#d67a16')
    bx.set_xticks(xx,['After main return\nnewline','Other\nnewline','Non-newline']);bx.set_ylabel('Tokens with positive activation (%)');bx.legend();bx.grid(axis='y',alpha=.15)
    fig.suptitle('Does 4309 prefer return-line boundaries?',fontsize=15)
    fig.text(.5,.01,'50 task pairs · same shared feature on different generated texts · pooled descriptive statistics, not independent token-level tests.',ha='center',fontsize=9)
    fig.subplots_adjust(left=.13,right=.98,wspace=.4,bottom=.26,top=.85);save(fig,'02_return_newline_specificity')
    # 3: reproducible discovery + counterexample panels, no cherry-picked highest activations.
    selections=['BigCodeBench/183','BigCodeBench/490','BigCodeBench/634','BigCodeBench/115','BigCodeBench/629']
    other=next(t for t in sorted(contexts,key=lambda s:int(s.split('/')[-1])) if contexts[t]['first_category']=='other_newline' and t not in selections)
    selections.append(other)
    selections.append(next(t for t in sorted(contexts,key=lambda s:int(s.split('/')[-1])) if contexts[t]['first_category']=='non_newline' and t not in selections))
    selections.append(next(t for t in sorted(contexts,key=lambda s:int(s.split('/')[-1])) if contexts[t]['first_category']==CATS[0] and t not in selections))
    fig,axs=plt.subplots(4,2,figsize=(16,14))
    for ax,tid in zip(axs.flat,selections):
        c=contexts[tid];t=next(r for r in timing if r['task_id']==tid)
        ax.set_facecolor('#1e2230');ax.set_xticks([]);ax.set_yticks([])
        title=f"{tid} | {'PASS' if t['passed'] else 'FAIL'} at alpha -5"
        ax.set_title(title,loc='left',color='#d67a16',fontsize=12)
        y=.86
        for line in c['lines']:
            raw=line['text']
            if line['first_active']:
                col=c['column'];raw=raw[:col]+'*'+raw[col:]
                raw+=' [newline]' if c['token_span']=='\n' else ''
            text=f"{line['number']:3d}  "+raw
            # Preserve all content by wrapping long display lines, not cropping.
            import textwrap
            wrapped=textwrap.wrap(text,width=79,replace_whitespace=False,drop_whitespace=False) or ['']
            for s in wrapped:
                ax.text(.025,y,s,fontfamily='monospace',fontsize=8.5,color='#ffd48a' if line['first_active'] else '#e0e4ee',va='top',transform=ax.transAxes);y-=.085
        ax.text(.025,.1,f"First activation: {c['first_category']} | z={c['activation']:.3f}\nTiming vs. region: {t['relation']}",color='#bfc8db',fontsize=8,transform=ax.transAxes,va='bottom')
    fig.suptitle('Natural first-activation examples: return boundaries and counterexamples',fontsize=15)
    fig.text(.5,.02,'Exact frozen merged-text snippets; * marks the token start (newline shown explicitly).\nIncludes both corrected cases, failed expansion, before-region cases, other-newline and non-newline counterexamples.\nAdditional examples selected by ascending task ID within the stated category; not a representative random sample.',ha='center',fontsize=9)
    fig.subplots_adjust(left=.03,right=.98,top=.91,bottom=.09,hspace=.35,wspace=.08);save(fig,'03_annotated_activation_examples')
    print(json.dumps(summary,indent=2));print('EXAMPLES',selections)
    REVIEW.close()

if __name__=='__main__':main()
