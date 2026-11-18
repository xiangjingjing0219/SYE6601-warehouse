import unittest
from copy import deepcopy
from claim_alignment import bind
from supplement_review import review_records,append_industrial
from gold_compare import validate,compare
import json,hashlib

class BindingTests(unittest.TestCase):
    def local(self,text):return {'run_id':'r','nodes':[{'id':'b','type':'claim','answer_excerpt':text}], 'checks':[{'id':'k','target':'b','state':'SUPPORT'}]}
    def test_exact(self):
        r=bind(self.local('产量4200件'),{'nodes':[{'id':'C7','type':'claim','content':'产量4200件。'}]})
        self.assertEqual(r['checks'][0]['a_claim_id'],'C7')
    def test_partial_not_promoted(self):
        r=bind(self.local('系统显示可以启动'),{'nodes':[{'id':'C','type':'claim','content':'系统显示可以启动，因此可以安全开机'}]})
        self.assertEqual(r['confidence_overlay_input']['checks'],[])
    def test_ambiguous_and_facts(self):
        g={'nodes':[{'id':x,'type':'claim','content':'foo'} for x in ['C1','C2']]}
        self.assertEqual(bind(self.local('foo'),g)['checks'][0]['alignment_status'],'AMBIGUOUS')
        l=self.local('foo');l['nodes'][0]['type']='fact'
        self.assertEqual(bind(l,{'nodes':g['nodes'][:1]})['confidence_overlay_input']['checks'],[])
    def test_numbers_and_units_not_normalized_away(self):
        self.assertIsNone(bind(self.local('1.5吨'),{'nodes':[{'id':'C','type':'claim','content':'15吨'}]})['checks'][0]['a_claim_id'])

class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.req={'case_id':'IND-043','run_id':'r','action_id':'a','tool':'production.daily_output','arguments':{'line_id':'Line-D','date_from':'2026-11-12T22:00:00+08:00','date_to':'2026-11-13T06:00:00+08:00'},'target':{'business_date':'2026-11-13'}}
        self.rec={'record_id':'x','lookup':{'line_id':'Line-D','start_at':'2026-11-12T22:00:00+08:00'},'data':{'shift':'夜班','start_at':'2026-11-12T22:00:00+08:00','end_at':'2026-11-13T06:00:00+08:00','business_date':'2026-11-13','units':1650},'provenance':{'kind':'SYNTHETIC'}}
        self.receipt={k:deepcopy(v) for k,v in self.req.items() if k!='target'};self.receipt.update(status='OK',records=[self.rec])
    def test_good_scope_is_not_answer_approval(self):
        r=review_records(self.req,self.receipt);self.assertTrue(r['metadata_passed']);self.assertEqual(r['answer_status'],'UNKNOWN');self.assertTrue(r['synthetic'])
    def test_wrong_scope_mutations(self):
        for field,value in [('business_date','2026-11-14'),('units',True),('start_at','2026-11-13T22:00:00+08:00')]:
            r=deepcopy(self.receipt);r['records'][0]['data'][field]=value
            self.assertFalse(review_records(self.req,r)['metadata_passed'])
        r=deepcopy(self.receipt);r['records'][0]['lookup']['line_id']='Line-E';self.assertFalse(review_records(self.req,r)['metadata_passed'])
    def test_timeout_empty_and_context(self):
        for field,value in [('status','TIMEOUT'),('records',[]),('run_id','other'),('action_id','other')]:
            r=deepcopy(self.receipt);r[field]=value
            self.assertFalse(review_records(self.req,r)['metadata_passed'])
    def test_duplicate_shift_other_id(self):
        r=deepcopy(self.receipt);r['records'].append(deepcopy(self.rec));r['records'][1]['record_id']='y'
        self.assertIn('DUPLICATE_SHIFT',review_records(self.req,r)['issues'])
    def test_append_and_reject_duplicate(self):
        c={'case_id':'IND-043','run_id':'r','trace':[]};out,_=append_industrial(c,self.req,self.receipt)
        self.assertEqual(c['trace'],[]);self.assertEqual(len(out['trace']),1)
        with self.assertRaises(ValueError):append_industrial(out,self.req,self.receipt)
    def test_renewal_unknown_not_negative(self):
        q={'case_id':'INS','run_id':'r','action_id':'a','tool':'policy_database.get_endorsement_renewal_status','arguments':{'policy_id':'P','endorsement_id':'E'},'target':{'as_of':'2026-11-12','policy_year':'2026-2027'}}
        r={k:deepcopy(v) for k,v in q.items() if k!='target'}
        r.update(status='OK',records=[{'record_id':'z','lookup':{'policy_id':'P','endorsement_id':'E','as_of':'2026-11-12'},'data':{'current_policy_year':'2026-2027','endorsement_renewal_status':'PENDING'},'provenance':{'kind':'SYNTHETIC'}}])
        self.assertEqual(review_records(q,r)['state'],'UNKNOWN')
        r['records'][0]['data']['endorsement_renewal_status']='NOT_RENEWED';self.assertEqual(review_records(q,r)['state'],'REFUTE')
        r['records'][0]['lookup']['as_of']='2025-11-12';self.assertFalse(review_records(q,r)['metadata_passed'])

class GoldTests(unittest.TestCase):
    def test_corrupt_source_rejected(self):
        c={'run_id':'r','case_id':'C','ai_answer':'hello','trace':[{'id':'e','result':{'x':1}}]};raw=json.dumps([c]).encode()
        claim={'gold_claim_id':'g','answer_span':'hello','assessment_scope':'AS_ASSERTED','gold_status':'SUPPORT','gold_status_four_state':'SUPPORT','evidence_values':[{'json_pointer':'/trace/0/result/x','value':2}]}
        gold={'source_sha256':hashlib.sha256(raw).hexdigest(),'review_status':'DRAFT','runs':[dict(c,claims=[claim])]}
        self.assertFalse(validate(gold,[c],raw)['passed']);claim['evidence_values'][0]['value']=1
        self.assertTrue(validate(gold,[c],raw)['passed'])
        r=compare(gold,[]);self.assertEqual(r['counts'],{'UNALIGNED':1});self.assertIsNone(r['formal_accuracy'])
    def test_scope_duplicate_not_double_scored(self):
        g={'review_status':'DRAFT','runs':[{'run_id':'r','case_id':'C','claims':[{'gold_claim_id':x,'answer_span':'hello','gold_status_four_state':'SUPPORT','assessment_scope':'AS_ASSERTED'} for x in ['a','b']]}]}
        p={'prediction':{'run_id':'r'},'b_review':{'local_review':{'nodes':[{'id':'n','type':'claim','answer_excerpt':'hello'}],'checks':[{'target':'n','state':'SUPPORT'}]}}}
        self.assertEqual(compare(g,[p])['counts'],{'UNALIGNED':2})

if __name__=='__main__':unittest.main()
