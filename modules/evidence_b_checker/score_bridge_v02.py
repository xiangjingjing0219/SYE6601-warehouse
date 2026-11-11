"""用 B 自己的 DYN-01 回放生成 PR #4 可读取的评分输入。仅限合成开发案例。"""
from checker_api import check_payload, make_score_snapshot
from graph_review import review_graph, digest
from run_dynamic_review import run


def project(task, graph, receipts, prev):
    # 将已有结构化检查与动态依赖放在同一张卡里，旧分数不转换。
    if graph.get('input_binding') != digest([task,receipts]) or (prev and (prev['identity']!=graph['identity'] or prev['graph_version']+1!=graph['graph_version'])):
        raise ValueError('任务、图版本或回执不匹配，不能跨轮生成成绩单')
    base = check_payload(receipts['base_payload'])
    legacy = make_score_snapshot(base, task['run_id'], str(graph['graph_version']))
    ev = {e['evidence_id']:e for e in legacy['evidence']}
    byid = {n['id']:n for n in graph['nodes']}
    obs,relations,clauses,changes=[],[],[],[]
    for item in legacy['obligations']:
        row=dict(item,obligation_id='base:'+item['obligation_id'],
                 rule_id=item['rule_id'],criticality='critical' if item['required_for_decision'] else 'non_critical',
                 prune=None,repair_action=None)
        obs.append(row)
    claim='claim:eligible'
    for edge,ch in zip(graph['edges'],graph['checks']):
        ob=byid[edge['target']]
        ref=ch['citation']
        state=ob['state']
        checks=dict.fromkeys(('source_allowed','scope_valid','version_valid','time_valid','query_sufficient'))
        ids=[]
        for citation in ch['evidence_used']:
            if citation['source_id']=='TICKET_SYSTEM':
                call=citation['call_id']
                ev[call]=dict(evidence_id=call,source_type='TICKET_SYSTEM',citation='合成查询回执：'+call)
                ids.append(call)
        # 旧的合成工单没有数据版本。07A 对已判定义务要求五项检查均有依据；
        # 不能仅为通过校验把缺失的 version_valid 写成 true。
        resolved=state in ('SUPPORT','REFUTE')
        if resolved:
            v=ch['version_review']
            if not (ids and v and v['valid'] is True and ch['time_comparison']==state):
                raise ValueError('快照缺少已核验的工单引用或版本依据')
            # 此时源、客户/事故、时间与查询充分性均由本轮 Checker 核过。
            checks=dict.fromkeys(checks,True)
        obs.append(dict(obligation_id=ob['id'],rule_id='demo:'+ch['object_id'],
                        statement='核对候选工单条件：'+ref['excerpt'],applicability='APPLICABLE' if edge['active'] else 'UNDETERMINED',
                        applicability_reason=ch['reason'],criticality='critical',required_for_decision=True,
                        must_verify=True,status=state,checks=checks,evidence_ids=ids,
                        reason_codes=[g.get('reason_code',g['type']) for g in graph['gaps'] if g['object_id']==ch['object_id']],
                        reason=v['basis'] if resolved else '；'.join(g['reason'] for g in graph['gaps'] if g['object_id']==ch['object_id']),
                        prune=None,repair_action=None))
        relations.append(dict(relation_id=edge['id'],relation_type=edge['type'],subject_id=edge['source'],
                              object_id=edge['target'],review_status=edge['review_status'],critical=True,
                              reason=ch['reason'],prune=None,repair_action=None))
        if ref['record_id'] in ev and any(r.get('evidence_id')==ref['record_id'] and r.get('clauses',{}).get(ref['locator'])==ref['excerpt'] for r in receipts['base_payload']['responses'].get('CRM_CONTRACT_DB',{}).get('records',[])):
            clauses.append(dict(clause_id='clause:'+ch['object_id'],source_evidence_id=ref['record_id'],
                                statement=ref['excerpt'],expanded=edge['active'],critical=True,
                                reason_codes=[] if edge['active'] else ['UNRESOLVED_SEMANTICS'],
                                reason=ch['reason'],prune=None,repair_action=None))
    for i,c in enumerate(graph['changes']):
        oid=c['object_id']
        kind='claim' if oid==claim else ('relation' if oid.startswith('edge:') else 'obligation')
        ids=next((o['evidence_ids'] for o in obs if o['obligation_id']==oid),[])
        if c.get('trigger',{}).get('record_id') in ev: ids=[c['trigger']['record_id']]
        changes.append(dict(change_id=f"change:{graph['graph_version']}:{i}",kind='added' if c['old'] is None else 'revised',
                            object_type=kind,object_id=oid,statement='审核对象更新：'+oid,
                            trigger_evidence_ids=ids,from_graph_version=str(c['old_version']),to_graph_version=str(c['new_version']),
                            affected_claim_ids=[claim],from_recommendation=prev['recommendation'] if prev else None,
                            to_recommendation=graph['recommendation'],explanation='来自 B 本轮快照的变更记录'))
    binding=dict(task_id=graph['task_id'],run_id=graph['run_id'],graph_version=str(graph['graph_version']),
                 answer_version=graph['answer_version'])
    # 专属合同是组长文件明确举出的基础必查；不能用“已生成节点”反推必查清单齐全。
    oid='base:B-CONTRACT'
    contract=byid.get(oid)
    complete=bool(contract and contract['state'] in ('SUPPORT','REFUTE'))
    unclear=any(g['type']=='MISSING_DEPENDENCY' and g['object_id']==claim for g in graph['gaps'])
    return dict(schema_version='0.2-draft',**binding,answer_binding=binding,rules_version=legacy['rules_version'],
        synthetic_demo=True,recommendation=graph['recommendation'],workflow_status=graph['workflow_status'],stop_reason=None,
        baseline_checks=[dict(check_id='baseline:contract',statement='核对适用专属合同',required=True,built=bool(contract),
            status='COMPLETE' if complete else 'INCOMPLETE',obligation_ids=[oid] if contract else [],
            reason_codes=[] if complete else ['CONTRACT_UNCONFIRMED' if contract else 'MISSING_FROM_GRAPH'],
            reason='按本轮合同核查状态记录',repair_action=None)],
        claims=[dict(claim_id=claim,statement='本次合成故障符合补偿资格',mapped=True,
            obligation_ids=[o['obligation_id'] for o in obs if o['required_for_decision']],evidence_ids=[],
            affects_answer=True,reason='以本轮已建入的必要条件核对资格；覆盖范围另列')],
        obligations=obs,clauses=clauses,relations=relations,changes=changes,
        scope_declaration=dict(scope_id='scope:demo',statement=graph['scope_declaration'],covers=['DYN-01'],
            known_limits=['没有 A 的正式必查全集或对实际答案的映射，仅核对 B 的合成主张。'],
            affects_answer=unclear,status='unclear' if unclear else 'declared',reason='依据 B 本轮合成覆盖确认记录'),
        evidence=list(ev.values()))


def replay():
    trace=run()
    previous=None
    for stage in trace['stages']:
        graph=review_graph(trace['task'],previous,stage['proposal'],stage['tool_receipts'],review_log=stage['review_log'])
        try:
            yield stage['stage'],project(trace['task'],graph,stage['tool_receipts'],previous),None
        except ValueError as err:
            yield stage['stage'],None,str(err)
        previous=graph
