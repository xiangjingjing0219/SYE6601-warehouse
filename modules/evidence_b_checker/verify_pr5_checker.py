"""开发回归：先运行 B 的注入入口，再与 PR5 的合成预期比较。"""
import json
from pathlib import Path
from run_pr5_checker import run
from dynamic_evidence.evaluate import GOLD,assess

def verify():
    rows=[]
    for name,(expected,_,_) in GOLD.items():
        b=run(name)
        result=assess(b)
        ok=(b['answer']['recommendation']==expected and
            all(b['graph'][k]==b['scorecard'][k]==b['answer'][k] for k in
                ('task_id','run_id','answer_version','graph_version')))
        rows.append(dict(case=name,expected=expected,actual=b['answer']['recommendation'],passed=ok))
    # 不改团队案例：只在测试层模拟错误回执，验证不会误判为“不赔”。
    for label in ('错客户','错事故','过期','缺版本','重复编号内容冲突','未来提交','截止前空页'):
        def wrapper(tool):
            def query(source,task,page=None):
                r=tool(source,task,page)
                if source=='TICKET_DB':
                    record=r['records'][0]
                    if label=='错客户': record['customer_id']='WRONG'
                    elif label=='错事故': record['incident_id']='WRONG'
                    elif label=='过期': record['effective_to']='2020-01-01T00:00:00Z'
                    elif label=='缺版本': record['version']=''
                    elif label=='重复编号内容冲突': r['records'].append(dict(record,submitted_at='2026-10-01T16:00:00Z'))
                    elif label=='未来提交': record['submitted_at']='2099-01-01T00:00:00Z'
                    else: r.update(records=[],fetched_at=task['event_time'])
                return r
            return query
        b=run('DYN-01',tool_wrapper=wrapper)
        n=next(n for n in b['graph']['nodes'] if n['id']=='condition:ticket_deadline_hours')
        ok=b['answer']['recommendation']=='undetermined' and n['state']=='UNKNOWN' and bool(b['scorecard']['blockers'])
        rows.append(dict(case=label,actual=b['answer']['recommendation'],condition=n['state'],passed=ok))
    p=Path(__file__).parent/'examples/pr5/regression.json'
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
    print(len(GOLD),'个团队合成案例，7 个 B 侧边界案例；通过',sum(r['passed'] for r in rows),'/',len(rows))
    assert all(r['passed'] for r in rows), [r for r in rows if not r['passed']]
if __name__=='__main__':verify()
