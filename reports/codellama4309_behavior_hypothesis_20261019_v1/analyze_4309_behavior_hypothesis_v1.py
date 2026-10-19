#!/usr/bin/env python3
"""Exploratory behavioral hypotheses for 4309, with discovery cases excluded in sensitivity tables."""
import ast
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import numpy as np
from scipy.stats import spearmanr
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
PREV=ROOT/'reports/section67_semantic_temporal_20261019_v1'
OUT=ROOT/'reports/codellama4309_behavior_hypothesis_20261019_v1'
DISCOVERY={'BigCodeBench/183','BigCodeBench/490'}

def rows(p):return [json.loads(s) for s in p.read_text().splitlines() if s.strip()]
def dump(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def csvwrite(p,rs):
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
def callname(node):
    if isinstance(node,ast.Name):return node.id
    if isinstance(node,ast.Attribute):
        stem=callname(node.value)
        return stem+'.'+node.attr if stem else node.attr
    return ''
def function(code):
    return next(n for n in ast.parse(code).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name=='task_func')
def statements(f):
    body=f.body
    if body and isinstance(body[0],ast.Expr) and isinstance(body[0].value,ast.Constant) and isinstance(body[0].value.value,str):body=body[1:]
    return body
def descendants(node):
    # Do not mistake statements in uncalled nested functions for executed main-body work.
    if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.Lambda)):return
    yield node
    for child in ast.iter_child_nodes(node):yield from descendants(child)
def stops(body):
    for s in body:
        if isinstance(s,(ast.Return,ast.Raise)):return True
        if isinstance(s,ast.If) and s.orelse and stops(s.body) and stops(s.orelse):return True
        if isinstance(s,(ast.With,ast.AsyncWith)) and stops(s.body):return True
    return False
def describe(code):
    try:f=function(code)
    except (SyntaxError,StopIteration):return dict(parseable=False)
    body=statements(f);nodes=[n for s in body for n in descendants(s)];returns=[n for n in nodes if isinstance(n,ast.Return)]
    calls=[n for n in nodes if isinstance(n,ast.Call)];names={callname(n.func) for n in calls}
    stmts=[n for n in nodes if isinstance(n,ast.stmt)]
    serial=[ast.dump(s,include_attributes=False) for s in body];repeat=max(Counter(serial).values(),default=0)
    args={a.arg for a in f.args.args};used={n.id for n in nodes if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load)}
    header=any(isinstance(n,ast.Assign) and any(isinstance(t,ast.Subscript) and isinstance(t.slice,ast.Constant) and t.slice.value=='UUID' for t in n.targets) for n in nodes)
    double=any(isinstance(n.func,ast.Name) and n.func.id=='HttpResponse' and n.args and isinstance(n.args[0],ast.Call) and callname(n.args[0].func)=='json.dumps' for n in calls)
    opens=[n for n in calls if callname(n.func)=='open']
    writing=any(any(isinstance(a,ast.Constant) and isinstance(a.value,str) and any(v in a.value for v in ['w','a','+','x']) for a in n.args[1:]) or
                any(k.arg=='mode' and isinstance(k.value,ast.Constant) and any(v in str(k.value.value) for v in ['w','a','+','x']) for k in n.keywords) for n in opens)
    pandas_json=[n for n in calls if callname(n.func).endswith('.to_json')]
    to_path=any((n.args and not(isinstance(n.args[0],ast.Constant) and n.args[0].value is None)) or
                any(k.arg=='path_or_buf' and not(isinstance(k.value,ast.Constant) and k.value.value is None) for k in n.keywords) for n in pandas_json)
    records=any(any(k.arg=='orient' and isinstance(k.value,ast.Constant) and k.value.value=='records' for k in n.keywords) for n in pandas_json)
    return dict(parseable=True,return_only=len(body)==1 and isinstance(body[0],ast.Return),
        no_value_return=not any(n.value is not None and not(isinstance(n.value,ast.Constant) and n.value.value is None) for n in returns),
        may_fallthrough=not stops(body),top_level_statements=len(body),all_statements=len(stmts),
        repeated_top_level_statement=repeat>=3,max_statement_repetition=repeat,
        unused_parameter_fraction=len(args-used)/max(1,len(args)),calls=sorted(names),call_count=len(calls),
        double_serialization_pattern=double,uuid_header_assignment=header,json_file_write_pattern=writing and 'json.dump' in names,
        json_persistence_indicator=bool((writing and 'json.dump' in names) or to_path),json_records_orientation_indicator=records)

def evstat(x,y,seed=42):
    x=np.asarray(x,float);y=np.asarray(y,bool)
    if y.sum()<3 or (~y).sum()<3:return dict(positives=int(y.sum()),controls=int((~y).sum()),effect=None,ev=None)
    observed=float(x[y].mean()-x[~y].mean());rng=np.random.default_rng(seed);null=[]
    for _ in range(2000):
        p=rng.permutation(y);null.append(float(x[p].mean()-x[~p].mean()))
    sd=float(np.std(null,ddof=1))
    return dict(positives=int(y.sum()),controls=int((~y).sum()),effect=observed,null_sd=sd,ev=observed/sd if sd else None,
                nominal_permutation_p=(1+sum(abs(v)>=abs(observed) for v in null))/2001)

def save(fig,name):
    for ext in ['pdf','png','svg']:fig.savefig(OUT/f'{name}.{ext}',dpi=220,bbox_inches='tight',facecolor='white')
    plt.close(fig)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    taxpath=ROOT/'reports/codellama_base_merged_topk100_v1_regression_taxonomy/regression_failure_cases.csv'
    tax={r['task_id']:r for r in csv.DictReader(taxpath.open()) if r['benchmark']=='bigcodebench'}
    natural=list(csv.DictReader((PREV/'natural_timing.csv').open()));natural=[r for r in natural if r['family']=='codellama']
    nmap={(r['task_id'],r['source_text']):r for r in natural};ids=sorted({r['task_id'] for r in natural},key=lambda s:int(s.split('/')[-1]))
    assert len(ids)==50
    activation=np.load(PREV/'codellama_feature_activations.npz');data=[];paired=[]
    for tid in ids:
        pair={}
        for source,col in [('codellama_base','base_code'),('codellama_merged','merged_code')]:
            code=tax[tid][col];d=describe(code);assert d['parseable']
            n=nmap[(tid,source)];key=tid.split('/')[-1]+'__'+source;z=activation[key+'__z'];tokens=activation[key+'__ids']
            newline=tokens==13;assert len(z)==int(n['n_tokens'])
            d.update(task_id=tid,source=source,discovery=tid in DISCOVERY,n_tokens=len(z),
                mean_activation=float(z.mean()),max_activation=float(z.max()),active_fraction=float(np.mean(z>0)),
                newline_fraction=float(newline.mean()),newline_mean_activation=float(z[newline].mean()) if newline.any() else 0.,
                newline_active_fraction=float(np.mean(z[newline]>0)) if newline.any() else 0.)
            data.append(d);pair[source]=d
        a,b=pair['codellama_base'],pair['codellama_merged']
        paired.append(dict(task_id=tid,discovery=tid in DISCOVERY,
            new_return_only=b['return_only'] and not a['return_only'],merged_return_only=b['return_only'],
            new_no_value_return=b['no_value_return'] and not a['no_value_return'],
            new_repetition=b['repeated_top_level_statement'] and not a['repeated_top_level_statement'],
            shorter_main=b['all_statements']<a['all_statements'],
            base_statements=a['all_statements'],merged_statements=b['all_statements'],
            mean_activation_delta=b['mean_activation']-a['mean_activation'],
            max_activation_delta=b['max_activation']-a['max_activation'],
            active_fraction_delta=b['active_fraction']-a['active_fraction'],
            newline_mean_activation_delta=b['newline_mean_activation']-a['newline_mean_activation']))
    dump(OUT/'natural_program_features.json',data);csvwrite(OUT/'paired_behavior_activation.csv',paired)
    # Drop discovery cases from the main exploratory test. This is not independent external validation.
    associations=[]
    for scope in ['all50','excluding_discovery48']:
        rs=[r for r in paired if scope=='all50' or not r['discovery']]
        for behavior in ['new_return_only','merged_return_only','new_no_value_return','new_repetition','shorter_main']:
            for metric in ['mean_activation_delta','max_activation_delta','active_fraction_delta','newline_mean_activation_delta']:
                associations.append(dict(scope=scope,behavior=behavior,metric=metric,**evstat([r[metric] for r in rs],[r[behavior] for r in rs])))
    dump(OUT/'exploratory_associations.json',associations)
    # Check correlation with newline density and source length before attributing semantics.
    correlations=[]
    for source in ['codellama_base','codellama_merged']:
        rs=[r for r in data if r['source']==source and not r['discovery']]
        for metric in ['mean_activation','max_activation','active_fraction']:
            for confound in ['newline_fraction','n_tokens','all_statements']:
                corr=spearmanr([r[metric] for r in rs],[r[confound] for r in rs])
                correlations.append(dict(source=source,metric=metric,variable=confound,spearman=float(corr.statistic)))
    dump(OUT/'structural_correlations.json',correlations)
    # Re-extracted alpha-zero programs and target/controls: exactly the same extraction pipeline.
    baselinepath=ROOT/'runs/feature_stress_alpha0_20261015_v1/codellama/evaluations/bigcodebench__codellama_weak_alpha0_eval.json'
    baseline={tid:r[0]['solution'] for tid,r in json.loads(baselinepath.read_text())['eval'].items()}
    cases=json.loads((PREV/'steering_cases.json').read_text());target={r['task_id']:r for r in cases if r['family']=='codellama' and r['alpha']==-5}
    arms=[dict(name='target_4309_neg5',kind='target',codes={tid:r['code_after'] for tid,r in target.items()},passes={tid for tid,r in target.items() if r['passed']})]
    stress=ROOT/'runs/feature_stress_shuffle_20261016_v1/codellama'
    for index in [1,2,3]:
        for sign in ['neg','pos']:
            name=f'codellama_shuffle{index}_{sign}5';post=stress/'postprocessed/results_repaired'/f'bigcodebench__{name}_repaired.jsonl'
            ev=json.loads((stress/'evaluations'/f'bigcodebench__{name}_eval.json').read_text())
            arms.append(dict(name=name,kind='shuffle',codes={r['task_id']:r['candidate_code_repaired'] for r in rows(post)},passes={tid for tid,rs in ev['eval'].items() if any(r['correct'] for r in rs)}))
    randomroot=ROOT/'runs/prospective_direct_controls_20260901_codellama';summary=json.loads((ROOT/'reports/prospective_direct_controls_20260902/summary.json').read_text())['codellama']['arms']
    for fid,sign in [(14260,-1),(2947,1),(3698,1)]:
        post=randomroot/'postprocessed/results_repaired'/f'bigcodebench__random_f{fid}_{sign*5:+d}_repaired.jsonl'
        r=next(r for r in summary if r['kind']=='random' and r['id']==fid and r['alpha']==sign*5)
        arms.append(dict(name=f'random_latent_{fid}_{sign*5:+d}',kind='random_latent',codes={r['task_id']:r['candidate_code_repaired'] for r in rows(post)},passes=set(r['pass_tasks'])))
    armrows=[];details=[]
    for arm in arms:
        assert set(arm['codes'])==set(ids)
        for tid in ids:
            before=describe(baseline[tid]);after=describe(arm['codes'][tid]);passed=tid in arm['passes'];changed=baseline[tid]!=arm['codes'][tid]
            d=dict(arm=arm['name'],kind=arm['kind'],task_id=tid,passed=passed,changed=changed,parseable=after['parseable'],
                   expands_return_only=before.get('return_only',False) and after.get('parseable',False) and after.get('all_statements',0)>1,
                   return_only_to_empty_body=before.get('return_only',False) and after.get('parseable',False) and after.get('all_statements',0)==0,
                   adds_value_return=before.get('no_value_return',False) and after.get('parseable',False) and not after.get('no_value_return',False),
                   adds_statements=after.get('all_statements',0)>before.get('all_statements',0),before=before,after=after)
            details.append(d)
        ds=[r for r in details if r['arm']==arm['name']]
        armrows.append(dict(arm=arm['name'],kind=arm['kind'],n=50,passes=sum(r['passed'] for r in ds),changed=sum(r['changed'] for r in ds),
            return_only_expansions=sum(r['expands_return_only'] for r in ds),value_return_additions=sum(r['adds_value_return'] for r in ds),
            return_only_to_empty_bodies=sum(r['return_only_to_empty_body'] for r in ds),
            statement_count_increases=sum(r['adds_statements'] for r in ds),parse_failures=sum(not r['parseable'] for r in ds),
            discovery_cases_corrected=sum(r['passed'] and r['task_id'] in DISCOVERY for r in ds)))
    dump(OUT/'intervention_behavior_details.json',details);csvwrite(OUT/'intervention_behavior_summary.csv',armrows)
    # Four deliberately inspected contract-pattern checklists, not a universal correctness classifier.
    contracts=[]
    for tid in ['BigCodeBench/183','BigCodeBench/490','BigCodeBench/206','BigCodeBench/630']:
        versions=[('passing_base',next(r for r in data if r['task_id']==tid and r['source']=='codellama_base')),
                  ('failing_merged',describe(baseline[tid]))]
        versions += [(a['name'],describe(a['codes'][tid])) for a in arms]
        for name,d in versions:
            if tid.endswith('/183'):
                checks={'uuid_header_assignment':d.get('uuid_header_assignment',False),
                        'no_double_serialization_pattern':not d.get('double_serialization_pattern',False)}
            else:
                checks={'json_persistence_indicator':d.get('json_persistence_indicator',False)}
                if tid.endswith('/630'):checks['records_orientation_indicator']=d.get('json_records_orientation_indicator',False)
            contracts.append(dict(task_id=tid,version=name,discovery=tid in DISCOVERY,checks=checks,
                                  all_indicators_present=bool(d.get('parseable')) and all(checks.values())))
    dump(OUT/'inspected_contract_patterns.json',contracts)
    # Simple feature/structure plots, without causal labels for observational differences.
    plt.rcParams.update({'font.size':9,'pdf.fonttype':42,'svg.fonttype':'none'})
    fig,axs=plt.subplots(1,2,figsize=(10.5,4.5));flags=['return_only','no_value_return','may_fallthrough','repeated_top_level_statement']
    x=np.arange(len(flags));labels=['Only a return','No value return','May fall through','Repeated statements']
    for source,shift,color in [('codellama_base',-.18,'#7654CF'),('codellama_merged',.18,'#D67A16')]:
        rs=[r for r in data if r['source']==source and not r['discovery']]
        axs[0].bar(x+shift,[sum(r[f] for r in rs) for f in flags],width=.34,label=source,color=color)
        axs[1].scatter([r['newline_fraction'] for r in rs],[r['mean_activation'] for r in rs],c=color,label=source,alpha=.7,s=25)
    axs[0].set_xticks(x,labels,rotation=20,ha='right');axs[0].set_ylabel('Tasks / 48');axs[0].legend(fontsize=8);axs[0].set_title('Program structure (discovery cases excluded)')
    axs[1].set_xlabel('Fraction of evaluated tokens that are newlines');axs[1].set_ylabel('Mean feature-4309 activation');axs[1].legend(fontsize=8);axs[1].set_title('Potential structural confound')
    fig.text(.5,.005,'Exploratory within-cohort diagnostics · AST indicators are not a correctness oracle or complete control-flow analysis.',ha='center',fontsize=8)
    fig.subplots_adjust(bottom=.23,wspace=.32);save(fig,'01_structure_and_newline_confound')
    fig,axs=plt.subplots(1,2,figsize=(10.5,4.4));rs=[r for r in paired if not r['discovery']]
    for ax,metric,title in zip(axs,['mean_activation_delta','newline_mean_activation_delta'],['Mean activation difference','Newline-conditioned activation difference']):
        vals=[[r[metric] for r in rs if r['new_return_only']==b] for b in [False,True]]
        ax.boxplot(vals,labels=[f'Other (n={len(vals[0])})',f'New return-only (n={len(vals[1])})'],showfliers=True)
        for i,v in enumerate(vals,1):ax.scatter(i+np.random.default_rng(42).uniform(-.08,.08,len(v)),v,s=15,alpha=.5,color='#D67A16')
        ax.axhline(0,color='#888888',ls='--',lw=1);ax.set_title(title);ax.set_ylabel('Merged-text minus base-text activation')
    fig.text(.5,.01,'The 48 non-discovery tasks still belong to the original exploratory cohort; they are not a fresh validation set.',ha='center',fontsize=8)
    fig.subplots_adjust(bottom=.17,wspace=.3);save(fig,'02_return_only_activation_contrast')
    fig,axs=plt.subplots(1,2,figsize=(13,5))
    labels=[r['arm'].replace('codellama_','').replace('random_latent_','R') for r in armrows]
    good=[sum(r['expands_return_only'] and r['passed'] for r in details if r['arm']==a['arm']) for a in armrows]
    bad=[a['return_only_expansions']-v for a,v in zip(armrows,good)]
    axs[0].barh(range(len(labels)),good,color='#D67A16',label='Expanded and passed')
    axs[0].barh(range(len(labels)),bad,left=good,color='#AAAAAA',label='Expanded, still failed')
    axs[0].set_yticks(range(len(labels)),labels,fontsize=8);axs[0].invert_yaxis();axs[0].set_xlabel('Return-only functions expanded to >1 executable statement')
    axs[0].legend(fontsize=8);axs[0].set_title('Observed rewrites at magnitude 5')
    versions=['passing_base','failing_merged','target_4309_neg5','codellama_shuffle1_neg5','random_latent_14260_-5']
    tasks=['BigCodeBench/183','BigCodeBench/490','BigCodeBench/206','BigCodeBench/630']
    matrix=[[int(next(r['all_indicators_present'] for r in contracts if r['task_id']==tid and r['version']==v)) for v in versions] for tid in tasks]
    axs[1].imshow(matrix,cmap='Greens',vmin=0,vmax=1,aspect='auto')
    axs[1].set_xticks(range(len(versions)),['Base','Merged','4309 −5','Shuffle1 −5','Random14260 −5'],rotation=30,ha='right')
    axs[1].set_yticks(range(len(tasks)),['/183 (discovery)','/490 (discovery)','/206 (additional)','/630 (additional)'])
    for i,row in enumerate(matrix):
        for j,v in enumerate(row):axs[1].text(j,i,str(v),ha='center',va='center',color='white' if v else '#222222')
    axs[1].set_title('Inspected contract-pattern indicators\n1=present, not a proof of correctness')
    fig.subplots_adjust(left=.14,wspace=.8,bottom=.2);save(fig,'03_intervention_rewrites_and_contracts')
    naturalcounts={}
    for scope in ['all50','excluding_discovery48']:
        naturalcounts[scope]={}
        for source in ['codellama_base','codellama_merged']:
            rs=[r for r in data if r['source']==source and(scope=='all50' or not r['discovery'])]
            naturalcounts[scope][source]=dict(n=len(rs),**{flag:sum(r[flag] for r in rs) for flag in flags})
    dump(OUT/'SUMMARY.json',dict(natural_counts=naturalcounts,associations=associations,correlations=correlations,intervention_summary=armrows))
    dump(OUT/'METHOD.json',dict(status='exploratory hypothesis test; no new inference',discovery_tasks=sorted(DISCOVERY),
        definition_return_only='Exactly one executable top-level main-body statement, which is Return; docstring ignored.',
        no_value_return='No syntactic non-None return in the main body excluding nested definitions.',
        newline_token_id=13,controls='same frozen random latents and shuffle directions at magnitude5',
        multiple_testing='40 exploratory contrasts; nominal permutation p values uncorrected; no significance claim',
        observational_unit='generated text encoded in shared same-text latent, not two independent per-model latents',
        static_analysis_limitations='Potential fallthrough/repetition/call indicators are syntax proxies, not semantic proofs.',
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [taxpath,PREV/'codellama_feature_activations.npz',PREV/'natural_timing.csv',baselinepath]}))
    print('NATURAL',json.dumps(naturalcounts));print('ASSOCIATIONS',json.dumps([r for r in associations if r['scope']=='excluding_discovery48' and r['behavior']=='new_return_only']))
    print('ARMS',json.dumps(armrows))

if __name__=='__main__':main()
