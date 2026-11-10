"""Read a dated full-year outlook with separate updated and prior range columns."""

import re
from decimal import Decimal

from .lodging_metrics import FOREIGN_CURRENCY


FULL_YEAR = r"(?:full[- ]year|fiscal year|annual)"
FORECAST = r"(?:outlook|guidance|forecast)"
VERSIONS = re.compile(
    rf"((?:updated|current|prior|previous) {FORECAST})\s+((?:updated|current|prior|previous) {FORECAST})",
    re.I,
)
FISCAL_TITLE = re.compile(
    rf"\b{FULL_YEAR}\s+(20\d\d)\b[^.;\n]{{0,100}}?\b{FORECAST}\b|\b(20\d\d)\s+{FULL_YEAR}\s+{FORECAST}\b",
    re.I,
)
ANNUAL_HEADING = re.compile(rf"\b{FULL_YEAR}(?:\s+20\d\d)?\s+{FORECAST}\b", re.I)
RATE = r"([+−-]?\d+(?:\.\d+)?)\s*%\s*(?:[–—-]|to)\s*([+−-]?\d+(?:\.\d+)?)\s*%"
MONEY = r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:[–—-]|to)\s*\$\s*([\d,]+(?:\.\d+)?)\s+(million|billion|thousand)\b"
MONEY_UNITS = {"美元": 1, "百万美元": 10**6, "亿美元": 10**8, "十亿美元": 10**9}
FACTORS = {"thousand": 10**3, "million": 10**6, "billion": 10**9}
REVPAR = r"Year[- ]over[- ]year global RevPAR growth"


def outlook_version(question):
    if re.search(r"此前|上次|原先|先前|上一版|更新前|\b(?:previous|prior)\b", question, re.I):
        return "prior"
    if re.search(r"本次|这次|此次|更新|最新|当前|\b(?:current|updated|latest)\b", question, re.I):
        return "current"
    return ""


def _year_evidence(text, page):
    return [(int(m[1] or m[2]), {"page": page, "quote": m[0]}) for m in FISCAL_TITLE.finditer(text)]


def revised_annual_cells(pages, request):
    if not pages or not request.guidance or request.quarter is not None:
        return []
    is_revpar = (
        request.metric == "revpar"
        and request.growth_basis == "constant"
        and request.groups == ("Global",)
    )
    is_money = (
        request.metric == "ebitda"
        and request.adjusted
        and not request.growth_basis
        and not request.groups
        and not request.products
        and request.unit in MONEY_UNITS
    )
    if not (is_revpar or is_money):
        return []
    metric = REVPAR if is_revpar else "Adjusted EBITDA"
    bounds = RATE if is_revpar else MONEY
    row_pattern = re.compile(rf"({metric})(?:\s*\(([a-z\d]+)\))?\s+{bounds}\s+{bounds}", re.I)
    cover_years = _year_evidence(pages[0]["text"], pages[0]["number"])
    result = []
    for page in pages:
        lines = [s.strip() for s in page["text"].splitlines() if s.strip()]
        for i, header in enumerate(lines):
            versions = VERSIONS.fullmatch(header)
            if not versions or not i or not ANNUAL_HEADING.search(lines[i - 1]):
                continue
            current = [bool(re.match("updated|current", v, re.I)) for v in versions.groups()]
            years = _year_evidence(lines[i - 1], page["number"]) or cover_years
            if sum(current) != 1 or {y for y, _ in years} != {request.year}:
                continue
            index = current.index(request.outlook_version != "prior")
            for line in lines[i + 1 :]:
                if re.match(
                    r"\([a-z\d]+\)\s|^(?:Full year|Year ending|Quarter|Q[1-4]|Outlook|Table)\b",
                    line,
                    re.I,
                ):
                    break
                match = row_pattern.fullmatch(line)
                if not match:
                    continue
                evidence = [years[0][1]]
                span = 2 if is_revpar else 3
                start = 3 + index * span
                values = [
                    Decimal(match[k].replace(",", "").replace("−", "-")) for k in (start, start + 1)
                ]
                if values[0] > values[1]:
                    continue
                if is_revpar:
                    if not match[2]:
                        continue
                    note_pattern = re.compile(
                        rf"^\({re.escape(match[2])}\)\s+(?:represents|calculated (?:on|in)|on) "
                        r"(?:a )?constant[- ]currency(?: basis)?\b",
                        re.I,
                    )
                    footnotes = []
                    for note in lines[i + 1 :]:
                        if VERSIONS.fullmatch(note) or re.match(
                            r"^(?:Table \d+|Outlook|Conference call)\b", note, re.I
                        ):
                            break
                        if note_match := note_pattern.match(note):
                            footnotes.append(note_match[0])
                    if len(footnotes) != 1:
                        continue
                    evidence.append({"page": page["number"], "quote": footnotes[0]})
                else:
                    if FOREIGN_CURRENCY.search(line) or any(
                        FOREIGN_CURRENCY.search(s) for s in lines[max(0, i - 3) : i]
                    ):
                        continue
                    factor = Decimal(FACTORS[match[start + 2].lower()]) / MONEY_UNITS[request.unit]
                    values = [v * factor for v in values]
                vintage = "更新后" if current[index] else "此前"
                result.append(
                    {
                        "page": page["number"],
                        "year": request.year,
                        "quarter": None,
                        "column": index + 1,
                        "raw_cell": [match[k] for k in (start, start + 1)],
                        "amounts": [format(v, ",f") for v in values],
                        "unit": request.unit,
                        "label": "RevPAR" if is_revpar else match[1],
                        "scope": "",
                        "measure_caption": "",
                        "basis": vintage + ("固定汇率同比" if is_revpar else "非 GAAP"),
                        "quote": line,
                        "header": header,
                        "context_quote": lines[i - 1],
                        "basis_evidence": evidence,
                        "priority": 5,
                    }
                )
    return result
