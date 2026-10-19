#!/usr/bin/env python3
"""Descriptive temporal precedence using saved, aligned measurements; no inference."""
import csv
import json
from collections import Counter
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'reports/section67_semantic_temporal_20261019_v1'
OUT=ROOT/'reports/codellama4309_temporal_precedence_20261019_v1'

def relation(x,a,b=None):
    if x is None:return 'not_observed_or_unmapped'
    if x<a-1e-9:return 'before'
    if x>(a if b is None else b)+1e-9:return 'after'
    return 'same_token_or_within_region'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    natural=[r for r in csv.DictReader((SRC/'natural_timing.csv').open()) if r['family']=='codellama']
    loc=json.loads((SRC/'codellama_error_localization.json').read_text())
    details=[]
    for r in loc:
        a=r['first_natural_activation'];lo=r['error_region_start_position'];hi=r['error_region_end_position']
        details.append(dict(task_id=r['task_id'],evidence=r['localization_type'],first_activation=a,
            error_region_start=lo,error_region_end=hi,relation=relation(a,lo,hi),
            active=r['feature_active_in_frozen_text'],passed=r['alpha5_passed'],changed=r['alpha5_changed'],
            first_steering_change=r['first_steering_change'],note=r['note']))
    tiers={tier:dict(Counter(r['relation'] for r in details if r['evidence']==tier)) for tier in sorted({r['evidence'] for r in details})}
    divergence=[]
    for r in natural:
        a=float(r['first_active_position']) if r['first_active_position'] else None
        d=float(r['model_divergence_position']) if r['model_divergence_position'] else None
        divergence.append(dict(task_id=r['task_id'],source_text=r['source_text'],first_activation=a,
            divergence=d,relation=relation(a,d) if d is not None else 'no_divergence',
            active_tokens=int(r['active_tokens']),n_tokens=int(r['n_tokens'])))
    summary=dict(n=50,error_region_relations=dict(Counter(r['relation'] for r in details)),
        by_evidence=tiers,
        by_outcome={k:dict(Counter(r['relation'] for r in details if r[field]==value)) for k,field,value in [('corrected','passed',True),('changed_still_failing','changed',True)]},
        divergence={s:dict(Counter(r['relation'] for r in divergence if r['source_text']==s)) for s in sorted({r['source_text'] for r in divergence})})
    # A distinct group must not accidentally include the corrected examples.
    summary['by_outcome']['changed_still_failing']=dict(Counter(r['relation'] for r in details if r['changed'] and not r['passed']))
    for name,data in [('SUMMARY.json',summary),('task_temporal_relations.json',details),('natural_divergence_relations.json',divergence)]:
        (OUT/name).write_text(json.dumps(data,indent=2)+'\n')
    for name,data in [('task_temporal_relations.csv',details),('natural_divergence_relations.csv',divergence)]:
        with (OUT/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    fig,ax=plt.subplots(figsize=(10,12))
    for i,r in enumerate(details):
        color='#d67a16' if r['evidence']=='runtime_execution_sites' else '#aaaaaa'
        ax.plot([100*r['error_region_start'],100*r['error_region_end']],[i,i],lw=5,color=color,alpha=.65)
        if r['first_activation'] is not None:ax.scatter(100*r['first_activation'],i,c='#7654cf',s=17)
    ax.set_yticks(range(50),[r['task_id'].replace('BigCodeBench','')+(' *' if r['passed'] else '') for r in details]);ax.invert_yaxis()
    ax.set_xlim(-2,102);ax.set_xlabel('Position in evaluated alpha-zero generated code (%)')
    ax.set_title('4309: first natural activation versus localized failure region')
    ax.grid(axis='x',alpha=.2)
    fig.text(.5,.02,'Purple: first mapped natural activation; gray: proposed region; orange: runtime execution site.\n* Corrected by alpha -5. Regions are NOT validated earliest semantic errors. Missing activations are not zero.',ha='center',fontsize=8)
    fig.subplots_adjust(left=.13,bottom=.08)
    for ext in ['pdf','png','svg']:fig.savefig(OUT/f'01_temporal_precedence.{ext}',dpi=200,bbox_inches='tight')
    (OUT/'METHOD.json').write_text(json.dumps(dict(new_inference=False,source=str(SRC),
        caveats=['Natural activations come from frozen jointly encoded source text, aligned to current extracted code.',
        'Missing means inactive or not mapped; consult active flag to distinguish.',
        'Strictly before is separate from same token/inside region.',
        'Runtime execution sites are not generation-time root-cause locations.',
        'Omissions have no unique first harmful token.',
        'Static continuous steering does not demonstrate mediation by naturally active feature.',
        'Textual divergence is not necessarily a semantic error; temporal precedence is necessary but not sufficient for mediation.']),indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    print('CORRECTED',json.dumps([r for r in details if r['passed']],indent=2))

if __name__=='__main__':main()
