"""Development-only comparison; gold is read AFTER predictions and never passed to B."""
import hashlib,json
from collections import Counter
from pathlib import Path
from log_intake import resolve
from claim_alignment import normalize

STATES={'SUPPORT','REFUTE','UNKNOWN','CONFLICT','MISSING_RULE'}

def validate(gold, cases, source_bytes):
    errors=[]; by_run={c['run_id']:c for c in cases}
    if len(by_run)!=len(cases):errors.append('DUPLICATE_SOURCE_RUN')
    if hashlib.sha256(source_bytes).hexdigest()!=gold.get('source_sha256'):errors.append('SOURCE_HASH_MISMATCH')
    runs=gold.get('runs',[])
    if len({r['run_id'] for r in runs})!=len(runs) or {r['run_id'] for r in runs}!=set(by_run):errors.append('RUN_SET_MISMATCH')
    for run in runs:
        src=by_run.get(run['run_id'])
        if not src:continue
        if src['case_id']!=run['case_id'] or src['ai_answer']!=run['ai_answer']:errors.append(run['run_id']+':SOURCE_MISMATCH')
        ids=[c['gold_claim_id'] for c in run['claims']]
        if len(ids)!=len(set(ids)):errors.append(run['run_id']+':DUPLICATE_CLAIM')
        for c in run['claims']:
            prefix=run['case_id']+':'+c['gold_claim_id']
            state=c.get('gold_status')
            if state not in STATES or c.get('gold_status_four_state')!=('UNKNOWN' if state=='MISSING_RULE' else state):errors.append(prefix+':STATE_MAPPING')
            if not c.get('answer_span') or c['answer_span'] not in src['ai_answer']:errors.append(prefix+':SPAN')
            for ev in c.get('evidence_values',[]):
                try:
                    actual=resolve(src,ev['json_pointer'])
                    if json.dumps(actual,sort_keys=True,ensure_ascii=False)!=json.dumps(ev['value'],sort_keys=True,ensure_ascii=False):errors.append(prefix+':EVIDENCE_VALUE')
                except (KeyError,IndexError,TypeError,ValueError):errors.append(prefix+':POINTER')
            for ev in c.get('evidence_locators',[]):
                try:
                    resolve(src,ev['json_pointer'])
                    idx=int(ev['json_pointer'].split('/')[2])
                    if src['trace'][idx]['id']!=ev['event_id']:errors.append(prefix+':EVENT_ID')
                except (KeyError,IndexError,TypeError,ValueError):errors.append(prefix+':LOCATOR')
    return {'passed':not errors,'errors':errors,'runs':len(runs),'claims':sum(len(r['claims']) for r in runs),
            'review_status':gold.get('review_status'),'formal_acceptance_eligible':False}

def compare(gold,reports):
    by_run={r['prediction']['run_id']:r for r in reports}; rows=[]
    for run in gold['runs']:
        report=by_run.get(run['run_id']);local=report['b_review']['local_review'] if report else {}
        nodes={n['id']:n for n in local.get('nodes',[])}
        candidates=[]
        for c in local.get('checks',[]):
            n=nodes.get(c.get('target'),{})
            if n.get('type')=='claim' and n.get('answer_excerpt'):candidates.append((n['answer_excerpt'],c))
        span_counts=Counter(normalize(c['answer_span']) for c in run['claims'])
        for g in run['claims']:
            matches=[c for text,c in candidates if normalize(text)==normalize(g['answer_span'])]
            # Overlapping scopes with identical text must be explicitly resolved, not double counted.
            unique=len(matches)==1 and span_counts[normalize(g['answer_span'])]==1 and g.get('assessment_scope')=='AS_ASSERTED'
            state=matches[0]['state'] if unique else None
            rows.append({'case_id':run['case_id'],'run_id':run['run_id'],'gold_claim_id':g['gold_claim_id'],
                         'answer_span':g['answer_span'],'gold_four_state':g['gold_status_four_state'],
                         'predicted_four_state':state,'comparison':'MATCH' if state==g['gold_status_four_state'] else 'MISMATCH' if state else 'UNALIGNED',
                         'scope':g.get('assessment_scope'),'review_status':run.get('review_status')})
    counts=Counter(r['comparison'] for r in rows)
    return {'purpose':'development_alignment_not_formal_accuracy','gold_review_status':gold.get('review_status'),
            'formal_accuracy':None,'total_gold_claims':len(rows),'counts':dict(counts),
            'unmatched_in_denominator':True,'rows':rows,
            'limitations':['Only unique exact span plus AS_ASSERTED alignment is scored.','Unaligned may mean extraction missing, broader/narrower scope or metadata-only checks; it is not a correct prediction.','AI-reviewed DRAFT labels are not independent human truth.']}
