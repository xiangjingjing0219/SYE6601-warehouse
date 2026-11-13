"""验证接口提示不会改变业务判断，同时保留可回查的原文位置。"""
from unittest import TestCase
from proposal_intake import ROOT, check_proposal, read_json


class Alignment(TestCase):
    def setUp(self):
        d=ROOT/'examples/proposal'
        self.p=read_json(d/'input.json')
        self.r=read_json(d/'receipts.json')
        self.tools={'sources':[{'source_type':'TICKET_DB'}]}

    def test_hint_is_not_a_route(self):
        hint=dict(state='NEEDS_OWNER_CONFIRMATION',alias_enabled=False,
                  requested_source='TICKET_SYSTEM',candidate_provider_source='TICKET_DB')
        row=check_proposal(self.p,self.r,self.tools,source_inventory=[hint])['rule_catalog'][0]
        self.assertIn('TICKET_SYSTEM',row['sources_not_registered'])
        self.assertEqual(row['pending_source_names'],{'TICKET_SYSTEM':'TICKET_DB'})

    def test_coordinates_and_ids(self):
        def matches():
            return check_proposal(self.p,self.r,self.tools)['reference_checks'][0]['matches']
        row=self.r[0]['records'][0]
        self.assertEqual(matches()[0]['record_locator'],row['locator'])
        self.assertEqual(matches()[0]['source_id'],row['source_id'])
        row['context']['end']+=1
        self.assertFalse(matches())

    def test_task_not_replaced_with_demo_customer(self):
        del self.p['task']['customer_id']
        out=check_proposal(self.p,self.r,self.tools)
        self.assertIn('customer_id',out['missing_query_fields'])
        self.assertFalse(out['reference_checks'][0]['located'])
        self.assertEqual(out['recommendation'],'undetermined')
