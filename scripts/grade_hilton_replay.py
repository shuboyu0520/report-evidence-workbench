"""Score a Hilton Q3 2026 replay using the sealed questions and physical PDF pages."""

import re
from decimal import Decimal

from scripts.grade_expedia_replay import CHINESE_Q, compact, main, numbers

# Evidence labels for the preregistered Hilton fixture. The reader never imports the grader.
LABELS = {
    "H01": ("total revenues",),
    "H02": ("total revenues",),
    "H03": (r"(?<!non-)operating income",),
    "H04": ("diluted",),
    "H05": ("adjusted ebitda",),
    "H06": ("net income",),
    "H07": ("franchise and licensing fees",),
    "H08": ("ownership", "revenues"),
    "H09": ("interest expense",),
    "H10": ("total expenses",),
    "H11": ("system-wide", "occupancy"),
    "H12": ("asia pacific", "revpar"),
    "H13": ("revpar", "currency neutral", "fourth quarter"),
    "H14": ("adjusted ebitda",),
}


def grade(case, result, pages, cutoff, *, labels=LABELS):
    answer = result.get("answer") or ""
    state = result.get("verification")
    refs = result.get("citations") or []
    if result.get("http") != 200:
        return False, "问答接口未成功返回。"
    if any(
        not (
            type(r["page"]) is int
            and 1 <= r["page"] <= len(pages)
            and r["quote"].strip()
            and compact(r["quote"]) in pages[r["page"] - 1]
        )
        for r in refs
    ):
        return False, "引文不能在所标物理页连续定位。"
    if case["kind"] == "missing":
        return (
            state == "insufficient_evidence" and not refs and "没找到足够证据" in answer,
            "按题目指定的国家、品牌和指标核验披露范围。",
        )
    if case["kind"] == "future":
        return (
            state == "not_yet_disclosed"
            and not refs
            and cutoff in answer
            and case["period_end"] in answer
            and "尚未披露" in answer,
            "研究截止日早于所问报告期的结束日。",
        )
    if not refs or state == "insufficient_evidence":
        return False, "原公告披露了所问指标，系统未给出有据答复。"
    year, term = case["period"].split()
    quarter = None if term == "FY" else int(term.removeprefix("Q"))
    if quarter is None:
        period = rf"{year}\s*(?:财年|年)?\s*全年"
    else:
        period = rf"{year}\s*(?:财年|年)\s*第?\s*(?:{quarter}|{CHINESE_Q[quarter - 1]})\s*(?:财季|季度)"
    if not re.search(period, answer):
        return False, "答复中的报告期间不符。"
    unit = case["unit"]
    if unit not in answer and not (
        unit == "美元/可售客房" and ("美元" in answer and "revpar" in answer.lower())
    ):
        return False, "答复中的单位不符。"
    selected = " ".join(compact(r["quote"]) for r in refs if r["page"] in case["accepted_pages"])
    if not all(re.search(label, selected) for label in labels[case["id"]]):
        return False, "指定原表或业务分项未经对应引文支持。"
    expected = [Decimal(x) for x in case["expected_values"]]
    answer_body = re.split(r"原表第|[（(]原文第", re.sub(period, "", answer), maxsplit=1)[0]
    amount = re.split(r"(?:实际|指引)[）)]?\s*为|(?:为|是)\s*(?=[+\-−\d$])", answer_body)[-1]
    if numbers(amount) != expected or not all(x in numbers(selected) for x in expected):
        return False, "原值、列示符号或区间端点与答案不符。"
    if case["kind"] == "guidance" and not re.search(r"指引|预计|展望|预期", answer):
        return False, "答复未标明预测口径。"
    cell = next((t for t in result.get("trace", []) if t["tool"] == "read_earnings_cell"), None)
    if cell and (
        cell["year"] != int(year)
        or cell["quarter"] != quarter
        or [Decimal(v.replace(",", "")) for v in cell["amounts"]] != expected
        or cell["page"] not in case["accepted_pages"]
    ):
        return False, "选中的原表单元格与所问期间或金额不符。"
    return True, "所问口径、报告期间、原值及物理页引文相符。"


if __name__ == "__main__":
    main(grade, __doc__)
