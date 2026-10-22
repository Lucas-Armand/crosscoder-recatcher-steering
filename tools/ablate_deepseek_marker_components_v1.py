#!/usr/bin/env python3
"""Ablate lexical heuristic components on frozen and matched alpha-zero texts."""
import csv,itertools,json,re
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'reports/section67_semantic_temporal_20261019_v1'
OUT=ROOT/'reports/deepseek4810_marker_components_20261022_v1'
PATTERNS={'test_path_comment':r'(?im)^\s*#\s*tests?[/\\]',
    'test_task_comment':r'(?im)^\s*#\s*test_task',
    'task_func_import':r'(?im)^\s*from\s+task_func\s+import',
    'test_class':r'(?im)^\s*class\s+Test\w*\s*\('}
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    meta={r['task_id']:r for r in csv.DictReader((SRC/'natural_timing.csv').open()) if r['family']=='deepseek' and r['source_text']=='deepseek_base'}
    frozen={r['task_id']:r['candidate_code_repaired'] for r in map(json.loads,Path('/tmp/dstk119_source_evaluation/bigcodebench__deepseek_base_repaired.jsonl').read_text().splitlines()) if r['task_id'] in meta}
    cases=[r for r in json.loads((SRC/'steering_cases.json').read_text()) if r['family']=='deepseek' and r['alpha']==-5]
    current={r['task_id']:r['code_before'] for r in cases};passed={r['task_id'] for r in cases if r['passed']}
    arrays=np.load(SRC/'deepseek_feature_activations.npz');details=[];summary={}
    for version,codes in [('frozen',frozen),('current_alpha0',current)]:
        for tid,code in sorted(codes.items(),key=lambda p:int(p[0].split('/')[-1])):
            start=int(meta[tid]['evaluated_code_start_char']);text=code[start:];hits={}
            for name,pat in PATTERNS.items():
                m=re.search(pat,text)
                if m:
                    pos=m.start();pos+=len(text[pos:])-len(text[pos:].lstrip());hits[name]=dict(char=pos+start,line=text[pos:].splitlines()[0])
            comments=[v for k,v in hits.items() if k.endswith('comment')];firstcomment=min(comments,key=lambda x:x['char']) if comments else None
            other=[v for k,v in hits.items() if not k.endswith('comment')];firstother=min(other,key=lambda x:x['char']) if other else None
            first=min(hits,key=lambda k:hits[k]['char']) if hits else None
            details.append(dict(version=version,task_id=tid,hits=hits,first_component=first,
                has_comment=bool(comments),has_import='task_func_import' in hits,has_class='test_class' in hits,
                noncomment_earlier_than_comment=firstcomment is not None and firstother is not None and firstother['char']<firstcomment['char'],
                passed_at_alpha5=tid in passed,
                relevant_excerpt=text[max(0,(min(v['char'] for v in hits.values())-start)-80):max(0,(min(v['char'] for v in hits.values())-start)-80)+650] if hits else ''))
        rr=[r for r in details if r['version']==version]
        combos={'comments_only':lambda r:r['has_comment'],'import_only':lambda r:r['has_import'],'class_only':lambda r:r['has_class'],
            'comments_plus_import':lambda r:r['has_comment'] or r['has_import'],
            'comments_plus_class':lambda r:r['has_comment'] or r['has_class'],
            'full':lambda r:r['has_comment'] or r['has_import'] or r['has_class']}
        summary[version]=dict(n=len(rr),coverage={k:sum(fn(r) for r in rr) for k,fn in combos.items()},
            component_coverage={k:sum(k in r['hits'] for r in rr) for k in PATTERNS},
            unique_to_component={k:[r['task_id'] for r in rr if set(r['hits'])=={k}] for k in PATTERNS},
            without_comment_cases=[r['task_id'] for r in rr if not r['has_comment']],
            noncomment_earlier_than_comment=[r['task_id'] for r in rr if r['noncomment_earlier_than_comment']],
            noncomment_first_cases=[r['task_id'] for r in rr if r['first_component'] in ['task_func_import','test_class']])
    for name,obj in [('SUMMARY.json',summary),('task_component_audit.json',details)]:
        (OUT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
    rr=[r for r in details if r['version']=='frozen'];missing=[r for r in rr if not r['has_comment']]
    md=['# Marker-component ablation on 119 DeepSeek contamination cases','',
        'Coverage within this preselected cohort is not precision/specificity on arbitrary generated code. Identical existing regular expressions; no new inference. Frozen capture text is distinct from current re-extracted alpha-zero text.','',
        '| Configuration | Frozen captured text | Current alpha-zero text |','|---|---:|---:|']
    for k in summary['frozen']['coverage']:md.append(f"| {k} | {summary['frozen']['coverage'][k]}/119 | {summary['current_alpha0']['coverage'][k]}/119 |")
    md+=['','## Frozen tasks missed by comments alone','']
    for r in missing:
        md += [f"### {r['task_id']}",'',f"First marker: {r['first_component']}; pass at alpha -5: {r['passed_at_alpha5']}",
            '','```python',r['relevant_excerpt'],'```','',f"Matched lines: {json.dumps(r['hits'],ensure_ascii=False)}"]
    md+=['','## Earlier non-comment marker despite a later matching comment','']
    for r in rr:
        if r['noncomment_earlier_than_comment']:md += [r['task_id'],'```python',r['relevant_excerpt'],'```']
    (OUT/'README.md').write_text('\n'.join(md)+'\n')
    plt.rcParams.update({'font.size':11,'pdf.fonttype':42,'svg.fonttype':'none'})
    fig,(ax,bx)=plt.subplots(1,2,figsize=(14,5.8));keys=['comments_only','comments_plus_import','comments_plus_class','full']
    labels=['Comments\nonly','Comments +\ntask_func import','Comments +\nTest class','Full\nheuristic']
    vals=[summary['frozen']['coverage'][k] for k in keys]
    bars=ax.bar(range(4),vals,color=['#888888','#7654cf','#b294d8','#268b75']);ax.set_xticks(range(4),labels)
    for bar,v in zip(bars,vals):ax.text(bar.get_x()+bar.get_width()/2,v+1,f'{v}/119\n{100*v/119:.1f}%',ha='center',fontsize=9)
    ax.set_ylim(0,139);ax.set_ylabel('Detected tasks');ax.set_title('Coverage on original captured texts');ax.grid(axis='y',alpha=.15)
    signatures={}
    for r in missing:
        sig=('import' if r['has_import'] else '')+(' + class' if r['has_class'] else '')
        signatures[sig]=signatures.get(sig,0)+1
    xx=list(signatures);vv=list(signatures.values());bars=bx.bar(xx,vv,color='#7654cf')
    for b,v in zip(bars,vv):bx.text(b.get_x()+b.get_width()/2,v+.1,str(v),ha='center')
    bx.set_ylim(0,max(vv)+2);bx.set_ylabel('Tasks without a matching comment');bx.set_title('How the remaining cases are recovered');bx.grid(axis='y',alpha=.15)
    fig.suptitle('Does the comment detector do most of the work?',fontsize=15)
    fig.text(.5,.015,'119 preselected contamination improvements. This is a coverage ablation, NOT validation of false positives or specificity.\nImport/class components can both recover missing comments and precede a later comment. Task-level audit and current-alpha-zero sensitivity retained.',ha='center',fontsize=9)
    fig.subplots_adjust(left=.06,right=.98,wspace=.25,bottom=.2,top=.85)
    for ext in ['pdf','png','svg']:fig.savefig(OUT/f'01_marker_component_ablation.{ext}',dpi=220,bbox_inches='tight',facecolor='white')
    print(json.dumps(summary,indent=2));print('WITHOUT_COMMENTS',json.dumps(missing,indent=2))

if __name__=='__main__':main()
