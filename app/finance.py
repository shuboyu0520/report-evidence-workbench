"""Strict table extraction and Decimal calculations; no model-generated arithmetic."""

import re
from decimal import Decimal, localcontext

ALIASES = {
    "营业收入": "revenue",
    "营业成本": "cost",
    "净利润": "net_profit",
    "经营活动产生的现金流量净额": "operating_cash_flow",
    "资产总计": "total_assets",
    "负债合计": "total_liabilities",
}
FACTORS = {
    "元": Decimal(1),
    "万元": Decimal(10000),
    "百万元": Decimal(1000000),
    "亿元": Decimal(100000000),
}
NUMBER = re.compile(r"-?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?")


def numeric(text):
    text = text.strip().replace("，", ",").replace("−", "-")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    if not NUMBER.fullmatch(text):
        raise ValueError("不支持的数值格式")
    value = Decimal(text.replace(",", ""))
    if len(value.as_tuple().digits) > 24 or value.as_tuple().exponent < -6:
        raise ValueError("数值精度超过限制")
    return value


def extract_metrics(pages):
    """Accept only explicit pipe tables with page-local annual/consolidated metadata.

    Duplicate facts invalidate automatic extraction, preventing silent choice of a
    restated/parent-company table. Arbitrary PDF tables must be reviewed manually.
    """
    facts = []
    for page in pages:
        text = page["text"]
        if "口径：合并" not in text or "期间：年度" not in text:
            continue
        if "母公司" in text:
            continue
        units = re.findall(r"单位[：:]\s*(百万元|万元|亿元|元)", text)
        currencies = re.findall(r"币种[：:]\s*([A-Z]{3})\b", text)
        if len(units) != 1 or len(currencies) != 1:
            continue
        years = None
        for line in text.splitlines():
            cells = [s.strip() for s in line.strip().strip("|").split("|")]
            if cells[0] == "项目":
                years = cells[1:]
                if not years or not all(re.fullmatch(r"20\d{2}", y) for y in years):
                    years = None
                continue
            if not years or cells[0] not in ALIASES or len(cells) != len(years) + 1:
                continue
            for year, cell in zip(years, cells[1:]):
                try:
                    value = numeric(cell) * FACTORS[units[0]]
                except ValueError:
                    continue
                facts.append(
                    dict(
                        name=ALIASES[cells[0]],
                        year=int(year),
                        value=str(value),
                        currency=currencies[0],
                        unit="元",
                        scope="consolidated_annual",
                        page=page["number"],
                        quote=line.strip(),
                        origin="strict_table_extraction",
                    )
                )
    keys = [(f["name"], f["year"]) for f in facts]
    if len(keys) != len(set(keys)):
        return [], ["发现重复指标或重述数据，已停止自动提取，请人工核对。"]
    return facts, ([] if facts else ["未识别到支持的明确表格；可检索原文，指标需人工确认。"])


def calculate(metrics, kind, year, metric="revenue"):
    index = {(m["name"], m["year"]): m for m in metrics}
    requirements = {
        "growth": [(metric, year), (metric, year - 1)],
        "gross_margin": [("revenue", year), ("cost", year)],
        "net_margin": [("net_profit", year), ("revenue", year)],
        "debt_ratio": [("total_liabilities", year), ("total_assets", year)],
        "cash_conversion": [("operating_cash_flow", year), ("net_profit", year)],
    }
    if kind not in requirements:
        return {"status": "unavailable", "reason": "不支持的计算类型"}
    keys = requirements[kind]
    missing = [key for key in keys if key not in index]
    if missing:
        # Required inputs and actually missing inputs differ when only one year is absent.
        return {
            "status": "unavailable",
            "reason": "缺少指标：" + "；".join(f"{y}年 {name}" for name, y in missing),
            "required": keys,
            "missing": missing,
            "available": [key for key in keys if key in index],
        }
    a, b = [index[key] for key in keys]
    if any(a[k] != b[k] for k in ("currency", "unit", "scope")):
        return {"status": "unavailable", "reason": "币种、单位或报表口径不一致"}
    x, y = Decimal(a["value"]), Decimal(b["value"])
    denominator = x if kind == "gross_margin" else y
    if denominator <= 0:
        return {
            "status": "unavailable",
            "reason": "分母非正，不输出可能误导的比率",
            "inputs": [a, b],
        }
    with localcontext() as context:
        context.prec = 80
        numerator = x - y if kind in ("growth", "gross_margin") else x
        result = (numerator / denominator * 100).quantize(Decimal("0.01"))
    return {
        "status": "ok",
        "kind": kind,
        "year": year,
        "metric": metric,
        "value": str(result),
        "unit": "%",
        "inputs": [a, b],
        "formula": f"({x} - {y}) / {denominator} * 100"
        if kind in ("growth", "gross_margin")
        else f"{x} / {y} * 100",
    }
