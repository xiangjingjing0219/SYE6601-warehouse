import unittest
from copy import deepcopy
from log_intake import inspect_log, inspect_dataset, verify_reference


class LogIntakeTests(unittest.TestCase):
    def setUp(self):
        self.log = dict(case_id='CASE', run_id='RUN', user_question='是否到账？',
                        visible_context={}, ai_answer='已到账', trace=[
            dict(id='c1', event='tool_call', type='external_api', tool='bank.query',
                 arguments={}, result={'status': 'TIMEOUT', 'rows': [], 'receipt': None}),
            dict(id='s1', event='assistant_progress_note', text='我认为已到账')])

    def test_failed_tool_and_note_are_not_success_evidence(self):
        report = inspect_log(self.log)
        self.assertEqual(len(report['evidence_index']), 1)
        self.assertEqual(len(report['progress_notes']), 1)
        self.assertEqual({x['code'] for x in report['observations']},
                         {'REPORTED_TOOL_OR_DATA_ERROR', 'EMPTY_ARRAY', 'NULL_VALUE'})
        self.assertIsNone(report['answer_verdict'])
        self.assertEqual(report['semantic_review_status'], 'not_performed')

    def test_input_and_snapshot_are_independent(self):
        before = deepcopy(self.log)
        report = inspect_log(self.log)
        self.assertEqual(before, self.log)
        self.log['ai_answer'] = 'changed'
        self.assertTrue(verify_reference(report, '/ai_answer', '已到账'))

    def test_modified_trace_invalidates_reference(self):
        report = inspect_log(self.log)
        report['raw_log']['trace'][0]['result']['status'] = 'SUCCESS'
        self.assertFalse(verify_reference(report, '/ai_answer', '已到账'))

    def test_escaped_pointer_and_type_strictness(self):
        self.log['trace'][0]['result'] = {'a/b~c': False}
        report = inspect_log(self.log)
        self.assertTrue(verify_reference(report, '/trace/0/result/a~1b~0c', False))
        self.assertFalse(verify_reference(report, '/trace/0/result/a~1b~0c', 0))
        self.assertFalse(verify_reference(report, '/trace/8', None))
        self.assertFalse(verify_reference(report, '/trace/-1/text', '我认为已到账'))

    def test_duplicate_event_rejected(self):
        self.log['trace'][1]['id'] = 'c1'
        with self.assertRaises(ValueError):
            inspect_log(self.log)

    def test_duplicate_run_rejected_but_new_run_allowed(self):
        with self.assertRaises(ValueError):
            inspect_dataset([self.log, self.log])
        second = deepcopy(self.log)
        second['run_id'] = 'RUN2'
        self.assertEqual(len(inspect_dataset([self.log, second])), 2)

    def test_unsupported_events_and_missing_answer_rejected(self):
        for field, value in [('event', 'inferred_tool_call'), ('arguments', None)]:
            modified = deepcopy(self.log)
            modified['trace'][0][field] = value
            with self.assertRaises(ValueError):
                inspect_log(modified)
        self.log.pop('ai_answer')
        with self.assertRaises(ValueError):
            inspect_log(self.log)

    def test_empty_trace_is_not_positive_verdict(self):
        self.log['trace'] = []
        report = inspect_log(self.log)
        self.assertEqual(report['evidence_index'], [])
        self.assertIsNone(report['answer_verdict'])

    def test_partial_pages_are_observations_not_answer_verdicts(self):
        for result in [{'page': 1, 'total_pages': 8}, {'has_more': True},
                       {'pagination_complete': False}]:
            self.log['trace'][0]['result'] = result
            report = inspect_log(self.log)
            self.assertEqual(report['observations'][0]['code'], 'PARTIAL_PAGE_RESPONSE')
            self.assertIsNone(report['answer_verdict'])
        self.log['trace'][0]['result'] = {'page': 8, 'total_pages': 8}
        self.assertEqual(inspect_log(self.log)['observations'], [])

    def test_partial_data_does_not_confuse_false_with_missing(self):
        self.log['trace'][0]['result'] = {'data_completeness': 'PARTIAL', 'release_eligible': False}
        report = inspect_log(self.log)
        self.assertEqual([o['code'] for o in report['observations']], ['REPORTED_PARTIAL_DATA'])


if __name__ == '__main__':
    unittest.main()
