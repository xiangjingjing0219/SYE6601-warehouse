# 工业候选图 B 侧对接（2026-11-16）

## 本次结果

团队仓库 origin/main 从 08edfd5 更新至 4a4695d，新增工业60条日志及案例说明，未新增候选图生成代码。仓库日志与收到的上传日志逐字节一致，SHA256 为 0939d2b307c866b064443890c5b624c2029a274e57cda29608becba4b9fa3746。

A 提供的 IND-001 两个文件用于接口理解；程序以原始 JSON 日志核对提案。案例说明标签未进入审核程序。

新增 industrial_proposal_review.py 支持 A 当前顶层 nodes/edges 格式，旧补偿业务 proposal_intake.py 保留，避免把工业 customer_id:null 错判成客户缺失。

- 核对 case/run、用户问题、节点/关系编号、关系端点。
- 把 trace[c2].result.sensors[0] 解析为 /trace/1/result/sensors/0，保留事件、参数、原值及日志摘要；不使用 eval。
- 核对来源命名空间和逐字摘录。引用成立不等于主张成立。
- A 自报的 SUPPORT 和 completed 不直接作为 B 审核结果。
- 支持单独的 B 审核记录，绑定整份日志和提案 SHA256，输入变化拒绝旧审核记录。保留历史报告。
- 不自动传播未确认的关系、不生成虚构业务规则、不执行真实补查、不计算评分。

## 运行（仓库根目录，Python 3）

只检查结构和引用，不加载任何语义判定：

```bash
python modules/evidence_b_checker/industrial_proposal_review.py modules/evidence_b_checker/examples/industrial_proposal/proposal.json modules/evidence_b_checker/examples/industrial_proposal/log.json --output /tmp/b_ind001_intake.json
```

重现这次助手离线逐项复核记录：

```bash
python modules/evidence_b_checker/industrial_proposal_review.py modules/evidence_b_checker/examples/industrial_proposal/proposal.json modules/evidence_b_checker/examples/industrial_proposal/log.json --decisions modules/evidence_b_checker/examples/industrial_proposal/b_review.json --output /tmp/b_ind001_review.json
```

`--previous` 可输入上一份报告。日志或提案有变化时须移除旧 decisions，先输出待审结果，再独立复核更新。两种运行方式都不需要密钥。

## IND-001 结果与性质

5 个证据引用均能定位；6 个 claim 中，CLM-001 保留 UNKNOWN/unresolved（其文字更像待回答目标，不是可判真假的原子结论）。CLM-002、003、005、006 经本次助手离线复核为 SUPPORT；CLM-004 当前实际积灰状态为 UNKNOWN。“可能积灰”表达本身不能因此判错。

**这些语义结果是明确标记 assistant_offline_review 的逐项复核记录，不是调用了某个 API 的结果，不是自动审核准确率，也不是独立人工金标准。** 不传 decisions 时，所有主张均保持 UNKNOWN/unresolved；该接收器不会猜测自然语言含义。原5类确定性工业检查仍由 industrial_review.py 执行。

19 条关系、4 个候选缺口仍待完整语义核对。此报告不宣称整图审核通过。

## 给 A 的具体反馈

1. 区分目标与主张：CLM-001 是“原因及可确认程度”，建议作为 goal，补充与答案原文对应的原子主张；保留原文及断言强度。
2. CLM-004 的“可能”与实际故障是否成立分开：现有差压支持排查线索，无法确认积灰事实。E-011 不应被程序作为充分确诊路径。
3. GAP-002 和 GAP-003 当前挂在 CLM-005（手册列出哪些原因）上。手册列举已可引用；参数标准和喷嘴检查缺失主要影响当前设备的具体故障判断，应关联相应目标/诊断主张。
4. GAP-004 是可选审慎核查；日志没有表明温度传感器失准，不能凭缺校准记录就否定读数。c3 的 last_calibrated 也不能自动当成 c2 温度传感器校准记录。
5. depends_on 的文字拆解由父指向子，而 JSON 为子指向父；derived_from 方向也需要明确。请约定各关系方向及 AND/OR 的明确字段，B 不猜测。
6. 继续保留 run_id、事件ID、字段路径。现有 trace[event].result 路径已兼容；created_by/created_at/call_id 缺失会列出，但不虚构值。手册 document_id 可保留原样，不能从 R4 字样自行推出正式版本和生效日期。
7. 下一步交可重复运行的生成程序、模型调用配置和提示词；不是要求重新手写60张图。用本例先接通，再处理其他日志。

## B 下一步与边界

现在已能接收这一版候选图并输出独立审核报告。全面自动语义审核仍需明确命题原文、字段映射与关系语义；若采用模型复核，需实现对应的工业语义适配器、配置有效接口并实际运行。旧 semantic_review.py 只针对旧合同申报时限，不冒充工业通用审核器。

实际补证依赖 Loop 的工具契约，评分权重属于评分模块。未提供这些内容时不代填。B 与 A 应先确认上面关系/缺口问题，再联调生成→审核；之后开展全量评估。

## 验证

仓库现有及新增测试合计84项通过，包括摘要过期、跨run、缺失事件、伪造摘录、来源不匹配、重复节点、悬空关系、工具失败、历史结果隔离。它们验证程序行为，不代表60条答案业务准确率。
