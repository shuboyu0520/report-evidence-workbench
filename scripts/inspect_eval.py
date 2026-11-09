"""Inspect archived financial-report answers and their original PDF pages."""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_ARCHIVE = Path(__file__).resolve().parents[1] / "evaluation/showcase.json"
TASK_GROUPS = {"actual": "lookup_guidance", "guidance": "lookup_guidance",
               "future": "disclosure_status", "missing": "disclosure_status"}
COHORT_LABELS = {"same_set_replay": "同题修复回放", "first_run": "冻结版本首次盲测"}


def read_archive(path):
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("cohorts"), dict):
        raise ValueError("需要 schema_version=1 且含 cohorts 的评测存档")
    for key, cohort in data["cohorts"].items():
        source = urlsplit(cohort["source"])
        if source.scheme not in {"https", "http"} or not source.netloc:
            raise ValueError(f"{key} 缺少原始报告链接")
        seen = set()
        for case in cohort["cases"]:
            cid = case["id"]
            if cid in seen or type(case["passed"]) is not bool or case["kind"] not in TASK_GROUPS:
                raise ValueError(f"{key}/{cid} 的编号、判定或问题类型无效")
            seen.add(cid)
            for citation in case["citations"]:
                page = citation["page"]
                quote = citation["quote"]
                if type(page) is not int or page < 1 or not isinstance(quote, str) or not quote.strip():
                    raise ValueError(f"{key}/{cid} 含无效页码或空引文")
            if any(type(page) is not int or page < 1 for page in case.get("gold_pages", [])):
                raise ValueError(f"{key}/{cid} 含无效的独立评分页码")
    return data["cohorts"]


def select(cohorts, cohort_key, case_id, failed):
    if cohort_key and cohort_key not in cohorts:
        raise ValueError(f"找不到批次 {cohort_key}，可选 {', '.join(cohorts)}")
    selected = {}
    for key, cohort in cohorts.items():
        if cohort_key and key != cohort_key:
            continue
        source = urlsplit(cohort["source"])
        counts = {group: {"passed": 0, "total": 0} for group in ("lookup_guidance", "disclosure_status")}
        cases = []
        for case in cohort["cases"]:
            count = counts[TASK_GROUPS[case["kind"]]]
            count["total"] += 1
            count["passed"] += int(case["passed"])
            if (case_id and case["id"] != case_id) or (failed and case["passed"]):
                continue
            cases.append({**case, "citations": [
                {**c, "url": source._replace(fragment=f"page={c['page']}").geturl()}
                for c in case["citations"]
            ]})
        if not case_id or cases:
            selected[key] = {"title": cohort["title"], "kind": cohort["kind"], "source": cohort["source"],
                             "scores": counts, "cases": cases}
    if case_id and not selected:
        raise ValueError(f"在所选批次找不到题目 {case_id}")
    return {"schema_version": 1, "mode": "archived_replay", "cohorts": selected}


def print_report(result, details):
    print("本地评测存档回放")
    for key, cohort in result["cohorts"].items():
        label = COHORT_LABELS.get(cohort["kind"], cohort["kind"])
        print(f"\n{cohort['title']} · {label}  [{key}]")
        for group, title in (("lookup_guidance", "查数与指引"), ("disclosure_status", "披露判断")):
            count = cohort["scores"][group]
            print(f"  {title}  {count['passed']}/{count['total']}")
        print(f"  原始报告  {cohort['source']}")
        if details and not cohort["cases"]:
            print("  本次筛选匹配 0 题")
        if details:
            for case in cohort["cases"]:
                outcome = "通过" if case["passed"] else "未通过"
                print(f"\n{case['id']}  {outcome}  {case['question']}")
                if case.get("previous_answer"):
                    print("  上版答案  " + case["previous_answer"])
                print("  本轮答案  " + case["answer"])
                print("  判定依据  " + case["grade"])
                for c in case["citations"]:
                    print(f"  原文第 {c['page']} 页  {c['url']}\n    {c['quote']}")
                for page in case.get("gold_pages", []):
                    url = urlsplit(cohort["source"])._replace(fragment=f"page={page}").geturl()
                    print(f"  独立评分参考第 {page} 页  {url}")
                if case.get("gold_quote"):
                    print("  独立评分参考原文  " + case["gold_quote"])


def main():
    parser = argparse.ArgumentParser(description="在本机查看已保存的财报评测分数、答案与证据。")
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE, help="指定评测存档 JSON")
    parser.add_argument("--cohort", help="选择批次，例如 booking 或 expedia")
    query = parser.add_mutually_exclusive_group()
    query.add_argument("--case", dest="case_id", help="查看一道题，例如 B14")
    query.add_argument("--failed", action="store_true", help="逐题查看未通过的结果")
    parser.add_argument("--json", action="store_true", help="输出可复用的 JSON，分母为完整批次的题数")
    args = parser.parse_args()
    try:
        result = select(read_archive(args.archive), args.cohort, args.case_id, args.failed)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print_report(result, bool(args.case_id or args.failed))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"评测存档读取失败  {error}\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
