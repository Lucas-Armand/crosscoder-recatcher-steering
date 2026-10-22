#!/usr/bin/env python3
"""Cross-check fixed manuscript claims and compile diagnostics against saved data."""
import csv,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];R=ROOT/'reports';OUT=R/'overleaf_sections67_68_20261022_v1'
def read(p):return json.loads(p.read_text())
def main():
    s=R/'section67_semantic_temporal_20261019_v1';curves=list(csv.DictReader((s/'curves.csv').open()))
    for family,fid,n,passes,changes,sp,sc in [('deepseek','4810',119,14,57,[6,6,6],[36,41,46]),('codellama','4309',50,2,27,[1,0,0],[21,19,19])]:
        a=next(r for r in curves if r['family']==family and r['kind']=='target' and float(r['alpha'])==-5)
        assert (int(a['n']),int(a['passed']),int(a['changed']))==(n,passes,changes)
        for i in [1,2,3]:
            a=next(r for r in curves if r['family']==family and r['kind']=='shuffle' and r['identity']==str(i) and float(r['alpha'])==-5)
            assert (int(a['passed']),int(a['changed']))==(sp[i-1],sc[i-1])
    p=R/'deepseek4810_marker_followup_20261022_v1';a=read(p/'SUMMARY.json');assert a['within_1_token']==77 and a['comment_line_relations']=={'inside_visible_line':71,'before_line':36}
    cases=read(p/'alpha5_changed_case_inspection.json');success=[r for r in cases if r['passed']]
    assert len(success)==14 and sum(r['comment_before'] for r in success)==11 and all(not r['comment_after'] and not r['any_marker_after'] for r in success)
    assert sum(not r['main_ast_changed'] for r in success)==8
    errors=read(p/'alpha5_success_failure_evidence.json');distance=[-r['activation_minus_matching_import_tokens'] for r in errors]
    assert len(errors)==14 and min(distance)==4 and max(distance)==29
    for r in success:
        module=next(x['missing_module'] for x in errors if x['task_id']==r['task_id'])
        assert module in ['task_func','task']
    assert read(R/'deepseek4810_marker_components_20261022_v1/SUMMARY.json')['frozen']['coverage']=={'comments_only':107,'import_only':96,'class_only':93,'comments_plus_import':117,'comments_plus_class':113,'full':119}
    cl=read(s/'codellama_two_successes.json');assert {r['task_id'] for r in cl}=={'BigCodeBench/183','BigCodeBench/490'}
    loc=read(s/'codellama_error_localization.json');assert len(loc)==50
    for f in ['deepseek4810_same_text_branches_20261022_v1','codellama4309_same_text_tables_20261022_v1']:
        v=read(R/f/'VALIDATION.json');assert v.get('max_abs_preact_minus_cached_active_z',v.get('max_preact_error'))<.002
    texfiles=list((OUT/'crosscoder_case_studies').rglob('*.tex'));combined='\n'.join(p.read_text() for p in texfiles)
    labels=re.findall(r'\\label\{([^}]+)\}',combined);refs=re.findall(r'\\ref\{([^}]+)\}',combined)
    assert len(labels)==len(set(labels));assert set(refs)<=set(labels)
    assert 'TODO' not in (OUT/'crosscoder_case_studies/sections67_68.tex').read_text()
    log=(OUT/'preview.log').read_text();bad=[line for line in log.splitlines() if 'undefined' in line.lower() or 'Overfull \\hbox' in line or line.startswith('!')]
    assert not bad,bad
    result=dict(validated=True,new_inference=False,curves_checked=True,semantic_counts_checked=True,latex_references_resolved=True,
        no_overfull_boxes=True,unrelated_manuscript_or_slide_changes=False,scope='Derived analysis and two new manuscript subsections only')
    (OUT/'VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
