"""Resolve earnings-release rows with their printed scope, fiscal column, basis and unit.

This reader works on the original stored page text, including reports imported before
the table retriever was added. It never consults an issuer-specific answer catalogue.
"""

import re
from dataclasses import dataclass
from decimal import Decimal

from .finance import numeric
from .table_lookup import SCALE, YEAR

ORDINAL = {"first": 1, "second": 2, "third": 3, "fourth": 4}
QUARTER = re.compile(
    r"\b(?:q([1-4])|([1-4])q)\b|\b(first|second|third|fourth)[ -](?:fiscal )?quarter\b", re.I
)
CN_Q = re.compile(r"第?\s*([一二三四1-4])\s*(?:财季|季度)|\bQ([1-4])\b", re.I)
CELL = r"(?:\(?[+-]?\s*[$€£]?\s*\d[\d,]*(?:\.\d+)?\s*[%BMK]?(?:\)\s*%?)?|[$€£]?[—–]|N/?M)"
TAIL = re.compile(rf"(?P<cells>(?:\s+{CELL}){{2,}})\s*$", re.I)
ATOM = re.compile(CELL, re.I)
RANGE = re.compile(
    r"(?P<lo>\(?-?\$?\s*\d[\d,]*(?:\.\d+)?[BMK%]?\)?)\s+(?:-|–|to)\s+(?P<hi>\(?-?\$?\s*\d[\d,]*(?:\.\d+)?[BMK%]?\)?)\s*$",
    re.I,
)
PERIOD_LINE = re.compile(
    r"quarter|months? ended|year ended|full year|fiscal|^20\d{2}\b|\b(?:Q[1-4]|FY)\s*\d?", re.I
)
SLOTS = re.compile(r"\b(?:19|20)\d{2}\b|\b(?:change|variance)\b", re.I)
SEGMENT = re.compile(
    r"\b(?:segment (?:results|revenues?|information|data)|(?:sales|revenues?) (?:by|streams)|business unit|by (?:offering|segment))\b",
    re.I,
)
GUIDANCE = re.compile(r"\b(?:guidance|outlook|estimates?|forecast)\b", re.I)
FORECAST_VERB = re.compile(
    r"\b(?:we|the company) (?:anticipate[s]?|expect[s]?|forecast[s]?)\b", re.I
)
# In a prose outlook, the following percentage is frequently YoY growth, a separate measure.
BOUND = r"\$?\s*-?\d[\d,]*(?:\.\d+)?(?:\s*(?:billion|million|thousand)\b|[BMK]\b)?"
PROSE_RANGE = re.compile(
    rf"^[•◦▪●*\-]?\s*(?P<label>[A-Za-z][A-Za-z0-9 &()/.'’\-]{{0,85}}?)\s+"
    rf"(?:of|from|between|in (?:the |a )?range of|is expected to (?:be(?: between)?|range from))\s+"
    rf"(?P<lo>{BOUND})\s*(?:\bto\b|\band\b|[–—-])\s*(?P<hi>{BOUND})"
    r"(?=[,.;:]|\s*(?:$|per (?:diluted )?share\b))",
    re.I,
)
SCALE_FACTORS = {
    "thousands": Decimal(1000),
    "millions": Decimal(1000000),
    "billions": Decimal(1000000000),
}
OUTPUT_UNITS = {
    "百万美元": Decimal(1000000),
    "十亿美元": Decimal(1000000000),
    "亿美元": Decimal(100000000),
    "美元": Decimal(1),
}
# These aliases translate questions to common financial row titles, independent of the issuer.
METRICS = [
    ("bookings", r"总预[订定]额|总预订金额|gross bookings?", r"\bgross bookings?\b"),
    (
        "eps",
        r"每股(?:摊薄|稀释)?(?:收益|盈利|利润)|(?:摊薄|稀释)每股|每股盈余|\bEPS\b|earnings per share",
        r"\bEPS\b|per (?:diluted |common )?share|\bdiluted\b",
    ),
    (
        "income",
        r"净利[润潤]|净收益|net (?:income|earnings)",
        r"\bnet (?:income|earnings|loss|profit)\b",
    ),
    (
        "operating",
        r"(?:营业|经营)利[润潤]|operating (?:income|profit|loss)",
        r"\b(?:operating (?:income|profit|loss)|income from operations)\b",
    ),
    ("gross", r"毛利润|毛利额|gross profit", r"\bgross profit\b"),
    (
        "revenue",
        r"营[业業收]|收入|销售额|\brevenues?\b|\bsales\b",
        r"\b(?:revenues?|sales|turnover)\b",
    ),
]
PRODUCTS = [
    (r"汽车|automotive", r"\b(?:automotive|automobile|vehicles?)\b"),
    (r"手机|智能手机|handsets?", r"\b(?:handsets?|smartphones?|mobile phones?)\b"),
    (r"物联网|\bIoT\b", r"\b(?:IoT|internet of things)\b"),
    (r"数据中心|data cent(?:er|re)", r"\bdata cent(?:er|re)s?\b"),
    (r"云服务|云计算|cloud", r"\bcloud\b"),
    (r"游戏|gaming", r"\bgaming\b"),
    (r"出行|客运|\bmobility\b", r"\b(?:mobility|passenger transportation)\b"),
    (r"配送|外卖|\bdelivery\b", r"\b(?:delivery|food delivery)\b"),
    (r"货运|\bfreight\b", r"\b(?:freight|cargo)\b"),
]
SCOPE_WORD = r"(?:业务(?:线)?|事业部|部门|分部|板块|板塊)"
NAMED_SCOPE = re.compile(
    r"(?<![A-Za-z])([A-Za-z][A-Za-z0-9&/-]*(?:[ \t]+[A-Za-z][A-Za-z0-9&/-]*){0,3})[ \t]*(?:[\u3400-\u9fff]{0,6})"
    + SCOPE_WORD
)
CAPTION = re.compile(
    r"(?:gross bookings?|(?:net |total |segment )?(?:revenues?|sales)|gross profit|"
    r"(?:segment |non[- ]GAAP )?operating (?:income|loss|profit)(?: \(loss\))?)",
    re.I,
)
ACRONYM = re.compile(r"\b[A-Z][A-Z0-9&-]{1,12}\b")
RESERVED = {
    "GAAP",
    "NON-GAAP",
    "IFRS",
    "EPS",
    "USD",
    "US",
    "FY",
    "PDF",
    "YOY",
    "EBT",
    "EBIT",
    "EBITDA",
}


def compact(text):
    return " ".join(text.split())


def qnum(text):
    found = QUARTER.search(text)
    if found:
        return int(found[1] or found[2]) if found[1] or found[2] else ORDINAL[found[3].lower()]
    return None


@dataclass(frozen=True)
class Lookup:
    metric: str
    pattern: str
    year: int
    quarter: int | None
    guidance: bool
    adjusted: bool
    unit: str
    groups: tuple
    products: tuple
    qualified: bool


def lookup_request(question):
    if re.search(
        r"新台币|港元|加元|澳元|人民币|欧元|日元|\b(?:CAD|TWD|EUR|HKD|AUD|JPY|CNY)\b",
        question,
        re.I,
    ):
        return None
    years = set(YEAR.findall(question))
    if len(years) != 1 or re.search(
        r"同比|增长率|环比|占比|多少倍|毛利率|原因|解释|比较|趋势|compare|growth rate",
        question,
        re.I,
    ):
        return None
    match = next(
        ((name, row) for name, asked, row in METRICS if re.search(asked, question, re.I)), None
    )
    if not match:
        return None
    quarter = CN_Q.search(question)
    q = None
    if quarter:
        digit = quarter[1] or quarter[2]
        q = "一二三四".index(digit) + 1 if digit in "一二三四" else int(digit)
    else:
        q = qnum(question)
    if q is None and not re.search(
        r"全年|全财年|年度|财年|full.year|fiscal year|annual", question, re.I
    ):
        return None
    metric, pattern = match
    guidance = bool(re.search(r"指引|展望|预测|guidance|outlook", question, re.I))
    unit = next((u for u in OUTPUT_UNITS if u in question), None)
    if metric == "eps":
        unit = "美元/股"
    groups = tuple(
        t
        for t in ACRONYM.findall(question)
        if t not in RESERVED and not re.fullmatch(r"Q[1-4]|FY\d+", t)
    )
    products = [pattern for asked, pattern in PRODUCTS if re.search(asked, question, re.I)]
    # A bilingual question can supply an arbitrary printed offering name. It still
    # has to match a business row AND the metric caption in the uploaded report.
    for m in NAMED_SCOPE.finditer(question):
        name = compact(m[1])
        if (
            name.upper() not in RESERVED
            and name not in groups
            and not re.fullmatch(r"Q[1-4]", name, re.I)
        ):
            products.append(r"\b" + re.escape(name) + r"\b")
    # A city, customer or other unresolved slice must never be silently dropped.
    qualified = bool(
        re.search(
            r"来自|城市|市的|地区|客户|分配给|地域|仅限|\b(?:city of|customer-specific)\b",
            question,
            re.I,
        )
    )
    if not (groups or products) and re.search(
        r"分部|部门|板块|事业部|业务线|业务的|\b(?:division|segment)\b", question, re.I
    ):
        qualified = True
    return Lookup(
        metric,
        pattern,
        int(years.pop()),
        q,
        guidance,
        bool(re.search(r"非\s*GAAP|non[- ]GAAP|adjusted|调整后", question, re.I)),
        unit or "百万美元",
        groups,
        tuple(products),
        qualified,
    )


def data_line(text):
    if len(text) > 520 or not re.search(r"[A-Za-z]", text) or not re.search(r"\d", text):
        return None
    ranged = RANGE.search(text)
    if ranged:
        label = text[: ranged.start()].strip()
        if label and re.search(r"[A-Za-z]", label):
            return label, (ranged["lo"].strip(), ranged["hi"].strip()), True
    match = TAIL.search(text)
    if not match:
        return None
    label = text[: match.start()].strip()
    if (
        not label
        or not re.search(r"[A-Za-z]", label)
        or len(label) > 130
        or re.search(
            r"^(?:Q[1-4]|Fiscal |Year ended|Three months ended)|\b(?:percentages|ended|change)\b",
            label,
            re.I,
        )
    ):
        return None
    cells = tuple(m.group().strip() for m in ATOM.finditer(match["cells"]))
    # Superscripts flatten to a single space after the row name. A currency cell
    # follows the wider column gap. Never discard a negative first data column.
    if re.match(r"^ \(\d{1,2}\) {2,}\$", match["cells"]):
        label = label + " " + cells[0]
        cells = cells[1:]
    if len(cells) < 2 or all(x.isdigit() and YEAR.fullmatch(x) for x in cells):
        return None
    return label, cells, False


@dataclass
class TableRow:
    page: int
    label: str
    line: str
    header: str
    section: str
    cells: tuple
    ranged: bool
    dollars: bool = False


def outlook_period(header):
    for line in reversed(header.splitlines()):
        line = re.sub(r"\b(guidance|outlook|estimates?|forecast)\d{1,2}\b", r"\1", line, flags=re.I)
        if len(line) > 170 or not (GUIDANCE.search(line) or FORECAST_VERB.search(line)):
            continue
        fy = re.search(r"\bFY\s*['’]?(\d{2,4})\b", line, re.I)
        years = {int(y) for y in YEAR.findall(line)}
        if fy:
            y = int(fy[1])
            years.add(2000 + y if y < 100 else y)
        qs = {qnum(m.group()) for m in QUARTER.finditer(line)}
        if (
            len(years) == 1
            and len(qs) <= 1
            and (qs or re.search(r"full[- ]year|fiscal year|annual|\bFY", line, re.I))
        ):
            return years.pop(), next(iter(qs), None)
    return None


def prose_outlook_rows(page):
    """Read ranges under an explicit dated outlook. Finite sections prevent bleed into actuals."""
    heading = ""
    lines = [s.strip() for s in page["text"].splitlines() if s.strip()]
    for i, line in enumerate(lines):
        if (
            len(line) < 170
            and "$" not in line
            and (GUIDANCE.search(line) or FORECAST_VERB.search(line))
        ):
            if "%" in line or re.search(r"\b(?:assumes?|headwind|growth)\b", line, re.I):
                continue
            heading = line if outlook_period(line) else ""
            continue
        if not heading:
            continue
        if re.search(
            r"^(?:actual|financial (?:and operational )?(?:results|highlights)|results (?:by|for)|historical|appendix|reconciliation)\b",
            line,
            re.I,
        ):
            heading = ""
            continue
        # A wrapped range is still one contiguous quotation on this physical page.
        quote = line
        m = PROSE_RANGE.match(quote)
        if not m and i + 1 < len(lines) and "$" in line and not re.match(r"[•◦▪●*]", lines[i + 1]):
            quote = line + "\n" + lines[i + 1]
            m = PROSE_RANGE.match(quote)
        if (
            m
            and "$" in (m["lo"] + m["hi"])
            and not re.search(
                r"\b(?:actual|historical|previous|prior|was|were)\b", m["label"], re.I
            )
        ):
            yield TableRow(
                page["number"],
                m["label"].strip(),
                quote,
                heading,
                "",
                (m["lo"].strip(), m["hi"].strip()),
                True,
                True,
            )
        elif not re.match(r"^[•◦▪●*]", line) and re.match(r"^[A-Z][A-Za-z &/-]{2,70}:?$", line):
            heading = ""


def measure_caption(row):
    for line in reversed([row.section, *row.header.splitlines()]):
        title = line.strip().rstrip(":")
        if CAPTION.fullmatch(title):
            return title
        if re.fullmatch(
            r"(?:[A-Z][\w&-]+ )?(?:revenue|sales) (?:streams|by segment)\d*", title, re.I
        ):
            return title
    return ""


def source_rows(pages):
    """Keep a table's local header until another printed header starts a new table."""
    result = []
    for page in pages:
        result.extend(prose_outlook_rows(page))
        pending = []
        header = ""
        section = ""
        block = []
        dollar_block = False
        for raw in page["text"].splitlines():
            s = raw.strip()
            if not s:
                continue
            row = data_line(s)
            if not row:
                pending.append(s)
                continue
            label, cells, ranged = row
            if pending:
                gap = "\n".join(pending)
                if (
                    not header
                    or SLOTS.search(gap)
                    or PERIOD_LINE.search(gap)
                    or GUIDANCE.search(gap)
                    or len(gap) > 240
                ):
                    header = "\n".join(pending[-18:])
                    # Leave prose behind when a fiscal heading directly precedes the numbers.
                    clean = header.splitlines()
                    while len(clean) > 1 and (
                        len(clean[0]) > 125 or clean[0].endswith((".", ".”"))
                    ):
                        clean.pop(0)
                    header = "\n".join(clean)
                    for h in pending:
                        if len(h) < 95 and SEGMENT.search(re.sub(r"(?<=[A-Za-z])\d+$", "", h)):
                            section = h
                        elif re.search(
                            r"consolidated (?:statements|results)|financial highlights|business outlook|reconciliation",
                            h,
                            re.I,
                        ):
                            section = h
                    block = []
                    dollar_block = bool(re.search(r"\b(?:USD|U\.?S\.? dollars)\b", header, re.I))
                elif len(pending) <= 2 and (
                    label.startswith("(") or label.lower() in {"diluted", "basic"}
                ):
                    label = compact(gap + " " + label)
                elif len(pending) <= 2 and re.search(
                    r"(?:revenue|sales) (?:information|streams)|\bsegments?\b", gap, re.I
                ):
                    section = gap
                pending = []
            item = TableRow(page["number"], label, s, header, section, cells, ranged)
            block.append(item)
            result.append(item)
            if not dollar_block and "$" in s:
                dollar_block = True
                for r in block:
                    r.dollars = True
            item.dollars = dollar_block
    return result


def column_labels(row, release_q):
    """Map groups of repeated year/change columns only when the printed cycles agree."""
    header = row.header
    w = len(row.cells)
    if row.ranged:
        period = outlook_period(header)
        return [(*period, None, False)] if period else []
    # Only the last full column cycle belongs to this table.
    slots = list(SLOTS.finditer(header))
    last_line = header.rsplit("\n", 1)[-1]
    horizontal = list(SLOTS.finditer(header, len(header) - len(last_line)))
    if sum(bool(YEAR.fullmatch(s.group())) for s in horizontal) >= 2:
        # A blank trailing variance column doesn't move the first year column.
        if len(horizontal) < w or any(YEAR.fullmatch(s.group()) for s in horizontal[w:]):
            return []
        slots = horizontal[:w]
    if len(slots) < w:
        return []
    slots = slots[-w:]
    if not any(YEAR.fullmatch(s.group()) for s in slots):
        return []
    first = slots[0].start()
    lead = header[:first]
    lines = lead.splitlines()
    groups = []
    for line in lines:
        tags = line.split()
        if (
            len(tags) >= 2
            and all(re.fullmatch(r"(?:[A-Z][A-Z0-9&-]{1,12}|Non-GAAP|non-GAAP)", t) for t in tags)
            and len(set(tags)) == len(tags)
        ):
            groups = tags
    if groups:
        if w % len(groups):
            return []
        cycle = w // len(groups)
        keys = [s.group().lower() for s in slots]
        if any(keys[j : j + cycle] != keys[:cycle] for j in range(cycle, w, cycle)):
            return []
    else:
        cycle = w
    periods = []
    for line in lines:
        m = re.fullmatch(
            r"((?:First|Second|Third|Fourth) Quarter|Q[1-4]|Three Months Ended)\s+(Fiscal(?: Year)?|Full Year|(?:Six|Nine|Twelve) Months Ended|Years? Ended)",
            line.strip(),
            re.I,
        )
        if m:
            periods = [
                qnum(m[1]) or release_q,
                None if re.search(r"Fiscal|year|twelve", m[2], re.I) else -1,
            ]
    # Detect captions spanning blocks on a shared year row.
    if not periods:
        spans = re.findall(
            r"(?:Three|Six|Nine|Twelve) Months Ended|(?:Full |Fiscal )?Years? Ended", lead, re.I
        )
        if len(spans) in (1, 2) and (len(spans) == 1 or w % 2 == 0):
            periods = [
                (release_q or -1)
                if "three" in x.lower()
                else (None if re.search(r"year|twelve", x, re.I) else -1)
                for x in spans
            ]
    if periods and w % len(periods):
        return []
    if len(periods) > 1:
        keys = [s.group().lower() for s in slots]
        width = w // len(periods)
        if any(keys[j : j + width] != keys[:width] for j in range(width, w, width)):
            return []
    cols = []
    for i, s in enumerate(slots):
        year = int(s.group()) if YEAR.fullmatch(s.group()) else None
        if not year:
            cols.append((None, None, None, True))
            continue
        before = header[slots[i - 1].end() if i else 0 : s.start()]
        direct = re.search(r"\bQ([1-4])\s*(?:Fiscal|FY)?\s*$", before, re.I)
        if direct:
            q = int(direct[1])
        elif periods:
            q = periods[i // (w // len(periods))]
        elif re.search(r"\bFiscal\s*$", before, re.I):
            q = None
        else:
            fiscal_lines = [
                h
                for h in lines
                if len(h) < 90
                and PERIOD_LINE.search(h)
                and not re.search(r"\bannounces\b|Page \d+ of", h, re.I)
            ]
            caption = fiscal_lines[-1] if fiscal_lines else ""
            q = qnum(caption)
            if q is None and not re.search(r"\bfiscal\b|\byear", caption, re.I):
                q = -1
        cols.append((year, q, groups[i // cycle] if groups else None, False))
    return cols


def resolve_sources(pages, req, rows=None):
    """Produce eligible original cells. A model can select an ID, never supply an amount."""
    if req.qualified:
        return []
    release_q = qnum(compact(pages[0]["text"][:400])) if pages else None
    result = []
    for row in source_rows(pages) if rows is None else rows:
        if req.guidance != row.ranged:
            continue
        caption = (
            measure_caption(row)
            if req.products
            or any(re.search(r"\b" + re.escape(g) + r"\b", row.label, re.I) for g in req.groups)
            else ""
        )
        if not re.search(req.pattern, row.label, re.I) and not (
            caption and re.search(req.pattern, caption, re.I)
        ):
            continue
        if req.products and not all(re.search(p, row.label, re.I) for p in req.products):
            continue
        if req.metric == "revenue" and re.search(
            r"\b(?:cost|expense|margin|percent|ratio|growth|change|EBT)\b|%", row.label, re.I
        ):
            continue
        if req.metric == "eps" and re.search(
            r"\b(?:less|basic|dividend|adjustment|outstanding|weighted|denominator|attributable to (?!common))\b",
            row.label,
            re.I,
        ):
            continue
        if req.metric != "eps" and "per share" in row.label.lower():
            continue
        if (
            req.metric == "bookings"
            and not (req.products or req.groups)
            and not re.fullmatch(r"(?:total |consolidated )?gross bookings?", row.label, re.I)
        ):
            continue
        cols = column_labels(row, release_q)
        for i, (year, q, group, change) in enumerate(cols):
            if change or year != req.year or q != req.quarter:
                continue
            basis = group if group and "gaap" in group.lower() else ""
            if req.adjusted != bool(
                re.search(r"non[- ]gaap|adjusted", basis + " " + row.label, re.I)
            ):
                continue
            section = row.section
            seg_group = group if group and not basis else ""
            scope = " ".join([seg_group, section, row.label])
            if req.groups and not all(
                re.search(r"\b" + re.escape(g) + r"\b", scope, re.I) for g in req.groups
            ):
                continue
            if seg_group and not any(g.casefold() == seg_group.casefold() for g in req.groups):
                continue
            if not (req.groups or req.products) and (SEGMENT.search(section) or seg_group):
                continue
            if (
                not (req.groups or req.products)
                and req.metric == "revenue"
                and not re.fullmatch(
                    r"(?:GAAP |Non-GAAP |Adjusted |Consolidated |Total |Net |Operating )*(?:Revenues?|Net Sales|Sales|Turnover)(?:\d{1,2}| \(\d+\))?",
                    row.label,
                    re.I,
                )
            ):
                continue
            raw = row.cells if row.ranged else (row.cells[i],)
            if (
                row.ranged
                and req.groups
                and not all(g in ACRONYM.findall(row.label) for g in req.groups)
            ):
                continue
            scale = SCALE.search(compact(row.header))
            if not row.dollars or re.search(
                r"(?<![A-Za-z])(?:C|CA|A|HK|NT|S)\$|\b(?:CAD|AUD|HKD|TWD|SGD|EUR)\b",
                row.header + " " + row.line,
            ):
                continue
            amounts = []
            bound_units = [
                re.search(r"(billion|million|thousand|[BMK])$", v.strip(), re.I) for v in raw
            ]
            shared = (
                bound_units[-1] if row.ranged and len(raw) == 2 and not bound_units[0] else None
            )
            for value, explicit in zip(raw, bound_units, strict=True):
                if explicit:
                    value = value[: explicit.start()]
                token = value.strip().replace("$", "").replace(" ", "")
                magnitude = explicit or shared
                if magnitude:
                    if req.metric == "eps":
                        break
                    factor = {
                        "b": Decimal(10**9),
                        "m": Decimal(10**6),
                        "t": Decimal(1000),
                        "k": Decimal(1000),
                    }[magnitude[1][0].lower()]
                elif req.metric == "eps":
                    factor = Decimal(1)
                elif scale:
                    factor = SCALE_FACTORS[scale[1].lower()]
                else:
                    break
                try:
                    amount = numeric(token) * factor / OUTPUT_UNITS.get(req.unit, Decimal(1))
                except ValueError:
                    break
                amounts.append(f"{amount:,f}")
            if len(amounts) != len(raw):
                continue
            if row.ranged and Decimal(amounts[0].replace(",", "")) > Decimal(
                amounts[-1].replace(",", "")
            ):
                continue
            score = (4 if basis else 0) + (3 if req.groups or req.products else 0)
            if re.search(r"reconciliations?|supplemental information", row.header, re.I):
                score -= 5
            result.append(
                {
                    "page": row.page,
                    "label": row.label,
                    "scope": seg_group or section,
                    "measure_caption": caption,
                    "basis": basis,
                    "year": year,
                    "quarter": q,
                    "column": i + 1,
                    "raw_cell": list(raw),
                    "amounts": amounts,
                    "unit": req.unit,
                    "quote": row.line,
                    "header": row.header,
                    "priority": score,
                }
            )
    return sorted(result, key=lambda c: (-c["priority"], c["page"], c["column"]))
