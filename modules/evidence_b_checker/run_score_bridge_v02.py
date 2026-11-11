"""先把 PR #4 的 confidence_a_mvp 放在本模块旁边，再运行此脚本。"""
from pathlib import Path
import json
import sys
from score_bridge_v02 import replay

root=Path(__file__).resolve().parent
sys.path.insert(0,str(root.parent/'confidence_a_mvp'))
try:
    from confidence_a.contracts_v02 import validate_snapshot_v02
    from confidence_a import score_snapshot
except ImportError:
    raise SystemExit('需要评分组 PR #4 的 modules/confidence_a_mvp。主分支旧版暂不支持。')
out=root/'examples/score_v02'
out.mkdir(parents=True,exist_ok=True)
def save(filename,obj):
    (out/filename).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8')
summary=[]
for i,(stage,s,error) in enumerate(replay(),1):
    if error:
        summary.append(dict(stage=stage,blocked=error))
        print(stage,error)
    else:
        validate_snapshot_v02(s)
        card=score_snapshot(s)
        save(f'{i}_input.json',s)
        save(f'{i}_card.json',card)
        summary.append(dict(stage=stage,level=card['level'],score=card['score']))
        print(stage,card['level'])
save('summary.json',summary)
