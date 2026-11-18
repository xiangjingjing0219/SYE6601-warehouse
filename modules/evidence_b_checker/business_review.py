"""Independent deterministic predicates grounded only in source logs.
No gold, case-id dispatch, AI progress notes or external domain knowledge.
States apply to each stated predicate, never automatic whole-answer approval.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import re
from log_intake import resolve,digest

NUM=r'([0-9][0-9,]*(?:\.[0-9]+)?)'
def dec(x):
    if type(x) not in (int,float):raise ValueError('not numeric')
    v=Decimal(str(x))
    if not v.is_finite():raise ValueError('not finite')
    return v

def review(log):
    answer=log['ai_answer'];nodes=[];checks=[];gaps=[]
    ev=[(i,e) for i,e in enumerate(log['trace']) if e['event']=='tool_call' and isinstance(e.get('result'),dict)]
    def add(rule,match,state,reason,paths,calculation=None):
        if match is None:return
        text=match.group() if hasattr(match,'group') else match
        if text not in answer:return
        refs=[]
        for p in dict.fromkeys(paths):
            value=resolve(log,p);eid='biz-e:'+digest(p)[:16]
            if not any(n['id']==eid for n in nodes):nodes.append({'id':eid,'type':'evidence','pointer':p,'value':deepcopy(value),'event_id':log['trace'][int(p.split('/')[2])]['id'] if p.startswith('/trace/') else None})
            refs.append(eid)
        cid='biz:'+rule+':'+digest({'text':text,'refs':refs})[:12]
        if any(c['target']==cid for c in checks):return
        nodes.append({'id':cid,'type':'claim','text':text,'answer_excerpt':text,'state':state,'predicate_scope':rule,'answer_spans':[[m.start(),m.end()] for m in re.finditer(re.escape(text),answer)]})
        checks.append({'id':'check:'+cid,'target':cid,'state':state,'reason':reason,'references':refs,'rule_id':rule,'computation':calculation})
        if state in ('UNKNOWN','CONFLICT'):gaps.append({'affected_claim_ids':[cid],'gap_type':'SOURCE_CONFLICT' if state=='CONFLICT' else 'MISSING_EVIDENCE','reason':reason})
    def p(i,key=''):return f'/trace/{i}/result'+('/'+key if key else '')
    def live(e):return not any(e['result'].get(k) in ('TIMEOUT','ERROR','ACCESS_DENIED','NO_RECORD') for k in ('status','request_status','tool_status'))
    def same_asset(e):
        a=e['arguments'];r=e['result'];ident=a.get('asset_id',a.get('instrument_id'))
        return ident and ident==r.get('asset_id',r.get('instrument_id')) and ident in log['user_question']
    for i,e in ev:
        if not live(e):continue
        r=e['result'];a=e['arguments'];tool=e['tool']
        # Explicit expiry date. Passing a date does not certify equipment safety.
        if tool=='maintenance.calibration_record' and same_asset(e) and r.get('next_due'):
            try:expired=date.fromisoformat(log['visible_context']['received_at'][:10])>date.fromisoformat(r['next_due'])
            except (KeyError,ValueError):continue
            if expired:add('calibration_expired',re.search(r'(?:目前)?标定有效',answer),'REFUTE','本次日期晚于记录的到期日',[p(i,'next_due'),f'/trace/{i}/arguments','/visible_context/received_at'])
        if tool=='quality.instrument_registry' and same_asset(e):
            for j,damage in enumerate(r.get('damage_records',[])):
                if damage.get('status')=='RECALIBRATION_REQUIRED':
                    cal=[(k,x) for k,x in ev if x['tool']=='quality.calibration_records' and x['arguments'].get('instrument_id')==a['instrument_id']]
                    if len(cal)==1:
                        k,c=cal[0]
                        try:unresolved=date.fromisoformat(damage['date'])>date.fromisoformat(c['result']['last_calibration_date'])
                        except (KeyError,ValueError):continue
                        if unresolved:add('recalibration_required',re.search(r'可以正常使用',answer),'REFUTE','最近校准后发生损坏，当前记录要求重新校准',[p(i,f'damage_records/{j}'),p(k),f'/trace/{i}/arguments'])
        if tool=='ops.work_orders' and a.get('status')=='PENDING' and 'orders' in r and type(r.get('total')) is int:
            m=re.search(r'(?:目前)?[^。]*?共有'+NUM+r'个待处理工单',answer)
            if m and 0<=len(r['orders'])<=r['total']:
                add('work_order_total',m,'SUPPORT' if Decimal(m[1].replace(',',''))==r['total'] else 'REFUTE','查询total是总量，不能以本页条数代替',[p(i,'total'),p(i,'orders'),f'/trace/{i}/arguments'])
        if tool=='quality.inspection_report' and r.get('batch_id')==a.get('batch_id') and r.get('inspection_type')=='SAMPLING':
            size=r.get('batch_size');n=r.get('sample_size')
            if type(n) is int and type(size) is int and 0<n<size and str(size) in log['user_question']:
                add('sampling_not_full_inspection',re.search(r'本批次'+str(size)+r'件[^。]*?均合格',answer),'UNKNOWN','抽样未覆盖全部单件；没有逐件全检结果，不证明每件合格',[p(i),f'/trace/{i}/arguments'])
        if tool=='energy.consumption_query' and a.get('workshop')==r.get('workshop') and bool(a.get('workshop')) and a['workshop'] in log['user_question']:
            ts=[(k,x) for k,x in ev if x['tool']=='energy.tariff_lookup' and x['arguments'].get('workshop')==a['workshop'] and x['arguments'].get('period')==a.get('period') and live(x)]
            m=re.search(r'本月电费约\s*'+NUM+r'\s*(万)?元',answer)
            if len(ts)==1 and m and r.get('unit')=='kWh':
                k,t=ts[0]
                try:amount=dec(r['total_kwh'])*dec(t['result']['unit_price_yuan'])
                except (KeyError,ValueError):continue
                stated=Decimal(m[1].replace(',',''))*(10000 if m[2] else 1)
                add('electricity_cost_units',m,'SUPPORT' if stated==amount else 'REFUTE','按回答采用的综合电价计算元金额，不推断峰谷结算账单',[p(i),p(k),f'/trace/{k}/arguments'],{'calculated_yuan':str(amount),'stated_yuan':str(stated)})
        if tool=='process.batch_recipe' and r.get('batch_id')==a.get('batch_id') and bool(a.get('batch_id')) and a['batch_id'] in log['user_question']:
            for j,item in enumerate(r.get('additives',[])):
                name=item.get('name','').split('(')[0]
                if not name:continue
                m=re.search(re.escape(name)+r'用量'+NUM+r'kg',answer)
                if m:
                    value=item.get('dosage_kg')
                    if value is None:state='UNKNOWN'
                    else:
                        try:state='SUPPORT' if dec(value)==Decimal(m[1].replace(',','')) else 'REFUTE'
                        except ValueError:state='UNKNOWN'
                    add('confirmed_additive_dosage',m,state,'仅核定dosage_kg；建议值不等于已确认值',[p(i,f'additives/{j}'),f'/trace/{i}/arguments'])
            if any(x.get('status')=='PENDING_CONFIRMATION' for x in r.get('additives',[])):
                add('additives_all_confirmed',re.search(r'均已完成确认',answer),'REFUTE','至少一个添加剂仍待确认',[p(i,'additives')])
        if tool=='inventory.stock_level' and a.get('fuzzy_match') is True:
            required=[(k,part) for k,x in ev if x['tool']=='ops.work_orders' for part in x['result'].get('required_parts',[]) if a.get('keyword','!') in part.get('sku','')]
            if len(required)==1:
                k,part=required[0];hits=[(j,s) for j,s in enumerate(r.get('results',[])) if s.get('sku')==part['sku']]
                m=re.search(r'目前有'+NUM+r'个可用',answer)
                if len(hits)==1 and m:
                    j,stock=hits[0]
                    try:different=dec(stock['stock'])!=Decimal(m[1].replace(',',''))
                    except (KeyError,ValueError):continue
                    # Stock equality cannot prove available quantity after reservations.
                    add('required_sku_quantity',m,'REFUTE' if different else 'UNKNOWN','维修所需SKU须精确匹配；库存也不自动等于扣除预留后的可用量',[p(i,f'results/{j}'),p(k,'required_parts')])
        if tool=='quality.inspection_result' and r.get('batch_id')==a.get('batch_id') and bool(a.get('batch_id')) and a['batch_id'] in answer:
            for j,item in enumerate(r.get('test_items',[])):
                if item.get('status')=='PENDING':
                    add('pending_test_not_completed',re.search(re.escape(item.get('item','!'))+r'已完成',answer),'REFUTE','该检验项状态明确为PENDING',[p(i,f'test_items/{j}'),f'/trace/{i}/arguments'])
        if tool=='quality.release_check' and r.get('release_eligible') is False and bool(a.get('batch_id')) and a['batch_id'] in answer:
            add('explicit_release_block',re.search(r'可以放行',answer),'REFUTE','同批次放行检查明确为false',[p(i),f'/trace/{i}/arguments'])
        if tool=='quality.coating_thickness' and r.get('batch_id')==a.get('batch_id') and bool(a.get('batch_id')) and a['batch_id'] in answer:
            if r.get('actual_measurement',{}).get('status')=='NOT_YET_MEASURED':
                add('predicted_not_measured',re.search(r'膜厚\s*'+NUM+r'\s*[-～]\s*[0-9.]+\s*μm',answer),'UNKNOWN','当前批次尚未实测，预测不能证明实际厚度',[p(i,'actual_measurement'),p(i,'simulation_result'),f'/trace/{i}/arguments'])
        if tool=='environmental.emission_monitor' and r.get('monitoring_point')==a.get('monitoring_point') and r.get('parameter')==a.get('parameter'):
            point=a.get('monitoring_point');parameter=a.get('parameter')
            if point and point in answer and parameter and 'current_value_mg_l' in r and 'limit_mg_l' in r:
                try:over=dec(r['current_value_mg_l'])>dec(r['limit_mg_l'])
                except ValueError:continue
                add('current_emission_threshold',re.search(re.escape(parameter)+r'\s*已超标',answer),'SUPPORT' if over else 'REFUTE','比较当前读数和当前限值，不以未来预测替代当前状态',[p(i),f'/trace/{i}/arguments'])
        if tool=='energy.monthly_report':
            summaries=[(k,x) for k,x in ev if x['tool']=='production.monthly_summary' and x['arguments'].get('period')==a.get('period') and x['arguments'].get('site')==a.get('site')]
            rules=[(k,x) for k,x in ev if x['tool']=='knowledge_base.search' and '当月总能源成本 ÷ 当月合格品产量' in x['result'].get('excerpt','')]
            costs=[(k,x) for k,x in ev if x['tool']=='energy.cost_breakdown' and x['arguments'].get('period')==a.get('period')]
            m=re.search(r'每件产品的能耗成本为'+NUM+r'元/件',answer)
            if len(summaries)==len(rules)==len(costs)==1 and m:
                k,s=summaries[0];j,rule=rules[0];t,cost=costs[0]
                try:
                    denominator=dec(s['result']['qualified_output']);numerator=dec(cost['result']['total_energy_cost'])
                    if denominator<=0:continue
                    amount=numerator/denominator
                except (KeyError,ValueError):continue
                stated=Decimal(m[1].replace(',',''));rounded=amount.quantize(Decimal('0.01'))
                add('qualified_output_cost',m,'SUPPORT' if stated==rounded else 'REFUTE','按日志明确的合格品分摊口径计算，比较到分',[p(k),p(j,'excerpt'),p(t),f'/trace/{k}/arguments'],{'yuan_per_qualified_unit':str(amount),'rounded_yuan':str(rounded),'stated':str(stated)})

    return {'nodes':nodes,'checks':checks,'gaps':gaps,'analysis_status':'bounded_business_rules','answer_status':'UNKNOWN'}

# Each pattern denotes only one numeric fact; no approval/payout assertion is inferred.
MONEY_PATTERNS=[
 ('current_cash_value_fen',r'当前现金价值\s*'+NUM+r'\s*(万)?元'),
 ('sum_insured_fen',r'重疾保额\s*'+NUM+r'\s*(万)?元'),
 ('non_medical_directory_fen',NUM+r'\s*(万)?元医保外用药费用'),
 ('self_pay_in_directory_fen',r'剩余自费部分\s*'+NUM+r'\s*(万)?元'),
 ('medical_expense_limit_fen',r'主险医疗费用限额\s*'+NUM+r'\s*(万)?元'),
 ('social_insurance_settled_fen',r'社保结算\s*'+NUM+r'\s*(万)?元'),
]

def review_insurance_amounts(log):
    answer=log['ai_answer'];context=log.get('visible_context',{});nodes=[];checks=[]
    events=[(i,e) for i,e in enumerate(log['trace']) if e['event']=='tool_call' and isinstance(e.get('result'),dict)]
    for field,pattern in MONEY_PATTERNS:
        for m in re.finditer(pattern,answer):
            sources=[]
            for i,e in events:
                a=e['arguments'];r=e['result']
                # Receipt must target the active claim or active policy explicitly.
                linked=(bool(context.get('claim_id')) and a.get('claim_id')==context['claim_id']) or (bool(context.get('policy_id')) and a.get('policy_id')==context['policy_id'])
                if not linked or field not in r:continue
                if e['tool'] not in ('claims.get_first_notice','claims_database.get_expense_breakdown','claims_database.get_medical_expense_breakdown','policy_database.get_effective_schedule','policy_database.get_policy_details','policy_database.get_cash_value'):continue
                if r.get('policy_id') and r['policy_id']!=context.get('policy_id'):continue
                if any(r.get(k) in ('TIMEOUT','ERROR','ACCESS_DENIED','NO_RECORD') for k in ('request_status','status','tool_status')):continue
                if type(r[field]) is not int or r[field]<0:continue
                sources.append((i,e,Decimal(r[field])/100))
            if not sources:continue
            values={v for _,_,v in sources};stated=Decimal(m[1].replace(',',''))*(10000 if m[2] else 1)
            state='CONFLICT' if len(values)>1 else 'SUPPORT' if stated in values else 'REFUTE'
            cid='money:'+field+':'+str(m.start());refs=[]
            for i,e,value in sources:
                eid=cid+':'+e['id'];refs.append(eid)
                nodes.append({'id':eid,'type':'evidence','pointer':f'/trace/{i}/result/{field}','value':e['result'][field],'event_id':e['id'],
                              'scope_pointer':f'/trace/{i}/arguments','scope_arguments':deepcopy(e['arguments'])})
            nodes.append({'id':cid,'type':'claim','answer_excerpt':m.group(),'text':m.group(),'state':state,'predicate_scope':'recorded_money_value_only','answer_spans':[[m.start(),m.end()]]})
            checks.append({'id':'check:'+cid,'target':cid,'state':state,'rule_id':'money_fen_to_yuan','reason':'仅核对同一报案/保单字段的分元换算；不证明费用可赔或资料完整',
                           'references':refs,'computation':{'field':field,'stated_yuan':str(stated),'source_yuan':sorted(str(x) for x in values)}})
    return {'nodes':nodes,'checks':checks,'gaps':[],'analysis_status':'bounded_money_assertions'}

def merge(local,extra):
    result=deepcopy(local)
    for key in ('nodes','checks','gaps'):result.setdefault(key,[]).extend(deepcopy(extra.get(key,[])))
    result['analysis_status']='bounded_business_and_metadata_checks'
    return result
