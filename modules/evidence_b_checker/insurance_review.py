"""Bounded checks on explicit insurance receipts; never a claim-payment decision.
No case IDs, design labels, answer text, or external insurance rules are used.
"""
from copy import deepcopy

MISSING = {'TIMEOUT', 'ACCESS_DENIED', 'NO_RECORD', 'NOT_FOUND', 'NOT_AVAILABLE',
           'NOT_UPLOADED', 'PRELIMINARY', 'PENDING', 'IN_PROGRESS', 'INVESTIGATING'}

def review(case):
    checks = []
    def add(event, index, field, predicate, state, reason, extra=None):
        pointer = f'/trace/{index}/result/{field}'
        refs = [{'record_id': event['id'], 'pointer': pointer,
                 'value': deepcopy(event['result'].get(field))}]
        if extra: refs.append(extra)
        checks.append({'check_id': f"{event['id']}:{field}:{predicate}",
                       'predicate': predicate, 'state': state, 'reason_codes': [reason],
                       'evidence_ids': [r['record_id'] for r in refs], 'citations': refs})
    events = [(i,e) for i,e in enumerate(case['trace']) if e['event']=='tool_call' and isinstance(e.get('result'),dict)]
    notices = [(i,e) for i,e in events if e['tool']=='claims.get_first_notice']
    for i,e in events:
        r=e['result']
        # These checks report what the receipt says, not whether the policy covers the loss.
        if 'waiting_period_expired' in r:
            v=r['waiting_period_expired']
            add(e,i,'waiting_period_expired','recorded_waiting_period_expired',
                'SUPPORT' if v is True else 'REFUTE' if v is False else 'UNKNOWN',
                'WAITING_PERIOD_EXPIRED' if v is True else 'WAITING_PERIOD_NOT_EXPIRED' if v is False else 'INVALID_WAITING_PERIOD_FLAG')
        for key,value in r.items():
            if 'status' in key and isinstance(value,str) and value in MISSING:
                add(e,i,key,'receipt_final_and_available','UNKNOWN',value)
        for total_key,list_key in [('total_locations','records'),('total_records','complaints')]:
            if total_key not in r: continue
            total=r[total_key]; returned=r.get('returned_count'); rows=r.get(list_key)
            valid=type(total) is int and type(returned) is int and total>=0 and 0<=returned<=total and isinstance(rows,list) and len(rows)==returned
            complete=valid and returned==total
            add(e,i,total_key,'receipt_collection_complete','SUPPORT' if complete else 'UNKNOWN',
                'PAGINATION_COMPLETE' if complete else 'PARTIAL_PAGE' if valid else 'INVALID_PAGINATION',
                {'record_id':e['id'],'pointer':f'/trace/{i}/result/{list_key}','value':deepcopy(rows)})
        if e['tool'].startswith('policy_database.') and 'insured_id_number' in r:
            matches=[(j,n) for j,n in notices if n['result'].get('policy_id') and n['result']['policy_id']==e.get('arguments',{}).get('policy_id')]
            if len(matches)==1:
                j,n=matches[0]; a=n['result'].get('insured_id_number'); b=r['insured_id_number']
                valid=isinstance(a,str) and bool(a.strip()) and isinstance(b,str) and bool(b.strip())
                # Masked equal IDs are not proof of full identity. Unequal recorded IDs conflict.
                same=valid and a==b
                state='UNKNOWN' if not valid or (same and '*' in a) else 'SUPPORT' if same else 'REFUTE'
                reason='MISSING_INSURED_ID' if not valid else 'MASKED_ID_NOT_FULLY_VERIFIABLE' if same and '*' in a else 'INSURED_ID_MATCH' if same else 'WRONG_INSURED_ID'
                add(e,i,'insured_id_number','notice_policy_insured_match',state,reason,
                    {'record_id':n['id'],'pointer':f'/trace/{j}/result/insured_id_number','value':a})
    return {'checks':checks,'gaps':[{'check_id':c['check_id'],'reason_codes':c['reason_codes']} for c in checks if c['state']=='UNKNOWN'],
            'analysis_status':'bounded_receipt_checks','answer_status':'UNKNOWN',
            'limitations':['No whole-answer or claim-payment approval.','Receipt warnings do not imply the whole answer is wrong; later evidence may resolve them.','No inference of absent obligations or applicable insurance rules.']}
