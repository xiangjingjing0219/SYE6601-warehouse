import copy
import unittest
from egraph_audit import audit, locate

class EgraphAuditTests(unittest.TestCase):
    def setUp(self):
        self.raw = dict(case_id='X', run_id='R', user_question='q', ai_answer='a', visible_context={}, trace=[
            dict(id='c1', event='tool_call', tool='lookup', type='retrieval', arguments={}, result={'items':[{'coverage_excerpt':'原文条款'}], 'flag':False}),
            dict(id='s1', event='assistant_progress_note', text='未经证实的说明')])
        self.graph = dict(case_id='X', run_id='R', nodes=[dict(id='MAT-1', type='evidence', locator='trace[c1].result'), dict(id='CLM-1', type='claim', evidence_status='SUPPORT')], edges=[], checks=[], paths=[])
    def codes(self, graph=None):
        return {f['code'] for f in audit(self.raw, graph or self.graph)['findings']}
    def test_nested_locator(self):
        self.assertEqual(locate(self.raw, 'trace[c1].result.items[0].coverage_excerpt'), ('/trace/0/result/items/0/coverage_excerpt', '原文条款'))
    def test_note_not_evidence(self):
        with self.assertRaises(ValueError): locate(self.raw, 'trace[s1].result')
    def test_no_negative_index(self):
        with self.assertRaises(ValueError): locate(self.raw, 'trace[c1].result.items[-1]')
    def test_ambiguous_event_rejected(self):
        self.raw['trace'].append(copy.deepcopy(self.raw['trace'][0]))
        with self.assertRaises(ValueError): audit(self.raw, self.graph)
    def test_dangling_reference(self):
        self.graph['edges'] = [dict(id='e', source='MAT-1', target='absent')]
        self.assertIn('DANGLING_REFERENCE', self.codes())
    def test_wrong_run(self):
        self.graph['run_id'] = 'other'
        self.assertIn('RUN_MISMATCH', self.codes())
    def test_unresolvable_locator(self):
        self.graph['nodes'][0]['locator'] = 'trace[c1].result.missing'
        self.assertIn('UNRESOLVED_LOCATOR', self.codes())
    def test_fabricated_excerpt(self):
        self.graph['nodes'].append(dict(id='RULE-1',type='rule',locator='trace[c1].result.items[0].coverage_excerpt',excerpt='编造条款'))
        self.assertIn('EXCERPT_NOT_VERIFIED', self.codes())
    def test_no_semantic_promotion(self):
        result = audit(self.raw, self.graph)
        self.assertEqual(result['claims'][0]['a_status'], 'SUPPORT')
        self.assertEqual(result['claims'][0]['b_status'], 'UNKNOWN')
        self.assertEqual(result['findings'], [])
        self.assertFalse(result['insurance_clause_inventory'][0]['represented_as_rule'])
    def test_actual_mutation(self):
        self.graph['checks'] = [dict(check_id='K', locator='trace[c1].result.flag', actual=True)]
        self.assertIn('CHECK_ACTUAL_NOT_IDENTICAL', self.codes())
    def test_fingerprint_changes(self):
        old = audit(self.raw, self.graph)['source_sha256']
        self.raw['trace'][0]['result']['flag'] = True
        self.assertNotEqual(old, audit(self.raw,self.graph)['source_sha256'])

if __name__ == '__main__': unittest.main()
