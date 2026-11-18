"""Replay A's actual rule engine, independently audit it, expose test-team contract.
No network/model calls. No inferred semantic approvals or invented Loop executions.
"""
import argparse
from copy import deepcopy
import importlib
import json
import os
from pathlib import Path
import sys
from collections import Counter
from log_intake import digest, inspect_log, resolve
from egraph_audit import audit, locate
from industrial_review import review as local_review
from insurance_review import review as insurance_review
from claim_alignment import bind
from business_review import review as business_review, review_insurance_amounts, merge

VERSION = 'egraph-b-bridge-5'

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':'))


def run_engine(case, project):
    project = Path(project).resolve()
    if not (project/'egraph/pipeline.py').is_file():
        raise ValueError('EG_PROJECT_ROOT must point to A evidence_graph directory')
    sys.path.insert(0, str(project))
    try:
        settings = importlib.import_module('config.settings')
        pipeline = importlib.import_module('egraph.pipeline')
        loader = importlib.import_module('egraph.loader')
        client = importlib.import_module('egraph.llm.client')
        for module in (settings, pipeline, loader, client):
            if not Path(module.__file__).resolve().is_relative_to(project):
                raise ValueError('Other A engine already imported: use a fresh Python process')
        config = settings.load_settings({'mode':'rule','render':False}, env={})
        result = pipeline.analyze_run(loader.normalize_record(deepcopy(case)), config,
                                      llm=client.NullLLM('B forced offline replay'), validate=True)
        return result.to_dict(), list(result.schema_errors)
    finally:
        sys.path.remove(str(project))


def check_artifact(case, payload):
    """Structural issues are independent of A's business evidence statuses."""
    graph = payload['graph']; issues = []
    def add(code, subject): issues.append({'code':code,'subject':subject})
    for key in ('graph','plan','scorecard'):
        if any(payload[key].get(k) != case[k] for k in ('case_id','run_id')): add('RUN_MISMATCH',key)
    collections = [('nodes','id'),('edges','id'),('gaps','id'),('checks','check_id'),('paths','path_id')]
    for group, key in collections:
        values = [v.get(key) for v in graph.get(group,[])]
        if any(not isinstance(v,str) or not v.strip() for v in values): add('INVALID_ID',group)
        if len(values)!=len(set(values)): add('DUPLICATE_ID',group)
    nodes = {n['id']:n for n in graph['nodes']}
    gaps = {g['id'] for g in graph.get('gaps',[])}
    if set(nodes)&gaps: add('CROSS_KIND_ID_COLLISION','nodes/gaps')
    claims = {k for k,v in nodes.items() if v['type']=='claim'}
    endpoints = set(nodes)|gaps
    checks = {c['check_id']:c for c in graph.get('checks',[])}
    for edge in graph.get('edges',[]):
        if edge.get('source') not in endpoints or edge.get('target') not in endpoints: add('DANGLING_EDGE',edge['id'])
    for gap in graph.get('gaps',[]):
        if not set(gap.get('affected_claims',[]))<=claims: add('DANGLING_GAP_CLAIM',gap['id'])
    for action in payload['plan'].get('actions',[]):
        if not set(action.get('gap_ids',[]))<=gaps or not set(action.get('target_claims',[]))<=claims: add('DANGLING_PLAN_REFERENCE',action['id'])
    for claim in payload['scorecard'].get('claims',[]):
        if claim.get('claim_id') not in claims: add('DANGLING_SCORE_CLAIM',claim.get('claim_id'))
    for node in graph['nodes']:
        locator = node.get('locator')
        if node.get('type')=='evidence' and not locator: add('MISSING_EVIDENCE_LOCATOR',node['id'])
        if locator:
            try:
                pointer,_ = locate(case,locator)
                event=case['trace'][int(pointer.split('/')[2])]
                if node.get('type') in ('evidence','rule','fact'):
                    if node.get('record_id') and node['record_id'] != event['id']: add('RECORD_LOCATOR_MISMATCH',node['id'])
                    if node.get('tool') and node['tool'] != event['tool']: add('TOOL_LOCATOR_MISMATCH',node['id'])
            except (ValueError,KeyError,IndexError,TypeError): add('UNRESOLVED_LOCATOR',node['id'])
    for path in graph.get('paths',[]):
        conditions=set(path.get('conditions',[]))
        satisfied=set(path.get('satisfied_conditions',[])); missing=set(path.get('missing_conditions',[]))
        if satisfied&missing or satisfied|missing != conditions: add('PATH_PARTITION_MISMATCH',path['path_id'])
        for ident in conditions:
            if ident not in nodes or nodes[ident].get('type')!='condition': add('INVALID_PATH_CONDITION',path['path_id'])
        if path.get('satisfied') is True:
            if not conditions:
                # A graph.py emits an empty-condition summary OR path for same-claim branches.
                branches=[p for p in graph.get('paths',[]) if p.get('goal_claim')==path.get('goal_claim') and p.get('conditions')]
                if '可替代路径' not in path.get('rationale','') or len(branches)<2 or not any(p.get('satisfied') is True for p in branches):
                    add('PATH_SATISFACTION_MISMATCH',path['path_id'])
            elif missing: add('PATH_SATISFACTION_MISMATCH',path['path_id'])
            for ident in conditions:
                check_id=nodes.get(ident,{}).get('meta',{}).get('check_id')
                if checks.get(check_id,{}).get('status')!='satisfied': add('PATH_SATISFACTION_MISMATCH',path['path_id'])
    return issues


def evaluate_payload(case, payload, context=None, schema_errors=None):
    inspect_log(case)
    graph=payload['graph']; provenance=audit(case,graph)
    issues=check_artifact(case,payload)
    # A permits edges to graph.gaps; old audit only knew nodes. Do not flag valid gap edges.
    edge_ids={e['id'] for e in graph.get('edges',[])}
    gap_ids={g['id'] for g in graph.get('gaps',[])}
    provenance['findings']=[f for f in provenance['findings'] if not (f['code']=='DANGLING_REFERENCE' and f['subject'] in edge_ids and f['detail'] in gap_ids)]
    hard_codes={'RUN_MISMATCH','INVALID_ID','DANGLING_REFERENCE','UNRESOLVED_LOCATOR','EXCERPT_NOT_VERIFIED','PATH_SET_MISMATCH'}
    issues += [f for f in provenance['findings'] if f['code'] in hard_codes]
    issues += [{'code':'A_SCHEMA_ERROR','subject':str(e)} for e in (schema_errors or [])]
    # Existing bounded B checks remain separate: matching a field is not approval of A's whole sentence.
    if case['case_id'].startswith('IND-'):
        local=merge(local_review(deepcopy(case)),business_review(case))
    elif case['case_id'].startswith('INS-'):
        local=merge(insurance_review(deepcopy(case)),review_insurance_amounts(case))
    else:
        local={'checks':[], 'gaps':[], 'analysis_status':'unsupported_domain'}
    local.setdefault('run_id',case['run_id'])
    local.setdefault('case_id',case['case_id'])
    local=bind(local,graph)
    b_statuses=dict(Counter(c['state'] for c in local['checks']))
    receipts=[]
    for i,event in enumerate(case['trace']):
        if event['event']=='tool_call':
            receipts.append(dict(id=event['id'],tool=event['tool'],source_text=canonical(event['result']),
                                 pointer=f'/trace/{i}/result', serialization='canonical_json', result_sha256=digest(event['result'])))
    snapshot_nodes=[]
    for node in graph['nodes']:
        refs=[]
        if node.get('locator'):
            try:
                pointer,value=locate(case,node['locator']); event=case['trace'][int(pointer.split('/')[2])]
                refs=[dict(receipt_id=event['id'],quote=canonical(value),pointer=pointer)]
            except (ValueError,KeyError,IndexError,TypeError): pass
        snapshot_nodes.append(dict(id=node['id'],type=node['type'],text=node['content'],review_status='candidate',
                                   a_review_status=node.get('review_status'),a_evidence_status=node.get('evidence_status'),evidence=refs))
    for gap in graph.get('gaps',[]):
        snapshot_nodes.append(dict(id=gap['id'],type='gap',text=gap['description'],review_status='candidate',evidence=[]))
    version='replay-'+digest({'source':case,'graph':graph})[:24]
    bundle=dict(execution_kind='replay',method='actual_A_rule_engine_with_B_bounded_checks',
                model_manifest={'model':None,'model_called':False},model_calls=[],prompt_version='not_used_rule_mode',
                config={'mode':'rule','network_calls':False,'b_version':VERSION},
                data_version=(context or {}).get('data_version',digest(case)),source_sha256=digest(case),
                tool_receipts=receipts,snapshots=[dict(version=version,nodes=snapshot_nodes,
                    edges=[dict(id=e['id'],source=e['source'],target=e['target'],relation=e['type'],review_status='candidate') for e in graph['edges']])],
                final_snapshot_version=version,answer={'snapshot_version':version,'text':case['ai_answer'],'review_status':'unverified_source_answer'},
                scorecard={'snapshot_version':version,'proposed':deepcopy(payload['scorecard']),'review_status':'candidate'},
                actions=[],planned_actions=deepcopy(payload['plan'].get('actions',[])),
                limitations=['One actual final replay snapshot only; no invented intermediate states.',
                             'Source tool receipts are logged data, not live tool calls.',
                             'A claims/edges remain candidates; B local checks do not certify whole-answer semantics.'])
    return dict(prediction={'case_id':case['case_id'],'run_id':case['run_id'],'structural_passed':not issues,
                           'semantic_accuracy_evaluated':False,'local_check_count':len(local['checks']),
                           'local_status_counts':b_statuses,'answer_status':'UNKNOWN'},
                raw_response=deepcopy(payload),graph_bundle=bundle,b_review={'issues':issues,'provenance':provenance,'local_review':local})


def evaluate(case, context=None):
    project=os.environ.get('EG_PROJECT_ROOT')
    if not project: raise ValueError('Set EG_PROJECT_ROOT to A evidence_graph folder; no API key required')
    payload,errors=run_engine(case,project)
    return evaluate_payload(case,payload,context,errors)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',required=True); p.add_argument('--logs',required=True); p.add_argument('--out',required=True)
    a=p.parse_args(); os.environ['EG_PROJECT_ROOT']=str(Path(a.project).resolve())
    cases=json.loads(Path(a.logs).read_text(encoding='utf-8-sig')); reports=[]
    if len({c['case_id'] for c in cases})!=len(cases) or len({c['run_id'] for c in cases})!=len(cases): raise ValueError('duplicate case/run IDs')
    for case in cases: reports.append(evaluate(case,{'data_version':digest(cases)}))
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    summary={'cases':len(reports),'structural_passed':sum(r['prediction']['structural_passed'] for r in reports),
             'model_calls':0,'semantic_accuracy_evaluated':False,
             'local_checks':sum(r['prediction']['local_check_count'] for r in reports),
             'issue_codes':dict(Counter(f['code'] for r in reports for f in r['b_review']['issues']))}
    for name,data in [('bridge_results.json',reports),('bridge_summary.json',summary)]:
        (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__': main()
