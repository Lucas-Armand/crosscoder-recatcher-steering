#!/usr/bin/env python3
"""Build paper-ready figures and data-derived tables for sections 6.7/6.8."""
import ast,csv,hashlib,json,shutil,textwrap
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from plot_section67_clouds_overlap_v1 import cloud

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'reports'
SRC=R/'section67_semantic_temporal_20261019_v1'
OUT=R/'overleaf_sections67_68_20261022_v1'
PKG=OUT/'crosscoder_case_studies'
FIG=PKG/'figures'
TBL=PKG/'tables'
def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def save(fig,name):
    for ext in ['pdf','png','svg']:fig.savefig(FIG/f'{name}.{ext}',dpi=260,bbox_inches='tight',facecolor='white')
    plt.close(fig)
def tablefile(name,text):
    (TBL/name).write_text(text.strip()+'\n')
def main():
    FIG.mkdir(parents=True,exist_ok=True);TBL.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.size':9,'pdf.fonttype':42,'svg.fonttype':'none'})
    curves=list(csv.DictReader((SRC/'curves.csv').open()));control=[r for r in curves if r['kind']=='target' or (r['kind']=='shuffle' and float(r['alpha'])<0)]
    # 1. Only comparable, same-sign controls in the main figure. Full positive arms remain in supporting reports.
    fig,axs=plt.subplots(2,2,figsize=(8.3,5.6),sharex=True,sharey='row')
    endpoint=[]
    for col,(family,fid,n,color) in enumerate([('deepseek',4810,119,'#7654cf'),('codellama',4309,50,'#d67a16')]):
        for kind,ident in [('target',str(fid))]+[('shuffle',str(i)) for i in [1,2,3]]:
            rr=sorted([r for r in control if r['family']==family and r['kind']==kind and r['identity']==ident],key=lambda r:float(r['magnitude']))
            assert len(rr)==5 and [float(r['magnitude']) for r in rr]==[1,2,3,4,5]
            linecolor=color if kind=='target' else ['#333333','#777777','#aaaaaa'][int(ident)-1]
            label=f'Feature {ident}' if kind=='target' else f'Shuffle {ident}'
            for row,field in [(0,'passed'),(1,'changed')]:
                axs[row,col].plot([0]+[float(r['magnitude']) for r in rr],[0]+[100*int(r[field])/n for r in rr],
                    color=linecolor,ls='-' if kind=='target' else '--',marker='o' if kind=='target' else None,lw=2 if kind=='target' else 1.3,ms=3,label=label)
            endpoint.append({**rr[-1]})
        axs[0,col].set_title(('DeepSeek base' if col==0 else 'CodeLlama merged')+f' (n={n})',color=color,fontsize=10)
        axs[0,col].legend(fontsize=7,loc='upper left');axs[1,col].set_xlabel(r'Steering magnitude $|\alpha|$ (negative direction)')
        for ax in axs[:,col]:ax.set_xticks(range(6));ax.grid(alpha=.15)
    axs[0,0].set_ylabel('Official fail-to-pass (%)');axs[1,0].set_ylabel('Changed evaluated code (%)')
    axs[0,0].set_ylim(0,14);axs[1,0].set_ylim(0,65)
    fig.tight_layout(pad=1.2);save(fig,'shuffle_corrections_and_changes')
    # 2. Task-level temporal evidence with no cross-text median interpretation.
    ds=read(R/'deepseek4810_marker_followup_20261022_v1/natural_task_positions.json')
    cl=read(R/'codellama4309_temporal_precedence_20261019_v1/task_temporal_relations.json')
    fig,(ax,bx)=plt.subplots(1,2,figsize=(8.3,3.3))
    dd=np.array([r['activation_minus_marker_tokens'] for r in ds]);bins=[int((dd<-20).sum()),int(((dd>=-20)&(dd<=-11)).sum()),int(((dd>=-10)&(dd<=-2)).sum()),int((dd==-1).sum()),int((dd==0).sum()),int((dd==1).sum())]
    assert sum(bins)==119 and dd.max()==1
    ax.bar(range(6),bins,color=['#268b75']*4+['#7654cf']*2)
    ax.set_xticks(range(6),['<-20','-20:-11','-10:-2','-1','0','+1']);ax.set_ylabel('Tasks');ax.set_xlabel('First activation minus visible marker (tokens)');ax.set_title('DeepSeek 4810: lexical precursor',color='#7654cf',fontsize=10)
    for i,v in enumerate(bins):ax.text(i,v+.5,str(v),ha='center',fontsize=8)
    ax.set_ylim(0,max(bins)+7);ax.grid(axis='y',alpha=.15)
    keys=['before','same_token_or_within_region','after','not_observed_or_unmapped'];counts=[sum(r['relation']==k for r in cl) for k in keys]
    bx.bar(range(4),counts,color=['#268b75','#d67a16','#999999','#cccccc']);bx.set_xticks(range(4),['Before','Within','After','Unavailable']);bx.set_ylabel('Tasks');bx.set_title('CodeLlama 4309: localized failure region',color='#d67a16',fontsize=10)
    for i,v in enumerate(counts):bx.text(i,v+.5,str(v),ha='center',fontsize=8)
    bx.set_ylim(0,max(counts)+7);bx.grid(axis='y',alpha=.15)
    fig.tight_layout(pad=1.2);save(fig,'temporal_relation_to_behavior')
    # 3. Token evidence: cloud for DeepSeek, concrete first-token contexts for CodeLlama.
    fig,(ax,bx)=plt.subplots(1,2,figsize=(8.3,3.5),gridspec_kw={'width_ratios':[1.05,1]})
    ax.set_axis_off();stats=list(csv.DictReader((SRC/'deepseek_base_token_statistics.csv').open()))
    ax.set_title('DeepSeek 4810: failing base text',color='#7654cf',fontsize=10)
    # Cloud method is unchanged, but smaller paper canvas requires proportionally smaller font.
    fig.tight_layout(pad=1.2);layout=cloud(ax,stats,'#7654cf',42)
    bx.set_axis_off();bx.set_title('CodeLlama 4309: failing merged text',color='#d67a16',fontsize=10)
    snippets=[('/183: repaired at alpha -5','return HttpResponse(json.dumps(data), status=200)'),('/490: repaired at alpha -5','return xmltodict.parse(s)'),('/115: still failing at alpha -5',"raise ValueError('task_func() requires a non-empty list of numbers')")]
    y=.87
    for label,code in snippets:
        bx.text(.01,y,label,transform=bx.transAxes,fontsize=8,weight='bold');y-=.11
        wrapped=textwrap.fill(code,width=40,replace_whitespace=False,drop_whitespace=False)
        bx.text(.01,y,wrapped+' [NEWLINE*]',transform=bx.transAxes,fontsize=7.5,fontfamily='monospace',va='top',color='#5a3b1e')
        y-=.20 if '\n' in wrapped else .15
    bx.text(.01,.01,'* First naturally active token.\nThe newline follows the preceding expression.',transform=bx.transAxes,fontsize=7.5,color='#555555')
    save(fig,'token_cloud_and_return_contexts')
    # 4. Exact excerpts: useful changes and limits, not a pure-stopping narrative.
    dsinspect={r['task_id']:r for r in read(R/'deepseek4810_marker_followup_20261022_v1/alpha5_changed_case_inspection.json')}
    clinspect={r['task_id']:r for r in read(R/'codellama4309_change_comparison_20261019_v1/task_arm_comparison.json') if r['kind']=='target'}
    entries=[('DeepSeek /695: FAIL -> PASS',"#tests/test_task_func.py\nimport unittest\nimport numpy as np\nfrom task_func import task_func",'#task_func([(1, 2, 3, 4),\n#           (5, 6, 7, 8),\n#           (9, 10, 11, 12)], 2)', 'Main-function AST unchanged.'),
        ('CodeLlama /490: FAIL -> PASS',clinspect['BigCodeBench/490']['before_main'].strip(),textwrap.dedent(clinspect['BigCodeBench/490']['after_main']),'Return-only body expands to include JSON persistence.'),
        ('DeepSeek /1115: FAIL -> PASS',"#test_task_func.py\nimport unittest\nimport random\nfrom task_func import task_func",'# Write your code here\n\n# Write your code here\n\n# Write your code here','Main-function AST unchanged; repeated comments remain.'),
        ('CodeLlama /634: still FAIL',clinspect['BigCodeBench/634']['before_main'], '\n'.join(clinspect['BigCodeBench/634']['after_main'].splitlines()[:3])+'\n[... further repeated assignments ...]','Expanded to 35 statements; no useful return.')]
    # Use exact post-steering excerpts for DeepSeek, not manually broken/commented lines.
    for idx,tid,marker in [(0,'BigCodeBench/695','#task_func([(1'),(2,'BigCodeBench/1115','# Write your code here')]:
        code=dsinspect[tid]['code_after']
        f=next(n for n in ast.parse(code).body if isinstance(n,ast.FunctionDef) and n.name=='task_func')
        endchar=sum(len(s) for s in code.splitlines(keepends=True)[:f.end_lineno])
        offset=code.index(marker,endchar);lines=code[offset:].splitlines();snippet='\n'.join(lines[:5] if idx==2 else lines[:1])
        assert dsinspect[tid]['main_ast_changed'] is False
        title,before,_,note=entries[idx];entries[idx]=(title,before,snippet,note)
    fig,axs=plt.subplots(2,2,figsize=(7.6,5.9))
    for ax,(title,before,after,note) in zip(axs.flat,entries):
        ax.set_facecolor('#1e2230');ax.set_xticks([]);ax.set_yticks([]);ax.set_title(title,loc='left',fontsize=9,color='#7654cf' if title.startswith('DeepSeek') else '#d67a16',pad=8)
        txt='BEFORE\n'+before+'\n\nAFTER (alpha -5)\n'+after
        shown=[]
        for line in txt.splitlines():shown.extend(textwrap.wrap(line,width=49,replace_whitespace=False,drop_whitespace=False) or [''])
        ax.text(.025,.96,'\n'.join(shown),transform=ax.transAxes,color='#e0e4ee',va='top',fontfamily='monospace',fontsize=7.5)
        ax.text(.025,.025,textwrap.fill(note,49),transform=ax.transAxes,fontsize=7,color='#bfc8db',va='bottom')
    fig.subplots_adjust(left=.025,right=.99,top=.92,bottom=.025,wspace=.08,hspace=.30);save(fig,'paired_code_examples')
    # Auto-populate exactly the simplified tables agreed with the user.
    nt=read(R/'codellama4309_same_text_tables_20261022_v1/natural_summary.json')
    nn=list(csv.DictReader((SRC/'natural_timing.csv').open()))
    dmean={s:float(np.mean([float(r['mean_activation']) for r in nn if r['source_text']==s])) for s in ['deepseek_base','deepseek_finetuned']}
    dsrow=next(r for r in read(R/'deepseek4810_same_text_branches_20261022_v1/paired_summary.json') if r['source_text']=='deepseek_base' and r['scope']=='marker_pm10tokens' and r['metric']=='encoder_contribution')
    clrow=next(r for r in read(R/'codellama4309_same_text_tables_20261022_v1/paired_summary.json') if r['source_text']=='codellama_merged' and r['scope']=='error_pm10tokens' and r['metric']=='encoder_contribution')
    naturaltex=r'''\begin{table}[t]
\centering\small
\caption{Natural expression of the shared feature on different generated texts. Updated denotes fine-tuned for DeepSeek and merged for CodeLlama. Mean activation is averaged over evaluated tokens within each task, then equally over all tasks, including inactive tasks.}
\label{tab:case-natural-expression}
\setlength{\tabcolsep}{4pt}
\begin{tabular}{@{}lrrrr@{}}
\toprule
 & \multicolumn{2}{c}{Tasks with activation} & \multicolumn{2}{c}{Mean activation} \\
\cmidrule(lr){2-3}\cmidrule(l){4-5}
Model / feature & Base text & Updated text & Base text & Updated text \\
\midrule
DeepSeek / 4810 & 119/119 & 75/119 & %.3f & %.3f \\
CodeLlama / 4309 & 50/50 & 44/50 & %.3f & %.3f \\
\bottomrule
\end{tabular}
\end{table}'''%(dmean['deepseek_base'],dmean['deepseek_finetuned'],nt['codellama_base']['mean_task_mean_activation'],nt['codellama_merged']['mean_task_mean_activation'])
    tablefile('natural_expression.tex',naturaltex)
    pairedtex=r'''\begin{table}[t]
\centering\small
\caption{Same-text encoder contributions within $\pm10$ tokens of the selected anchor. Both models replay the identical weak-model text: base-generated for DeepSeek, merged-generated for CodeLlama. These are terms of one joint encoder preactivation, not independent sparse activations.}
\label{tab:case-same-text}
\setlength{\tabcolsep}{4pt}
\begin{tabular}{@{}lrrr@{}}
\toprule
 & \multicolumn{2}{c}{Mean encoder contribution} & \\
\cmidrule(lr){2-3}
Model / feature & Base model & Updated model & Updated lower \\
\midrule
DeepSeek / 4810 & %.3f & %.3f & %d/%d \\
CodeLlama / 4309 & %.3f & %.3f & %d/%d \\
\bottomrule
\end{tabular}
\end{table}'''%(dsrow['base_task_mean'],dsrow['ft_task_mean'],dsrow['ft_lower_tasks'],dsrow['n_tasks'],clrow['base_mean'],clrow['merged_mean'],clrow['merged_lower'],clrow['n_tasks'])
    tablefile('same_text_contributions.tex',pairedtex)
    sources=[SRC/'curves.csv',SRC/'natural_timing.csv',SRC/'deepseek_base_token_statistics.csv',
        R/'deepseek4810_marker_followup_20261022_v1/SUMMARY.json',R/'deepseek4810_marker_components_20261022_v1/SUMMARY.json',
        R/'deepseek4810_same_text_branches_20261022_v1/paired_summary.json',R/'codellama4309_same_text_tables_20261022_v1/paired_summary.json',
        SRC/'steering_cases.json',R/'codellama4309_change_comparison_20261019_v1/task_arm_comparison.json']
    write(PKG/'plot_data.json',dict(control_curves=control,endpoint=endpoint,deepseek_timing=ds,codellama_timing=cl,cloud_layout=layout,natural_means=dmean,same_text_rows=[dsrow,clrow]))
    write(PKG/'DATA_MANIFEST.json',dict(new_inference=False,source_files=[dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sources],
        primary_control_sign='negative, matching both targets',paired_tasks=dict(deepseek=119,codellama=48),
        excluded_codellama_error_anchors=['BigCodeBench/115','BigCodeBench/423'],
        natural_text='frozen evaluated capture source',intervention_comparison='matched current extraction of alpha0 and steering arm'))
    # Supporting visualizations retain the caveats outside the short main narrative.
    supp=PKG/'supporting_figures';supp.mkdir(exist_ok=True)
    files={
        'deepseek_full_same_text_review.pdf':R/'deepseek4810_same_text_branches_20261022_v1/SAME_TEXT_BRANCH_REVIEW.pdf',
        'codellama_full_same_text_review.pdf':R/'codellama4309_same_text_tables_20261022_v1/CODELLAMA4309_NATURAL_AND_SAME_TEXT_TABLES.pdf',
        'deepseek_markers_and_continuations.pdf':R/'deepseek4810_marker_followup_20261022_v1/DEEPSEEK4810_MARKER_DISTRIBUTION_AND_STEERING.pdf',
        'marker_component_ablation.pdf':R/'deepseek4810_marker_components_20261022_v1/01_marker_component_ablation.pdf',
        'codellama_all50_regions.pdf':R/'codellama4309_temporal_return_visuals_20261019_v1/01_temporal_regions_50.pdf',
        'codellama_return_newline_specificity.pdf':R/'codellama4309_temporal_return_visuals_20261019_v1/02_return_newline_specificity.pdf',
        'codellama_eight_activation_examples.pdf':R/'codellama4309_temporal_return_visuals_20261019_v1/03_annotated_activation_examples.pdf',
        'shuffle_both_signs.pdf':SRC/'03_shuffle_both_signs.pdf'}
    for dest,path in files.items():shutil.copyfile(path,supp/dest)
    # Preserve the exact evaluated strings behind natural activations, not just ephemeral /tmp paths.
    data_dir=PKG/'data';data_dir.mkdir(exist_ok=True)
    wanted={r['task_id'] for r in ds};snapshot_hashes={}
    for source in ['deepseek_base','deepseek_finetuned']:
        path=Path('/tmp/dstk119_source_evaluation')/f'bigcodebench__{source}_repaired.jsonl'
        dest=data_dir/path.name
        if path.exists():
            source_rows=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
            source_rows=[r for r in source_rows if r['task_id'] in wanted]
            assert len(source_rows)==119
            dest.write_text(''.join(json.dumps(dict(task_id=r['task_id'],candidate_code_repaired=r['candidate_code_repaired']),ensure_ascii=False)+'\n' for r in source_rows))
        assert dest.exists(),f'Restore frozen evaluated source from {dest}'
        restored=[json.loads(line) for line in dest.read_text().splitlines() if line.strip()];assert {r['task_id'] for r in restored}==wanted
        snapshot_hashes[source]={r['task_id']:hashlib.sha256(r['candidate_code_repaired'].encode()).hexdigest() for r in restored}
    write(data_dir/'frozen_code_sha256.json',snapshot_hashes)
    print('BUILT',OUT,flush=True)
if __name__=='__main__':main()
