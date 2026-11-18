import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from egraph_bridge import check_artifact, evaluate_payload, canonical

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.case=dict(case_id='X',run_id='X-r1',user_question='q',ai_answer='a',visible_context={},trace=[dict(id='c1',event='tool_call',tool='t.lookup',type='retrieval',arguments={},result={'text':'原文\n"片段"','flag':True})])
        self.graph=dict(case_id='X',run_id='X-r1',nodes=[dict(id='MAT-1',type='evidence',content='result',record_id='c1',locator='trace[c1].result'),dict(id='CLM-1',type='claim',content='a',evidence_status='SUPPORT')],edges=[],gaps=[],checks=[],paths=[])
        self.payload=dict(graph=self.graph,plan=dict(case_id='X',run_id='X-r1',actions=[]),scorecard=dict(case_id='X',run_id='X-r1',claims=[dict(claim_id='CLM-1')]))
    def codes(self):return {x['code'] for x in check_artifact(self.case,self.payload)}
    def test_no_input_mutation(self):
        before=copy.deepcopy((self.case,self.payload)); evaluate_payload(self.case,self.payload)
        self.assertEqual((self.case,self.payload),before)
    def test_no_approval_or_model_fabrication(self):
        r=evaluate_payload(self.case,self.payload);b=r['graph_bundle']
        self.assertEqual(r['prediction']['answer_status'],'UNKNOWN')
        self.assertFalse(b['model_manifest']['model_called']);self.assertEqual(b['model_calls'],[])
        self.assertEqual(b['execution_kind'],'replay');self.assertEqual(b['actions'],[])
        self.assertTrue(all(n['review_status']=='candidate' for n in b['snapshots'][0]['nodes']))
    def test_canonical_receipt_quotes(self):
        self.graph['nodes'][0]['locator']='trace[c1].result.text'
        b=evaluate_payload(self.case,self.payload)['graph_bundle']
        ref=b['snapshots'][0]['nodes'][0]['evidence'][0]
        self.assertIn(ref['quote'],b['tool_receipts'][0]['source_text'])
        self.assertEqual(json.loads(ref['quote']),self.case['trace'][0]['result']['text'])
    def test_dataset_binding(self):
        b=evaluate_payload(self.case,self.payload,{'data_version':'dataset-v'})['graph_bundle']
        self.assertEqual(b['data_version'],'dataset-v')
    def test_snapshot_changes_on_source_mutation(self):
        old=evaluate_payload(self.case,self.payload)['graph_bundle']['final_snapshot_version']
        self.case['trace'][0]['result']['flag']=False
        self.assertNotEqual(old,evaluate_payload(self.case,self.payload)['graph_bundle']['final_snapshot_version'])
    def test_valid_gap_endpoint(self):
        self.graph['gaps']=[dict(id='G1',description='缺证',affected_claims=['CLM-1'])]
        self.graph['edges']=[dict(id='E1',source='G1',target='CLM-1',type='blocks')]
        self.assertTrue(evaluate_payload(self.case,self.payload)['prediction']['structural_passed'])
    def test_missing_edge_endpoint(self):
        self.graph['edges']=[dict(id='E1',source='absent',target='CLM-1',type='supports')]
        self.assertIn('DANGLING_EDGE',self.codes())
    def test_plan_binding(self):
        self.payload['plan']['actions']=[dict(id='P1',gap_ids=['missing'],target_claims=['CLM-1'])]
        self.assertIn('DANGLING_PLAN_REFERENCE',self.codes())
    def test_score_binding(self):
        self.payload['scorecard']['claims'][0]['claim_id']='missing'
        self.assertIn('DANGLING_SCORE_CLAIM',self.codes())
    def test_run_binding(self):
        self.payload['plan']['run_id']='other';self.assertIn('RUN_MISMATCH',self.codes())
    def test_duplicate_node(self):
        self.graph['nodes'].append(copy.deepcopy(self.graph['nodes'][0]));self.assertIn('DUPLICATE_ID',self.codes())
    def test_record_mismatch(self):
        self.graph['nodes'][0]['record_id']='s1';self.assertIn('RECORD_LOCATOR_MISMATCH',self.codes())
    def test_false_empty_proof(self):
        self.graph['paths']=[dict(path_id='P1',goal_claim='CLM-1',conditions=[],satisfied=True)]
        self.assertIn('PATH_SATISFACTION_MISMATCH',self.codes())
    def test_typed_boolean_rendering(self):
        self.graph['nodes'].append(dict(id='R1',type='rule',content='required',locator='trace[c1].result.flag',excerpt='True'))
        r=evaluate_payload(self.case,self.payload)
        self.assertTrue(r['prediction']['structural_passed'])
        self.assertIn('SCALAR_RENDERING',{f['code'] for f in r['b_review']['provenance']['findings']})
    def test_schema_error_is_not_pass(self):
        r=evaluate_payload(self.case,self.payload,schema_errors=['bad schema'])
        self.assertFalse(r['prediction']['structural_passed'])

if __name__=='__main__':unittest.main()
