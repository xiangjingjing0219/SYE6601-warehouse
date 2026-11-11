"""DYN-01：模拟 A 和工单接口；B 的审核、版本更新和计算实际执行。"""
from copy import deepcopy
import json
from pathlib import Path
from graph_review import review_graph,review_key,digest

ROOT=Path(__file__).resolve().parent


def samples():
    base=json.loads((ROOT/'examples/normal_input.json').read_text())
    task={**base['task'],'event_time':base['task']['incident_start'],'run_id':'B-DYN-DEMO',
          'answer_version':'draft-1','question':'本次故障是否符合补偿条件？'}
    receipt=base['responses']['CRM_CONTRACT_DB']
    rec=receipt['records'][0]
    clause='客户须在故障开始后24小时内提交本次事故的工单（含截止时刻）。'
    rec['clauses']={'第4条':clause}
    c=dict(id='ticket-deadline',target='claim:eligible',relation='depends_on',
           expression={'kind':'ticket_within_hours','hours':24},
           citation=dict(source_id='CRM_CONTRACT_DB',record_id=rec['evidence_id'],
                         locator='第4条',excerpt=clause,call_id=receipt['evidence_id']))
    log={review_key(task,c,rec,receipt):dict(mode='fixture_human',reviewer='演示复核记录',
            decision='accepted',reason='合成原句明确从故障开始计24小时，包含截止时刻。'),
         'coverage:'+digest([task,receipt,[(c['id'],c)]]):dict(mode='fixture_human',complete=True)}
    ticket=dict(source_id='TICKET_SYSTEM',call_id='Q-SUBMITTED',customer_id=task['customer_id'],
                incident_id=task['incident_id'],scope=task['scope'],run_id=task['run_id'],
                tool_status='SUCCESS',pagination_complete=True,query_from=task['event_time'],
                query_to='2026-06-03T00:00:00Z',fetched_at='2026-06-03T00:00:00Z',
                records=[dict(customer_id=task['customer_id'],incident_id=task['incident_id'],
                              scope=task['scope'],record_id='T-1',submitted_at='2026-06-02T10:00:00Z')])
    return task,base,c,log,ticket


def run():
    task,base,c,log,ticket=samples()
    first=deepcopy(base)
    del first['responses']['CRM_CONTRACT_DB']
    rows=[('尚未取得合同',first,[],None,{}),('补到合同，语义等待审核',base,[c],None,{}),
          ('按示例复核原句，尚无工单',base,[],None,log),('补到截止时刻提交的工单',base,[],ticket,log)]
    old=None
    trace=[]
    for title,b,upserts,t,l in rows:
        p=dict(base_version=len(trace),upserts=upserts)
        receipts=dict(base_payload=b,tickets=t)
        old=review_graph(task,old,p,receipts,review_log=l)
        trace.append(dict(stage=title,proposal=p,tool_receipts=receipts,review_log=l,snapshot=old))
    return dict(synthetic=True,task=task,stages=trace)


if __name__=='__main__':
    trace=run()
    dest=ROOT/'examples/dynamic_trace.json'
    dest.write_text(json.dumps(trace,ensure_ascii=False,indent=2),encoding='utf8')
    for s in trace['stages']:
        print(s['stage'],s['snapshot']['recommendation'])
