"""只核验 B 发布的证据引用和证明路径；不增加业务规则。"""
from dynamic_evidence.tools import applicable


def reference_matches(ref,row,receipt,task):
    """新版引用核对文档、位置和原句；旧版仅按原有引用协议核对。"""
    if not applicable(row,receipt['source_type'],task) or row.get('statement') != ref.get('excerpt'):
        return False
    loc=ref.get('locator')
    if isinstance(loc,str):
        return (bool(loc) and ref.get('source_id')==receipt['source_type']
                and row.get('citation')==loc)
    if not isinstance(loc,dict) or loc!=row.get('locator') or loc.get('unit')!='unicode_code_points':
        return False
    ctx=row.get('context') or {}
    a,b=loc.get('start'),loc.get('end')
    start,end=ctx.get('start'),ctx.get('end')
    text=ctx.get('text')
    return (bool(ref.get('source_id')) and ref['source_id']==row.get('source_id')==ctx.get('source_id')
            and ref.get('record_id')==row.get('record_id')
            and ctx.get('available') is not False and isinstance(text,str)
            and all(type(x) is int for x in (a,b,start,end))
            and 0<=start<=a<b<=end and end-start==len(text)
            and text[a-start:b-start]==ref['excerpt']==row.get('excerpt'))


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
        if (r.get('tool_status')!='SUCCESS' or len(found)!=1
            or not reference_matches(ref,found[0],r,task)):
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
