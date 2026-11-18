"""批量接收运行日志，输出逐例定位和统计；不读取案例答案说明。"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from log_intake import inspect_dataset, resolve, verify_reference


def run(source, output):
    data = source.read_bytes()
    reports = inspect_dataset(json.loads(data.decode('utf-8-sig')))
    output.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    rows = []
    for report in reports:
        pointers = [report['answer_pointer']]
        pointers += [p for e in report['evidence_index'] for p in (e['arguments_pointer'], e['result_pointer'])]
        pointers += [n['pointer'] for n in report['progress_notes']]
        pointers += [o['pointer'] for o in report['observations']]
        if not all(verify_reference(report, p, resolve(report['raw_log'], p)) for p in pointers):
            raise ValueError('引用回读失败：' + report['case_id'])
        counts.update(o['code'] for o in report['observations'])
        rows.append(dict(case_id=report['case_id'], run_id=report['run_id'],
                         log_sha256=report['log_sha256'],
                         tool_calls=len(report['evidence_index']),
                         progress_notes=len(report['progress_notes']),
                         observations=len(report['observations']),
                         references_verified=len(pointers), answer_verdict=None))
    summary = dict(dataset_sha256=hashlib.sha256(data).hexdigest(), records=len(reports),
                   tool_calls=sum(r['tool_calls'] for r in rows),
                   progress_notes=sum(r['progress_notes'] for r in rows),
                   observation_counts=dict(counts),
                   cases_with_observations=sum(r['observations'] > 0 for r in rows),
                   references_verified=sum(r['references_verified'] for r in rows),
                   semantic_review_status='not_performed', cases=rows)
    for name, value in [('reports.json', reports), ('summary.json', summary)]:
        target = output / name
        if target.resolve() == source.resolve():
            raise ValueError('输出不能覆盖输入')
        target.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.input, args.output_dir)
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}, ensure_ascii=False, indent=2))
