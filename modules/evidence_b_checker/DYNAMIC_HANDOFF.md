# 证据链 B｜按 02 修正说明制作的独立审核练习

原来的 checker_v2.py 和 checker_api.py 保留。运行 python run_dynamic_review.py 看四轮结果；python -m unittest discover -v 运行开发自测。Colab 可单独打开“动态审核演示.ipynb”，从上到下运行，CPU 即可。

| 02 修正说明要求 | 本版对应位置 | 边界 |
|---|---|---|
| 保留原检查，引用要能定位 | graph_review.py 调用原 check_payload，核对客户、事故、合同、回执号、条款位置与整句 | clauses、tickets 等是 B 侧样例字段，不要求 A 按此重做 |
| 候选审核与四态分开 | checks 中的 review_status 表示是否接纳关系；nodes 中的 state 表示条件是否已有证据 | 合同原句存在本身，不代表它能证明 A 的解释 |
| 固定输入可重放，增量更新 | examples/dynamic_trace.json 保存四轮输入、示例复核、图快照与变化 | 顺序调用、传入上一版。未实现多用户存储或团队通用图引擎 |
| 模型或人工复核 | semantic_review.py 提供可选的兼容接口、原始输入输出和缓存；默认没有审核记录就 unresolved | 此交付未实际调用模型。fixture_human 是预置演示数据，不是真人签字，也不是模型验证 |
| DYN-01、待审核与拒绝样例 | run_dynamic_review.py、examples/dynamic_rejected.json、test_dynamic_review.py | 只支持本例“资格依赖工单时限”。其他关系未决；未实现通用覆盖、例外和任意依赖图传播 |
| 关键缺口阻断、非缺证时允许否定 | 缺合同或工单时 undetermined；另有有效版本复核且完整查询明确迟交时本例 ineligible | 合成条款自行明确了起算点与端点，不宣称这是 A 的真实合同；没有演示范围覆盖确认时不输出整体资格建议 |

**输入交接**：review_graph(task, previous_graph, proposal, tool_receipts, *, review_log=None)。前三个 JSON 输入示例及完整回执见 dynamic_trace.json。首次 previous_graph 传 None，之后传上一轮 snapshot。proposal 只提交 base_version 与 upserts，B 自行分配 graph_version。review_log 由 B 侧注入，禁止从 A 提案直接复制。语义判断只对当次任务、候选及原始材料指纹有效。模型适配器由调用方发起；异常需转人工，不能记为成功。示例的“覆盖确认”仅用于限定合成范围，团队验收时须换成正式必查结构。

**给 A 的最小请求**：请发 DYN-01 的一条实际候选依赖 JSON，配套它引用的合同原句、条款位置、工具回执编号，以及补合同前后的两个提案。无需改 rules.json，也无需制作整套数据库。B 用它核对编号、引用字段及更新方式；Loop B 的真实工单返回另行对齐。证据链 B 不制定业务优先级、不选补查工具、不重试、不评分。
