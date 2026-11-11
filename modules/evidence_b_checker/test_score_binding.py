"""检查“工单上写的时间”和“这份工单是否可用”能否分开追溯。"""
import unittest
from copy import deepcopy
from graph_review import review_graph,version_review_key
from score_bridge_v02 import project
from run_dynamic_review import samples

class VersionTests(unittest.TestCase):
    def setUp(self):
        self.task,self.base,self.c,self.log,self.t=samples()
        self.receipts=dict(base_payload=self.base,tickets=self.t)
        self.audit=dict(valid=True,mode='fixture_human',reviewer='合成测试',basis='本测试单独给定有效版本',basis_locator='fixture://test/review')
    def graph(self):
        return review_graph(self.task,None,dict(base_version=0,upserts=[self.c]),self.receipts,review_log=self.log)
    def card_input(self):
        return project(self.task,self.graph(),self.receipts,None)
    def test_missing_version(self):
        g=self.graph()
        self.assertEqual(g['checks'][0]['time_comparison'],'SUPPORT')
        self.assertEqual(g['recommendation'],'undetermined')
        self.assertIn('TICKET_VERSION_UNVERIFIED',self.card_input()['obligations'][-1]['reason_codes'])
    def test_verified_fixture(self):
        self.log[version_review_key(self.task,self.t)]=self.audit
        self.assertEqual(self.card_input()['recommendation'],'eligible')
    def test_review_not_reused(self):
        self.log[version_review_key(self.task,self.t)]=self.audit
        self.t['records'][0]['record_id']='a-different-ticket'
        self.assertEqual(self.card_input()['recommendation'],'undetermined')
    def test_trace_cannot_mix_receipts(self):
        g=self.graph()
        self.t['call_id']='other'
        with self.assertRaises(ValueError): project(self.task,g,self.receipts,None)
    def test_missing_basis(self):
        del self.audit['basis_locator']
        self.log[version_review_key(self.task,self.t)]=self.audit
        self.assertEqual(self.graph()['recommendation'],'undetermined')
    def test_failure_reasons_in_card(self):
        for status in ('ACCESS_DENIED','TIMEOUT'):
            self.t['tool_status']=status
            self.assertIn(status,self.card_input()['obligations'][-1]['reason_codes'])
    def test_future_record_is_not_proof_of_late_submission(self):
        self.t['records'][0]['submitted_at']='2099-12-31T23:59:00Z'
        self.log[version_review_key(self.task,self.t)]=self.audit
        self.assertEqual(self.graph()['checks'][0]['time_comparison'],'UNKNOWN')
