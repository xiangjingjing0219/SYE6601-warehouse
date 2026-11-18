"""Read case-design notes for evaluation planning; never pass them into the evaluator."""
import json
import re
import argparse
from pathlib import Path
from log_intake import digest


def build_catalog(text, logs):
    rows=[]; notes=[]
    for lineno,line in enumerate(text.splitlines(),1):
        if not line.startswith('|'): continue
        cells=[c.strip() for c in line.strip('|').split('|')]
        match=re.search(r'INS-A\d{2}$',cells[0])
        if not match or len(cells)!=5:continue
        if cells[0]!=match[0]: notes.append({'line':lineno,'case_id':match[0],'issue':'unexpected_prefix_in_case_cell_removed_in_catalog_only'})
        rows.append(dict(case_id=match[0],domain=cells[1],design_description=cells[2],tool_sequence=cells[3],key_behavior=cells[4],source_line=lineno))
    ids=[r['case_id'] for r in rows]
    if len(ids)!=len(set(ids)):raise ValueError('duplicate design case')
    expected={r['case_id'] for r in logs}
    if set(ids)!=expected:raise ValueError('case design table and log IDs do not match')
    return dict(purpose='evaluation_design_only_not_runtime_input',not_four_state_gold_labels=True,
                source_text_sha256=digest(text),dataset_sha256=digest(logs),format_notes=notes,cases=rows)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('notes');p.add_argument('logs');p.add_argument('out');a=p.parse_args()
    result=build_catalog(Path(a.notes).read_text(encoding='utf-8-sig'),json.loads(Path(a.logs).read_text(encoding='utf-8-sig')))
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Cases:',len(result['cases']))
