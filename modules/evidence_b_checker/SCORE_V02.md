# B 的新版成绩单联调（DYN-01 合成案例）
在本目录运行 python run_score_bridge_v02.py。需要同级的 confidence_a_mvp（团队 PR #4，dc811cb），下载包已包含这份评分程序。无需安装插件或调用模型。
现在未核验工单版本也能生成卡：工单上的时间比较可支持“按时”，但工单义务状态仍为 UNKNOWN，不能建议补偿。具体原因码 TICKET_VERSION_UNVERIFIED 可以在第四张卡的义务明细中查看。原始审核快照保留单独的 time_comparison 和 version_review。

只有 B 独立取得了可追溯的有效版本确认时，才可通过 review_log 提交审核结果；其键绑定当前任务和整份回执。basis_locator 指向复核依据，是 B 侧审核日志字段，不是要求 Loop B 新增的业务字段。调用者负责保管可信审核记录，不能把 A 的说明直接视为 B 的确认。测试中有单独标记的合成复核，用于确认支持与反驳路径；默认第四张卡不带这种确认。旧版学习笔记及0.1演示保留为历史材料，不代表本次新版结果。实际 A 提案、工具工单回执及真实模型判读未接入。

运行 python -m unittest discover -q 做开发回归。examples/score_v02 保存 B 的输入及评分组程序实际生成的成绩单；examples/dynamic_trace.json 保存四轮审核历史。没有查询工具动作、人工升级或真实客户资料。
