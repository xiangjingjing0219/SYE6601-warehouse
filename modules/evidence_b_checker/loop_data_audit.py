"""Verify latest LoopB records against supplied source cases, preserving synthetic labels."""
import json
from pathlib import Path
from log_intake import resolve, digest

def audit(root,cases):
    root=Path(root);by_case={c['case_id']:c for c in cases};errors=[];counts={'LOG_DERIVED':0,'SYNTHETIC':0};ids=set()
    files=sorted((root/'databases').rglob('*.json'))+[root/'knowledge_base/documents.json']
    for path in files:
        payload=json.loads(path.read_text(encoding='utf-8-sig'));records=payload.get('records',payload.get('documents',[]))
        for record in records:
            rid=record.get('record_id');prov=record.get('provenance',{});kind=prov.get('kind')
            if not rid or rid in ids:errors.append({'record_id':rid,'code':'DUPLICATE_OR_MISSING_ID'})
            ids.add(rid)
            if kind not in counts:errors.append({'record_id':rid,'code':'MISSING_PROVENANCE'});continue
            counts[kind]+=1
            if kind=='LOG_DERIVED':
                try:
                    source=by_case[prov['case_id']]
                    if source['run_id']!=prov['run_id']:raise ValueError('WRONG_RUN')
                    pointer=prov['json_pointer'];value=resolve(source,pointer)
                    if source['trace'][int(pointer.split('/')[2])]['id']!=prov['event_id']:raise ValueError('WRONG_EVENT')
                    actual=record['data'] if 'data' in record else record['excerpt']
                    if digest(actual)!=digest(value):raise ValueError('SOURCE_VALUE_MISMATCH')
                except (ValueError,KeyError,TypeError,IndexError) as e:errors.append({'record_id':rid,'code':str(e)})
    return {'passed':not errors,'records':len(ids),'provenance_counts':counts,'errors':errors,'scope':'source equality only; synthetic data is not original fact; no live tool execution'}
