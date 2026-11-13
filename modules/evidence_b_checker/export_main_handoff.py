"""将团队 main 建链入口与 B 审核实际连跑，导出同次提案、回执及快照。"""
import argparse
import json
from pathlib import Path
from run_unified_checker import TEAM_ROOT, checked_provider, unified_review
from dynamic_evidence.controller import Harness
from dynamic_evidence.cases import make_case
from dynamic_evidence.mock_model import FixtureModel
from dynamic_evidence import graph as team_graph


def export(out, blocked):
    # 此入口只允许主程序，不用历史演示冒充 main。
    if Path(team_graph.__file__).resolve().parent != TEAM_ROOT / 'dynamic_evidence':
        raise RuntimeError('请在包含 dynamic_evidence 和 loop_b_unified 的团队主仓库运行')
    from loop_b_unified import create_provider
    task, _ = make_case('DYN-01')
    provider = create_provider('bundle-01', faults={'TICKET_DB':'forbidden'} if blocked else {})
    stages=[]
    def reviewer(task, prev, proposal, receipts, model, cache):
        from copy import deepcopy
        snapshot=unified_review(task,prev,proposal,receipts,model,cache)
        stages.append(deepcopy(dict(proposal=proposal,receipts=receipts,snapshot=snapshot)))
        return snapshot
    result=Harness(FixtureModel(),checked_provider(provider),reviewer=reviewer).run(task)
    assert result['graph']['recommendation']==('undetermined' if blocked else 'eligible')
    assert len(stages)==3
    assert all(s['snapshot']['run_id']==result['graph']['run_id'] for s in stages)
    assert all(s['proposal'] is not None for s in stages[:2])
    def ticket_state(s):
        return next((n['state'] for n in s['snapshot']['nodes'] if n['id']=='condition:ticket_deadline_hours'),None)
    assert [ticket_state(s) for s in stages]==[None,'UNKNOWN','UNKNOWN' if blocked else 'SUPPORT']
    stages[-1]['snapshot']=result['graph']
    out.mkdir(exist_ok=True,parents=True)
    def save(name,x):
        (out/(name+'.json')).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
    for index,s in enumerate(stages,1):
        save(f'{index}_本轮',s)
    save('完整运行',result)
    print(out.name, result['graph']['recommendation'],result['graph']['stop_reason'])


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,default=Path(__file__).parent/'examples/main_handoff')
    args=ap.parse_args()
    export(args.output/'正常工单',False)
    export(args.output/'无权限工单',True)
