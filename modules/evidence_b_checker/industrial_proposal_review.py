"""B 侧工业候选图接收与审核。提案自报状态不作为审核结果。"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
from log_intake import digest, inspect_log, resolve

VERSION = 'industrial-proposal-b-1'
STATES = {'SUPPORT', 'REFUTE', 'UNKNOWN', 'CONFLICT'}


def locate(log, node):
    """仅解析 A 的 trace[event_id].result 路径，不执行表达式。"""
    match = re.fullmatch(r'trace\[([^\[\]]+)\]\.result((?:\.[A-Za-z_][A-Za-z_0-9]*|\[\d+\])*)', node.get('locator', ''))
    if not match or match[1] != node.get('record_id'):
        raise ValueError('定位格式不支持或 record_id 不一致')
    found = [(i, e) for i, e in enumerate(log['trace']) if e['id'] == match[1]]
    if len(found) != 1 or found[0][1].get('event') != 'tool_call':
        raise ValueError('未找到唯一工具事件')
    i, event = found[0]
    if node.get('source_id') != event['tool'].split('.')[0]:
        raise ValueError('来源与工具命名空间不一致')
    pointer = f'/trace/{i}/result'
    for field, index in re.findall(r'\.([A-Za-z_][A-Za-z_0-9]*)|\[(\d+)\]', match[2]):
        pointer += '/' + (field or index)
    value = resolve(log, pointer)
    if 'excerpt' in node and (not isinstance(value, str) or node['excerpt'] != value):
        raise ValueError('摘录与原文不一致')
    result = event['result']
    blocked = isinstance(result, dict) and result.get('status') in {'ERROR','TIMEOUT','ACCESS_DENIED','FORBIDDEN','UNAVAILABLE','NO_DATA'}
    return dict(pointer=pointer, value=deepcopy(value), event_id=event['id'], tool=event['tool'],
                arguments=deepcopy(event['arguments']), usable=not blocked,
                note='引用可定位不等于语义成立；模拟日志不证明真实工具执行')


def review_proposal(proposal, log, decisions=None, previous=None):
    intake = inspect_log(log)
    task = proposal.get('task', {})
    if task.get('task_id') != log['case_id'] or task.get('run_id') != log['run_id']:
        raise ValueError('候选图与日志 case/run 不一致')
    if task.get('question') != log['user_question']:
        raise ValueError('候选图问题与日志不一致')
    nodes, edges = proposal.get('nodes'), proposal.get('edges')
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError('需要 nodes 和 edges 数组')
    ids = [n.get('id') for n in nodes]
    if any(not isinstance(x, str) or not x.strip() for x in ids) or len(set(ids)) != len(ids):
        raise ValueError('空白或重复节点 ID')
    edge_ids = [e.get('id') for e in edges]
    if any(not isinstance(x, str) or not x.strip() for x in edge_ids) or len(set(edge_ids)) != len(edge_ids):
        raise ValueError('空白或重复关系 ID')
    for e in edges:
        if e.get('from') not in ids or e.get('to') not in ids:
            raise ValueError('关系端点不存在')
    references = {}
    for n in nodes:
        if n.get('type') == 'evidence':
            try:
                references[n['id']] = dict(located=True, **locate(log, n))
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                references[n['id']] = dict(located=False, usable=False, reason=str(exc))
    binding = dict(proposal_sha256=digest(proposal), log_sha256=intake['log_sha256'])
    if decisions is not None:
        if any(decisions.get(k) != v for k, v in binding.items()):
            raise ValueError('独立审核记录已过期：提案或日志发生变化，请重新审核')
        if not decisions.get('reviewer') or decisions.get('mode') not in {'human_review','assistant_offline_review'}:
            raise ValueError('独立审核记录缺少审核人或审核方式')
        if not isinstance(decisions.get('claims'), dict) or set(decisions['claims']) - {n['id'] for n in nodes if n.get('type') == 'claim'}:
            raise ValueError('审核记录含未知主张')
    claims = []
    for n in nodes:
        if n.get('type') != 'claim':
            continue
        item = dict(claim_id=n['id'], content=n.get('content'), proposed_status=n.get('evidence_status'),
                    evidence_status='UNKNOWN', review_status='unresolved', reason='尚未独立审核命题与适用证据')
        d = (decisions or {}).get('claims', {}).get(n['id'])
        if d:
            refs = d.get('evidence_ids', [])
            if d.get('status') not in STATES or not isinstance(d.get('reason'), str) or not d['reason'].strip() or not isinstance(refs,list):
                raise ValueError('审核记录字段无效')
            if not refs or any(x not in references or not references[x].get('usable') for x in refs):
                item['reason'] = '独立审核引用未定位或工具失败；保持未知'
            else:
                item.update(evidence_status=d['status'], review_status='reviewed', reason=d['reason'],
                            evidence_ids=refs, reviewer=decisions['reviewer'], mode=decisions['mode'])
        claims.append(item)
    # 普通连线不定义充分性；不自动把 A 的 supports 当作 B 验证通过的证明。
    relations = [dict(edge=deepcopy(e), review_status='unresolved',
                      reason='需确认关系方向、语义及 AND/OR 条件，尚未自动传播四态') for e in edges]
    warnings = ['候选图状态未直接采信', '节点与关系完整性、语义覆盖和业务规则完备性未全部验证',
                'depends_on/derived_from 方向需与 A 确认；普通连线不等于 AND/OR 路径',
                '未执行真实补证或评分；原始日志为模拟数据']
    provenance = {n['id']: [k for k in ('created_by','created_at','call_id') if not n.get(k)] for n in nodes}
    out = dict(case_id=log['case_id'], run_id=log['run_id'], reviewer_version=VERSION, **binding,
               reference_checks=references, claim_reviews=claims, relation_reviews=relations,
               candidate_gaps=[dict(proposed=deepcopy(g), review_status='unresolved') for g in proposal.get('gaps',[])],
               missing_provenance=provenance, observations=intake['observations'], limitations=warnings,
               original_proposal=deepcopy(proposal), original_log=deepcopy(log), history=[])
    if previous:
        if (previous.get('case_id'),previous.get('run_id')) != (log['case_id'],log['run_id']):
            raise ValueError('历史记录属于其他运行')
        out['history'] = deepcopy(previous.get('history', [])) + [{k: deepcopy(previous[k]) for k in
            ('proposal_sha256','log_sha256','claim_reviews','reviewer_version')}]
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('proposal', type=Path); p.add_argument('logs', type=Path)
    p.add_argument('--decisions', type=Path); p.add_argument('--previous', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.resolve() in {x.resolve() for x in (a.proposal,a.logs,a.decisions,a.previous) if x}:
        p.error('输出不可覆盖输入')
    read = lambda path: json.loads(path.read_text(encoding='utf-8-sig')) if path else None
    proposal, logs = read(a.proposal), read(a.logs)
    logs = [logs] if isinstance(logs, dict) else logs
    matches = [l for l in logs if (l.get('case_id'),l.get('run_id')) == (proposal['task']['task_id'],proposal['task']['run_id'])]
    if len(matches) != 1: p.error('未找到唯一对应日志')
    result = review_proposal(proposal,matches[0],read(a.decisions),read(a.previous))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('已输出审核报告；未审核关系仍保留 unresolved。')

if __name__ == '__main__':
    main()
