"""证据链 B：接收团队格式的候选图。输出审核清单，不把候选图当成已发布的证据图。"""
import argparse
import json
from pathlib import Path
from graph_review import digest
from checker_api import read_json
from datetime import datetime
from copy import deepcopy

ROOT = Path(__file__).resolve().parent
CONTRACTS = ROOT / "contracts_04da37d"


def validate(value, spec, path="$"):
    """当前团队 Schema 只用了这几种关键字。出现新约束时明确报错，避免漏检。"""
    if set(spec) - {"$schema", "title", "type", "properties", "required", "items", "enum"}:
        raise ValueError("不支持的新 Schema 约束：" + path)
    kind = {"object": dict, "array": list, "string": str}[spec["type"]]
    if not isinstance(value, kind) or ("enum" in spec and value not in spec["enum"]):
        raise ValueError("字段类型或取值错误：" + path)
    if kind is dict:
        for k in spec.get("required", []):
            if k not in value:
                raise ValueError("缺少字段：" + path + "." + k)
        for k, sub in spec.get("properties", {}).items():
            if k in value:
                validate(value[k], sub, path + "." + k)
    if kind is list:
        for i, item in enumerate(value):
            validate(item, spec["items"], f"{path}[{i}]")


def instant(s):
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if t.utcoffset() is None:
        raise ValueError("缺时区")
    return t


def check_reference(ref, task, receipts):
    """只接受本次客户、本次事故同一轮取得的带原文记录。locator 暂支持完整引用地址。"""
    if not all(isinstance(ref.get(k), str) and ref[k].strip() for k in ("source_id", "locator", "excerpt")):
        return "未提供完整的来源、定位和原句", []
    matches = []
    for r in receipts:
        if (r.get("tool_status") != "SUCCESS" or not r.get("call_id")
                or any(not task.get(k) or task[k] != r.get(k)
                       for k in ("task_id","run_id","customer_id","incident_id"))
                or r.get("arguments", {}).get("event_time") != task.get("event_time")):
            continue
        for row in r.get("records", []):
            if (row.get("source_id") != ref["source_id"] or row.get("citation") != ref["locator"]
                    or row.get("excerpt") != row.get("statement") or not isinstance(row.get("excerpt"),str)
                    or ref["excerpt"] not in row["excerpt"] or not row.get("record_id")
                    or row.get("source_type") != r.get("source_type") or not row.get("version")
                    or any(row.get(k) != task[k] for k in ("customer_id","incident_id"))):
                continue
            try:
                if not instant(row["effective_from"]) <= instant(task["event_time"]) <= instant(row["effective_to"]):
                    continue
                ctx, pos = row["context"], row["locator"]
                if any(type(v) is not int for v in (ctx["start"], ctx["end"], pos["start"], pos["end"])) or not (
                        0 <= ctx["start"] <= pos["start"] < pos["end"] <= ctx["end"]
                        and ctx["end"] - ctx["start"] == len(ctx["text"])):
                    continue
                left, right = pos["start"]-ctx["start"], pos["end"]-ctx["start"]
                if (ctx.get("available") is False or ctx.get("source_id") != ref["source_id"]
                        or pos["unit"] != "unicode_code_points" or not 0 <= left < right <= len(ctx["text"])
                        or ctx["text"][left:right] != row["excerpt"]):
                    continue
            except (TypeError, KeyError, ValueError, AttributeError):
                continue
            matches.append({"call_id": r["call_id"], "provider_call_id": r.get("provider_call_id"),
                            "source_type": r["source_type"], "source_id": row["source_id"],
                            "record_id": row["record_id"], "citation": row["citation"],
                            "record_locator": deepcopy(pos),
                            "record_excerpt": row["excerpt"], "cited_excerpt": ref["excerpt"]})
    return ("已定位适用记录中的原句" if len(matches)==1 else "没有唯一可核对的适用原句"), matches


def check_proposal(payload, receipts, tool_registry, *, human_reviews=None, source_inventory=()):
    schema = read_json(CONTRACTS / "GraphProposal_Schema.json")
    rules = read_json(CONTRACTS / "base_rules_registry.json")
    validate(payload, schema)
    if not isinstance(receipts, list) or any(
            not isinstance(r, dict) or not isinstance(r.get("arguments"), dict)
            or not isinstance(r.get("records"), list)
            or any(not isinstance(row, dict) for row in r["records"]) for r in receipts):
        raise ValueError("回执必须是含 arguments 和 records 的原始回执列表")
    task, graph = payload["task"], payload["graph_proposal"]
    ids, checks = set(), []
    for n in graph["nodes"]:
        key = n["node_id"]
        if not key.strip() or key in ids:
            raise ValueError("空白或重复的节点编号：" + key)
        ids.add(key)
        if n["type"] == "evidence" or "source_locator" in n:
            reason, refs = check_reference(n.get("source_locator", {}), task, receipts)
            checks.append(dict(node_id=key, located=len(refs)==1, reason=reason, matches=refs))
    for e in graph["edges"]:
        if e["from"] not in ids or e["to"] not in ids:
            raise ValueError("关系指向不存在的节点：" + str(e))
    # 只查证明链的循环；覆盖和适用关系不当作循环自证。
    proof = {node: set() for node in ids}
    for e in graph["edges"]:
        a, b = e["from"], e["to"]
        if e["relation"] in ("supports", "refutes"):
            proof[b].add(a)
        elif e["relation"] in ("depends_on", "derived_from"):
            proof[a].add(b)
    visited, visiting = set(), set()
    def visit(node):
        if node in visiting:
            raise ValueError("候选证明链循环自证：" + node)
        if node not in visited:
            visiting.add(node)
            for child in proof[node]:
                visit(child)
            visiting.remove(node)
            visited.add(node)
    for node in ids:
        visit(node)
    # 从实际工具清单比较原名；不擅自将“监控系统”映射成“故障库”。
    available = {s["source_type"] for s in tool_registry["sources"]}
    # 候选对应只作为接口提示；没有注册的名称不用于检索或判定。
    hints = {x["requested_source"]: x["candidate_provider_source"] for x in source_inventory
             if x.get("state") == "NEEDS_OWNER_CONFIRMATION" and x.get("alias_enabled") is False
             and x.get("candidate_provider_source") in available}
    catalog = []
    for rule in rules:
        spec = rule["dynamic_extraction_spec"]
        sources = {c["target_source"] for c in spec["mandatory_base_checks"]}
        sources.update(s for o in spec["runtime_obligations_to_extract"] for s in o["target_sources"])
        catalog.append(dict(rule_id=rule["rule_id"], name=rule["rule_name"],
                            priority=rule["priority"], scope=rule["applicable_scope"],
                            sources_registered=sorted(sources & available),
                            sources_not_registered=sorted(sources - available),
                            pending_source_names={s:hints[s] for s in sorted(sources - available) if s in hints},
                            sources_without_candidate=sorted(sources - available - hints.keys())))
    # 人工审核单独传入，不读取 A 在提案里自报的分数或审核状态。
    candidates = {n["node_id"]: n for n in graph["nodes"]}
    checked = {c["node_id"]: c for c in checks}
    relations = []
    for edge in graph["edges"]:
        ends = [candidates[edge[k]] for k in ("from", "to")]
        key = digest([task, graph, edge, receipts])
        item = dict(edge, review_key=key, review_status="unresolved",
                    reason="请独立核对两端命题、关系方向与原文")
        cited = [checked[n["node_id"]] for n in ends if n["node_id"] in checked]
        decision = (human_reviews or {}).get(key, {})
        if (cited and all(c["located"] for c in cited)
                and decision.get("decision") in ("accepted", "rejected", "unresolved")
                and all(isinstance(decision.get(k), str) and decision[k].strip()
                        for k in ("reviewer", "reason"))):
            item.update(review_status=decision["decision"], reviewer=decision["reviewer"],
                        reason=decision["reason"])
        relations.append(item)
    return dict(task_id=task["task_id"], run_id=task["run_id"],
                proposal_version=graph["graph_version"], reference_checks=checks,
                missing_query_fields=[k for k in ("task_id","run_id","customer_id","incident_id","event_time")
                                      if not task.get(k,"").strip()],
                candidate_gaps=graph.get("gaps", []), rule_catalog=catalog,
                relation_checks=relations,
                stage="proposal_intake", recommendation="undetermined",
                reason="本步骤核对格式与原句。候选关系仍需独立语义复核，不发布补偿结论。")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for arg in ("proposal", "receipts", "tool_registry"):
        ap.add_argument(arg, type=Path)
    ap.add_argument("--alignment", type=Path, help="可选：Loop B 的接口核对报告，仅展示待确认对应")
    ap.add_argument("--human-reviews", type=Path, help="B 侧单独保存的人工复核记录")
    args = ap.parse_args()
    print(json.dumps(check_proposal(*(read_json(getattr(args,k)) for k in
          ("proposal","receipts","tool_registry")), human_reviews=read_json(args.human_reviews) if args.human_reviews else None,
          source_inventory=read_json(args.alignment)["source_inventory"] if args.alignment else ()), ensure_ascii=False, indent=2))
