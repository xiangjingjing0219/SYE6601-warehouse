# 证据链 B：保险与工业日志接收

本轮接收 `case_id/run_id/user_question/visible_context/trace/ai_answer` 格式。逐条保存原始日志、工具结果位置、阶段性说明位置和内容指纹。工具报错、空数组及 null 单独列出，保留原始值。

这一步只完成日志接收及可追溯检查。`format_valid=true` 不代表答案正确；`answer_verdict=null`、`semantic_review_status=not_performed` 表示尚未执行业务语义审核。没有观察项也不表示证据充分。空列表可能是完整空结果，也可能是缺测，必须结合具体工具协议判断。指纹只能检测本地内容变化，不能证明日志由真实系统产生。

## 运行

从仓库根目录运行，Python 3.10+，无需模型 API：

```sh
python modules/evidence_b_checker/log_intake.py modules/evidence_b_checker/examples/logs/industrial_logs.json --output modules/evidence_b_checker/examples/logs/industrial_logs_intake.json
python -m unittest discover -s modules/evidence_b_checker -p 'test_*.py'
```

每个工具事件由 `event_id` 与 `/trace/序号/result` 定位，连同 `case_id/run_id/log_sha256` 确定具体运行内容。`verify_reference` 核对整条日志是否改变、定位值是否一致。阶段性说明独立保存，不视为工具取数结果。重复事件、同批重复运行、缺少答案及未对齐事件类型明确报错。

这些定位字段是 B 侧的本地接收约定，尚不是团队已签认的新建链协议。旧 GraphProposal 接收入口继续保留，不强行给工业/保险日志补 customer_id、incident_id 或旧补偿规则。

## 本轮验证

- 原有 49 项回归与新增 8 项接收测试，共 57 项通过。
- `insurance_industry_samples.json`：4 条结构样例。
- `industrial_logs.json`：2 条工业样例，聊天已认可其结构。
- `insurance_fire_sample.json`：1 条保险火灾样例，未标为已验收。
- 三份分别接收，合计 7 条输入；同名案例在不同版本中不能不加区分地合并。
- 最新团队 main `08edfd5eb3ab70212f15333880e4f75be80966ca` 联调：正常工单最终 eligible；无权限工单最终 undetermined / ACCESS_DENIED。两次各导出三阶段快照，位于 `examples/main_08edfd5/`。运行使用团队本地模拟器，未调用在线模型。

上述都是开发和接口验证，不是新场景准确率，也不是全部 60 条数据验收。

## 新场景下一步需要的接口

| 对接方 | 最少需要什么 | 用途 |
| --- | --- | --- |
| 证据链 A | 同一条已认可日志对应的候选图、待审核命题、适用规则/条件、引用与版本字段，以及可执行入口或正式调用约定 | B 才能核对关系、必查覆盖并发布业务四态 |
| 测试 A/B | 最终日志集与单独保存的逐例说明/预期；明确样例版本 | 独立验收，避免把错误标签作为审核输入 |
| Loop A/B | 新行业日志中缺口如何传入补查、补查工具入口、回执和轮次关联方式 | 对实际补回材料重新审核；旧故障补偿工具不能冒充保险/工业工具 |

优先与 A 对齐一条工业或保险案例，不需要先等全部数据。当前日志包含自由文本规则，不能自行规定安全温度、赔付资格或把 `false` 统一解释成已排除风险。旧规则只继续用于旧场景。
