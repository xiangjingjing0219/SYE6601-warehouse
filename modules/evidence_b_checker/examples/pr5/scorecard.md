# 证据成绩单

Is this outage eligible for compensation?

建议补偿

已建模范围内证据充分

task_id=DYN-01 · run_id=c4dd6e52-9d1d-42e1-9b69-db1e0c5d6eba · graph_version=3 · answer_version=1

模式 replay · 终止 COMPLETED

仅覆盖合成故障补偿中的时长、工单期限、已配置维护例外及专属合同覆盖。未知规则仍需人工核实。

## 分项
- 基础必查 4/4
- 已映射主张 1/1
- 条件已判定 3/3
- 关系审核通过 3/3

## 优先复核

## 主张与条件
- claim-eligibility · SUPPORT · Is this outage eligible for compensation?
- condition:duration_min · SUPPORT · 90
- condition:ticket_deadline_hours · SUPPORT · 24
- condition:no-maintenance-exclusion · SUPPORT · 

## 来源
- C-DEADLINE · synthetic:C-DEADLINE · A ticket must be submitted within 24 hours after the incident.
- C-THRESHOLD · synthetic:C-THRESHOLD · The incident must last at least 90 minutes.
- I-DURATION · synthetic:I-DURATION · Verified outage duration.
- P-THRESHOLD · synthetic:P-THRESHOLD · Compensation requires an outage lasting at least 60 minutes.
- T-01 · synthetic:T-01 · Verified ticket submission.

## 结构变化
- v1 · added · claim-eligibility
- v1 · added · condition:duration_min
- v1 · added · condition:no-maintenance-exclusion
- v1 · added · depends:condition:duration_min
- v1 · added · depends:maintenance
- v1 · added · depends:required:CRM_CONTRACT_DB
- v1 · added · depends:required:INCIDENT_DB
- v1 · added · depends:required:MAINTENANCE_CALENDAR
- v1 · added · depends:required:POLICY_DB
- v1 · added · evidence:I-DURATION
- v1 · added · evidence:P-THRESHOLD
- v1 · added · fact-source:I-DURATION
- v1 · added · fact:I-DURATION
- v1 · added · logic:condition:duration_min:P-THRESHOLD
- v1 · added · origin:rule:P-THRESHOLD:duration_min
- v1 · added · proof:condition:duration_min:I-DURATION
- v1 · added · required-source:INCIDENT_DB:I-DURATION
- v1 · added · required-source:POLICY_DB:P-THRESHOLD
- v1 · added · required:CRM_CONTRACT_DB
- v1 · added · required:INCIDENT_DB
- v1 · added · required:MAINTENANCE_CALENDAR
- v1 · added · required:POLICY_DB
- v1 · added · rule:P-THRESHOLD:duration_min
- v2 · revised · condition:duration_min
- v2 · added · condition:ticket_deadline_hours
- v2 · added · depends:condition:ticket_deadline_hours
- v2 · added · evidence:C-DEADLINE
- v2 · added · evidence:C-THRESHOLD
- v2 · added · logic:condition:duration_min:C-THRESHOLD
- v2 · invalidated · logic:condition:duration_min:P-THRESHOLD
- v2 · added · logic:condition:ticket_deadline_hours:C-DEADLINE
- v2 · added · origin:rule:C-DEADLINE:ticket_deadline_hours
- v2 · added · origin:rule:C-THRESHOLD:duration_min
- v2 · added · override:C-THRESHOLD:rule:P-THRESHOLD:duration_min
- v2 · added · required-source:CRM_CONTRACT_DB:C-DEADLINE
- v2 · added · required-source:CRM_CONTRACT_DB:C-THRESHOLD
- v2 · revised · required:CRM_CONTRACT_DB
- v2 · added · rule:C-DEADLINE:ticket_deadline_hours
- v2 · added · rule:C-THRESHOLD:duration_min
- v2 · revised · rule:P-THRESHOLD:duration_min
- v3 · revised · claim-eligibility
- v3 · revised · condition:ticket_deadline_hours
- v3 · added · evidence:T-01
- v3 · added · fact-source:T-01
- v3 · added · fact:T-01
- v3 · added · proof:condition:ticket_deadline_hours:T-01
