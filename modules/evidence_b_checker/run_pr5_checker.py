"""从团队仓库根目录启动，或使用附带的离线笔记本。不会调用收费 API。"""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from dynamic_evidence.cases import make_case
from dynamic_evidence.controller import Harness,Budget
from dynamic_evidence.mock_model import FixtureModel
from dynamic_evidence.models import Replay
from dynamic_evidence.report import markdown
from pr5_reviewer import review

def run(name, model=None, recorded=None, tool_wrapper=None):
    task,tool=make_case(name)
    if recorded: task=recorded['task']
    return Harness(model or FixtureModel(),tool_wrapper(tool) if tool_wrapper else tool,
                   reviewer=review,budget=Budget(**recorded['budget']) if recorded else None).run(task)

def main():
    rec=json.loads((ROOT/'docs/dynamic-evidence/records/dyn01-model-replay.json').read_text())
    b=run('DYN-01',Replay(rec['model_calls']),rec)
    out=Path(__file__).parent/'examples/pr5'
    out.mkdir(exist_ok=True,parents=True)
    for name,v in [('replayed_bundle.json',b),('ticket_receipts.json',[r for r in b['tool_receipts'] if r['source_type']=='TICKET_DB'])]:
        (out/name).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
    (out/'scorecard.md').write_text(markdown(b),encoding='utf8')
    print('团队模型记录离线回放：',b['answer']['text'],b['graph']['stop_reason'])
    assert b['graph']['recommendation']=='eligible' and b['graph']['stop_reason']=='COMPLETED'
    return b

if __name__=='__main__': main()
