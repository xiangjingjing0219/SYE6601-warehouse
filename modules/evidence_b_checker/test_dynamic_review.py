"""针对组长提出的误读、错引、关键缺口、旧关系和否定建议做回归。"""
import unittest
from copy import deepcopy
from graph_review import review_graph,review_key,version_review_key,InputError
from run_dynamic_review import samples,run


class DynamicTests(unittest.TestCase):
    def setUp(self):
        self.task,self.b,self.c,self.log,self.t=samples()

    def verified_fixture(self):
        # 仅本测试增加独立的合成复核，不改变默认材料。
        self.log[version_review_key(self.task,self.t)]=dict(mode='fixture_human',valid=True,
            reviewer='测试角色',basis='独立合成回执版本复核',basis_locator='fixture://review/1')

    def snapshot(self,old=None):
        return review_graph(self.task,old,dict(base_version=old['graph_version'] if old else 0,upserts=[self.c]),
                            dict(base_payload=self.b,tickets=self.t),review_log=self.log)

    def test_stages(self):
        trace=run()['stages']
        self.assertEqual([x['snapshot']['recommendation'] for x in trace],
                         ['undetermined']*4)
        self.assertEqual(trace[2]['snapshot']['checks'][0]['review_status'],'accepted')
        self.assertEqual(trace[2]['snapshot']['nodes'][-1]['state'],'UNKNOWN')
        self.assertEqual(trace,run()['stages'])

    def test_late(self):
        self.t['records'][0]['submitted_at']='2026-06-02T10:00:01Z'
        self.verified_fixture()
        self.assertEqual(self.snapshot()['recommendation'],'ineligible')

    def test_negative_requires_complete_closed_window(self):
        self.t['records']=[]
        for key,value in [('pagination_complete',False),('fetched_at',self.task['event_time']),
                          ('customer_id','wrong'),('tool_status','ACCESS_DENIED')]:
            original=self.t[key];self.t[key]=value
            self.verified_fixture()
            self.assertEqual(self.snapshot()['recommendation'],'undetermined')
            self.t[key]=original

    def test_positive_does_not_require_last_page(self):
        self.t['pagination_complete']=False
        self.verified_fixture()
        self.assertEqual(self.snapshot()['recommendation'],'eligible')

    def test_wrong_location_and_answer_reference(self):
        for key in ['source_id','record_id','excerpt','locator','call_id']:
            prev=self.c['citation'][key];self.c['citation'][key]='answer'
            self.assertEqual(self.snapshot()['checks'][0]['review_status'],'rejected')
            self.c['citation'][key]=prev

    def test_changed_semantics_needs_new_review(self):
        old=self.snapshot();saved=deepcopy(old)
        self.c['expression']={'kind':'ticket_within_minutes','minutes':24}
        new=self.snapshot(old)
        self.assertEqual(old,saved)
        self.assertFalse(new['edges'][0]['active'])
        self.assertEqual(new['recommendation'],'undetermined')
        self.assertTrue(new['changes'])

    def test_review_rejected(self):
        receipt=self.b['responses']['CRM_CONTRACT_DB']
        key=review_key(self.task,self.c,receipt['records'][0],receipt)
        self.log[key].update(decision='rejected',reason='示例：人工判读不支持候选关系')
        self.assertFalse(self.snapshot()['edges'][0]['active'])

    def test_new_wording_not_implicitly_approved(self):
        r=self.b['responses']['CRM_CONTRACT_DB']['records'][0]
        r['clauses']['第4条']=self.c['citation']['excerpt']='须于事故开始后的一日内报单。'
        self.assertEqual(self.snapshot()['checks'][0]['review_status'],'unresolved')

    def test_stale_proposal(self):
        old=self.snapshot()
        with self.assertRaises(InputError):
            review_graph(self.task,old,dict(base_version=0,upserts=[]),dict(base_payload=self.b))

    def test_metadata_and_self_reference(self):
        self.c['target']='ob:'+self.c['id']
        self.assertEqual(self.snapshot()['recommendation'],'undetermined')
        self.c['target']='claim:eligible'
        self.b['responses']['CRM_CONTRACT_DB']['records'][0]['customer_id']='other'
        self.assertFalse(self.snapshot()['edges'][0]['active'])
