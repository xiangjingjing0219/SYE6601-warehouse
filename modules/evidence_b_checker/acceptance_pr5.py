"""岗位验收：原始记录 → 独立复核请求 → 候选审核结果 → 业务四态。"""
from pathlib import Path
import json
from copy import deepcopy
from run_pr5_checker import run,main as replay
from dynamic_evidence.mock_model import FixtureModel
from proof_review import proof_issues


class WrongUnit(FixtureModel):
    def __call__(self,stage,messages,timeout):
        reply=super().__call__(stage,messages,timeout)
        if stage=='build':
            obj=json.loads(reply['raw_output'])
            for c in obj['conditions']:
                if c['kind']=='ticket_deadline_hours': c['kind']='duration_min'
            reply['raw_output']=json.dumps(obj)
        return reply


def relation_trace(b):
    out=[]
    for check in b['graph']['checks']:
        key=('record_id','kind','value','excerpt')
        ref=check['checker_b_audit']['citation']
        matches=[]
        for m in b['model_calls']:
            if m['stage']!='review' or not m.get('response'):continue
            req=json.loads(m['messages'][-1]['content'])
            if all(req.get(k)==check.get(k) for k in key) and ref and req.get('original_clause')==next(
                (r.get('statement') for t in b['tool_receipts'] if t['call_id']==ref['call_id']
                 for r in t['records'] if r['evidence_id']==ref['record_id']),None):
                matches.append(dict(call_id=m['call_id'],model=m['response'].get('model'),
                                    raw_output=m['response']['raw_output']))
        out.append(dict(mode=b['mode'],check=check,model_reviews=matches))
    return out


def main():
    b=replay()
    graph=b['graph']; task=b['task']; raw=b['tool_receipts']
    green=relation_trace(b)
    assert all(x['model_reviews'] for x in green if x['check']['review_status']=='accepted')
    wrong=run('DYN-01',WrongUnit());red=relation_trace(wrong)
    assert any(x['check']['review_status']=='rejected' for x in red)
    unclear=run('REFERRAL');amber=relation_trace(unclear)
    assert any(x['check']['review_status']=='unresolved' for x in amber)
    assert wrong['answer']['recommendation']==unclear['answer']['recommendation']=='undetermined'
    # 破坏一条原本有效的引用：缓存里的相同文字不能代替这个回执。
    bad=deepcopy(graph)
    next(n for n in bad['nodes'] if n['type']=='evidence')['reference']['call_id']='missing'
    assert proof_issues(bad,raw,task)
    # 相同两个端点：循环证明应拒绝，不用来证明的关系不因此被误判。
    bad=deepcopy(graph);edge=next(e for e in bad['edges'] if e['type']=='depends_on')
    reverse=dict(edge,id='injected-test',**{'from':edge['to'],'to':edge['from']})
    bad['edges'].append(reverse)
    assert any('循环' in s for s in proof_issues(bad,raw,task))
    reverse['type']='applies_to'
    assert not proof_issues(bad,raw,task)
    # 确认旧阈值确实退出了当前判定，而非只在界面画出覆盖箭头。
    assert any(n['type']=='rule' and n['value']==60 and not n['active'] for n in graph['nodes'])
    assert any(n['type']=='rule' and n['value']==90 and n['active'] for n in graph['nodes'])
    oid='condition:ticket_deadline_hours'
    states=[next((n['state'] for n in g['nodes'] if n['id']==oid),None) for g in b['history']]
    assert states[0] is None and 'UNKNOWN' in states and states[-1]=='SUPPORT'
    late=run('LATE-TICKET')
    assert late['answer']['recommendation']=='ineligible' and late['scorecard']['level']=='已建模范围内证据充分'
    # 固定任务、证据、候选提案和模型输出时，重复审核必须生成相同的图。
    from pr5_reviewer import review
    def fixed(stage,prompt,payload):
        for m in b['model_calls']:
            if m['stage']==stage and json.loads(m['messages'][-1]['content'])==payload:
                return json.loads(m['response']['raw_output'])
        raise ValueError('找不到独立审核输入')
    last=b['history'][-2]
    args=(task,last,None,raw,fixed)
    assert review(*args,{})==review(*args,{})
    dest=Path(__file__).parent/'examples/pr5/acceptance.json'
    dest.write_text(json.dumps(dict(accepted=green,rejected=red,unresolved=amber,
        deadline_history=states,late_decision=late['answer'],negative_card_level=late['scorecard']['level'],
        other_checks=['错引拒绝','循环自证拒绝','非证明关系成环不过度阻断','旧阈值退出','固定输入复现']),ensure_ascii=False,indent=2),encoding='utf8')
    print('岗位验收样例通过：三类审核、引用、循环、覆盖、重算和证据充分的否定结论。')

if __name__=='__main__': main()
