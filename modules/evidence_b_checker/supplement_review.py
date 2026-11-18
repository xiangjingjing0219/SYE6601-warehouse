"""B-side validation of supplied records; no tool querying or Loop scheduling.
Contract is a proposed offline envelope using the latest LoopB lookup/data/provenance.
"""
from copy import deepcopy
from datetime import datetime
from log_intake import digest

def review_records(request, receipt):
    issues=[]; records=receipt.get('records',[])
    required=('case_id','run_id','action_id','tool','arguments')
    for key in required:
        if not request.get(key) or receipt.get(key)!=request.get(key):issues.append('CONTEXT_MISMATCH:'+key)
    if receipt.get('status')!='OK':issues.append('TOOL_NOT_OK')
    if not isinstance(records,list) or not records:issues.append('NO_RECORDS');records=[]
    ids=[r.get('record_id') for r in records if isinstance(r,dict)]
    if len(ids)!=len(records) or any(not x for x in ids) or len(ids)!=len(set(ids)):issues.append('INVALID_RECORD_IDS')
    tool=request.get('tool');args=request.get('arguments',{});target=request.get('target',{})
    if tool not in ('production.daily_output','policy_database.get_endorsement_renewal_status'):issues.append('UNSUPPORTED_TOOL')
    states=[]
    for r in records:
        if not isinstance(r,dict):issues.append('INVALID_RECORD');continue
        lookup=r.get('lookup',{});data=r.get('data',{});prov=r.get('provenance',{})
        if prov.get('kind') not in ('LOG_DERIVED','SYNTHETIC'):issues.append('MISSING_PROVENANCE')
        if prov.get('kind')=='LOG_DERIVED' and (prov.get('case_id')!=request.get('case_id') or prov.get('run_id')!=request.get('run_id')):issues.append('WRONG_SOURCE_RUN')
        if tool=='production.daily_output':
            if not args.get('line_id') or lookup.get('line_id')!=args['line_id']:issues.append('WRONG_LINE')
            if not target.get('business_date') or data.get('business_date')!=target['business_date']:issues.append('WRONG_BUSINESS_DATE')
            try:
                start=datetime.fromisoformat(data['start_at']);end=datetime.fromisoformat(data['end_at'])
                lo=datetime.fromisoformat(args['date_from']);hi=datetime.fromisoformat(args['date_to'])
                if any(x.utcoffset() is None for x in (start,end,lo,hi)) or not (lo<=start<hi and start<end<=hi):issues.append('WRONG_TIME_WINDOW')
                if lookup.get('start_at')!=data['start_at']:issues.append('LOOKUP_TIME_MISMATCH')
            except (KeyError,ValueError,TypeError):issues.append('INVALID_TIME')
            if type(data.get('units')) is not int or data['units']<0:issues.append('INVALID_UNITS')
        elif tool=='policy_database.get_endorsement_renewal_status':
            for k in ('policy_id','endorsement_id'):
                if not args.get(k) or lookup.get(k)!=args[k]:issues.append('WRONG_'+k.upper())
            if not target.get('as_of') or lookup.get('as_of')!=target['as_of']:issues.append('WRONG_OBSERVATION_DATE')
            if not target.get('policy_year') or data.get('current_policy_year')!=target['policy_year']:issues.append('WRONG_POLICY_YEAR')
            states.append(data.get('endorsement_renewal_status'))
    if tool=='production.daily_output':
        keys=[(r.get('lookup',{}).get('line_id'),r.get('data',{}).get('start_at')) for r in records if isinstance(r,dict)]
        if len(keys)!=len(set(keys)):issues.append('DUPLICATE_SHIFT')
    accepted=not issues
    state='UNKNOWN'
    if accepted and states:
        if set(states)=={'RENEWED','NOT_RENEWED'}:state='CONFLICT'
        elif set(states)=={'NOT_RENEWED'}:state='REFUTE'
        elif set(states)=={'RENEWED'}:state='SUPPORT'
    return {'metadata_passed':accepted,'issues':sorted(set(issues)),
            'predicate':'renewal_record_reports_renewed' if states else 'supplement_scope_verified',
            'state':state,'accepted_record_ids':ids if accepted else [],
            'receipt_sha256':digest(receipt),'synthetic':any(r.get('provenance',{}).get('kind')=='SYNTHETIC' for r in records if isinstance(r,dict)),
            'answer_status':'UNKNOWN','tool_executed_by_B':False,
            'note':'Receipt applicability only. No overall coverage/payment approval. Proposed offline contract, not an agreed live API.'}

def append_industrial(case, request, receipt):
    result=review_records(request,receipt)
    if request.get('case_id')!=case.get('case_id') or request.get('run_id')!=case.get('run_id'):raise ValueError('CASE_RUN_MISMATCH')
    if not result['metadata_passed'] or request['tool']!='production.daily_output':raise ValueError('SUPPLEMENT_NOT_ACCEPTED')
    out=deepcopy(case);event_id='b_supplement_'+digest(receipt)[:16]
    if any(e['id']==event_id for e in out['trace']):raise ValueError('DUPLICATE_SUPPLEMENT')
    out['trace'].append({'id':event_id,'event':'tool_call','type':'database_query','tool':request['tool'],
                         'arguments':deepcopy(request['arguments']),
                         'result':{'line_id':request['arguments']['line_id'],
                                   'shifts':[deepcopy(r['data']) for r in receipt['records']],
                                   'b_provenance':{'execution_kind':'offline_fixture','receipt_sha256':result['receipt_sha256'],'synthetic':result['synthetic']}}})
    return out,result
