"""使用统一工具实际回执；错误变体只用于验证守门逻辑。"""
import unittest
from proposal_intake import ROOT, check_proposal, read_json


class Intake(unittest.TestCase):
    def setUp(self):
        folder=ROOT/'examples/proposal'
        self.p=read_json(folder/'input.json')
        self.r=read_json(folder/'receipts.json')
        self.tools={'sources':[{'source_type':'CRM_CONTRACT_DB'}]}

    def check(self, reviews=None):
        return check_proposal(self.p,self.r,self.tools,human_reviews=reviews)

    def test_located_is_not_accepted(self):
        v=self.check()
        self.assertTrue(v['reference_checks'][0]['located'])
        self.assertEqual(v['relation_checks'][0]['review_status'],'unresolved')
        self.assertEqual(v['recommendation'],'undetermined')
        self.assertEqual(len(v['rule_catalog']),5)

    def test_expired_and_foreign_run(self):
        for k in ('expired','other_run'):
            self.setUp()
            if k=='expired': self.r[0]['records'][0]['effective_to']='2020-01-01T00:00:00Z'
            else: self.r[0]['run_id']='unrelated'
            self.assertFalse(self.check()['reference_checks'][0]['located'])

    def test_wrong_reference(self):
        self.p['graph_proposal']['nodes'][0]['source_locator']['excerpt']='24 minutes'
        self.assertFalse(self.check()['reference_checks'][0]['located'])

    def test_invalid_edge_or_cycle(self):
        for target in ('missing','E1'):
            self.p['graph_proposal']['edges'][0]['to']=target
            with self.assertRaises(ValueError): self.check()

    def test_invalid_schema_and_registry_type_mismatch(self):
        self.p['graph_proposal']['nodes'][1]['type']='exemption'
        with self.assertRaises(ValueError): self.check()

    def test_edited_claim_invalidates_human_review(self):
        key=self.check()['relation_checks'][0]['review_key']
        # 测试用复核单，不是项目实际人工签认。
        review={key:dict(decision='accepted',reviewer='fixture',reason='测试用记录')}
        self.assertEqual(self.check(review)['relation_checks'][0]['review_status'],'accepted')
        self.p['graph_proposal']['nodes'][1]['content']='须在24分钟内提交'
        self.assertEqual(self.check(review)['relation_checks'][0]['review_status'],'unresolved')
