#!/usr/bin/env python3
"""CodeLlama analogues of natural-text and same-input branch tables, CPU only."""
import ast,csv,difflib,hashlib,json,time
from pathlib import Path
import numpy as np
import torch
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from analyze_4309_behavior_hypothesis_v1 import statements,descendants
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'reports/section67_semantic_temporal_20261019_v1'
OUT=ROOT/'reports/codellama4309_same_text_tables_20261022_v1'
ACT=ROOT/'runs/same_text_activations/codellama_base_merged_layer16_rms'
CK=ROOT/'runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt'
FID=4309
def at(off,c):
    x=np.flatnonzero(off[:,1]>c);return int(x[0]) if len(x) else len(off)-1
def cos(h,v):return (h@v)/(np.maximum(np.linalg.norm(h,axis=1),1e-12)*np.linalg.norm(v))
def main():
    started=time.monotonic();OUT.mkdir(parents=True,exist_ok=True);torch.set_num_threads(4)
    ck=torch.load(CK,map_location='cpu',weights_only=False);s=ck['model_state_dict'];dim=s['decoder_a.weight'].shape[0]
    ea=s['encoder.weight'][FID,:dim].numpy().copy();eb=s['encoder.weight'][FID,dim:].numpy().copy();bias=float(s['encoder.bias'][FID])
    da=s['decoder_a.weight'][:,FID].numpy().copy();db=s['decoder_b.weight'][:,FID].numpy().copy()
    ba=s['decoder_a.bias'].numpy().copy();bb=s['decoder_b.bias'].numpy().copy();dc=da/np.linalg.norm(da)+db/np.linalg.norm(db);dc/=np.linalg.norm(dc)
    norms=dict(encoder_base=float(np.linalg.norm(ea)),encoder_merged=float(np.linalg.norm(eb)),decoder_base=float(np.linalg.norm(da)),decoder_merged=float(np.linalg.norm(db)))
    del ck,s
    tax={r['task_id']:r for r in csv.DictReader((ROOT/'reports/codellama_base_merged_topk100_v1_regression_taxonomy/regression_failure_cases.csv').open()) if r['benchmark']=='bigcodebench'}
    loc={r['task_id']:r for r in json.loads((SRC/'codellama_error_localization.json').read_text())}
    ix={(r['task_id'],r['source_text']):r for r in json.loads((ACT/'capture_manifest.json').read_text()) if r['benchmark']=='bigcodebench'}
    natural=[r for r in csv.DictReader((SRC/'natural_timing.csv').open()) if r['family']=='codellama']
    cached=np.load(SRC/'codellama_feature_activations.npz');rows=[];naturalrows=[];error=0.;checked=0;tokenarrays={};hashes={}
    metrics=['encoder_contribution','encoder_cosine','decoder_cosine','decoder_centered_cosine','decoder_common_cosine','decoder_base_reference_cosine','decoder_merged_reference_cosine']
    for source,field in [('codellama_base','base_code'),('codellama_merged','merged_code')]:
        for tid in sorted(loc,key=lambda t:int(t.split('/')[-1])):
            code=tax[tid][field];key=tid.split('/')[-1]+'__'+source;m=ix[(tid,source)]
            pa=ACT/'bigcodebench/codellama_base'/m['filename'];pb=ACT/'bigcodebench/codellama_merged'/m['filename'];a=np.load(pa);b=np.load(pb)
            assert np.array_equal(a['input_ids'],b['input_ids']) and np.array_equal(a['input_ids'],cached[key+'__ids'])
            ha=a['layer_16'].astype(np.float32);hb=b['layer_16'].astype(np.float32);off=cached[key+'__offsets'];z=cached[key+'__z'];n=len(z)
            assert ha.shape==hb.shape==(n,dim)
            ua=ha@ea;ub=hb@eb;active=np.flatnonzero(z>0)
            if len(active):error=max(error,float(np.max(abs((ua+ub+bias)[active]-z[active]))));checked+=len(active)
            data=dict(encoder_contribution_base=ua,encoder_contribution_merged=ub,
                encoder_cosine_base=cos(ha,ea),encoder_cosine_merged=cos(hb,eb),
                decoder_cosine_base=cos(ha,da),decoder_cosine_merged=cos(hb,db),
                decoder_centered_cosine_base=cos(ha-ba,da),decoder_centered_cosine_merged=cos(hb-bb,db),
                decoder_common_cosine_base=cos(ha,dc),decoder_common_cosine_merged=cos(hb,dc),
                decoder_base_reference_cosine_base=cos(ha,da),decoder_base_reference_cosine_merged=cos(hb,da),
                decoder_merged_reference_cosine_base=cos(ha,db),decoder_merged_reference_cosine_merged=cos(hb,db),shared_z=z)
            f=next(v for v in ast.parse(code).body if isinstance(v,ast.FunctionDef) and v.name=='task_func');lines=code.splitlines(keepends=True)
            endchar=sum(map(len,lines[:f.end_lineno]));last_newline=at(off,endchar-1)
            nr=next(r for r in natural if r['task_id']==tid and r['source_text']==source)
            first=int(active[0]) if len(active) else None
            naturalrows.append(dict(task_id=tid,source_text=source,active=bool(len(active)),mean_activation=float(z.mean()),
                first_position=first/max(1,n-1) if first is not None else None,
                first_after_main=bool(int(off[first,0])>=endchar) if first is not None else False))
            scopes={'all':np.ones(n,bool),'main_end_pm10tokens':abs(np.arange(n)-last_newline)<=10};anchor=None
            if source=='codellama_merged':
                # Reuse the SAME proposed/runtime site, transfer only through an exact text block.
                l=loc[tid];current=l['code'];ln=l['solution_line_start'];cl=current.splitlines(keepends=True)
                char=sum(map(len,cl[:ln-1]))+len(cl[ln-1])-len(cl[ln-1].lstrip())
                for block in difflib.SequenceMatcher(None,current,code,autojunk=False).get_matching_blocks():
                    if block.a<=char<block.a+block.size:anchor=at(off,block.b+char-block.a);break
                if anchor is not None:
                    jj=np.arange(n);scopes.update(error_pm10tokens=abs(jj-anchor)<=10,
                        before_error_10tokens=(jj>=anchor-10)&(jj<anchor),error_and_next10tokens=(jj>=anchor)&(jj<=anchor+10))
            for scope,mask in scopes.items():
                if not mask.any():continue
                row=dict(task_id=tid,source_text=source,scope=scope,n_tokens=int(mask.sum()),total_tokens=n,
                    error_anchor=anchor,error_evidence=loc[tid]['localization_type'] if source=='codellama_merged' else None)
                for metric in metrics:
                    row[metric+'_base']=float(data[metric+'_base'][mask].mean());row[metric+'_merged']=float(data[metric+'_merged'][mask].mean())
                    row[metric+'_merged_minus_base']=row[metric+'_merged']-row[metric+'_base']
                rows.append(row)
            for name,v in data.items():tokenarrays[key+'__'+name]=v
            for p in [pa,pb]:hashes[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    assert error<.002,error
    nt={}
    for source in ['codellama_base','codellama_merged']:
        rr=[r for r in naturalrows if r['source_text']==source];aa=[r for r in rr if r['active']]
        nt[source]=dict(n=len(rr),active=len(aa),mean_task_mean_activation=float(np.mean([r['mean_activation'] for r in rr])),
            median_first_position_active=float(np.median([r['first_position'] for r in aa])),first_after_main=sum(r['first_after_main'] for r in rr))
    ss=[]
    for source in ['codellama_base','codellama_merged']:
        for scope in ['all','before_error_10tokens','error_and_next10tokens','error_pm10tokens','main_end_pm10tokens']:
            rr=[r for r in rows if r['source_text']==source and r['scope']==scope]
            if not rr:continue
            for metric in metrics:
                d=np.array([r[metric+'_merged_minus_base'] for r in rr]);rng=np.random.default_rng(42);means=d[rng.integers(0,len(d),(2000,len(d)))].mean(axis=1)
                ss.append(dict(source_text=source,scope=scope,metric=metric,n_tasks=len(rr),base_mean=float(np.mean([r[metric+'_base'] for r in rr])),
                    merged_mean=float(np.mean([r[metric+'_merged'] for r in rr])),mean_delta=float(d.mean()),merged_lower=int((d<0).sum()),merged_higher=int((d>0).sum()),
                    delta_bootstrap95=list(map(float,np.quantile(means,[.025,.975])))))
    validation=dict(task_pairs=50,texts=100,token_identifiers_equal=True,max_preact_error=error,active_tokens_checked=int(checked),norms=norms,
        input_hashes=hashes,checkpoint_sha256=hashlib.sha256(CK.read_bytes()).hexdigest(),new_inference=False,device='cpu',wall_seconds=time.monotonic()-started)
    whole={r['task_id']:r for r in rows if r['source_text']=='codellama_merged' and r['scope']=='all'}
    local={r['task_id']:r for r in rows if r['source_text']=='codellama_merged' and r['scope']=='error_pm10tokens'}
    validation['unmapped_error_anchors']=sorted(set(whole)-set(local))
    spec=[]
    for metric in metrics:
        vals=[]
        for tid,r in local.items():
            nn=whole[tid]['n_tokens'];mm=r['n_tokens']
            if nn<=mm:continue
            d=r[metric+'_merged_minus_base'];outside=(whole[tid][metric+'_merged_minus_base']*nn-d*mm)/(nn-mm);vals.append(d-outside)
        vv=np.asarray(vals);rng=np.random.default_rng(42);boots=vv[rng.integers(0,len(vv),(2000,len(vv)))].mean(axis=1)
        spec.append(dict(metric=metric,n=len(vv),mean_local_minus_outside=float(vv.mean()),local_more_positive=int((vv>0).sum()),bootstrap95=list(map(float,np.quantile(boots,[.025,.975])))))
    (OUT/'local_specificity_summary.json').write_text(json.dumps(spec,indent=2)+'\n')
    for name,obj in [('natural_summary.json',nt),('paired_summary.json',ss),('task_scope_metrics.json',rows),('natural_task_metrics.json',naturalrows),('VALIDATION.json',validation)]:
        (OUT/name).write_text(json.dumps(obj,indent=2)+'\n')
    np.savez_compressed(OUT/'per_token_measurements.npz',**tokenarrays)
    with (OUT/'task_scope_metrics.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    plt.rcParams.update({'font.size':11,'pdf.fonttype':42})
    with PdfPages(OUT/'CODELLAMA4309_NATURAL_AND_SAME_TEXT_TABLES.pdf') as pdf:
        fig=plt.figure(figsize=(13,8));fig.text(.06,.93,'CodeLlama 4309: natural-text expression',fontsize=21,weight='bold')
        fig.text(.06,.86,'50 regressions: original base output passes; original merged output fails. Joint sparse latent measured on each text.',fontsize=11)
        ax=fig.add_axes([.06,.35,.88,.4]);ax.axis('off')
        aa=nt['codellama_base'];bb=nt['codellama_merged']
        values=[['Tasks with any activation',f"{aa['active']}/50",f"{bb['active']}/50"],
            ['Mean task-mean activation',f"{aa['mean_task_mean_activation']:.4f}",f"{bb['mean_task_mean_activation']:.4f}"],
            ['Median first activation (active texts only)',f"{100*aa['median_first_position_active']:.1f}%",f"{100*bb['median_first_position_active']:.1f}%"],
            ['First activation after main-function end',f"{aa['first_after_main']}/50",f"{bb['first_after_main']}/50"]]
        t=ax.table(cellText=values,colLabels=['Measurement','Base-generated text','Merged-generated text'],cellLoc='left',loc='center',colWidths=[.54,.23,.23]);t.auto_set_font_size(False);t.set_fontsize(12);t.scale(1,2)
        fig.text(.06,.22,'The shared latent is NOT generally stronger on failing merged texts by task-mean activation.\nFirst-position percentages compare different generated programs and only active cases.\nAfter-function excludes the newline ending the function itself; a return-line newline is not after-function.',fontsize=11,linespacing=1.5)
        pdf.savefig(fig);fig.savefig(OUT/'01_natural_text_table.png',dpi=220,bbox_inches='tight');plt.close(fig)
        fig=plt.figure(figsize=(13,8));fig.text(.06,.93,'Same text: base versus merged encoder contributions',fontsize=20,weight='bold')
        fig.text(.06,.85,'Both models replay exactly the same original failing merged text. Contributions precede the JOINT ReLU / TopK.',fontsize=11)
        labels={'all':'Whole evaluated code','before_error_10tokens':'10 tokens before localized region start','error_and_next10tokens':'Region start + next 10 tokens','error_pm10tokens':'Region start +/-10 tokens'}
        rr=[r for r in ss if r['source_text']=='codellama_merged' and r['metric']=='encoder_contribution' and r['scope'] in labels]
        vals=[[labels[r['scope']],f"{r['base_mean']:.3f}",f"{r['merged_mean']:.3f}",f"{r['merged_lower']}/{r['n_tasks']}"] for r in rr]
        ax=fig.add_axes([.04,.35,.92,.4]);ax.axis('off');t=ax.table(cellText=vals,colLabels=['Region','Base contribution','Merged contribution','Merged lower'],cellLoc='left',loc='center',colWidths=[.46,.18,.18,.18]);t.auto_set_font_size(False);t.set_fontsize(11);t.scale(1,2)
        fig.text(.06,.23,'Anchor is NOT the uniform DeepSeek test/import marker. It reuses existing failure localization:\n16 runtime execution-site cases, 18 provisional line/interval cases and 16 omission regions.\nEach anchor is transferred to frozen source code only via an exact matching text block.\nWindows use available tokens; counts may differ by scope. These are NOT independent sparse activations.',fontsize=11,linespacing=1.5)
        pdf.savefig(fig);fig.savefig(OUT/'02_same_text_encoder_table.png',dpi=220,bbox_inches='tight');plt.close(fig)
        fig,axs=plt.subplots(1,3,figsize=(15,5.5))
        for ax,metric in zip(axs,['encoder_cosine','decoder_cosine','decoder_common_cosine']):
            xx=[r for r in rows if r['source_text']=='codellama_merged' and r['scope']=='error_pm10tokens'];d=[r[metric+'_merged_minus_base'] for r in xx]
            ax.boxplot([d],showfliers=False);ax.scatter(1+np.random.default_rng(42).uniform(-.1,.1,len(d)),d,color='#d67a16',alpha=.45,s=20);ax.axhline(0,color='#555555',ls='--')
            ax.set_title(metric);ax.set_xticks([1],[f'{sum(v<0 for v in d)}/{len(d)} merged lower']);ax.set_ylabel('Merged minus base, same text / tokens');ax.grid(axis='y',alpha=.15)
        fig.suptitle('Normalized / fixed-readout checks near the localized region',fontsize=15)
        fig.text(.5,.015,'Own encoder / own decoder directions, then one common decoder direction for both models.\nGeometric readouts are not calibrated independent feature activations; selected exploratory cohort, no mediation claim.',ha='center',fontsize=10)
        fig.subplots_adjust(bottom=.20,wspace=.32,top=.83);pdf.savefig(fig);fig.savefig(OUT/'03_normalized_same_text_checks.png',dpi=220,bbox_inches='tight');plt.close(fig)
    print('NATURAL',json.dumps(nt,indent=2));print('PAIRED',json.dumps([r for r in ss if r['source_text']=='codellama_merged' and r['metric'] in ['encoder_contribution','decoder_cosine','decoder_common_cosine']],indent=2));print('VALIDATION',error,time.monotonic()-started)
if __name__=='__main__':main()
