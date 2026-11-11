"""证据链 B：受限的增量审核入口；只支持文档说明中列明的依赖表达式。"""
from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
import json
from checker_api import check_payload, InputError, ensure_json_data


def digest(value):
    """把本次待审内容做成指纹，换了合同或表达式就不能沿用旧审核。"""
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def instant(value):
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.tzinfo is None:
        raise ValueError('时间必须带时区')
    return t


def review_key(task, candidate, record, receipt):
    return digest([task, candidate, record, receipt['evidence_id'], receipt['fetched_at']])


def version_review_key(task, ticket):
    """B 的版本复核只对这一次任务和这份原始回执有效。"""
    return 'ticket_version:'+digest([task,ticket])


def review_graph(task, previous_graph, proposal, tool_receipts, *, review_log=None):
    """前四项是跨组入口。review_log 仅由 B 的独立复核入口提供，不能来自 A 提案。"""
    for data in (task, previous_graph, proposal, tool_receipts, review_log):
        ensure_json_data(data)
    if not isinstance(proposal,dict) or set(proposal)!={'base_version','upserts'} or type(proposal['base_version']) is not int or not isinstance(proposal['upserts'],list):
        raise InputError('提案必须包含整数 base_version 和列表 upserts')
    old = previous_graph or {}
    base = tool_receipts['base_payload']
    bt = base['task']
    for key in ('customer_id', 'incident_id', 'task_id', 'scope'):
        if not task.get(key) or task[key] != bt[key]:
            raise InputError('任务与原检查器输入不符：'+key)
    if not task.get('run_id') or not task.get('answer_version') or task.get('event_time') != bt['incident_start']:
        raise InputError('缺运行编号、回答版本或事件时间不一致')
    identity = {k: task[k] for k in ('task_id','run_id','customer_id','incident_id','scope','event_time')}
    if old and old['identity'] != identity:
        raise InputError('禁止跨任务沿用旧快照')
    version = old.get('graph_version', 0) + 1
    if proposal.get('base_version') != version-1:
        raise InputError('旧版本提案，请基于最新快照重做')
    candidates = deepcopy(old.get('candidates', {}))
    seen = set()
    for c in proposal['upserts']:
        if not isinstance(c,dict) or not isinstance(c.get('citation'),dict) or not isinstance(c.get('expression'),dict):
            raise InputError('每条候选需要引用和结构化表达式')
        cid = c.get('id')
        if not isinstance(cid,str) or not cid or cid in seen:
            raise InputError('缺少或重复的候选编号')
        seen.add(cid)
        candidates[cid] = deepcopy(c)

    # 每轮都用当前完整回执重审，包括上一轮接纳的条款。旧快照只读。
    baseline = check_payload(base)
    contract = base['responses'].get('CRM_CONTRACT_DB', {})
    target = 'claim:eligible'
    nodes = [{'id':target,'type':'claim'}]
    edges, gaps, checks, changes = [], [], [], []
    def gap(kind, obj, source, reason):
        gaps.append(dict(type=kind, object_id=obj, affected_claims=[target],
                         critical=True, must_verify=True, target_source=source, reason=reason))
    for g in baseline['gaps']:
        gap('MISSING_EVIDENCE',g['obligation_id'],g['required_sources'],g['reason'])
    for o in baseline['obligation_results']:
        nodes.append(dict(id='base:'+o['obligation_id'],type='obligation',state=o['status'],
                          evidence_ids=o['evidence_ids']))
    states = []
    for cid,c in sorted(candidates.items()):
        ref=c.get('citation',{})
        expr=c.get('expression',{})
        record=next((r for r in contract.get('records',[]) if r.get('evidence_id')==ref.get('record_id')),None)
        audit=None
        status, reason='unresolved','没有可用的独立语义复核记录'
        state='UNKNOWN'
        citations=[]
        time_result='UNKNOWN'
        version_review=None
        ticket_reason='尚无法核实是否按时申报'
        code='MISSING_EVIDENCE'
        # 来源、定位和原句必须能在回执中逐项复现；引用自己的答案没有证明力。
        if ref.get('source_id')!='CRM_CONTRACT_DB' or ref.get('call_id')!=contract.get('evidence_id') or not record:
            status,reason='rejected','找不到原合同回执或记录'
        elif not isinstance(ref.get('excerpt'),str) or not ref['excerpt'].strip() or record.get('clauses',{}).get(ref.get('locator'))!=ref['excerpt']:
            status,reason='rejected','无法在指定条款定位完整引用'
        elif (contract.get('tool_status')!='SUCCESS' or contract.get('pagination_complete') is not True
              or any(record.get(k)!=task[k] for k in ('scope','customer_id'))
              or not record.get('version') or not any(o['status']=='SUPPORT' and record['evidence_id'] in o['evidence_ids']
                 for o in baseline['obligation_results'] if 'CONTRACT' in o['obligation_id'])):
            reason='当前合同未获原检查器确认，或缺少完整的合同选择依据'
        elif c.get('target')!=target or c.get('relation')!='depends_on' or expr.get('kind')!='ticket_within_hours' or type(expr.get('hours')) is not int or not 0<expr['hours']<=8760:
            reason='关系或表达式超出演示范围，不能自动执行'
        else:
            key=review_key(task,c,record,contract)
            audit=(review_log or {}).get(key)
            if audit and audit.get('mode') in ('human','fixture_human','model') and audit.get('reviewer') and audit.get('reason') and audit.get('decision') in ('accepted','rejected','unresolved'):
                status,reason=audit['decision'],audit['reason']
            if status=='accepted':
                citations.append(ref)
                # 只核对同一次事故的申报。存在一份及时工单即可证明及时；
                # 反驳则需要查全且查询覆盖整个时限，不能据第一页空结果否定。
                t=tool_receipts.get('tickets') or {}
                try:
                    start=instant(task['event_time'])
                    end=start+timedelta(hours=expr['hours'])
                    valid=(all(t.get(k)==task[k] for k in ('customer_id','incident_id','scope','run_id'))
                           and t.get('source_id')=='TICKET_SYSTEM' and t.get('tool_status')=='SUCCESS'
                           and bool(t.get('call_id')) and isinstance(t.get('records'),list))
                    if valid:
                        times=[instant(r['submitted_at']) for r in t['records'] if
                               all(r.get(k)==task[k] for k in ('customer_id','incident_id','scope')) and r.get('record_id')]
                        if any(start<=d<=end and d<=instant(t['fetched_at']) for d in times):
                            state='SUPPORT'
                        elif (all(d<=instant(t['fetched_at']) for d in times) and len(times)==len(t['records']) and t.get('pagination_complete') is True
                              and instant(t['query_from'])<=start and instant(t['query_to'])>=end
                              and instant(t['fetched_at'])>=end):
                            state='REFUTE'
                        citations.append({'source_id':t['source_id'],'call_id':t['call_id'],
                                          'record_ids':[r.get('record_id') for r in t['records']]})
                except (AttributeError,KeyError,TypeError,ValueError,OverflowError):
                    state='UNKNOWN'
                time_result=state
                if state in ('SUPPORT','REFUTE'):
                    # 能做时间比较，不等于这份工单已获版本确认。
                    item=(review_log or {}).get(version_review_key(task,t))
                    if (isinstance(item,dict) and item.get('mode') in ('human','fixture_human')
                            and item.get('valid') is True and all(isinstance(item.get(k),str)
                            and item[k].strip() for k in ('reviewer','basis','basis_locator'))):
                        version_review=deepcopy(item)
                    else:
                        state='UNKNOWN'
                        code='TICKET_VERSION_UNVERIFIED'
                        ticket_reason='已完成时间比较，但还没有能定位的工单版本复核依据'
                elif t.get('tool_status') in ('ACCESS_DENIED','TIMEOUT'):
                    code=t['tool_status']
                elif t.get('pagination_complete') is False:
                    code='PAGINATION_INCOMPLETE'
        if status!='accepted':
            gap('UNRESOLVED_SEMANTICS',cid,'CRM_CONTRACT_DB',reason)
        elif state=='UNKNOWN':
            gap('TOOL_BLOCKED' if (tool_receipts.get('tickets') or {}).get('tool_status') in ('TIMEOUT','ACCESS_DENIED') else 'MISSING_EVIDENCE',cid,'TICKET_SYSTEM',ticket_reason)
            gaps[-1]['reason_code']=code
        states.append(state)
        nodes.append(dict(id='ob:'+cid,type='obligation',state=state,review_status=status))
        edges.append(dict(id='edge:'+cid,source=target,target='ob:'+cid,type='depends_on',
                          review_status=status,active=status=='accepted'))
        checks.append(dict(object_id=cid,check_type='semantic_relation',review_status=status,
                           reason=reason,citation=ref,evidence_used=citations,assessment=audit,time_comparison=time_result,version_review=version_review))
    # 支持范围有限：只在明确标为合成、且 B 有独立完整性确认的演示中发布资格建议。
    coverage_key=digest([task,contract,sorted(candidates.items())])
    covered=(review_log or {}).get('coverage:'+coverage_key)=={'mode':'fixture_human','complete':True}
    if not covered:
        gap('MISSING_DEPENDENCY',target,'合同复核','未确认候选条件是否覆盖本次合同')
    decision=baseline['current_decision']
    overall='UNKNOWN' if gaps or decision is None else ('REFUTE' if not decision or 'REFUTE' in states else 'SUPPORT')
    if any(o['status']=='CONFLICT' and o['required_for_decision'] for o in baseline['obligation_results']):
        overall='CONFLICT'
    nodes[0]['state']=overall
    for n in nodes:
        before=next((x for x in old.get('nodes',[]) if x['id']==n['id']),None)
        if n!=before:
            changes.append(dict(object_id=n['id'],old=before,new=deepcopy(n),old_version=version-1,
                                new_version=version,affected_claims=[target]))
    for e,check in zip(edges,checks):
        prior=next((x for x in old.get('checks',[]) if x['object_id']==check['object_id']),None)
        if prior!=check or old.get('candidates',{}).get(check['object_id'])!=candidates[check['object_id']]:
            changes.append(dict(object_id=e['id'],old_version=version-1,new_version=version,
                                trigger=check['citation'],old=prior,new=deepcopy(check),affected_claims=[target]))
    return dict(input_binding=digest([task,tool_receipts]),**identity,identity=identity,answer_version=task['answer_version'],graph_version=version,
                nodes=nodes,edges=edges,gaps=gaps,checks=checks,changes=changes,candidates=candidates,
                scope_declaration='草案：旧 Checker 加同一事故申报时限；资格建议限经覆盖确认的合成案例',
                recommendation={'SUPPORT':'eligible','REFUTE':'ineligible'}.get(overall,'undetermined'),
                workflow_status='checking',baseline_decision=decision)
