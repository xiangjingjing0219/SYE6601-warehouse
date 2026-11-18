"""批量 B 局部审核：每条保留输出或失败原因，不读取案例说明。"""
import argparse
from collections import Counter
import json
from pathlib import Path
from industrial_review import review, VERSION
from log_intake import digest


def run(source, output):
    records=json.loads(source.read_text(encoding='utf-8-sig'))
    if not isinstance(records,list): raise ValueError('输入须为日志数组')
    results=[]; seen=set()
    for index,record in enumerate(records):
        try:
            key=(record['case_id'],record['run_id'])
            if key in seen: raise ValueError('重复运行标识')
            seen.add(key)
            graph=review(record)
            results.append(graph)
        except (KeyError,ValueError,TypeError,IndexError) as exc:
            results.append(dict(input_index=index,case_id=record.get('case_id') if isinstance(record,dict) else None,
                                analysis_status='failed',error=str(exc)))
    summary=dict(records=len(records),dataset_digest=digest(records),rule_version=VERSION,
                 analysis_status_counts=dict(Counter(r['analysis_status'] for r in results)),
                 check_state_counts=dict(Counter(c['state'] for r in results for c in r.get('checks',[]))),
                 accuracy=None,reason='未做独立标注评测；局部审核不得当作整条回答通过',
                 cases=[dict(case_id=r.get('case_id'),analysis_status=r['analysis_status'],
                             check_count=len(r.get('checks',[])),error=r.get('error')) for r in results])
    output.mkdir(exist_ok=True,parents=True)
    for name,data in [('graphs.json',results),('summary.json',summary)]:
        if (output/name).resolve()==source.resolve(): raise ValueError('不能覆盖输入')
        (output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    s=run(args.input,args.output_dir)
    print(json.dumps({k:v for k,v in s.items() if k!='cases'},ensure_ascii=False,indent=2))
