#!/usr/bin/env python3
"""Activation-weighted token clouds and task-set overlap, without new inference."""
from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/section67_semantic_temporal_20261019_v1'
STRESS=ROOT/'runs/feature_stress_shuffle_20261016_v1'
COLORS={'deepseek':'#7654CF','codellama':'#D67A16'}

def save(fig,name):
    for ext in ['pdf','png','svg']:fig.savefig(OUT/f'{name}.{ext}',dpi=230,bbox_inches='tight',facecolor='white')
    plt.close(fig)

def label(token):
    if token and token.isspace():
        if token=='\n':return 'NEWLINE'
        if set(token)=={' '}:return f'SPACE×{len(token)}'
        if set(token)=={'\n'}:return f'NEWLINE×{len(token)}'
    return token.replace('\n','↵').replace('\t','TAB').replace(' ','·')

def cloud(ax,stats,color,seed):
    fig=ax.figure;fig.canvas.draw();renderer=fig.canvas.get_renderer();bounds=ax.get_window_extent(renderer)
    width,height=bounds.width,bounds.height;placed=[];layout=[]
    stats=[r for r in stats if int(r['active_task_support'])>=3][:40]
    maximum=max(float(r['activation_sum']) for r in stats)
    rng=np.random.default_rng(seed)
    for rank,row in enumerate(stats):
        word=label(row['token']);mass=float(row['activation_sum']);size=9+36*math.sqrt(mass/maximum)
        artist=ax.text(.5,.5,word,ha='center',va='center',fontsize=size,fontweight='bold',color=color,transform=ax.transAxes)
        accepted=False
        for scale in [1.,.85,.7]:
            artist.set_fontsize(size*scale);b=artist.get_window_extent(renderer);w,h=b.width+7,b.height+6
            phase=float(rng.uniform(0,2*math.pi))
            for j in range(10000):
                radius=1.4*math.sqrt(j);theta=phase+j*2.3999632297
                x=width/2+1.5*radius*math.cos(theta);y=height/2+radius*math.sin(theta)
                rect=(x-w/2,y-h/2,x+w/2,y+h/2)
                if rect[0]<2 or rect[1]<2 or rect[2]>width-2 or rect[3]>height-2:continue
                if any(not(rect[2]<p[0] or rect[0]>p[2] or rect[3]<p[1] or rect[1]>p[3]) for p in placed):continue
                artist.set_position((x/width,y/height));placed.append(rect);accepted=True;break
            if accepted:break
        if not accepted:artist.remove()
        layout.append(dict(token_id=row['token_id'],token=row['token'],display=word,activation_sum=mass,
                           active_task_support=int(row['active_task_support']),displayed=accepted))
    return layout

def main():
    plt.rcParams.update({'font.size':10,'pdf.fonttype':42,'svg.fonttype':'none'})
    fig,axs=plt.subplots(2,2,figsize=(12,7.7));layouts={}
    for col,(family,sources) in enumerate([('deepseek',['deepseek_base','deepseek_finetuned']),('codellama',['codellama_base','codellama_merged'])]):
        for row,source in enumerate(sources):
            stats=list(csv.DictReader((OUT/f'{source}_token_statistics.csv').open()));ax=axs[row,col];ax.set_axis_off()
            ax.set_title(f'{source} · feature {4810 if family=="deepseek" else 4309}',color=COLORS[family],pad=8)
            layouts[source]=cloud(ax,stats,COLORS[family],42+col*2+row)
    fig.suptitle('Activating-token clouds — original focal-cohort texts',fontsize=14,y=.99)
    fig.text(.5,.015,'Font size increases with summed TopK activation · support ≥3 tasks · NEWLINE/SPACE are visible aliases, not words\n119 DeepSeek tasks / 50 CodeLlama tasks · separate base/variant texts encoded in the shared same-text latent space',ha='center',fontsize=9)
    fig.subplots_adjust(top=.9,bottom=.11,hspace=.2,wspace=.16);save(fig,'10_activation_token_clouds')
    (OUT/'token_cloud_layout.json').write_text(json.dumps(layouts,indent=2,ensure_ascii=False)+'\n')
    cases=json.loads((OUT/'steering_cases.json').read_text());records=[]
    for orientation in ['negative_only','both_signs']:
        fig,axs=plt.subplots(1,2,figsize=(11,4.6))
        for ax,family in zip(axs,COLORS):
            familycases=[r for r in cases if r['family']==family and r['alpha']==-5]
            universe={r['task_id'] for r in familycases};target={r['task_id'] for r in familycases if r['passed']}
            shuffles=set();byarm={};hashes={}
            for index in [1,2,3]:
                for sign in ([-1] if orientation=='negative_only' else [-1,1]):
                    name=f'{family}_shuffle{index}_{"neg" if sign<0 else "pos"}5'
                    p=STRESS/family/'evaluations'/f'bigcodebench__{name}_eval.json';ev=json.loads(p.read_text())
                    passed={tid for tid,rs in ev['eval'].items() if any(r['correct'] for r in rs)}
                    assert set(ev['eval'])==universe
                    shuffles|=passed;byarm[name]=sorted(passed);hashes[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
            left=target-shuffles;both=target&shuffles;right=shuffles-target;neither=universe-(target|shuffles)
            records.append(dict(family=family,alpha_target=-5,shuffle_magnitudes=[5],shuffle_signs=[-1] if orientation=='negative_only' else [-1,1],
                comparison=orientation,n=len(universe),target_only=sorted(left),both=sorted(both),shuffle_only=sorted(right),neither=sorted(neither),
                target_pass_tasks=sorted(target),shuffle_union_pass_tasks=sorted(shuffles),shuffle_arms=byarm,source_sha256=hashes))
            ax.add_patch(Circle((.37,.50),.27,color=COLORS[family],alpha=.3));ax.add_patch(Circle((.63,.50),.27,color='#555555',alpha=.22))
            for x,count in [(.25,len(left)),(.5,len(both)),(.75,len(right))]:ax.text(x,.5,str(count),ha='center',va='center',fontsize=26,fontweight='bold')
            ax.text(.26,.83,f'Target −5\n{len(target)} tasks',ha='center',fontsize=11,color=COLORS[family]);ax.text(.75,.83,f'Shuffle union\n{len(shuffles)} tasks',ha='center',fontsize=11,color='#444444')
            ax.text(.5,.12,f'Neither corrected: {len(neither)}/{len(universe)}',ha='center');ax.set_title(f'{family.upper()} · feature {4810 if family=="deepseek" else 4309}',color=COLORS[family])
            ax.set_xlim(0,1);ax.set_ylim(0,1);ax.set_aspect('equal');ax.set_axis_off()
        arms=3 if orientation=='negative_only' else 6
        fig.suptitle(f'Corrected tasks: target versus union of {arms} shuffle arms at |α|=5',fontsize=13)
        fig.text(.5,.01,'Schematic areas; counts are exact · one target arm versus multiple control arms · same originally failing cohort',ha='center',fontsize=9)
        save(fig,'11_task_overlap_negative' if orientation=='negative_only' else '12_task_overlap_both_signs')
    (OUT/'task_overlap_sets.json').write_text(json.dumps(records,indent=2)+'\n')
    print(json.dumps([{k:v for k,v in r.items() if k in ['family','comparison','n','target_only','both','shuffle_only']} for r in records],indent=2))

if __name__=='__main__':main()
