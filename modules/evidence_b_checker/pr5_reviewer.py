"""证据链 B：通过 PR #5 的 reviewer 插口接收原生提案和工具回执。"""
from copy import deepcopy
from datetime import timedelta

from dynamic_evidence.graph import review_graph as team_review
from proof_review import proof_issues, bind_checks
from dynamic_evidence.tools import TICKET, applicable, moment


def review(task, previous_graph, proposal, tool_receipts, call_model, cache):
    """先核对工单来源与版本，再交给团队原有的原句复核、四态和图发布流程。"""
    if previous_graph and any(previous_graph[k]!=task[k] for k in ('run_id','task_id')):
        raise ValueError('上一版图不属于本次任务')
    view=deepcopy(tool_receipts)
    pages=[p for p in view if p['source_type']==TICKET]
    audit=[]
    seen={}
    for p in pages:
        if p['tool_status']!='SUCCESS':
            continue
        reasons=[]
        if (any(p.get(k)!=task[k] for k in ('task_id','run_id','customer_id','incident_id'))
                or p.get('requested_source')!=TICKET or not p.get('call_id')):
            reasons.append('工单回执与本次查询不匹配')
        for row in p['records']:
            rid=row.get('evidence_id')
            if not applicable(row,TICKET,task) or row.get('incident_id')!=task['incident_id']:
                reasons.append('工单客户、事故、版本、有效期或引用不适用')
                continue
            if rid in seen and seen[rid]!=row:
                reasons.append('相同工单编号出现了不同内容，不能任选一份')
            seen[rid]=row
            try:
                if not moment(task['event_time'])<=moment(row['submitted_at'])<=moment(p['fetched_at']):
                    reasons.append('提交时间早于故障或晚于工具取数时间')
            except (KeyError,TypeError,ValueError,AttributeError):
                reasons.append('缺少可核对的带时区时间')
        audit.append(dict(call_id=p['call_id'],record_ids=[r.get('evidence_id') for r in p['records']],
                          reasons=sorted(set(reasons)),version_basis='按 PR5 草案检查版本及有效期；任务指定版本时另核对是否一致'))
    # 错客户/过期记录可能被上游过滤成空数组；保留原始回执，禁止把这种情况当作查无工单。
    def block():
        for page in pages:
            if page['tool_status']=='SUCCESS':
                page.update(tool_status='ERROR',records=[],pagination_complete=False)
    if any(a['reasons'] for a in audit):
        block()
    # 独立处理上次审核的副本，避免补充审计字段后影响团队的语义缓存/去重。
    prev=deepcopy(previous_graph)
    for c in (prev or {}).get('checks',[]):
        c.pop('checker_b_audit',None)
    g=team_review(task,prev,proposal,view,call_model,cache)
    node=next((n for n in g['nodes'] if n['id']=='condition:ticket_deadline_hours'),None)
    # 即使查全，截止之前的空结果也不能证明最终迟交。
    if node and node['state']=='REFUTE' and not seen and pages:
        try:
            closed=moment(pages[-1]['fetched_at'])>=moment(task['event_time'])+timedelta(hours=node['value'])
        except (KeyError,TypeError,ValueError,AttributeError,OverflowError):
            closed=False
        if not closed:
            audit[-1]['reasons'].append('查询时申报期限尚未确认结束')
            block()
            g=team_review(task,prev,proposal,view,call_model,cache)
    g['checker_b_ticket_audit']=audit
    if node:
        for a in audit:
            if a['reasons']:
                g['gaps'].append(dict(gap_type='UNRESOLVED_SEMANTICS',reason='；'.join(a['reasons']),
                                      target_source=TICKET,critical=True,must_verify=True,
                                      affected_claim_ids=['claim-eligibility'],call_id=a['call_id']))
    errors=proof_issues(g,tool_receipts,task)
    if errors:
        # 不发布坏图；由既有调度接口处理回退/人工升级。
        raise ValueError('；'.join(errors))
    bind_checks(g,tool_receipts)
    return g
