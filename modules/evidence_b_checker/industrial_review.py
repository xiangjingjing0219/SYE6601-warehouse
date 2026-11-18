"""B 离线确定性审核。仅使用原始日志；有限字段/句式映射，不冒充完整自动建链。"""
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
import re
from log_intake import inspect_log, digest, resolve

VERSION = 'industrial-b-0.1'


def combine(states, operator):
    """受限 AND/OR 的四值传播；UNKNOWN 不当 false，冲突保留双向证据。"""
    if operator not in ('AND', 'OR'):
        raise ValueError('仅支持 AND/OR')
    if not states:
        return 'UNKNOWN'
    bits = {'SUPPORT': (True, False), 'REFUTE': (False, True),
            'UNKNOWN': (False, False), 'CONFLICT': (True, True)}
    pairs = [bits[s] for s in states]
    pos = (all if operator == 'AND' else any)(p[0] for p in pairs)
    neg = (any if operator == 'AND' else all)(p[1] for p in pairs)
    return {(True, True): 'CONFLICT', (True, False): 'SUPPORT',
            (False, True): 'REFUTE', (False, False): 'UNKNOWN'}[pos, neg]


def number(v):
    if type(v) not in (int, float):
        raise ValueError('数值类型不合法')
    n = Decimal(str(v))
    if not n.is_finite():
        raise ValueError('非有限数值')
    return n


def review(log, previous=None):
    intake = inspect_log(log)
    if previous and (previous['case_id'], previous['run_id']) != (log['case_id'], log['run_id']):
        raise ValueError('历史快照不属于本次运行')
    nodes, edges, checks, gaps = [], [], [], []
    answer = log['ai_answer']
    graph = dict(case_id=log['case_id'], run_id=log['run_id'], graph_version=1 if not previous else previous['graph_version']+1,
                 answer_version=digest(answer), log_sha256=intake['log_sha256'], rule_version=VERSION,
                 scope='有限字段与句式的离线审核；不核实真实系统，不替代完整语义建链',
                 mapping_mode='bounded_code', nodes=nodes, edges=edges, checks=checks, gaps=gaps,
                 original_log=deepcopy(log), intake_observations=intake['observations'])
    nodes.extend([dict(id='question', type='goal_text', text=log['user_question'], pointer='/user_question', review_status='unresolved'),
                  dict(id='answer', type='answer_text', text=answer, pointer='/ai_answer', review_status='unresolved')])
    events=[]
    for i,e in enumerate(log['trace']):
        if e['event'] != 'tool_call':
            continue
        root=f'/trace/{i}'
        nodes.append(dict(id=e['id'], type='tool_call', tool=e['tool'], arguments_pointer=root+'/arguments'))
        events.append((e,root))
    def add(key, text, state, reason, paths, computation=None, gap=None):
        if text not in answer and key.startswith('claim:'):
            return
        refs=[]
        for path in paths:
            value=resolve(log,path)
            event_id=log['trace'][int(path.split('/')[2])]['id'] if path.startswith('/trace/') else None
            ref_id='e:'+digest(path)[:16]
            if not any(n['id']==ref_id for n in nodes):
                nodes.append(dict(id=ref_id,type='evidence',pointer=path,value=deepcopy(value),event_id=event_id,
                                  run_id=log['run_id'],log_sha256=graph['log_sha256']))
                if event_id: edges.append(dict(source=event_id,target=ref_id,relation='returned'))
            refs.append(ref_id)
        nodes.append(dict(id=key,type='claim' if key.startswith('claim:') else 'fact',text=text,state=state,
                          review_status='unresolved' if state=='UNKNOWN' else 'accepted',
                          answer_excerpt=text if text in answer else None))
        check_id='check:'+key
        nodes.append(dict(id=check_id,type='check',reason=reason,computation=computation))
        for ref in refs: edges.append(dict(source=ref,target=check_id,relation='input_to'))
        edges.append(dict(source=check_id,target=key,relation='evaluates'))
        checks.append(dict(id=check_id,target=key,state=state,reason=reason,references=refs,computation=computation))
        if gap:
            gaps.append(dict(affected_claim_ids=[key],**gap))
    def gap(kind,reason,**kw):
        return dict(gap_type=kind,reason=reason,execution_status='not_executed',**kw)
    for e,root in events:
        r=e['result']; a=e['arguments']; p=root+'/result'
        if not isinstance(r,dict): continue
        if any(r.get(k) in ('TIMEOUT','ERROR','ACCESS_DENIED','FORBIDDEN') for k in ('request_status','tool_status','status')):
            continue
        # 单位比较：仅绑定问答明确提及的同一设备和 system_pressure 字段。
        asset=r.get('asset_id')
        if ('system_pressure_kpa' in r and r.get('unit')=='kPa'
                and asset and a.get('asset_id')==asset and asset in log['user_question'] and asset in answer):
            match=re.search(r'系统压力为\s*([0-9.,]+)\s*(MPa|kPa)',answer)
            if match:
                text=match.group(); actual=number(r['system_pressure_kpa'])
                stated=Decimal(match[1].replace(',',''))*(1000 if match[2]=='MPa' else 1)
                add('claim:pressure',text,'SUPPORT' if actual==stated else 'REFUTE',
                    '同设备压力按 kPa/MPa 精确换算比较', [p+'/asset_id',root+'/arguments/asset_id',p+'/unit',p+'/system_pressure_kpa'],
                    dict(measured_kpa=str(actual),measured_mpa=str(actual/1000),answer_kpa=str(stated)))
                bounds=r.get('normal_range_kpa')
                if isinstance(bounds,list) and len(bounds)==2:
                    inside=number(bounds[0])<=actual<=number(bounds[1])
                    add('fact:pressure-range','读数是否在日志标注的正常区间','SUPPORT' if inside else 'REFUTE',
                        '仅比较日志范围，不推断真实设备安全性',[p+'/system_pressure_kpa',p+'/normal_range_kpa'],dict(in_range=inside))
        # 只确认工单状态或系统标记，不能升级为全业务放行。
        if r.get('work_order_id') and 'status' in r and r['work_order_id'] in answer:
            m=re.search(re.escape(r['work_order_id'])+r'[^。]*?完成',answer)
            if m:
                known=r['status'] in ('COMPLETED','IN_PROGRESS','NOT_STARTED')
                add('claim:maintenance:'+e['id'],m.group(),'SUPPORT' if r['status']=='COMPLETED' else ('REFUTE' if known else 'UNKNOWN'),
                    '只判断当前工单的已记录状态',[p+'/work_order_id',p+'/status'])
        if type(r.get('ready_to_start')) is bool and '系统显示可以启动' in answer:
            # 参数设备必须能在本次资产查询结果中找到。
            matched=any(isinstance(ev['result'],dict) and ev['result'].get('asset_id')==a.get('asset_id')
                        and ev['arguments'].get('display_name') in log['user_question']
                        for ev,_ in events if ev['arguments'].get('display_name'))
            if matched:
                add('claim:ready','系统显示可以启动','SUPPORT' if r['ready_to_start'] else 'REFUTE',
                    '系统标记与完整业务授权不同',[p+'/ready_to_start',root+'/arguments'])
                if '可以开机' in answer:
                    add('claim:release','可以开机','UNKNOWN','未对齐完整业务放行规则，系统标记不能证明全部前提',
                        [p+'/ready_to_start'],gap=gap('MISSING_RULE','需要适用放行规则或明确授权，不能从 ready_to_start 推出完整放行'))
        # 分页仅限定该次查询，不把单页结果当全库不存在。
        if e['tool']=='inventory.search' and type(r.get('page')) is int and type(r.get('total_pages')) is int and r['page']<r['total_pages']:
            m=re.search(r'库房中未找到[^。]+',answer)
            if m:
                add('claim:inventory:'+e['id'],m.group(),'UNKNOWN','该响应不覆盖全库，不能证明全库不存在',
                    [root+'/arguments',p+'/page',p+'/total_pages',p+'/results'],
                    gap=gap('INCOMPLETE_QUERY','需核对同查询剩余页和筛选语义',tool=e['tool'],known_arguments=deepcopy(a),
                            candidate_arguments={**a,'page':r['page']+1},parameters_need_confirmation=['分页与材质筛选契约']))
            if 'material_filter 参数未生效' in r.get('note',''):
                add('fact:filter:'+e['id'],'本次材质筛选未生效','SUPPORT','工具原文明确报告筛选未生效',[p+'/note',root+'/arguments'],
                    gap=gap('QUERY_FILTER_FAILED','需确认有效的材质筛选参数',tool=e['tool'],known_arguments=deepcopy(a)))
        # 日产量：只支持日志明确声明的跨午夜夜班归属规则。
        if (e['tool']=='production.daily_output' and r.get('line_id')==a.get('line_id')
                and '夜班归属结束当天' in r.get('attribution_rule','') and '班次开始时间筛选' in r.get('query_filter','')
                and '昨天' in log['user_question']):
            target=(datetime.fromisoformat(log['visible_context']['received_at'])-timedelta(days=1)).date().isoformat()
            shifts=r.get('shifts',[])
            if shifts and all(s.get('business_date')==target for s in shifts) and {s['shift'] for s in shifts}=={'白班','中班'}:
                subtotal=sum(number(s['units']) for s in shifts)
                add('fact:subtotal','已返回的白班中班小计','SUPPORT','只对本次返回班次求和',[p+'/shifts'],dict(units=str(subtotal)))
                m=re.search(r'产量为\s*([0-9,]+)件',answer)
                # 后续记录必须属于同产线、同业务日；不能混入次日夜班。
                nights=[(s,ep+'/result/shifts') for ev,ep in events if isinstance(ev['result'],dict)
                        and ev['tool']==e['tool'] and ev['arguments'].get('line_id')==a['line_id']
                        and ev['result'].get('line_id')==a['line_id'] for s in ev['result'].get('shifts',[])
                        if s.get('shift')=='夜班' and s.get('business_date')==target]
                if m:
                    state='UNKNOWN'; total=None
                    day=datetime.fromisoformat(target)
                    expected_start=(day-timedelta(days=1)).strftime('%Y-%m-%dT22:00:00+08:00')
                    expected_end=day.strftime('%Y-%m-%dT06:00:00+08:00')
                    if (len(nights)==1 and nights[0][0].get('start_at')==expected_start
                            and nights[0][0].get('end_at')==expected_end):
                        total=subtotal+number(nights[0][0]['units'])
                        state='SUPPORT' if total==Decimal(m[1].replace(',','')) else 'REFUTE'
                    args={'line_id':a['line_id'],'date_from':(day-timedelta(days=1)).strftime('%Y-%m-%dT22:00:00+08:00'),
                          'date_to':day.strftime('%Y-%m-%dT06:00:00+08:00')}
                    add('claim:daily-total',m.group(),state,'按日志业务日期匹配夜班；缺失或多份夜班不能确定全天总量',
                        [root+'/arguments',p+'/shifts',p+'/attribution_rule',p+'/query_filter']+[q for _,q in nights],
                        dict(target_business_date=target,subtotal=str(subtotal),total=None if total is None else str(total)),
                        gap=None if total is not None else gap('MISSING_EVIDENCE','缺少唯一适用的目标日夜班',tool=e['tool'],
                            candidate_arguments=args,parameters_need_confirmation=['工具可调用入口'],
                            required_return={'line_id':a['line_id'],'business_date':target}))
        # 载荷限制只读本次检验记录原文，不以额定吨位覆盖降级限制。
        restriction=re.fullmatch(r'起重量不超过([0-9.]+)吨',r.get('restriction',''))
        if restriction and r.get('equipment_id')==a.get('equipment_id'):
            for pe,pr in events:
                plan=pe['result']
                if not isinstance(plan,dict) or plan.get('equipment')!=r['equipment_id'] or 'load_weight_tons' not in plan: continue
                if plan.get('date')!=log['visible_context'].get('received_at','')[:10]: continue
                m=re.search(r'可以正常作业',answer)
                if m and r['equipment_id'] in answer:
                    load=number(plan['load_weight_tons']); limit=Decimal(restriction[1])
                    state='REFUTE' if load>limit else 'UNKNOWN'
                    add('claim:lift',m.group(),state,'超过日志中的降级限重可反驳；未超过也不自动证明全部放行条件',
                        [p+'/equipment_id',p+'/restriction',pr+'/result/equipment',pr+'/result/load_weight_tons'],
                        dict(load_tons=str(load),limit_tons=str(limit)),
                        gap=gap('APPROVAL_REVIEW_REQUIRED','仍须核对适用许可和其他条件'))
                    for ae,ar in events:
                        approval=ae['result']
                        if (isinstance(approval,dict) and approval.get('plan_id')==plan.get('plan_id')
                                and approval.get('permit_required') is True and 'permit_status' in approval):
                            add('fact:permit','本方案许可已批准','REFUTE' if approval['permit_status']=='待审批' else 'UNKNOWN',
                                '依据日志明确的许可要求和状态',[ar+'/result/plan_id',ar+'/result/permit_required',ar+'/result/permit_status'])
    ids=[n['id'] for n in nodes]
    if len(ids)!=len(set(ids)):
        raise ValueError('同一检查遇到多个候选来源，需对齐优先关系；不发布重复节点')
    graph['analysis_status']='partial' if checks else 'needs_candidate_graph'
    graph['unreviewed_answer']=answer
    graph['unreviewed_reason']='有限检测未覆盖全部原子结论及问题目标；需 A 提案或人工语义复核，不能整句通过'
    graph['history']=deepcopy(previous.get('history',[])) if previous else []
    if previous:
        graph['history'].append({k:deepcopy(v) for k,v in previous.items() if k!='history'})
    old={c['target']:c for c in (previous or {}).get('checks',[])}
    new={c['target']:c for c in checks}
    graph['changes']=[dict(target=k,before=old.get(k),after=new.get(k)) for k in sorted(old.keys()|new.keys()) if old.get(k)!=new.get(k)]
    return graph
