"""Bind hotel operating measures to their printed period, geography and unit."""

import re
from datetime import datetime
from decimal import Decimal

HOTEL_METRICS = {"occupancy", "revpar"}
NAMES = {"occupancy": "Occupancy", "revpar": "RevPAR"}
ORDINALS = ("first", "second", "third", "fourth")
HOTEL_METRIC = re.compile(r"入住率|\boccupancy\b|每间可售客房收入|\brevpar\b", re.I)
YEAR_PAIR = re.compile(r"(20\d\d)\s+vs\.?\s+(20\d\d)", re.I)
NUMBER = r"(?:\(\s*\d[\d,.]*\s*\)|[-+]?\d[\d,.]*|[—–])"
CELL = re.compile(rf"(?:\$\s*)?{NUMBER}(?:\s*%(?:\s*pts\.?)?)?", re.I)
PERIOD = re.compile(r"^(first|second|third|fourth) quarter\s+(20\d\d)$", re.I)
GROWTH = re.compile(
    r"^[•◦*\s-]*system[- ]wide comparable RevPAR,? on a currency[- ]neutral basis,? "
    r"is (?:projected|expected) to increase between (\d+(?:\.\d+)?)\s*(?:%|percent) and "
    r"(\d+(?:\.\d+)?)\s*(?:%|percent) compared to the (first|second|third|fourth) quarter of (20\d\d)\.?$",
    re.I,
)
FOREIGN_CURRENCY = re.compile(
    r"(?:CA|C|A|HK|NT|NZ|SG)\$|[€£¥]|\b(?:CAD|AUD|NZD|SGD|HKD|TWD|EUR|GBP|JPY)\b", re.I
)


def operating_request(question, year, quarter, guidance, make_request):
    metric = "revpar" if re.search(r"RevPAR|每间可售客房收入", question, re.I) else "occupancy"
    growth = bool(re.search(r"同比|增幅|增长|growth|year.over.year", question, re.I))
    constant = bool(
        re.search(
            r"固定汇率|不变汇率|恒定汇率|currency[- ]neutral|constant currency", question, re.I
        )
    )
    groups = re.findall(r"[(（]([a-z][a-z &.\-]+)[)）]", question, re.I)
    groups = [
        name.strip() for name in groups if name.casefold() not in {"revpar", "occupancy", "adr"}
    ]
    if re.search(r"全系统|system[- ]wide", question, re.I):
        groups.append("System-wide")
    if re.search(r"全球|\bglobal\b", question, re.I):
        groups.append("Global")
    if re.search(r"亚太|\basia pacific\b", question, re.I):
        groups.append("Asia Pacific")
    groups = tuple({name.casefold(): name for name in groups}.values())
    sections = tuple(
        name
        for name, pat in (
            ("Region", r"地区|地域|亚太|\bregion\b"),
            ("Brand", r"品牌|\bbrand\b"),
            ("Segment", r"分部|\bsegment\b"),
        )
        if re.search(pat, question, re.I)
    )
    unwanted_scope = re.search(
        r"非可比|non.comparable|单一国家|仅限.*(?:城市|酒店)|百分[点點]|percentage points?|环比|累计|九个月|比较|对比|差异|为什么|原因",
        question,
        re.I,
    )
    supported = (
        not unwanted_scope
        and len(groups) == 1
        and len(sections) <= 1
        and (
            (quarter and not growth and not guidance)
            or (
                guidance
                and growth
                and constant
                and metric == "revpar"
                and (
                    (quarter and groups == ("System-wide",))
                    or (
                        not quarter
                        and groups == ("Global",)
                        and re.search(r"全年|全财年|年度|full[- ]year|annual", question, re.I)
                    )
                )
            )
        )
    )
    unit = "%" if metric == "occupancy" or growth else "美元/可售客房"
    if metric == "occupancy" and re.search(r"美元|\bUSD\b|\$", question, re.I):
        supported = False
    if metric == "revpar" and not growth and re.search(r"百分比|%|percent", question, re.I):
        supported = False
    return make_request(
        metric=metric,
        pattern=NAMES[metric],
        year=year,
        quarter=quarter,
        guidance=guidance,
        adjusted=False,
        unit=unit,
        groups=groups,
        products=sections,
        qualified=not bool(supported),
        growth_basis="constant" if growth and constant else "",
        comparable_hotels=bool(re.search(r"可比酒店|comparable hotels?", question, re.I)),
    )


def calendar_quarter(date_text):
    try:
        date = datetime.strptime(date_text.rstrip(","), "%B %d, %Y").date()
    except ValueError:
        return None
    if (date.month, date.day) not in {(3, 31), (6, 30), (9, 30), (12, 31)}:
        return None
    return date.year, date.month // 3


def _row(text):
    start = re.search(r"\s+(?=\$?\s*(?:\d|\(\d|[—–]))", text)
    if not start:
        return None
    label, tail = text[: start.start()].strip(), text[start.end() :]
    if CELL.sub("", tail).strip():
        return None
    return label, [m.group().strip() for m in CELL.finditer(tail)]


def _level_cells(page, lines, request):
    title = next(
        (
            s
            for s in lines
            if "hotel operating statistics" in s.lower() and "comparable" in s.lower()
        ),
        None,
    )
    if not title:
        return
    for i, line in enumerate(lines[:-3]):
        date = re.fullmatch(r"three months ended\s+([A-Za-z]+ \d{1,2}),?", line, re.I)
        if not date:
            continue
        metrics = lines[i + 1].lower().split()
        if sorted(metrics) != ["adr", "occupancy", "revpar"]:
            continue
        years = YEAR_PAIR.findall(lines[i + 2])
        if (
            len(years) != len(metrics)
            or len(set(years)) != 1
            or YEAR_PAIR.sub("", lines[i + 2]).strip()
        ):
            continue
        when = calendar_quarter(date[1] + ", " + years[0][0])
        if when != (request.year, request.quarter) or int(years[0][1]) != request.year - 1:
            continue
        column = metrics.index(request.metric) * 2
        wanted = request.groups[0].casefold()
        header = "\n".join(lines[i : i + 3])
        if FOREIGN_CURRENCY.search(" ".join(lines[: i + 3])):
            continue
        unit_quote = ""
        section = section_quote = ""
        for raw in lines[i + 3 :]:
            if group := re.fullmatch(r"(region|brand|segment)(?:\s*\(\d+\))?", raw, re.I):
                section, section_quote = group[1].title(), raw
                unit_quote = ""
                continue
            row = _row(raw)
            if not row or len(row[1]) != 2 * len(metrics):
                break
            label, cells = row
            value = cells[column]
            if FOREIGN_CURRENCY.search(raw):
                unit_quote = ""
                break
            unit_marker = "%" if request.metric == "occupancy" else "$"
            if ("$" if unit_marker == "%" else "%") in value:
                unit_quote = ""
                continue
            if unit_marker in value:
                unit_quote = raw
            if (
                label.casefold() != wanted
                or not unit_quote
                or (request.products and section not in request.products)
            ):
                continue
            amount = re.fullmatch(r"\$?\s*(\d[\d,]*(?:\.\d+)?)\s*%?", value)
            if not amount or (
                request.metric == "occupancy" and Decimal(amount[1].replace(",", "")) > 100
            ):
                continue
            yield {
                "page": page,
                "year": request.year,
                "quarter": request.quarter,
                "column": column + 1,
                "raw_cell": [value],
                "amounts": [amount[1]],
                "unit": request.unit,
                "label": NAMES[request.metric],
                "scope": label,
                "measure_caption": "",
                "basis": "可比酒店",
                "quote": raw,
                "header": header,
                "context_quote": title,
                "unit_quote": unit_quote if unit_quote != raw else "",
                "priority": 0,
                "basis_evidence": [{"page": page, "quote": section_quote}]
                if request.products
                else [],
            }


def _forecast_cells(page, lines, request):
    heading = ""
    for i, line in enumerate(lines):
        if period := PERIOD.fullmatch(line):
            heading = (
                line
                if (int(period[2]), ORDINALS.index(period[1].lower()) + 1)
                == (request.year, request.quarter)
                else ""
            )
            continue
        if re.search(
            r"^(?:full year|fiscal year|Q[1-4]|outlook|forward.looking|historical results)\b",
            line,
            re.I,
        ):
            heading = ""
        if not heading or not re.search(r"^[•◦*\s-]*system[- ]wide comparable RevPAR", line, re.I):
            continue
        quote = line
        match = GROWTH.fullmatch(" ".join(quote.split()))
        if not match and i + 1 < len(lines):
            quote += "\n" + lines[i + 1]
            match = GROWTH.fullmatch(" ".join(quote.split()))
        if (
            not match
            or int(match[4]) != request.year - 1
            or ORDINALS.index(match[3].lower()) + 1 != request.quarter
        ):
            continue
        if Decimal(match[1]) > Decimal(match[2]):
            continue
        yield {
            "page": page,
            "year": request.year,
            "quarter": request.quarter,
            "column": 1,
            "raw_cell": [match[1] + " percent", match[2] + " percent"],
            "amounts": [match[1], match[2]],
            "unit": "%",
            "label": "RevPAR",
            "scope": "System-wide",
            "measure_caption": "",
            "basis": "可比酒店固定汇率同比",
            "quote": quote,
            "header": heading,
            "priority": 0,
        }


def _regional_levels(page, request, cover):
    """Extract the level column of a regional RevPAR table alongside its change column."""
    if (
        request.metric != "revpar"
        or request.comparable_hotels
        or request.products not in ((), ("Region",))
    ):
        return
    text = page["text"]
    header = re.compile(
        r"three\s+months\s+ended\s+([A-Za-z]+\s+\d{1,2}),\s*(20\d\d)?\s*"
        r"(?:constant\s+currency\s+)?%\s*change(?:\s*\([a-z\d]+\))?\s*"
        r"regional\s+RevPAR(?:\s+growth)?\b",
        re.I,
    )
    for m in header.finditer(text):
        date = " ".join(m[1].split())
        year = m[2]
        evidence = []
        if not year:
            # A quarter caption may omit the year. Verify both the results announcement
            # and an independently dated table through the same day on this page.
            yr_pattern = rf"{re.escape(date)}[,]?\s+(20\d\d)\b"
            report = list(
                re.finditer(
                    r"results\s+for\s+the\s+three\s+months\s+ended\s+" + yr_pattern,
                    cover["text"],
                    re.I,
                )
            )
            local = list(
                re.finditer(r"(?:six|nine|twelve)\s+months\s+ended\s+" + yr_pattern, text, re.I)
            )
            if not report or not local or len({a[1] for a in report + local}) != 1:
                continue
            year = report[0][1]
            evidence = [
                {"page": cover["number"], "quote": report[0][0]},
                {"page": page["number"], "quote": local[0][0]},
            ]
        if calendar_quarter(date + ", " + year) != (request.year, request.quarter):
            continue
        marker = ""
        for line in text[m.end() :].splitlines():
            line = line.strip()
            if not line:
                continue
            if re.match(r"(?:three|six|nine|twelve)\s+months|^(?:table|notes?)\b", line, re.I):
                break
            # A non-numeric region heading starts a fresh currency context.
            if re.fullmatch(r"[a-z][a-z ,&-]+", line, re.I):
                marker = ""
                continue
            row = re.fullmatch(
                r"(?P<label>[a-z][a-z .,&'-]+?)(?:\s*\([a-z]\))?\s+"
                r"(?P<value>\$?\s*\d[\d,]*(?:\.\d+)?)\s+"
                r"(?P<change>\(?[-+]?\d+(?:\.\d+)?%?\)?|[—–]%?)",
                line,
                re.I,
            )
            if not row or FOREIGN_CURRENCY.search(line):
                break
            value = row["value"].strip()
            if "$" in value:
                marker = line
            if marker and row["label"].strip().casefold() == request.groups[0].casefold():
                yield {
                    "page": page["number"],
                    "year": request.year,
                    "quarter": request.quarter,
                    "column": 1,
                    "raw_cell": [value],
                    "amounts": [value.replace("$", "").strip()],
                    "unit": "美元/可售客房",
                    "label": "RevPAR",
                    "scope": row["label"].strip(),
                    "basis": "",
                    "measure_caption": "",
                    "quote": line,
                    "header": m[0],
                    "unit_quote": marker if marker != line else "",
                    "basis_evidence": evidence,
                    "priority": 0,
                }


def operating_cells(pages, request, calendar_year):
    result = []
    for page in pages:
        lines = [s.strip() for s in page["text"].splitlines() if s.strip()]
        if request.guidance:
            result.extend(_forecast_cells(page["number"], lines, request))
        elif calendar_year:
            result.extend(_level_cells(page["number"], lines, request))
            result.extend(_regional_levels(page, request, pages[0]))
    return result


def low_high_outlook(page, parse_row, make_row):
    """Read two scenario columns only inside a dated, explicitly scaled outlook."""
    lines = [s.strip() for s in page["text"].splitlines() if s.strip()]
    for i in range(2, len(lines)):
        if not re.fullmatch(r"low case\s+high case", lines[i], re.I) or not re.fullmatch(
            r"three months ending", lines[i - 2], re.I
        ):
            continue
        period = calendar_quarter(lines[i - 1])
        labels = lines[max(0, i - 8) : i - 2]
        title = next(
            (
                s
                for s in reversed(labels)
                if re.match(r"^(?:financial )?(?:outlook|guidance|forecast)\b", s, re.I)
            ),
            "",
        )
        units = [
            s
            for s in labels
            if re.fullmatch(
                r"\((?:amounts |dollars )?in (?:millions|billions|thousands)\)", s, re.I
            )
        ]
        if (
            not period
            or not title
            or len(set(units)) != 1
            or FOREIGN_CURRENCY.search(" ".join(labels))
        ):
            continue
        for raw in lines[i + 1 :]:
            row = parse_row(raw)
            if not row or row[2] or len(row[1]) != 2:
                break
            label, cells, _ = row
            if not all(re.fullmatch(r"\$\s*[\d,]+(?:\.\d+)?", value) for value in cells):
                continue
            yield make_row(
                page["number"],
                label,
                raw,
                "\n".join(lines[i - 2 : i + 1]),
                "",
                cells,
                True,
                True,
                forecast_period=period,
                unit_quote=units[0],
                scope_quote=title,
            )
