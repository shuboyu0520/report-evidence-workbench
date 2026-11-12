"""Bind revenue and free cash flow to printed quarterly column headings.

Supports both statement dates and compact investor-slide fiscal headings. All
amounts use a local currency scale. A table row or a graph on its own cannot
establish company scope or the fiscal quarter.
"""

import re
from datetime import datetime
from decimal import Decimal

from .finance import numeric
from .table_lookup import MONTH, SCALE

DATE = re.compile(rf"({MONTH})\.?\s+(\d{{1,2}})\s*,?\s+((?:19|20)\d{{2}})\b", re.I)
MONTH_DAY = re.compile(rf"({MONTH})\.?\s+(\d{{1,2}})\b", re.I)
FISCAL = re.compile(r"\bFY\s*['’]?(\d{2}|\d{4})\s+Q([1-4])\b", re.I)
TITLE = re.compile(
    r"^(First|Second|Third|Fourth) Quarter of Fiscal (?:Year )?(20\d{2}) Summary\b", re.I
)
QUARTERS = ("first", "second", "third", "fourth")
SHORT_COLUMN = re.compile(r"Q([1-4])\s*['’](\d{2})|Y/Y|Q/Q", re.I)
MONEY = r"(?:\$\s*)?\(?[−–-]?\s*\d[\d,]*(?:\.\d+)?\)?"
SCALAR = re.compile(MONEY)
GROUP_ROW = re.compile(r"(?:consolidated |total |net |GAAP )*(?:revenues?|net sales|sales)$", re.I)
GROUP_TABLE = re.compile(
    r"^(?:(?:condensed|combined|consolidated|unaudited)\s+)*(?:statements? of (?:income|operations|earnings)|income statements?)\b"
    r"|^(?:(?:Q[1-4]|(?:first|second|third|fourth) quarter)(?:\s+\d{4})?\s+)?(?:financial highlights|summary P&L)\b"
    r"|^(?:first|second|third|fourth) quarter of fiscal (?:year )?\d+ summary"
    r"|^the following table summarizes (?:our|the company's) consolidated financial results",
    re.I,
)
SPLIT_TABLE = re.compile(
    r"segment results|revenues? by |(?:product|service).*offerings revenue|segment revenues", re.I
)
REVENUE_CAPTION = re.compile(
    r"^revenues?(?:\s*:| by .*)?$|(?:product|service).*offerings revenue", re.I
)
FCF_TITLE = re.compile(r"reconciliation of (?:GAAP|non.GAAP|free cash flow)", re.I)
FOREIGN_CURRENCY = re.compile(
    r"(?<![A-Za-z])(?:CA?|AU?|HK|NT|S)\$|\b(?:CAD|AUD|HKD|TWD|SGD|EUR|Canadian dollars|Australian dollars)\b",
    re.I,
)


def _table_context(prior):
    """Titles from a preceding table must not leak through its data or a new section."""
    context = []
    for line in prior:
        if len(line) < 190 and (
            GROUP_TABLE.search(line) or SPLIT_TABLE.search(line) or FCF_TITLE.search(line)
        ):
            context = [line]
        elif SCALE.search(line) or re.fullmatch(r"\(?unaudited\)?", line, re.I):
            continue
        else:
            context = []
    return context


def _row_values(lines, pos, width):
    raw = lines[pos]
    match = re.fullmatch(
        r"(?P<label>[A-Za-z][A-Za-z &/.,’-]*?)\s+(?P<values>(?:\$|\(|[−\d-]).*)", raw
    )
    if match:
        tail = re.sub(r"\b(?:Up|Down)\s+(?=\d)", "", match["values"], flags=re.I)
        pattern = MONEY + r"(?:\s*%)?"
        if re.sub(pattern, "", tail).strip():
            return "", [], ""
        return match["label"].strip(), re.findall(pattern, tail), raw
    values = []
    for nxt in lines[pos + 1 : pos + width + 2]:
        if not SCALAR.fullmatch(nxt):
            break
        values.append(nxt)
    return raw, values, "\n".join([raw, *values])


def _release(pages):
    """Pair a release's fiscal label and its stated calendar cutoff, if available."""
    head = pages[0]["text"][:12000]
    ending = re.search(
        r"(?:for\s+(?:the\s+)?(?:fiscal\s+)?(?:quarter|quarterly period)|quarterly period)\s+ended\s+("
        + DATE.pattern
        + ")",
        head,
        re.I,
    )
    if not ending:
        return None, None, []
    date = (int(ending[4]), datetime.strptime(ending[2][:3].title(), "%b").month, int(ending[3]))
    labels = []
    for page in pages:
        for line in page["text"].splitlines():
            line = line.strip()
            if len(line) > 100:
                continue
            fy = (
                FISCAL.search(line)
                if re.search(r"earnings release|financial results", line, re.I)
                else None
            )
            title = TITLE.match(line)
            if fy:
                y = int(fy[1])
                labels.append(((y + 2000 if y < 100 else y, int(fy[2])), page["number"], line))
            elif title:
                labels.append(
                    ((int(title[2]), QUARTERS.index(title[1].lower()) + 1), page["number"], line)
                )
    fiscal = {rec[0] for rec in labels}
    refs = [{"page": pages[0]["number"], "quote": ending[0]}]
    if len(fiscal) == 1:
        refs.append({"page": labels[0][1], "quote": labels[0][2]})
        return date, labels[0][0], refs
    return date, None, refs


def _date_header(lines, start, end_date):
    """Return slot index and numeric-column width for the three-month band."""
    if not end_date:
        return None
    for stop in range(start, min(start + 9, len(lines))):
        header = " ".join(lines[start : stop + 1])
        last = lines[stop]
        full = list(DATE.finditer(last))
        if len(full) >= 2:
            dates = [
                (int(m[3]), datetime.strptime(m[1][:3].title(), "%b").month, int(m[2]))
                for m in full
            ]
            width = len(dates)
            if re.search(r"(?:Six|Nine|Twelve) Months Ended|Years? Ended", header, re.I):
                if width % 2 or dates[: width // 2] != dates[width // 2 :]:
                    return None
                dates = dates[: width // 2]
            return (stop, dates.index(end_date), width) if end_date in dates else None
        if not re.fullmatch(r"(?:(?:19|20)\d{2}\s*)+", last):
            continue
        years = [int(y) for y in last.split()]
        # A table pasted from HTML can place each year and every cell on its own line.
        while stop + 1 < len(lines) and re.fullmatch(r"(?:19|20)\d{2}", lines[stop + 1]):
            stop += 1
            years.append(int(lines[stop]))
        if len(years) < 2:
            continue
        md = {
            (datetime.strptime(m[1][:3].title(), "%b").month, int(m[2]))
            for m in MONTH_DAY.finditer(header)
        }
        if md != {end_date[1:]}:
            return None
        width = len(years)
        if re.search(r"(?:Six|Nine|Twelve) Months Ended|Years? Ended", header, re.I):
            if width % 2 or years[: width // 2] != years[width // 2 :]:
                return None
            years = years[: width // 2]
        return (stop, years.index(end_date[0]), width) if years.count(end_date[0]) == 1 else None
    return None


def _label(req, label, context, scope):
    section = "\n".join(context)
    if req.metric == "free_cash_flow":
        return label.lower() == "free cash flow" and bool(FCF_TITLE.search(section))
    if req.products:
        if scope and GROUP_ROW.fullmatch(label) and SPLIT_TABLE.search(section):
            return all(re.search(p, scope, re.I) for p in req.products)
        return all(re.search(p, label, re.I) for p in req.products) and any(
            REVENUE_CAPTION.search(s) for s in context
        )
    return (
        GROUP_ROW.fullmatch(label)
        and GROUP_TABLE.search(section)
        and not (scope or SPLIT_TABLE.search(section))
    )


def statement_cells(pages, req, calendar_year, factors, units):
    if (
        not pages
        or req.qualified
        or req.guidance
        or req.adjusted
        or req.groups
        or req.revenue_line
        or not req.quarter
        or req.metric not in {"revenue", "free_cash_flow"}
    ):
        return []
    result = []
    cutoff, fiscal, release_refs = _release(pages)
    if cutoff and not fiscal and calendar_year:
        fiscal = (cutoff[0], (cutoff[1] - 1) // 3 + 1)
    for page in pages:
        lines = [s.strip() for s in page["text"].splitlines() if s.strip()]
        for start, line in enumerate(lines):
            slide = list(SHORT_COLUMN.finditer(line))
            if slide and SCALE.search(line):
                columns = [(2000 + int(m[2]), int(m[1])) if m[1] else None for m in slide]
                if columns.count((req.year, req.quarter)) != 1:
                    continue
                stop, index, width = start, columns.index((req.year, req.quarter)), len(columns)
            elif fiscal == (req.year, req.quarter) and re.match(
                r"^(?:Three Months|Quarter) Ended\b", line, re.I
            ):
                dated = _date_header(lines, start, cutoff)
                if not dated:
                    continue
                stop, index, width = dated
            else:
                continue
            prior = lines[max(0, start - 6) : start]
            context = _table_context(prior)
            if slide and any(re.search(r"non[- ]GAAP", s, re.I) for s in context):
                continue
            header = "\n".join(lines[start : stop + 1])
            unit = next(
                (
                    s
                    for s in reversed(prior + lines[start : stop + 2])
                    if SCALE.search(s) and len(s) < 190
                ),
                "",
            )
            if not unit or FOREIGN_CURRENCY.search(unit):
                continue
            scale = factors[SCALE.search(unit)[1].lower()]
            scope = ""
            dollars = "$" in unit or bool(re.search(r"\bUSD\b|U\.?S\.? dollars", unit, re.I))
            for pos in range(stop + 1, min(stop + 100, len(lines))):
                raw = lines[pos]
                if SHORT_COLUMN.search(raw) and SCALE.search(raw):
                    break
                if (
                    re.match(
                        r"^(?:(?:Three|Six|Nine|Twelve) Months|Quarter|Years?) Ended\b", raw, re.I
                    )
                    or len(raw) > 280
                ):
                    break
                if (
                    pos > stop + 1
                    and (GROUP_TABLE.search(raw) or FCF_TITLE.search(raw))
                    and not re.search(r"\d", raw)
                ):
                    break
                if re.search(r"^operating income(?: \(loss\))?:?$", raw, re.I):
                    break
                if REVENUE_CAPTION.search(raw):
                    context.append(raw)
                if (
                    pos + 1 < len(lines)
                    and re.fullmatch(r"[A-Za-z][A-Za-z &/-]{1,85}", raw)
                    and not REVENUE_CAPTION.fullmatch(raw)
                    and re.match(r"^(?:net )?revenues?(?:\s+\$|$)", lines[pos + 1], re.I)
                ):
                    scope = raw
                # Percent-change columns have numeric cells but no currency units.
                label, values, quote = _row_values(lines, pos, width)
                dollars |= any("$" in value for value in values)
                if not dollars or len(values) < width or not _label(req, label, context, scope):
                    continue
                if slide and len(values) != width:
                    continue
                if not slide and (
                    any("%" in v for v in values[:width])
                    or any("%" not in v for v in values[width:])
                ):
                    continue
                value = values[index].strip()
                if "%" in value:
                    continue
                try:
                    printed = numeric(value.replace("$", "").replace(" ", "").replace("−", "-"))
                except ValueError:
                    continue
                if (
                    req.exact_amount
                    and scale * Decimal(10) ** printed.as_tuple().exponent > units[req.unit]
                ):
                    continue
                result.append(
                    dict(
                        page=page["number"],
                        label=label,
                        scope=scope,
                        measure_caption=scope,
                        basis="",
                        year=req.year,
                        quarter=req.quarter,
                        column=index + 1,
                        raw_cell=[value],
                        amounts=[f"{printed * scale / units[req.unit]:,f}"],
                        unit=req.unit,
                        quote=quote,
                        header=header,
                        context_quote=scope or (context[-1] if context else ""),
                        unit_quote=unit if unit not in header.splitlines() else "",
                        priority=3,
                        basis_evidence=[] if slide else release_refs,
                    )
                )
    return result
