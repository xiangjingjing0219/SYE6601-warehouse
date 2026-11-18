"""Exact scope-preserving B -> A bindings. Never promote substring checks to full claims."""
from copy import deepcopy
import re

def normalize(text):
    # Only cosmetic whitespace and terminal punctuation, not operators/units/numbers.
    return re.sub(r'\s+', '', text or '').strip('。；;')

def bind(local, graph):
    out=deepcopy(local)
    claims=[n for n in graph.get('nodes',[]) if n.get('type')=='claim']
    nodes={n['id']:n for n in out.get('nodes',[])}
    bindings=[]
    for chk in out.get('checks',[]):
        target=nodes.get(chk.get('target'),{})
        excerpt=target.get('answer_excerpt') if target.get('type')=='claim' else None
        hits=[n for n in claims if excerpt and normalize(excerpt)==normalize(n.get('content'))]
        chk['a_claim_id']=hits[0]['id'] if len(hits)==1 else None
        chk['alignment_status']='EXACT' if len(hits)==1 else 'AMBIGUOUS' if hits else 'UNMAPPED'
        if len(hits)==1:target['a_claim_id']=hits[0]['id']
        bindings.append({'check_id':chk.get('id',chk.get('check_id')),'a_claim_id':chk['a_claim_id'],'status':chk['alignment_status']})
    out['claim_bindings']=bindings
    mapped={b['a_claim_id'] for b in bindings if b['status']=='EXACT'}
    out['claim_review_coverage']=[{'a_claim_id':c['id'],'claim_text':c.get('content'),'review_state':'LOCAL_CHECK_BOUND' if c['id'] in mapped else 'NOT_REVIEWED_BY_B','reason':None if c['id'] in mapped else '尚无完整范围一致的B检查；不是证据已被判为不足或结论已被判错'} for c in claims]
    # Feed this restricted view to 07A's existing text-matching overlay, never the broader local view.
    safe=deepcopy(out)
    safe['checks']=[c for c in safe.get('checks',[]) if c.get('alignment_status')=='EXACT']
    out['confidence_overlay_input']=safe
    return out
