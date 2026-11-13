"""用团队统一模拟工具运行证据链 B；只使用本地合成材料。"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "unified_runtime"))
from dynamic_evidence.cases import make_case
from dynamic_evidence.controller import Harness
from dynamic_evidence.mock_model import FixtureModel
from pr5_reviewer import review

# 名称仅用于选取演示数据，不参与运行中的判断。
CASES = [
    ("DYN-01", 1), ("NO-TICKET", 2), ("REFERRAL", 3), ("AMOUNT", 4),
    ("LATE-TICKET", 5), ("BOUNDARY", 6), ("MISSING-TICKET", 7),
    ("MAINTENANCE", 8), ("CONFLICT", 9), ("EMPTY-CONTRACT", 10),
    ("TICKET-403", 1), ("CONTRACT-403", 1), ("OLD-CONTRACT", 1),
    ("REFERRAL", 11),
]


def checked_provider(provider):
    """只有能从本次记录定位到原句的材料，才进入后续判断。"""
    def query(source, task, page=None):
        raw = provider(source, task, page)
        if raw["tool_status"] != "SUCCESS":
            return raw
        reasons = []
        for row in raw["records"]:
            try:
                excerpt = provider.resolve_reference(row["source_id"], row["record_id"], row["locator"])
                if excerpt != row["excerpt"] or excerpt != row["statement"]:
                    reasons.append("原文与引用不一致")
                if row["context"].get("available") is False or not row["context"].get("text"):
                    reasons.append("缺少核实条款所需的上下文")
            except (KeyError, ValueError, TypeError):
                reasons.append("无法定位原文")
        if reasons:
            # 保留原回执，不能把不可用的一页伪装成“完整空结果”。
            return dict(raw, status="ERROR", tool_status="ERROR", records=[], pagination_complete=False,
                        next_page_token=None, error_code="CHECKER_SOURCE_UNVERIFIED",
                        checker_reasons=sorted(set(reasons)), original_receipt=raw)
        return raw
    return query


def unified_review(task, previous, proposal, receipts, call_model, cache):
    graph = review(task, previous, proposal, receipts, call_model, cache)
    # 计划维护是事实，是否免责是另一个问题。只有原审核器已报告
    # 缺少例外字段时才修正节点展示；保留其关键缺口和总体未知结论。
    if any(g["reason"] == "维护材料缺少可验证的例外字段" for g in graph["gaps"]):
        key = "condition:no-maintenance-exclusion"
        node = next(n for n in graph["nodes"] if n["id"] == key)
        old = next((n for n in (previous or {}).get("nodes", []) if n["id"] == key), None)
        node["state"] = "UNKNOWN"
        graph["changes"] = [c for c in graph["changes"] if c["object_id"] != key]
        if old != node:
            graph["changes"].append(dict(object_id=key, kind="added" if old is None else "revised",
                old_graph_version=graph["graph_version"]-1, graph_version=graph["graph_version"],
                before=old, after=node, affected_claim_ids=["claim-eligibility"]))
    return graph


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loop-dir", type=Path, default=HERE.parents[1] / "loop_b_unified")
    parser.add_argument("--output", type=Path, default=HERE / "examples/unified_results.json")
    args = parser.parse_args()
    if not (args.loop_dir / "provider_setup.py").is_file():
        parser.error("请用 --loop-dir 指定团队 main 中的 loop_b_unified 文件夹")
    directory = args.loop_dir.resolve()
    if directory.name == "loop_b_unified" and (directory / "__init__.py").is_file():
        sys.path.insert(0, str(directory.parent))
        from loop_b_unified import create_provider
    else:
        # 团队 main 的旧版没有包入口，仍按它的原方式运行。
        sys.path.insert(0, str(directory))
        from provider_setup import create_provider
    results = []
    for i, (name, number) in enumerate(CASES, 1):
        task, _ = make_case(name)
        faults = dict(task.get("scenarios", {}))
        if number == 9:
            faults.pop("CRM_CONTRACT_DB", None)  # 此数据包已包含相互冲突的合同
        task.update(task_id=f"TASK-{i:03}", scenarios={})
        provider = create_provider(f"bundle-{number:02}", faults=faults, fetched_at="2026-11-12T16:00:00Z")
        bundle = Harness(FixtureModel(), checked_provider(provider), reviewer=unified_review).run(task)
        graph = bundle["graph"]
        node = next(n for n in graph["nodes"] if n["id"] == "condition:no-maintenance-exclusion")
        results.append(dict(case=name, dataset=number, decision=bundle["answer"]["recommendation"],
            maintenance_state=node["state"], stop=graph["stop_reason"],
            gaps=[g["reason"] for g in graph["gaps"]], calls=len(bundle["tool_receipts"]),
            errors=[r.get("error_code") for r in bundle["tool_receipts"] if r["tool_status"] != "SUCCESS"]))
    args.output.parent.mkdir(exist_ok=True, parents=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("已生成", len(results), "个合成场景的结果：", args.output)


if __name__ == "__main__":
    main()
