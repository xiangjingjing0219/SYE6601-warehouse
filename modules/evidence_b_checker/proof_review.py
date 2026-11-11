"""只核验 B 发布的证据引用和证明路径；不增加业务规则。"""
from dynamic_evidence.tools import applicable


def proof_issues(graph, receipts, task):
    """把关系按「要证明的对象 → 依据」统一方向。覆盖/适用关系不参与循环自证检查。"""
    nodes={n['id']:n for n in graph['nodes']}
    calls={r['call_id']:r for r in receipts}
    issues=[]
    if len(nodes)!=len(graph['nodes']) or len(calls)!=len(receipts):
        issues.append('重复节点或调用编号，无法唯一定位')
    proof={k:set() for k in nodes}
    for n in nodes.values():
        if n['type']!='evidence':
            continue
        ref=n.get('reference',{})
        r=calls.get(ref.get('call_id'),{})
        found=[x for x in r.get('records',[]) if x.get('evidence_id')==ref.get('record_id')]
        if (r.get('tool_status')!='SUCCESS' or r.get('source_type')!=ref.get('source_id')
            or not any(x.get('citation')==ref.get('locator') and x.get('statement')==ref.get('excerpt')
                       and applicable(x,r['source_type'],task) for x in found)):
            issues.append('原始回执不能证实引用：'+n['id'])
    for e in graph['edges']:
        a,b=e['from'],e['to']
        if a not in nodes or b not in nodes:
            issues.append('关系端点不存在：'+e['id'])
            continue
        if e['review_status']!='accepted':
            continue
        if e['type'] in ('supports','refutes'):
            proof[b].add(a)
        elif e['type'] in ('depends_on','derived_from'):
            proof[a].add(b)
    visiting=set()
    done=set()
    def visit(k):
        if k in visiting:
            issues.append('证明路径循环：'+k)
        elif k not in done:
            visiting.add(k)
            for child in sorted(proof[k]): visit(child)
            visiting.remove(k)
            done.add(k)
    for k in sorted(nodes): visit(k)
    return sorted(set(issues))


def bind_checks(graph, receipts):
    """check 的候选值可回查原始条款；不把被拒提案的假引用写成有效引用。"""
    evidence={n['reference']['record_id']:n['reference'] for n in graph['nodes'] if n['type']=='evidence'}
    for i,c in enumerate(graph['checks']):
        ref=evidence.get(c.get('record_id'))
        excerpt=c.get('excerpt')
        c['checker_b_audit']={'object_id':f"review:{c.get('record_id')}:{c.get('kind')}:{i}",
            'check_type':'candidate_relation','citation':dict(ref,excerpt=excerpt) if ref and isinstance(excerpt,str)
            and excerpt and isinstance(ref['excerpt'],str) and excerpt in ref['excerpt'] else None,
            'lookup':'模型调用按同一运行的 stage=review 及 record_id/kind/value/excerpt 回查；结构拒绝无需模型'}
