#!/usr/bin/env python3
"""Distribution around visible markers and matched steering continuation changes."""
import ast,csv,difflib,json,re,hashlib,textwrap
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from plot_deepseek4810_marker_precedence_v1 import PATTERN

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'reports/section67_semantic_temporal_20261019_v1'
OUT=ROOT/'reports/deepseek4810_marker_followup_20261022_v1'
COMMENT=re.compile(r'(?im)^[ \t]*#[ \t]*(?:tests?[/\\]|test_task)')
IMPORT=re.compile(r'(?im)^[ \t]*from[ \t]+task_func[ \t]+import\b')
def dump(name,obj):(OUT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
def token_at(offsets,char):
    ix=np.flatnonzero(offsets[:,1]>char);return int(ix[0]) if len(ix) else len(offsets)-1
def main_ast(code):
    try:
        f=next(n for n in ast.parse(code).body if isinstance(n,ast.FunctionDef) and n.name=='task_func')
        body=f.body
        if body and isinstance(body[0],ast.Expr) and isinstance(body[0].value,ast.Constant) and isinstance(body[0].value.value,str):body=body[1:]
        return ast.dump(ast.Module(body=body,type_ignores=[]),include_attributes=False)
    except (SyntaxError,StopIteration):return None
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    natural=[r for r in csv.DictReader((SRC/'natural_timing.csv').open()) if r['family']=='deepseek' and r['source_text']=='deepseek_base']
    frozen={r['task_id']:r['candidate_code_repaired'] for r in map(json.loads,Path('/tmp/dstk119_source_evaluation/bigcodebench__deepseek_base_repaired.jsonl').read_text().splitlines())}
    arrays=np.load(SRC/'deepseek_feature_activations.npz');timing=[];meta={r['task_id']:r for r in natural}
    for r in natural:
        tid=r['task_id'];code=frozen[tid];start=int(r['evaluated_code_start_char']);m=re.search(PATTERN,code[start:]);assert m
        ch=start+m.start();visible=ch+len(code[ch:])-len(code[ch:].lstrip());end=code.find('\n',visible);end=len(code) if end<0 else end
        key=tid.split('/')[-1]+'__deepseek_base';off=arrays[key+'__offsets'];a=int(r['first_active_token']);lo,hi=map(int,off[a]);mi=token_at(off,visible);endindex=token_at(off,end)
        kind='comment' if code[visible]=='#' else 'import' if code[visible:].lower().startswith('from') else 'class'
        charrel='before_line' if lo<visible else 'inside_visible_line' if lo<end else 'newline_ending_line' if lo==end and code[lo:hi].startswith('\n') else 'after_line'
        im=IMPORT.search(code[start:]);importchar=start+im.start() if im else None
        if importchar is not None:importchar+=len(code[importchar:])-len(code[importchar:].lstrip())
        timing.append(dict(task_id=tid,marker_kind=kind,marker_line=code[visible:end],first_activation_token=a,
            marker_first_token=mi,marker_line_end_token=endindex,activation_minus_marker_tokens=a-mi,
            activation_minus_marker_pp=100*(a-mi)/max(1,len(off)-1),activation_vs_line=charrel,
            first_activation_span=code[lo:hi],activation_context=code[max(start,lo-90):hi+90],
            feature_before_task_func_import_token=a<token_at(off,importchar) if importchar is not None else None,
            activation_minus_task_func_import_tokens=a-token_at(off,importchar) if importchar is not None else None))
    cases=[r for r in json.loads((SRC/'steering_cases.json').read_text()) if r['family']=='deepseek'];assert len(cases)==595
    baseline_eval=json.loads((ROOT/'runs/feature_stress_alpha0_20261015_v1/deepseek/evaluations/bigcodebench__deepseek_weak_alpha0_eval.json').read_text())['eval']
    records=[];inspection=[]
    for r in cases:
        tid=r['task_id'];prefix=frozen[tid][:int(meta[tid]['evaluated_code_start_char'])]
        assert r['code_before'].startswith(prefix) and r['code_after'].startswith(prefix)
        b=r['code_before'][len(prefix):];a=r['code_after'][len(prefix):]
        beforemarker=bool(re.search(PATTERN,b));aftermarker=bool(re.search(PATTERN,a))
        bc=bool(COMMENT.search(b));ac=bool(COMMENT.search(a));bi=bool(IMPORT.search(b));ai=bool(IMPORT.search(a))
        bast,aast=main_ast(r['code_before']),main_ast(r['code_after'])
        rec=dict(task_id=tid,alpha=r['alpha'],passed=r['passed'],changed=r['changed'],
            comment_before=bc,comment_after=ac,comment_removed=bc and not ac,comment_retained=bc and ac,
            any_marker_before=beforemarker,any_marker_after=aftermarker,all_markers_removed=beforemarker and not aftermarker,
            task_func_import_before=bi,task_func_import_after=ai,task_func_import_removed=bi and not ai,
            main_ast_comparable=bast is not None and aast is not None,main_ast_changed=bast!=aast if bast is not None and aast is not None else None)
        records.append(rec)
        if r['alpha']==-5 and r['changed']:
            inspection.append(dict(**rec,code_before=r['code_before'],code_after=r['code_after'],
                diff='\n'.join(difflib.unified_diff(r['code_before'].splitlines(),r['code_after'].splitlines(),fromfile='alpha0',tofile='alpha-5',lineterm=''))))
    summaries=[]
    for alpha in [-1,-2,-3,-4,-5]:
        rr=[r for r in records if r['alpha']==alpha]
        summaries.append(dict(alpha=alpha,n=len(rr),changed=sum(r['changed'] for r in rr),passed=sum(r['passed'] for r in rr),
            by_group={label:dict(n=len(sel),comment_before=sum(r['comment_before'] for r in sel),comment_removed=sum(r['comment_removed'] for r in sel),
                comment_retained=sum(r['comment_retained'] for r in sel),all_markers_removed=sum(r['all_markers_removed'] for r in sel),
                task_func_import_before=sum(r['task_func_import_before'] for r in sel),task_func_import_removed=sum(r['task_func_import_removed'] for r in sel),
                main_ast_changed=sum(r['main_ast_changed'] is True for r in sel),main_ast_unavailable=sum(not r['main_ast_comparable'] for r in sel))
                for label,sel in [('all',rr),('changed',[r for r in rr if r['changed']]),('passed',[r for r in rr if r['passed']])]}))
    tc=Counter(r['activation_vs_line'] for r in timing if r['marker_kind']=='comment')
    d=np.array([r['activation_minus_marker_tokens'] for r in timing]);pp=np.array([r['activation_minus_marker_pp'] for r in timing])
    summ=dict(n=119,sign_definition='activation minus visible marker; negative = before, positive = after',
        token_quantiles={str(q):float(np.quantile(d,q)) for q in [0,.1,.25,.5,.75,.9,1]},
        within_1_token=int((abs(d)<=1).sum()),within_5_tokens=int((abs(d)<=5).sum()),within_10_tokens=int((abs(d)<=10).sum()),
        comment_line_relations=dict(tc),marker_types=dict(Counter(r['marker_kind'] for r in timing)),
        task_func_import_present=sum(r['feature_before_task_func_import_token'] is not None for r in timing),
        feature_before_task_func_import_token=sum(r['feature_before_task_func_import_token'] is True for r in timing),
        new_inference=False)
    dump('SUMMARY.json',summ);dump('dose_summary.json',summaries);dump('natural_task_positions.json',timing)
    dump('steering_marker_transitions.json',records);dump('alpha5_changed_case_inspection.json',inspection)
    # For successes, use the actually recorded missing module, not the comment heuristic.
    success_errors=[]
    for r in inspection:
        if not r['passed']:continue
        tid=r['task_id'];details=baseline_eval[tid][0]['details'];err=str(details.get('ALL',''));match=re.search(r"No module named '([^']+)'",err)
        module=match.group(1) if match else None;code=frozen[tid];found=[]
        if module:
            for node in ast.walk(ast.parse(code)):
                if (isinstance(node,ast.ImportFrom) and node.module==module) or (isinstance(node,ast.Import) and any(a.name==module for a in node.names)):
                    found.append(node)
        first=min(found,key=lambda n:(n.lineno,n.col_offset)) if found else None
        key=tid.split('/')[-1]+'__deepseek_base';off=arrays[key+'__offsets'];a=int(meta[tid]['first_active_token'])
        char=sum(len(s) for s in code.splitlines(keepends=True)[:first.lineno-1])+first.col_offset if first else None
        ii=token_at(off,char) if char is not None else None
        success_errors.append(dict(task_id=tid,baseline_failure=details,missing_module=module,
            matching_import_line=code.splitlines()[first.lineno-1] if first else None,
            activation_minus_matching_import_tokens=a-ii if ii is not None else None,
            note='Earliest textual import matching the recorded missing-module error; not a full runtime-trace localization. Natural positions refer to frozen source.'))
    dump('alpha5_success_failure_evidence.json',success_errors)
    with (OUT/'natural_task_positions.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(timing[0]));w.writeheader();w.writerows(timing)
    # Review all 57 changed alpha-five cases, not just successful/comment-removed examples.
    md=['# DeepSeek 4810: all changed programs at alpha -5','',
        'Same re-extracted alpha-zero/steering code comparison. Comment presence is lexical, not a correctness judgment. Full solutions and diff are retained in companion JSON.','']
    for r in inspection:
        md += [f"## {r['task_id']} / {'PASS' if r['passed'] else 'FAIL'}",'',
            f"Comment: {r['comment_before']} -> {r['comment_after']}; task_func import: {r['task_func_import_before']} -> {r['task_func_import_after']}; main AST changed: {r['main_ast_changed']}",'','```diff',r['diff'],'```','']
    (OUT/'ALPHA5_ALL_CHANGED_DIFFS.md').write_text('\n'.join(md)+'\n')
    plt.rcParams.update({'font.size':11,'pdf.fonttype':42,'svg.fonttype':'none'})
    with PdfPages(OUT/'DEEPSEEK4810_MARKER_DISTRIBUTION_AND_STEERING.pdf') as pdf:
        def save(fig,name):
            pdf.savefig(fig,bbox_inches='tight')
            for ext in ['pdf','png','svg']:fig.savefig(OUT/f'{name}.{ext}',dpi=220,bbox_inches='tight',facecolor='white')
            plt.close(fig)
        fig,(ax,bx)=plt.subplots(1,2,figsize=(14,5.7))
        # Integer-wide near-boundary histogram + full signed ECDF retains outliers.
        near=d[(d>=-15)&(d<=15)];ax.hist(near,bins=np.arange(-15.5,16.5,1),color='#7654cf',edgecolor='white');ax.axvline(0,color='#333333',ls='--')
        ax.set_xlabel('First activation token minus visible marker token');ax.set_ylabel('Tasks');ax.set_title(f'Near marker: {len(near)}/119 tasks (remaining tails retained at right)')
        sd=np.sort(d);bx.step(sd,np.arange(1,120)/119*100,where='post',color='#7654cf',lw=2);bx.axvline(0,color='#333333',ls='--')
        bx.set_xlabel('Signed token distance (full range)');bx.set_ylabel('Cumulative tasks (%)');bx.set_title(f'All 119 tasks; median distance {np.median(d):+.0f} tokens');bx.grid(alpha=.15)
        fig.suptitle('DeepSeek 4810: distribution relative to the FIRST VISIBLE marker token',fontsize=15)
        fig.text(.5,.015,'Negative = activation before marker; zero = same token; positive = after. Prompt excluded. Lexical marker, not a validated first harmful operation.',ha='center',fontsize=9)
        fig.subplots_adjust(wspace=.3,bottom=.17,top=.83);save(fig,'01_signed_token_distance_distribution')
        fig,ax=plt.subplots(figsize=(11,5.4));keys=['before_line','inside_visible_line','newline_ending_line','after_line'];labels=['Before visible\ncomment line','Within comment\ntext','Newline ending\ncomment line','After comment\nline']
        bars=ax.bar(labels,[tc[k] for k in keys],color=['#268b75','#c49a37','#7654cf','#999999'])
        for b,k in zip(bars,keys):ax.text(b.get_x()+b.get_width()/2,b.get_height()+.6,f'{tc[k]}/107\n{100*tc[k]/107:.1f}%',ha='center')
        ax.set_ylim(0,max(tc.values())+12);ax.set_ylabel('Tasks');ax.set_title('Where is first activation relative to the comment itself?');ax.grid(axis='y',alpha=.15)
        fig.text(.5,.015,'107 tasks whose first lexical marker is a test-file comment. Other 12 begin with task_func import / Test-class marker.\nComment text is not executable Python; this chart does not identify the first actual error.',ha='center',fontsize=9)
        fig.subplots_adjust(bottom=.2);save(fig,'02_activation_relative_to_comment_line')
        fig,(ax,bx)=plt.subplots(1,2,figsize=(14,5.7));s=summaries[-1]
        for ax,group,title in [(ax,'changed','All changed outputs at alpha -5'),(bx,'passed','Official corrections at alpha -5')]:
            g=s['by_group'][group];base=g['comment_before'];vals=[g['comment_removed'],g['comment_retained'],g['n']-base];labs=['Comment\nremoved','Comment\nretained','No matching\ncomment before']
            bars=ax.bar(labs,vals,color=['#268b75','#7654cf','#999999'])
            for b,v in zip(bars,vals):ax.text(b.get_x()+b.get_width()/2,v+.3,str(v),ha='center')
            ax.set_ylim(0,max(vals)+5);ax.set_ylabel('Tasks');ax.set_title(title+f" (n={g['n']})");ax.grid(axis='y',alpha=.15)
        fig.suptitle('Did steering remove the #tests / #test_task comments?',fontsize=15)
        fig.text(.5,.015,'Matched alpha-zero versus alpha-minus-five evaluated code, same extractor. Removing a comment is not itself a repair.\nAll doses and task_func-import transitions are recorded separately in dose_summary.json and the case inspection files.',ha='center',fontsize=9)
        fig.subplots_adjust(wspace=.25,bottom=.2,top=.83);save(fig,'03_comment_removal_under_steering')
        # Concrete examples include successful residual continuation and a failed cleanup.
        selections=['BigCodeBench/695','BigCodeBench/666','BigCodeBench/1115','BigCodeBench/25']
        fig,axs=plt.subplots(4,2,figsize=(15,12.5))
        for row,tid in enumerate(selections):
            r=next(r for r in inspection if r['task_id']==tid);prefix=frozen[tid][:int(meta[tid]['evaluated_code_start_char'])]
            b=r['code_before'];m=re.search(PATTERN,b[len(prefix):]);start=len(prefix)+m.start();start+=len(b[start:])-len(b[start:].lstrip())
            # Same preceding text anchor makes after excerpts auditable; fallback is marked.
            anchor=b[max(0,start-60):start];hits=r['code_after'].find(anchor)
            at=hits+len(anchor) if hits>=0 else None
            for col,code in enumerate([b,r['code_after']]):
                ax=axs[row,col];ax.set_facecolor('#1e2230');ax.set_xticks([]);ax.set_yticks([])
                caption='baseline FAIL' if col==0 else 'steering '+('PASS' if r['passed'] else 'FAIL')
                ax.set_title(tid+' | '+caption,loc='left',fontsize=11,color='#b66e19')
                if col==0:snippet=code[start:].splitlines()[:8]
                elif at is not None:snippet=code[at:].splitlines()[:8]
                else:
                    # Mark a nonaligned excerpt; do not pretend it is the exact old boundary.
                    ff=next(n for n in ast.parse(code).body if isinstance(n,ast.FunctionDef) and n.name=='task_func')
                    snippet=['[After main function; old boundary changed]']+code.splitlines()[ff.end_lineno:ff.end_lineno+7]
                shown=[]
                for line in snippet:
                    shown.extend(textwrap.wrap(line,width=75,replace_whitespace=False,drop_whitespace=False) or [''])
                ax.text(.025,.92,'\n'.join(shown),fontfamily='monospace',fontsize=8,color='#dde3ef',va='top',transform=ax.transAxes)
                ax.text(.025,.035,f"main AST changed: {r['main_ast_changed']} | display excerpt only",color='#c0cad6',fontsize=8,transform=ax.transAxes)
        fig.suptitle('Removing the harmful test/import continuation is not the same as stopping generation',fontsize=15)
        fig.text(.5,.015,'Exact saved evaluated-code excerpts. /695: cleanup; /666: executable examples remain; /1115: repetitive comments remain; /25: marker removal without a pass.\nFull before/after code and diffs are retained in the companion inspection JSON / Markdown.',ha='center',fontsize=9)
        fig.subplots_adjust(left=.03,right=.98,top=.93,bottom=.08,hspace=.35,wspace=.08);save(fig,'04_concrete_continuation_examples')
        fig,ax=plt.subplots(figsize=(11,6));ss=sorted(success_errors,key=lambda r:r['activation_minus_matching_import_tokens'])
        values=[-r['activation_minus_matching_import_tokens'] for r in ss]
        ax.barh(range(len(ss)),values,color='#268b75')
        ax.set_yticks(range(len(ss)),[r['task_id'].replace('BigCodeBench','') for r in ss]);ax.invert_yaxis()
        for i,v in enumerate(values):ax.text(v+.3,i,str(v),va='center',fontsize=9)
        ax.set_xlim(0,max(values)+4);ax.set_xlabel('Tokens from first natural activation to matching missing-module import')
        ax.set_title('All 14 corrected tasks: activation precedes the import associated with baseline failure',fontsize=12)
        ax.grid(axis='x',alpha=.15)
        fig.text(.5,.02,'Baseline evaluator reports missing module task_func (11 cases) or task (3). Match earliest textual import of that module.\nThis is stronger temporal context than a comment marker, but not a proof of natural causal mediation. Frozen-text activation offsets.',ha='center',fontsize=9)
        fig.subplots_adjust(left=.10,bottom=.17,top=.88);save(fig,'05_successes_before_missing_module_import')
    print(json.dumps(summ,indent=2));print(json.dumps(summaries,indent=2))
    print('SUCCESS_IMPORT_TIMING',json.dumps(success_errors,indent=2))

if __name__=='__main__':main()
