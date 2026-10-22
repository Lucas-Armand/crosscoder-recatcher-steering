#!/usr/bin/env python3
"""Paired first activation / existing lexical heuristic comparison, no inference."""
import csv,json,re,hashlib
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'reports/section67_semantic_temporal_20261019_v1'
OUT=ROOT/'reports/deepseek4810_marker_precedence_20261022_v1'
PATTERN=r'(?im)^\s*(?:#\s*tests?[/\\]|#\s*test_task|from\s+task_func\s+import|class\s+Test\w*\s*\()'
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rr=[r for r in csv.DictReader((SRC/'natural_timing.csv').open()) if r['family']=='deepseek' and r['source_text']=='deepseek_base']
    assert len(rr)==119
    sourcepath=Path('/tmp/dstk119_source_evaluation/bigcodebench__deepseek_base_repaired.jsonl')
    sources={r['task_id']:r['candidate_code_repaired'] for r in map(json.loads,sourcepath.read_text().splitlines())} if sourcepath.exists() else {}
    arrays=np.load(SRC/'deepseek_feature_activations.npz');out=[];audit=[]
    for r in rr:
        a=float(r['first_active_position']) if r['first_active_position'] else None
        m=float(r['contamination_marker_position']) if r['contamination_marker_position'] else None
        n=int(r['n_tokens']);ai=int(r['first_active_token']) if r['first_active_token'] else None
        mi=round(m*max(1,n-1)) if m is not None else None
        rel='unavailable' if a is None or m is None else 'before' if ai<mi else 'after' if ai>mi else 'same_token'
        rec=dict(task_id=r['task_id'],n_tokens=n,activation_token=ai,marker_token=mi,
            activation_pct=100*a if a is not None else None,marker_pct=100*m if m is not None else None,
            marker_minus_activation_pp=100*(m-a) if a is not None and m is not None else None,
            marker_minus_activation_tokens=mi-ai if ai is not None and mi is not None else None,relation=rel)
        if r['task_id'] in sources:
            code=sources[r['task_id']];start=int(r['evaluated_code_start_char']);match=re.search(PATTERN,code[start:]);assert match
            char=start+match.start();sub=code[char:];skip=len(sub)-len(sub.lstrip());actual=char+skip
            key=r['task_id'].split('/')[-1]+'__deepseek_base';offsets=arrays[key+'__offsets']
            hits=np.flatnonzero(offsets[:,1]>actual);actualindex=int(hits[0]) if len(hits) else len(offsets)-1
            kind='test_file_comment' if code[actual:].startswith('#') else 'task_func_import' if code[actual:].lower().startswith('from') else 'test_class'
            rec.update(marker_kind=kind,marker_first_nonwhitespace_token=actualindex,
                relation_to_first_nonwhitespace='before' if ai<actualindex else 'after' if ai>actualindex else 'same_token')
            audit.append(dict(task_id=r['task_id'],marker_kind=kind,regex_start_char=char,first_nonwhitespace_char=actual,
                prefix_whitespace=code[char:actual],marker_line=code[actual:].splitlines()[0],
                context=code[max(start,actual-120):actual+180],source_sha256=hashlib.sha256(code.encode()).hexdigest()))
        out.append(rec)
    valid=[r for r in out if r['relation']!='unavailable'];d=np.array([r['marker_minus_activation_pp'] for r in valid]);counts=Counter(r['relation'] for r in out)
    summary=dict(n=119,counts=dict(counts),percentages={k:100*v/119 for k,v in counts.items()},median_lead_pp=float(np.median(d)),
        within_1pp=int((abs(d)<=1).sum()),within_5pp=int((abs(d)<=5).sum()),within_10pp=int((abs(d)<=10).sum()),
        strict_before_definition='First active token index < heuristic marker token index; same token is not antecedent to its own emission.',
        first_nonwhitespace_sensitivity=dict(Counter(r.get('relation_to_first_nonwhitespace','unavailable') for r in out)),
        marker_kinds=dict(Counter(r.get('marker_kind','unavailable') for r in out)),regex=PATTERN,
        source_csv_sha256=hashlib.sha256((SRC/'natural_timing.csv').read_bytes()).hexdigest(),new_inference=False)
    for name,data in [('SUMMARY.json',summary),('paired_positions.json',out),('marker_audit_contexts.json',audit)]:
        (OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
    with (OUT/'paired_positions.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
    plt.rcParams.update({'font.size':11,'pdf.fonttype':42,'svg.fonttype':'none'})
    with PdfPages(OUT/'DEEPSEEK4810_MARKER_PRECEDENCE_REVIEW.pdf') as pdf:
        def save(fig,name):
            pdf.savefig(fig,bbox_inches='tight')
            for ext in ['pdf','png','svg']:fig.savefig(OUT/f'{name}.{ext}',dpi=220,bbox_inches='tight',facecolor='white')
            plt.close(fig)
        fig,(ax,bx)=plt.subplots(1,2,figsize=(14,5.5),gridspec_kw={'width_ratios':[1.05,1]})
        av=[r['activation_pct'] for r in valid];mv=[r['marker_pct'] for r in valid]
        bp=ax.boxplot([av,mv],positions=[1,0],vert=False,patch_artist=True,widths=.4,showfliers=False)
        for patch,c in zip(bp['boxes'],['#7654cf','#aaaaaa']):patch.set_facecolor(c);patch.set_alpha(.45)
        rng=np.random.default_rng(42)
        ax.scatter(av,1+rng.uniform(-.1,.1,len(av)),s=12,color='#7654cf',alpha=.35)
        ax.scatter(mv,rng.uniform(-.1,.1,len(mv)),s=12,color='#666666',alpha=.35)
        ax.set_yticks([1,0],['First activation\nbase-generated text','First test/import marker\nsame base-generated text'])
        ax.set_xlim(0,100);ax.set_xlabel('Position in evaluated generated tokens (%)');ax.set_title('The two relevant marginal distributions');ax.grid(axis='x',alpha=.2)
        cmap={'before':'#248c75','same_token':'#b48820','after':'#7654cf'}
        for rel,label in [('before','Before'),('same_token','Same token'),('after','After')]:
            rs=[r for r in valid if r['relation']==rel]
            bx.scatter([r['marker_pct'] for r in rs],[r['activation_pct'] for r in rs],color=cmap[rel],s=25,alpha=.65,label=f'{label}: {len(rs)}/119 ({100*len(rs)/119:.1f}%)')
        bx.plot([0,100],[0,100],'--',color='#555555',lw=1);bx.set_xlim(0,100);bx.set_ylim(0,100);bx.set_aspect('equal')
        bx.set_xlabel('Test/import marker position (%)');bx.set_ylabel('First activation position (%)');bx.set_title('Paired comparison: one point per task');bx.legend(fontsize=8,loc='upper left');bx.grid(alpha=.15)
        fig.suptitle('DeepSeek 4810: first activation versus lexical contamination marker',fontsize=15)
        fig.text(.5,.01,'119 contamination-improvement tasks, original failing base text. Diagonal = same token position. Marker is not an annotated semantic error onset.',ha='center',fontsize=9)
        fig.subplots_adjust(left=.16,right=.98,wspace=.5,bottom=.16,top=.84);save(fig,'01_two_boxplots_and_paired_comparison')
        fig,(ax,bx)=plt.subplots(1,2,figsize=(14,5.5),gridspec_kw={'width_ratios':[1,2]})
        labels=['Before','Same token','After'];keys=['before','same_token','after']
        vals=[100*counts[k]/119 for k in keys];bars=ax.bar(labels,vals,color=[cmap[k] for k in keys])
        for bar,k,v in zip(bars,keys,vals):ax.text(bar.get_x()+bar.get_width()/2,v+1,f'{counts[k]}/119\n{v:.1f}%',ha='center',fontsize=10)
        ax.set_ylim(0,76);ax.set_ylabel('Tasks (%)');ax.set_title('Does first activation precede the marker?');ax.grid(axis='y',alpha=.15)
        sortedr=sorted(valid,key=lambda r:r['marker_minus_activation_pp']);xx=np.arange(len(sortedr))
        bx.bar(xx,[r['marker_minus_activation_pp'] for r in sortedr],width=1,color=[cmap[r['relation']] for r in sortedr])
        bx.axhline(0,color='#333333',lw=1);bx.set_xlabel('All 119 tasks, sorted by lead (task IDs in companion CSV)');bx.set_ylabel('Marker position minus first activation (percentage points)')
        bx.set_title(f'Positive = activation earlier; median = {np.median(d):+.2f} pp');bx.grid(axis='y',alpha=.15)
        fig.suptitle('How far before or after? Retain the paired temporal distance.',fontsize=15)
        fig.text(.5,.01,f'{int((abs(d)<=5).sum())}/119 tasks within +/-5 percentage points; {int((abs(d)<=10).sum())}/119 within +/-10. Near the marker does not imply before it or causal mediation.',ha='center',fontsize=9)
        fig.subplots_adjust(left=.07,right=.98,wspace=.32,bottom=.15,top=.83);save(fig,'02_precedence_and_per_task_lead')
        if audit:
            fig,ax=plt.subplots(figsize=(11,5.5));xx=np.arange(3)
            corrected=Counter(r['relation_to_first_nonwhitespace'] for r in out)
            for shift,cc,label,color in [(-.18,counts,'Original marker: regex match start','#888888'),(.18,corrected,'Sensitivity: first non-whitespace of marker line','#7654cf')]:
                vv=[100*cc[k]/119 for k in keys];bars=ax.bar(xx+shift,vv,width=.34,label=label,color=color)
                for bar,k,v in zip(bars,keys,vv):ax.text(bar.get_x()+bar.get_width()/2,v+.7,f'{cc[k]}/119\n{v:.1f}%',ha='center',fontsize=9)
            ax.set_xticks(xx,labels);ax.set_ylim(0,76);ax.set_ylabel('Tasks (%)');ax.legend(fontsize=9);ax.grid(axis='y',alpha=.15)
            ax.set_title('Important sensitivity: whitespace can move the lexical anchor',fontsize=15)
            fig.text(.5,.02,'The original regex starts with ^\\s*: it may include blank lines / indentation BEFORE the visible marker.\nSensitivity changes only the anchor, not the feature, cohort, model or code. Neither anchor is an annotated semantic error onset.',ha='center',fontsize=10)
            fig.subplots_adjust(bottom=.20,top=.87);save(fig,'03_whitespace_anchor_sensitivity')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
