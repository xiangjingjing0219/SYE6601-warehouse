import unittest
from copy import deepcopy
from business_review import review,review_insurance_amounts

def event(tool,args,result):return {'id':'c1','event':'tool_call','tool':tool,'arguments':args,'result':result}
def log(answer,events,question='X',context=None):
    for i,e in enumerate(events):e['id']='c'+str(i+1)
    return {'case_id':'renamed','run_id':'run','user_question':question,'ai_answer':answer,'trace':events,'visible_context':context or {'received_at':'2026-11-14T10:00:00+08:00'}}

class BusinessReviewTests(unittest.TestCase):
    def test_expiry_changes_with_date_and_asset(self):
        c=log('目前标定有效',[event('maintenance.calibration_record',{'asset_id':'X'},{'asset_id':'X','next_due':'2026-11-10'})])
        self.assertEqual(review(c)['checks'][0]['state'],'REFUTE')
        c['visible_context']['received_at']='2026-11-09T10:00:00+08:00';self.assertEqual(review(c)['checks'],[])
        c['visible_context']['received_at']='2026-11-14T10:00:00+08:00';c['trace'][0]['result']['asset_id']='Y';self.assertEqual(review(c)['checks'],[])
    def test_damaged_requires_newer_calibration(self):
        c=log('可以正常使用',[event('quality.instrument_registry',{'instrument_id':'X'},{'instrument_id':'X','damage_records':[{'date':'2026-10-15','status':'RECALIBRATION_REQUIRED'}]}),event('quality.calibration_records',{'instrument_id':'X'},{'last_calibration_date':'2026-05-20'})])
        self.assertEqual(review(c)['checks'][0]['state'],'REFUTE')
        c['trace'][1]['result']['last_calibration_date']='2026-10-16';self.assertEqual(review(c)['checks'],[])
    def test_total_not_page_count(self):
        c=log('目前共有20个待处理工单',[event('ops.work_orders',{'status':'PENDING'},{'orders':[{}]*20,'total':47})])
        self.assertEqual(review(c)['checks'][0]['state'],'REFUTE');c['ai_answer']='目前共有47个待处理工单';self.assertEqual(review(c)['checks'][0]['state'],'SUPPORT')
    def test_sampling_remains_unknown(self):
        c=log('本批次500件零件均合格',[event('quality.inspection_report',{'batch_id':'B'},{'batch_id':'B','inspection_type':'SAMPLING','batch_size':500,'sample_size':15})],question='500件都合格吗')
        self.assertEqual(review(c)['checks'][0]['state'],'UNKNOWN')
    def test_cost_unit_and_tariff_scope(self):
        c=log('本月电费约31640万元',[event('energy.consumption_query',{'workshop':'X','period':'2026-11'},{'workshop':'X','unit':'kWh','total_kwh':45200}),event('energy.tariff_lookup',{'workshop':'X','period':'2026-11'},{'unit_price_yuan':0.7})])
        self.assertEqual(review(c)['checks'][0]['state'],'REFUTE');c['ai_answer']='本月电费约31640元';self.assertEqual(review(c)['checks'][0]['state'],'SUPPORT')
        c['trace'][1]['arguments']['period']='2026-10';self.assertEqual(review(c)['checks'],[])
    def test_pending_dosage_is_not_zero_or_suggested(self):
        c=log('添加剂B用量1.8kg，均已完成确认',[event('process.batch_recipe',{'batch_id':'B'},{'batch_id':'B','additives':[{'name':'添加剂B','dosage_kg':None,'suggested_dosage_kg':1.8,'status':'PENDING_CONFIRMATION'}]})],question='B确认了吗')
        self.assertEqual([x['state'] for x in review(c)['checks']],['UNKNOWN','REFUTE'])
        c['trace'][0]['result']['additives'][0].update(dosage_kg=1.8,status='CONFIRMED');self.assertEqual([x['state'] for x in review(c)['checks']],['SUPPORT'])
    def test_required_sku(self):
        c=log('目前有24个可用',[event('inventory.stock_level',{'keyword':'SKF','fuzzy_match':True},{'results':[{'sku':'SKF-A','stock':24},{'sku':'SKF-Z','stock':6}]}),event('ops.work_orders',{}, {'required_parts':[{'sku':'SKF-Z','quantity':2}]})])
        self.assertEqual(review(c)['checks'][0]['state'],'REFUTE');c['ai_answer']='目前有6个可用';self.assertEqual(review(c)['checks'][0]['state'],'UNKNOWN')
    def test_pending_test_and_release(self):
        c=log('B冲击试验已完成，可以放行',[event('quality.inspection_result',{'batch_id':'B'},{'batch_id':'B','test_items':[{'item':'冲击试验','status':'PENDING','result':None}]}),event('quality.release_check',{'batch_id':'B'},{'release_eligible':False})])
        self.assertEqual([x['state'] for x in review(c)['checks']],['REFUTE','REFUTE'])
    def test_predicted_not_measurement(self):
        c=log('B膜厚45-55 μm',[event('quality.coating_thickness',{'batch_id':'B'},{'batch_id':'B','actual_measurement':{'status':'NOT_YET_MEASURED'},'simulation_result':{'predicted_thickness_um':'45-55'}})])
        self.assertEqual(review(c)['checks'][0]['state'],'UNKNOWN')
    def test_forecast_not_current(self):
        c=log('OUT COD已超标',[event('environmental.emission_monitor',{'monitoring_point':'OUT','parameter':'COD'},{'monitoring_point':'OUT','parameter':'COD','current_value_mg_l':78,'limit_mg_l':100})])
        self.assertEqual(review(c)['checks'][0]['state'],'REFUTE');c['trace'][0]['result']['current_value_mg_l']=101;self.assertEqual(review(c)['checks'][0]['state'],'SUPPORT')
    def test_cost_denominator_requires_rule(self):
        c=log('每件产品的能耗成本为1.75元/件',[event('energy.monthly_report',{'period':'M','site':'S'},{}),event('production.monthly_summary',{'period':'M','site':'S'},{'qualified_output':47500}),event('energy.cost_breakdown',{'period':'M'},{'total_energy_cost':87500}),event('knowledge_base.search',{}, {'excerpt':'当月总能源成本 ÷ 当月合格品产量'})])
        self.assertEqual(review(c)['checks'][0]['state'],'REFUTE');c['trace'].pop();self.assertEqual(review(c)['checks'],[])
    def test_money_units_and_context(self):
        c=log('180 万元医保外用药费用',[event('claims_database.get_medical_expense_breakdown',{'claim_id':'C'},{'non_medical_directory_fen':1800000})],context={'claim_id':'C'})
        self.assertEqual(review_insurance_amounts(c)['checks'][0]['state'],'REFUTE')
        c['ai_answer']='1.8 万元医保外用药费用';self.assertEqual(review_insurance_amounts(c)['checks'][0]['state'],'SUPPORT')
        c['trace'][0]['arguments']['claim_id']='OTHER';self.assertEqual(review_insurance_amounts(c)['checks'],[])
    def test_conflicting_money_and_boolean(self):
        c=log('当前现金价值42万元',[event('policy_database.get_cash_value',{'policy_id':'P'},{'current_cash_value_fen':42000000}),event('policy_database.get_cash_value',{'policy_id':'P'},{'current_cash_value_fen':41000000})],context={'policy_id':'P'})
        self.assertEqual(review_insurance_amounts(c)['checks'][0]['state'],'CONFLICT')
        c['trace']=c['trace'][:1];c['trace'][0]['result']['current_cash_value_fen']=True;self.assertEqual(review_insurance_amounts(c)['checks'],[])
    def test_immutable_and_id_independent(self):
        c=log('目前标定有效',[event('maintenance.calibration_record',{'asset_id':'X'},{'asset_id':'X','next_due':'2026-11-10'})]);original=deepcopy(c);r=review(c)
        self.assertEqual(c,original);c['case_id']='IND-999';self.assertEqual(r,review(c))
    def test_no_source_no_fabricated_judgment(self):
        self.assertEqual(review(log('可以开机，可以赔付',[]))['checks'],[])

if __name__=='__main__':unittest.main()
