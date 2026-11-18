import unittest
from copy import deepcopy
from insurance_review import review

def case(result,tool='policy_database.get_policy_details'):
    return {'trace':[{'id':'c1','event':'tool_call','tool':tool,'arguments':{},'result':result}]}

class InsuranceReviewTests(unittest.TestCase):
    def test_waiting_flag_strict_types(self):
        for value,expected in [(True,'SUPPORT'),(False,'REFUTE'),(1,'UNKNOWN'),('true','UNKNOWN'),(None,'UNKNOWN')]:
            with self.subTest(value=value):
                self.assertEqual(review(case({'waiting_period_expired':value}))['checks'][0]['state'],expected)
    def test_no_fabricated_obligations(self):
        self.assertEqual(review(case({}))['checks'],[])
    def test_partial_and_invalid_pagination(self):
        for total,count,rows,state,reason in [(5,2,[{},{}],'UNKNOWN','PARTIAL_PAGE'),(2,2,[{},{}],'SUPPORT','PAGINATION_COMPLETE'),(2,2,[{}],'UNKNOWN','INVALID_PAGINATION'),(True,1,[{}],'UNKNOWN','INVALID_PAGINATION')]:
            c=review(case({'total_locations':total,'returned_count':count,'records':rows}))['checks'][0]
            self.assertEqual((c['state'],c['reason_codes'][0]),(state,reason))
    def test_unavailable_is_not_refusal(self):
        for status in ['TIMEOUT','NOT_FOUND','PRELIMINARY','PENDING']:
            self.assertEqual(review(case({'request_status':status}))['checks'][0]['state'],'UNKNOWN')
    def test_same_policy_identity(self):
        c=case({'insured_id_number':'XYZ'}); c['trace'][0]['arguments']={'policy_id':'P'}
        c['trace'].insert(0,{'id':'notice','event':'tool_call','tool':'claims.get_first_notice','arguments':{},'result':{'policy_id':'P','insured_id_number':'ABC'}})
        self.assertEqual(review(c)['checks'][0]['state'],'REFUTE')
        c['trace'][1]['result']['insured_id_number']='ABC'
        self.assertEqual(review(c)['checks'][0]['state'],'SUPPORT')
        c['trace'][0]['result']['insured_id_number']='A***';c['trace'][1]['result']['insured_id_number']='A***'
        self.assertEqual(review(c)['checks'][0]['state'],'UNKNOWN')
        c['trace'][1]['arguments']['policy_id']='OTHER'
        self.assertEqual(review(c)['checks'],[])
    def test_input_immutable_and_not_answer_approval(self):
        c=case({'waiting_period_expired':True}); original=deepcopy(c)
        self.assertEqual(review(c)['answer_status'],'UNKNOWN');self.assertEqual(c,original)
    def test_no_case_or_answer_label_dependency(self):
        c=case({'waiting_period_expired':False});a=review(c)
        c.update(case_id='renamed',ai_answer='can pay',design_label='correct')
        self.assertEqual(review(c),a)
    def test_citations_resolve_to_original_value(self):
        c=case({'waiting_period_expired':False})
        for check in review(c)['checks']:
            for ref in check['citations']:
                value=c
                for part in ref['pointer'].split('/')[1:]:value=value[int(part)] if isinstance(value,list) else value[part]
                self.assertEqual(value,ref['value'])

if __name__=='__main__':unittest.main()
