import unittest
from insurance_design_catalog import build_catalog
class CatalogTests(unittest.TestCase):
    def test_prefix_is_explicitly_recorded(self):
        c=build_catalog('| [bad](local)INS-A18 | d | 正确 | t | b |',[{'case_id':'INS-A18'}])
        self.assertEqual(c['cases'][0]['case_id'],'INS-A18');self.assertEqual(len(c['format_notes']),1)
        self.assertTrue(c['not_four_state_gold_labels'])
    def test_missing_case_fails(self):
        with self.assertRaises(ValueError):build_catalog('',[{'case_id':'INS-A03'}])
    def test_duplicate_case_fails(self):
        row='| INS-A03 | d | 正确 | t | b |\n'
        with self.assertRaises(ValueError):build_catalog(row*2,[{'case_id':'INS-A03'}])
