"""主分支引用会带字符范围；不能仅凭原句相同就接受错误文档或位置。"""
from pathlib import Path
import json, sys, unittest
from copy import deepcopy
D=Path(__file__).resolve().parent
sys.path.append(str(D/'unified_runtime'))
from proof_review import reference_matches
class MainLocator(unittest.TestCase):
    def test_wrong_doc_and_shifted_range(self):
        bundle=json.loads((D/'examples/main_handoff/正常工单/完整运行.json').read_text())
        ref=next(n['reference'] for n in bundle['graph']['nodes']
                 if n['type']=='evidence' and n['reference']['excerpt'].startswith('A ticket must'))
        receipt=next(r for r in bundle['tool_receipts'] if r['call_id']==ref['call_id'])
        row=next(r for r in receipt['records'] if r['record_id']==ref['record_id'])
        self.assertTrue(reference_matches(ref,row,receipt,bundle['task']))
        for field in ('source_id','locator'):
            changed=deepcopy(ref)
            if field=='source_id': changed[field]='OTHER'
            else: changed[field]['start']+=1
            self.assertFalse(reference_matches(changed,row,receipt,bundle['task']))
