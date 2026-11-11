# 证据链 B：DYN-01 原生联调
版本依据：团队 PR #5（8d544b8），尚未合入 main。原 Checker 与 PR #4 成绩单路径保留；本次入口使用 PR #5 自带的成绩单。PR5 工具数据是合成扩展；团队模型调用记录只做离线回放，不使用密钥，不发生新的模型费用。

打开“PR5工单联调.ipynb”可一键演示。团队代码对接：将本次新增的 pr5_reviewer.py、run_pr5_checker.py、verify_pr5_checker.py 保存在 modules/evidence_b_checker，仓库根目录须有 PR5 的 dynamic_evidence 包和 docs/dynamic-evidence/records/dyn01-model-replay.json。然后运行 python modules/evidence_b_checker/run_pr5_checker.py，或运行 python modules/evidence_b_checker/verify_pr5_checker.py。原 PR5 的主程序仍然默认使用原 reviewer；用 run_pr5_checker.py 才会注入 B 的审核。团队运行包附带对应 PR5 源码，解压后即可运行。

哪些是组员提供的：提案、原文抽取、语义审核回放、规则优先级、调度和最终卡由 PR5 提供。B 新增的是审核入口与工单回执检查：记录客户/事故/来源、有效期、版本、提交时间、重复编号等问题，让失效记录不被当成“查完且没有工单”。原始回执不改；有问题时只处理交给判断程序的工作副本，保留对应 call_id 和可读原因。
版本仅按 PR5 合成约定（版本非空、故障时生效，若任务给了期望版本则匹配）；不声称存在正式版本目录。截止时刻和维护规则是该原型口径，不覆盖证据链 A 文件里的规则。无新模型调用，不等于完成团队正式业务验收。

examples/pr5/ticket_receipts.json 是工具原始工单样例；replayed_bundle.json 保存提案、各版图、审核日志和最终答复；scorecard.md 是可读成绩单；regression.json 是逐例检查结果。63 个团队预期和 7 个新增边界都是开发验证，不是独立测试集准确率。
