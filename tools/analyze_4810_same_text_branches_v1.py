#!/usr/bin/env python3
"""Same-input branch analysis of one JOINT CrossCoder feature, CPU only."""
import ast,csv,hashlib,json,re,time
from pathlib import Path
import numpy as np
import torch
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'reports/section67_semantic_temporal_20261019_v1'
OUT=ROOT/'reports/deepseek4810_same_text_branches_20261022_v1'
ACT=ROOT/'runs/same_text_activations/deepseek_base_finetuned_layer16_rms'
CHECK=ROOT/'runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt'
FID=4810
PAT=r'(?im)^\s*(?:#\s*tests?[/\\]|#\s*test_task|from\s+task_func\s+import|class\s+Test\w*\s*\()'
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def index_at(off,char):
    hit=np.flatnonzero(off[:,1]>char);return int(hit[0]) if len(hit) else len(off)-1
def cosine(h,v):return (h@v)/(np.maximum(np.linalg.norm(h,axis=1),1e-12)*np.linalg.norm(v))
def boot_delta(x,seed=42):
    x=np.asarray(x,float);rng=np.random.default_rng(seed);means=np.mean(x[rng.integers(0,len(x),(2000,len(x)))],axis=1)
    return dict(n_tasks=len(x),mean_delta=float(x.mean()),median_delta=float(np.median(x)),ft_greater_tasks=int((x>0).sum()),
        ft_lower_tasks=int((x<0).sum()),mean_delta_bootstrap95=list(map(float,np.quantile(means,[.025,.975]))))

def main():
    started=time.monotonic();OUT.mkdir(parents=True,exist_ok=True);torch.set_num_threads(4)
    ck=torch.load(CHECK,map_location='cpu',weights_only=False);state=ck['model_state_dict']
    ea=state['encoder.weight'][FID,:4096].numpy().copy();eb=state['encoder.weight'][FID,4096:].numpy().copy();bias=float(state['encoder.bias'][FID])
    da=state['decoder_a.weight'][:,FID].numpy().copy();db=state['decoder_b.weight'][:,FID].numpy().copy()
    ba=state['decoder_a.bias'].numpy().copy();bb=state['decoder_b.bias'].numpy().copy()
    ec=ea/np.linalg.norm(ea)+eb/np.linalg.norm(eb);ec=ec/np.linalg.norm(ec)
    dc=da/np.linalg.norm(da)+db/np.linalg.norm(db);dc=dc/np.linalg.norm(dc)
    np.savez(OUT/'feature4810_branch_vectors.npz',encoder_base=ea,encoder_ft=eb,encoder_bias=bias,decoder_base=da,decoder_ft=db,decoder_bias_base=ba,decoder_bias_ft=bb)
    del ck,state
    index={(r['task_id'],r['source_text']):r for r in json.loads((ACT/'capture_manifest.json').read_text()) if r['benchmark']=='bigcodebench'}
    old=list(csv.DictReader((SRC/'natural_timing.csv').open()));old=[r for r in old if r['family']=='deepseek']
    ids=sorted({r['task_id'] for r in old},key=lambda s:int(s.split('/')[-1]));assert len(ids)==119
    cached=np.load(SRC/'deepseek_feature_activations.npz');rows=[];arrays={};profiles=[];hashes={};error=0.;activechecked=0
    weights=dict(encoder_base_norm=float(np.linalg.norm(ea)),encoder_ft_norm=float(np.linalg.norm(eb)),encoder_bias=bias,
        decoder_base_norm=float(np.linalg.norm(da)),decoder_ft_norm=float(np.linalg.norm(db)),
        encoder_direction_cosine=float(ea@eb/(np.linalg.norm(ea)*np.linalg.norm(eb))),decoder_direction_cosine=float(da@db/(np.linalg.norm(da)*np.linalg.norm(db))))
    metricnames=['encoder_contribution','encoder_cosine','decoder_cosine','decoder_centered_cosine',
        'encoder_common_cosine','decoder_common_cosine','encoder_base_reference_cosine','encoder_ft_reference_cosine',
        'decoder_base_reference_cosine','decoder_ft_reference_cosine']
    for source in ['deepseek_base','deepseek_finetuned']:
        p=Path('/tmp/dstk119_source_evaluation')/f'bigcodebench__{source}_repaired.jsonl'
        codes={r['task_id']:r['candidate_code_repaired'] for r in map(json.loads,p.read_text().splitlines())};hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
        for ti,tid in enumerate(ids,1):
            m=index[(tid,source)];pa=ACT/'bigcodebench/deepseek_base'/m['filename'];pb=ACT/'bigcodebench/deepseek_finetuned'/m['filename']
            # One source text, identically replayed through BOTH models.
            na=np.load(pa);nb=np.load(pb);ha=na['layer_16'].astype(np.float32);hb=nb['layer_16'].astype(np.float32)
            key=tid.split('/')[-1]+'__'+source;off=cached[key+'__offsets'];z=cached[key+'__z'];n=len(z)
            assert np.array_equal(na['input_ids'],nb['input_ids']) and np.array_equal(na['input_ids'],cached[key+'__ids'])
            assert ha.shape==hb.shape==(n,4096)
            ua=ha@ea;ub=hb@eb;pre=ua+ub+bias;active=z>0
            if np.any(active):error=max(error,float(np.max(abs(pre[active]-z[active]))));activechecked+=int(active.sum())
            data=dict(encoder_contribution_base=ua,encoder_contribution_ft=ub,
                encoder_cosine_base=cosine(ha,ea),encoder_cosine_ft=cosine(hb,eb),
                decoder_cosine_base=cosine(ha,da),decoder_cosine_ft=cosine(hb,db),
                decoder_centered_cosine_base=cosine(ha-ba,da),decoder_centered_cosine_ft=cosine(hb-bb,db),
                shared_z=z,shared_pre=pre)
            for name,vec in [('encoder_common_cosine',ec),('decoder_common_cosine',dc),
                ('encoder_base_reference_cosine',ea),('encoder_ft_reference_cosine',eb),
                ('decoder_base_reference_cosine',da),('decoder_ft_reference_cosine',db)]:
                data[name+'_base']=cosine(ha,vec);data[name+'_ft']=cosine(hb,vec)
            code=codes[tid];nr=next(r for r in old if r['task_id']==tid and r['source_text']==source);start=int(nr['evaluated_code_start_char'])
            marker=re.search(PAT,code[start:]);markchar=start+marker.start() if marker else None
            if markchar is not None:markchar+=len(code[markchar:])-len(code[markchar:].lstrip())
            mi=index_at(off,markchar) if markchar is not None else None
            f=next(t for t in ast.parse(code).body if isinstance(t,ast.FunctionDef) and t.name=='task_func')
            # End of first function's final non-newline character; same anchor for both models.
            lines=code.splitlines(keepends=True);endchar=sum(map(len,lines[:f.end_lineno]))
            endchar-=len(lines[f.end_lineno-1])-len(lines[f.end_lineno-1].rstrip('\r\n'))
            endi=index_at(off,endchar)
            scopes={'all':np.ones(n,bool),'main_end_pm10tokens':abs(np.arange(n)-endi)<=10,'after_main_end':off[:,0]>=endchar,
                'shared_feature_active':active}
            if mi is not None:
                scopes['marker_pm10tokens']=abs(np.arange(n)-mi)<=10
                scopes['before_marker_10tokens']=(np.arange(n)>=mi-10)&(np.arange(n)<mi)
                scopes['marker_and_next10tokens']=(np.arange(n)>=mi)&(np.arange(n)<=mi+10)
            for scope,mask in scopes.items():
                if not np.any(mask):continue
                row=dict(task_id=tid,source_text=source,scope=scope,n_tokens=int(mask.sum()),total_tokens=n,
                    shared_feature_active_tokens=int(active.sum()),mean_shared_z=float(z[mask].mean()),marker_token=mi,main_end_token=endi)
                for metric in metricnames:
                    row[metric+'_base']=float(data[metric+'_base'][mask].mean());row[metric+'_ft']=float(data[metric+'_ft'][mask].mean())
                    row[metric+'_ft_minus_base']=row[metric+'_ft']-row[metric+'_base']
                rows.append(row)
            for anchor,idx in [('visible_marker',mi),('main_end',endi)]:
                if idx is None:continue
                for rel in range(-20,41):
                    j=idx+rel
                    if 0<=j<n:
                        profiles.append(dict(task_id=tid,source_text=source,anchor=anchor,relative_token=rel,
                            **{k:float(v[j]) for k,v in data.items()}))
            for name,val in data.items():arrays[key+'__'+name]=val
            for p in [pa,pb]:hashes[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
            if ti%20==0:print('PROGRESS',source,ti,'/119',f'{time.monotonic()-started:.1f}s',flush=True)
    assert error<.002,(error,activechecked)
    summary=[]
    for source in ['deepseek_base','deepseek_finetuned']:
        for scope in ['all','main_end_pm10tokens','marker_pm10tokens','before_marker_10tokens','marker_and_next10tokens','after_main_end','shared_feature_active']:
            rr=[r for r in rows if r['source_text']==source and r['scope']==scope]
            if not rr:continue
            for metric in metricnames:
                ss=boot_delta([r[metric+'_ft_minus_base'] for r in rr]);ss.update(source_text=source,scope=scope,metric=metric,
                    base_task_mean=float(np.mean([r[metric+'_base'] for r in rr])),ft_task_mean=float(np.mean([r[metric+'_ft'] for r in rr])))
                summary.append(ss)
    dump(OUT/'paired_summary.json',summary);dump(OUT/'task_scope_metrics.json',rows);dump(OUT/'aligned_profiles.json',profiles)
    # Difference-in-differences against the rest of the SAME program, not another corpus.
    whole={r['task_id']:r for r in rows if r['source_text']=='deepseek_base' and r['scope']=='all'}
    local={r['task_id']:r for r in rows if r['source_text']=='deepseek_base' and r['scope']=='marker_pm10tokens'}
    specificity=[];specificity_values={}
    for metric in metricnames:
        vals=[];outside=[]
        for tid,r in local.items():
            nn=whole[tid]['n_tokens'];mm=r['n_tokens']
            if nn<=mm:continue
            delta=r[metric+'_ft_minus_base'];other=(whole[tid][metric+'_ft_minus_base']*nn-delta*mm)/(nn-mm)
            vals.append(delta-other);outside.append(other)
        stat=boot_delta(vals);stat.update(metric=metric,definition='(FT-base) within marker +/-10 tokens minus (FT-base) outside that window in the same program',
            outside_mean_delta=float(np.mean(outside)));specificity.append(stat);specificity_values[metric]=vals
    dump(OUT/'local_specificity_summary.json',specificity)
    np.savez_compressed(OUT/'per_token_measurements.npz',**arrays)
    with (OUT/'task_scope_metrics.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    dump(OUT/'VALIDATION.json',dict(texts=238,task_pairs=119,identical_token_ids_verified=True,total_active_tokens_verified=activechecked,
        max_abs_preact_minus_cached_active_z=error,checkpoint_sha256=hashlib.sha256(CHECK.read_bytes()).hexdigest(),weights=weights,
        raw_input_files_sha256=hashes,cached_npz_sha256=hashlib.sha256((SRC/'deepseek_feature_activations.npz').read_bytes()).hexdigest(),
        wall_seconds=time.monotonic()-started,new_model_execution=False,device='cpu'))
    plt.rcParams.update({'font.size':10,'pdf.fonttype':42,'svg.fonttype':'none'})
    colors=['#7654cf','#d67a16']
    with PdfPages(OUT/'SAME_TEXT_BRANCH_REVIEW.pdf') as pdf:
        def save(fig,name):
            pdf.savefig(fig,bbox_inches='tight')
            for ext in ['pdf','png','svg']:fig.savefig(OUT/f'{name}.{ext}',dpi=220,bbox_inches='tight',facecolor='white')
            plt.close(fig)
        fig=plt.figure(figsize=(13,8))
        fig.text(.06,.94,'4810: does fine-tuning change the signal under identical text?',fontsize=19,weight='bold',va='top')
        fig.text(.06,.86,'119 tasks x 2 source texts x 2 replayed models | layer 16 | existing activations only | CPU',fontsize=11)
        fig.text(.06,.78,'One shared latent: z = TopK100(ReLU(u_base + u_FT + b)), with u_model = w_model dot h_model.\nThe two u terms below are contributions to one encoder, NOT independent sparse feature activations.',fontsize=12,linespacing=1.6)
        ss=[r for r in summary if r['source_text']=='deepseek_base' and r['metric']=='encoder_contribution' and r['scope'] in ['all','before_marker_10tokens','marker_and_next10tokens','marker_pm10tokens']]
        labels={'all':'Whole evaluated text','before_marker_10tokens':'10 tokens before visible marker','marker_and_next10tokens':'Marker + next 10 tokens','marker_pm10tokens':'Marker +/-10 tokens'}
        ax=fig.add_axes([.06,.37,.88,.28]);ax.axis('off')
        tab=ax.table(cellText=[[labels[r['scope']],f"{r['base_task_mean']:.3f}",f"{r['ft_task_mean']:.3f}",f"{r['ft_lower_tasks']}/{r['n_tasks']}"] for r in ss],
            colLabels=['Original base-text region','Base contribution','FT contribution','FT lower tasks'],cellLoc='left',loc='center',colWidths=[.43,.19,.19,.19])
        tab.auto_set_font_size(False);tab.set_fontsize(11);tab.scale(1,1.7)
        fig.text(.06,.30,'Near the marker: own-branch decoder cosine is lower in FT in 113/119 tasks.\nSame fixed decoder direction: lower in 119/119 (base reference) or 111/119 (FT reference).\nThe local model contrast is also more negative than the contrast outside the window.',fontsize=11,linespacing=1.5)
        fig.text(.06,.12,'Limits: selected exploratory cohort; geometric readouts are not calibrated latent activations.\nA smaller representation under forced text does not prove that this feature mediates the behavioral improvement.\nBands on profile figures are task interquartile ranges, not confidence intervals; prompt activations excluded.',fontsize=10,color='#555555',linespacing=1.5)
        save(fig,'00_reading_guide_and_summary')
        fig,axs=plt.subplots(2,2,figsize=(13,9))
        for ax,metric,title in zip(axs.flat,metricnames,['Encoder contribution: w_m dot h_m','Encoder alignment: cosine(h_m, w_m)','Decoder alignment: cosine(h_m, d_m)','Centered decoder alignment: cosine(h_m - b_dec,m, d_m)']):
            for i,source in enumerate(['deepseek_base','deepseek_finetuned']):
                rr=[r for r in rows if r['source_text']==source and r['scope']=='all'];vals=[r[metric+'_ft_minus_base'] for r in rr]
                bp=ax.boxplot([vals],positions=[i],widths=.4,patch_artist=True,showfliers=False);bp['boxes'][0].set_facecolor(colors[i]);bp['boxes'][0].set_alpha(.4)
                rng=np.random.default_rng(42);ax.scatter(i+rng.uniform(-.12,.12,len(vals)),vals,s=10,alpha=.35,color=colors[i])
            ax.axhline(0,color='#555555',ls='--',lw=1);ax.set_xticks([0,1],['Base-generated text\n119 identical-input comparisons','FT-generated text\n119 identical-input comparisons']);ax.set_title(title,fontsize=10)
            ax.set_ylabel('FT model minus base model (task mean)');ax.grid(axis='y',alpha=.15)
        fig.suptitle('Feature 4810: compare models while holding the text fixed',fontsize=15)
        fig.text(.5,.01,'Both models read the SAME token IDs for each point. These are branch contributions / alignments, NOT separate sparse feature activations.\nRaw encoder contribution also reflects encoder weight norms; centered decoder alignment is a sensitivity check.',ha='center',fontsize=9)
        fig.subplots_adjust(hspace=.48,wspace=.32,bottom=.15,top=.9);save(fig,'01_same_text_paired_model_differences')
        def profile(ax,source,anchor,metric,title):
            rr=[r for r in profiles if r['source_text']==source and r['anchor']==anchor];ns=[]
            for side,label,color in [('base','Base model','#7654cf'),('ft','Fine-tuned model','#d67a16')]:
                xx=[];yy=[];lo=[];hi=[]
                for rel in range(-20,41):
                    vals=np.array([r[metric+'_'+side] for r in rr if r['relative_token']==rel])
                    if not len(vals):continue
                    xx.append(rel);yy.append(float(vals.mean()));lo.append(float(np.quantile(vals,.25)));hi.append(float(np.quantile(vals,.75)))
                ax.plot(xx,yy,label=label,color=color);ax.fill_between(xx,lo,hi,color=color,alpha=.12)
            ax.axvline(0,color='#555555',ls='--',lw=1);ax.set_title(title,fontsize=10);ax.set_xlabel('Token offset from shared text anchor');ax.grid(alpha=.12);ax.legend(fontsize=8)
        fig,axs=plt.subplots(2,2,figsize=(13,8.5))
        for ax,metric,title in zip(axs.flat,metricnames,['Actual encoder contribution','Unit-normalized encoder cosine','Unit-normalized decoder cosine','Centered decoder cosine']):
            profile(ax,'deepseek_base','visible_marker',metric,title)
        fig.suptitle('Both models replay the original failing base text: around the visible test/import marker',fontsize=14)
        fig.text(.5,.01,'Line: task-balanced mean; shaded band: interquartile task range, NOT confidence interval. Availability varies at sequence boundaries.\nMarker is a lexical precursor, not necessarily the first harmful operation. Encoder terms sum with one shared bias before ReLU / joint TopK.',ha='center',fontsize=9)
        fig.subplots_adjust(hspace=.42,wspace=.28,bottom=.15,top=.9);save(fig,'02_same_text_marker_profiles')
        fig,axs=plt.subplots(2,2,figsize=(13,8.5))
        for col,source in enumerate(['deepseek_base','deepseek_finetuned']):
            for row,metric in enumerate(['encoder_cosine','decoder_centered_cosine']):
                profile(axs[row,col],source,'main_end',metric,('Base-generated' if col==0 else 'FT-generated')+' text | '+metric)
        fig.suptitle('Hold text fixed within each panel: model comparison at the main-function boundary',fontsize=14)
        fig.text(.5,.01,'Anchor: newline ending first task_func definition. Left/right use DIFFERENT source texts; within each panel token IDs are identical.\nNormalized similarities are descriptive, not calibrated model-specific latent activations or causal mediation.',ha='center',fontsize=9)
        fig.subplots_adjust(hspace=.42,wspace=.28,bottom=.15,top=.9);save(fig,'03_same_text_main_end_profiles')
        fig,axs=plt.subplots(2,2,figsize=(13,8.5))
        for ax,metric,title in zip(axs.flat,
            ['encoder_base_reference_cosine','encoder_ft_reference_cosine','decoder_base_reference_cosine','decoder_ft_reference_cosine'],
            ['Both residuals: BASE encoder\nreference direction','Both residuals: FT encoder\nreference direction',
             'Both residuals: BASE decoder\nreference direction','Both residuals: FT decoder\nreference direction']):
            profile(ax,'deepseek_base','visible_marker',metric,title)
        fig.suptitle('Sensitivity: same text AND the exact same readout vector for both models',fontsize=14)
        fig.text(.5,.01,'Original failing base texts, 119 paired tasks. Eliminates branch readout differences within each panel.\nSame architecture / coordinate dimension; still a descriptive geometric comparison, not an independent sparse activation or causal mediation test.',ha='center',fontsize=9)
        fig.subplots_adjust(hspace=.42,wspace=.28,bottom=.15,top=.9);save(fig,'04_fixed_reference_direction_sensitivity')
        fig,axs=plt.subplots(2,2,figsize=(13,8))
        for ax,metric in zip(axs.flat,['encoder_contribution','encoder_cosine','decoder_cosine','decoder_common_cosine']):
            vals=np.asarray(specificity_values[metric]);rng=np.random.default_rng(42)
            ax.boxplot([vals],positions=[0],widths=.35,showfliers=False)
            ax.scatter(rng.uniform(-.13,.13,len(vals)),vals,s=12,color='#7654cf',alpha=.4);ax.axhline(0,color='#555555',ls='--')
            ax.set_xticks([0],[f'{int((vals<0).sum())}/{len(vals)} tasks: more negative near marker']);ax.set_title(metric)
            ax.set_ylabel('Local FT-base delta minus outside-window delta');ax.grid(axis='y',alpha=.15)
        fig.suptitle('Local contrast versus the rest of the SAME original base-generated program',fontsize=14)
        fig.text(.5,.01,'Negative: model difference is more negative near the marker than outside it. Task-level paired descriptive analysis.\nThis checks a global-shift explanation; it is not a held-out validation or proof of mediation. +/-10 tokens fixed for this exploratory analysis.',ha='center',fontsize=9)
        fig.subplots_adjust(hspace=.4,wspace=.32,bottom=.15,top=.9);save(fig,'05_local_contrast_vs_rest_of_code')
    print('SUMMARY',json.dumps([r for r in summary if r['scope'] in ['all','marker_pm10tokens','main_end_pm10tokens']],indent=2),flush=True)
    print('VALIDATION',json.dumps(dict(max_error=error,weights=weights,seconds=time.monotonic()-started)),flush=True)

if __name__=='__main__':main()
