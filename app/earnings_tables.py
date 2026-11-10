"""Resolve earnings-release rows with their printed scope, fiscal column, basis and unit.

This reader works on the original stored page text, including reports imported before
the table retriever was added. It never consults an issuer-specific answer catalogue.
"""

import re
from dataclasses import dataclass, replace
from decimal import Decimal

from .finance import numeric
from .growth_guidance import growth_guidance_cells
from .lodging_metrics import HOTEL_METRIC, HOTEL_METRICS, low_high_outlook, operating_cells, operating_request
from .metric_grids import metric_grid_rows, metric_outlook_rows, supported_growth
from .revised_outlook import outlook_version, revised_annual_cells
from .quarter_schedules import schedule_cells
from .table_lookup import SCALE, YEAR

ORDINAL = {"first": 1, "second": 2, "third": 3, "fourth": 4}
QUARTER = re.compile(
    r"\b(?:q([1-4])|([1-4])q)\b|\b(first|second|third|fourth)[ -](?:fiscal )?quarter\b", re.I
)
CN_Q = re.compile(r"第?\s*([一二三四1-4])\s*(?:财季|季度)|\bQ([1-4])\b", re.I)
CELL = r"(?:[$€£]\s*\(\s*\d[\d,]*(?:\.\d+)?\s*\)|\(?[+-]?\s*[$€£]?\s*\d[\d,]*(?:\.\d+)?\s*[%BMK]?(?:\)\s*%?)?|[$€£]?[—–]|N/?M)"
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
    rf"(?:of|from|between|in (?:the |a )?range of|is (?:expected|projected) to (?:be(?: between)?|range from))\s+"
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
    "百万个": Decimal(1000000),
    "个": Decimal(1),
    "百万间夜": Decimal(1000000),
    "间夜": Decimal(1),
}
# These aliases translate questions to common financial row titles, independent of the issuer.
COMPANY_EXPENSES_ZH = (
    r"(?:^|[，,。?？：:\s]|季度|财季|全年|集团|公司|合并利润表|合并损益表)(?:的)?"
    r"(?:总费用|费用(?:合计|总额))"
)
EXPENSE_QUESTION_WORDS = set(
    "what was were is are how much the did company group s its report reported consolidated "
    "total expenses for in of during as at and from please show give exact amount quarter "
    "first second third fourth fiscal year ended q fy us usd dollars million millions "
    "billion billions income statement statements operations gaap".split()
)
METRICS = [
    ("free_cash_flow", r"自由现金流|free cash flow", r"^free cash flow(?: \(\d+\))?$"),
    ("room_nights", r"间夜数|room nights", r"^(?:booked )?room nights$"),
    (
        "adr",
        r"\bADR\b|平均(?:每日房价|预订价格)|average daily rate",
        r"\b(?:ADR|average daily rate)\b",
    ),
    (
        "booked_count",
        r"预订住宿晚数|nights (?:and seats )?booked",
        r"^(?:room )?nights (?:and seats )?booked$",
    ),
    (
        "development_expense",
        r"产品开发费|\bproduct development\b",
        r"^product development(?: expense[s]?)?(?: \(\d+\))?$",
    ),
    (
        "ebitda",
        r"(?:调整后|adjusted)\s*EBITDA(?!\s*(?:利润率|率|margin))",
        r"^adjusted EBITDA(?: \(\d+\)|\*+)?$",
    ),
    ("bookings", r"总预[订定]额|总预订金额|gross bookings?", r"\bgross bookings?\b"),
    ("interest_expense", r"利息(?:费用?|支出|开支)|\binterest expense\b", r"^interest expense(?:,? net)?$"),
    (
        "total_expenses",
        COMPANY_EXPENSES_ZH + r"|\btotal expenses\b",
        r"^total (?:costs and )?expenses$",
    ),
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
    "ADR",
    "GBV",
}
INCOME_STATEMENT = re.compile(
    r"^(?:(?:condensed|consolidated|combined|unaudited|interim)\s+)*"
    r"(?:statements? of (?:operations|income|earnings|profit (?:and|or) loss)|income statements?)$",
    re.I,
)
REVENUE_HEADING = re.compile(r"(?:(?:net )?revenues?|net sales|sales)\s*:?", re.I)
BEFORE_NCI = re.compile(
    r"(?:分配给|归属(?:于)?)\s*(?:非控股|少数股东)(?:权益|损益|股东)?(?:之?前|前)|"
    r"before (?:allocation|attribution) to (?:non[- ]?controlling|minority) interests?", re.I
)


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
    exact_amount: bool = False
    diluted_eps: bool = False
    growth_basis: str = ""
    parent_income: bool = False
    revenue_line: str = ""
    income_before_nci: bool = False
    outlook_version: str = ""
    comparable_hotels: bool = False


def lookup_request(question):
    if re.search(
        r"新台币|港元|加元|澳元|人民币|欧元|日元|\b(?:CAD|TWD|EUR|HKD|AUD|JPY|CNY)\b",
        question,
        re.I,
    ):
        return None
    years = set(YEAR.findall(question))
    guidance = bool(re.search(r"指引|展望|预测|预计|guidance|outlook", question, re.I))
    hotel = HOTEL_METRIC.search(question)
    if hotel and len(years) == 1:
        found = CN_Q.search(question)
        quarter = qnum(question)
        if found:
            digit = found[1] or found[2]
            quarter = "一二三四".index(digit) + 1 if digit in "一二三四" else int(digit)
        request = operating_request(question, int(years.pop()), quarter, guidance, Lookup)
        return replace(request, outlook_version=outlook_version(question)) if guidance else request
    growth_range = bool(guidance and re.search(r"同比增长|year.over.year growth|yoy growth",question,re.I)
                        and re.search(r"区间|端点|range",question,re.I))
    if len(years) != 1 or (not growth_range and re.search(
        r"同比|增长率|环比|占比|多少倍|毛利率|原因|解释|比较|趋势|compare|growth rate",
        question,
        re.I,
    )):
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
    if metric=="free_cash_flow" and re.search(r"TTM|滚动|trailing|转换率|margin|率",question,re.I):
        return None
    unit = next((u for u in OUTPUT_UNITS if u in question), None)
    if metric == "eps":
        unit = "美元/股"
    elif metric == "adr":
        unit = "美元"
    elif metric in {"booked_count", "room_nights"}:
        if any(symbol in question for symbol in ("美元", "$", "USD")):
            return None
        count_unit = "间夜" if metric == "room_nights" else "个"
        unit = ("百万" if "百万" in question else "") + count_unit
    groups = tuple(dict.fromkeys(
        t
        for t in ACRONYM.findall(question)
        if t not in RESERVED and not re.fullmatch(r"Q[1-4]|FY\d+", t)
    ))
    products = [pattern for asked, pattern in PRODUCTS if re.search(asked, question, re.I)]
    # A parenthesized source row is a request for that revenue category.
    # Only accept its exact printed label, never the group total.
    revenue_line = ""
    if metric == "revenue":
        # The source row name can be paired with a locally printed category, e.g.
        # “Maintenance fees” in the revenues section. Never resolve it to a total.
        for named in re.finditer(r"[(（]([A-Za-z][A-Za-z0-9 ,&/'-]{0,70})[)）]", question):
            if re.search(r"\b(?:sales|revenues?)$", named[1], re.I):
                continue
            if re.match(r"\s*(?:的|列在|计入|属于)?\s*(?:营收|收入|销售额)", question[named.end():]) or re.search(
                r"(?:收入项下|收入分项|营收分项|服务费|授权费|许可费|自有酒店|自营酒店)[^，。；！？,;?]{0,16}$",
                question[:named.start()],
            ):
                revenue_line = compact(named[1])
                break
        if not revenue_line and re.search(r"特许(?:经营)?(?:及|和|与)(?:授权|许可)费", question):
            revenue_line = "Franchise and licensing fees"
        elif not revenue_line and re.search(r"自有酒店(?:业务)?(?:的)?(?:营收|收入|销售额)", question):
            revenue_line = "Ownership"
        row_names = re.findall(
            r"[(（]([A-Za-z][A-Za-z &/-]{0,60}\s+(?:revenues?|sales))[)）]", question, re.I
        )
        products.extend(r"^" + re.escape(compact(name)) + r"$" for name in row_names)
        for name in re.findall(r"[(（]([A-Za-z][A-Za-z &/-]{0,60})[)）]\s*产品", question):
            products.append(r"^" + re.escape(compact(name)) + r"$")
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
    income_before_nci = metric == "income" and bool(BEFORE_NCI.search(question))
    qualifiers = BEFORE_NCI.sub("", question) if income_before_nci else question
    qualified = bool(
        re.search(
            r"来自|城市|市的|地区|客户|分配给|地域|仅限|品牌|单一国家|\b(?:city of|customer-specific)\b",
            qualifiers,
            re.I,
        )
    )
    if not (groups or products or revenue_line) and re.search(
        r"分部|部门|板块|事业部|业务线|业务(?:的|收入|营收)|收入(?:项下|类型|分项)|费(?:的)?(?:营收|收入)|产品(?:的|拆分)|模式的(?:营收|收入)|\b(?:division|segment)\b",
        re.sub(r"(?:全部|所有|整体)业务的?", "", question), re.I
    ):
        qualified = True
    if metric == "development_expense" and re.search(
        r"股权|股份|薪酬|stock.based|share.based", question, re.I
    ):
        qualified = True
    if metric in {"interest_expense", "total_expenses"}:
        requested_basis = re.sub(r"(?:不要|别用|不用|排除|而非|而不是|不取|不采用)[^，。！？；,;?]*", "", question)
        if re.search(r"加回|调节表|调整表|add.back|reconciliation", requested_basis, re.I):
            qualified = True
    if metric == "total_expenses":
        # A printed total label can be a subtotal for a narrower scope. Accept
        # the group reading only if the question has no unexplained qualifier.
        if re.search(r"只看|只计|只含|仅看|仅计|仅含|限于|分项|费用类别", question):
            qualified = True
        if re.search(r"总费用|费用(?:合计|总额)", question) and not re.search(COMPANY_EXPENSES_ZH, question):
            qualified = True
        english_terms = re.findall(r"[a-z]+", question.casefold())
        if set(english_terms) - EXPENSE_QUESTION_WORDS:
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
        bool(re.search(r"精确|准确金额|exact amount", question, re.I)),
        metric == "eps" and bool(re.search(r"摊薄|稀释|\bdiluted\b", question, re.I)),
        ("constant" if re.search(r"固定汇率|恒定汇率|不变汇率|constant.currency",question,re.I) else "reported")
        if growth_range else "",
        metric == "income" and bool(re.search(r"归母|归属(?:于)?母公司|attributable to (?:the )?parent",question,re.I)),
        revenue_line,
        income_before_nci,
        outlook_version(question) if guidance else "",
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
    expense_heading: str = ""
    per_share_heading: str = ""
    forecast_period: tuple | None = None
    unit_quote: str = ""
    unit_page: int | None = None
    reconciliation_total: bool = False
    period_columns: tuple = ()
    scope_quote: str = ""
    growth_line: str = ""
    revenue_heading: str = ""
    statement_title: str = ""


YEAR_BAND = re.compile(r"(?:\d{4}\s+)*\d{4}")
QUARTER_BAND = re.compile(r"Q[1-4](?:\s+Q[1-4])+", re.I)


def grid_columns(header):
    """Bind year spanners to complete ordered quarter runs. Never zip years to cells."""
    lines = header.splitlines()
    if len(lines) != 2 or not YEAR_BAND.fullmatch(lines[0]) or not QUARTER_BAND.fullmatch(lines[1]):
        return []
    years = [int(s) for s in lines[0].split()]
    quarters = [int(s[1]) for s in lines[1].upper().split()]
    if any(b != a + 1 for a, b in zip(years, years[1:])):
        return []
    if any(b != a % 4 + 1 for a, b in zip(quarters, quarters[1:])):
        return []
    year = years[0]
    cols = []
    for i, quarter in enumerate(quarters):
        if i and quarter == 1:
            year += 1
        cols.append((year, quarter, None, False))
    return cols if year == years[-1] else []


def quarterly_grid_rows(page):
    """Read wrapped row labels and separate value lines as contiguous PDF quotations."""
    lines = [line.strip() for line in page["text"].splitlines() if line.strip()]
    header, width, fragments = "", 0, []
    for i, line in enumerate(lines):
        if YEAR_BAND.fullmatch(line):
            header, width, fragments = "", 0, []
            continue
        if i and QUARTER_BAND.fullmatch(line):
            header = lines[i - 1] + "\n" + line
            width = len(grid_columns(header))
            fragments = []
            continue
        if not width:
            continue
        quote = "\n".join([*fragments, line])
        parsed = data_line(compact(quote))
        if parsed and not parsed[2] and len(parsed[1]) == width:
            label, cells, _ = parsed
            yield TableRow(page["number"], label, quote, header, "", cells, False, "$" in quote)
            fragments = []
        elif (
            len(line) < 75
            and re.fullmatch(r"[A-Za-z(][A-Za-z /().&’-]*", line)
            and len(fragments) < 4
        ):
            fragments.append(line)
        else:
            fragments = []


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


def prose_range(source):
    lead = re.sub(
        r"^[\s¦•◦▪●*\-]*(?:we (?:expect|anticipate) to (?:generate|report|achieve)\s+)",
        "",
        source,
        flags=re.I,
    )
    return PROSE_RANGE.match(lead)


def prose_outlook_rows(page):
    """Read ranges under an explicit dated outlook. Finite sections prevent bleed into actuals."""
    heading = ""
    in_outlook = False
    subperiod = None
    lines = [s.strip() for s in page["text"].splitlines() if s.strip()]
    for i, line in enumerate(lines):
        if re.fullmatch(r"(?:financial |business )?(?:outlook|guidance)\s*:?", line, re.I):
            in_outlook, heading, subperiod = True, "", None
            continue
        if re.match(
            r"^(?:actual|financial (?:and operational )?(?:results|highlights)|results (?:by|for)|historical|appendix|reconciliation|(?:first|second|third|fourth) quarter results)\b",
            line,
            re.I,
        ):
            in_outlook, heading, subperiod = False, "", None
            continue
        if in_outlook and re.fullmatch(r"(?:Q[1-4]|(?:first|second|third|fourth) quarter|full[- ]year|FY)\s+20\d{2}", line, re.I):
            heading, subperiod = line, (int(line[-4:]), qnum(line))
            continue
        if (
            len(line) < 170
            and "$" not in line
            and (GUIDANCE.search(line) or FORECAST_VERB.search(line))
        ):
            if "%" in line or re.search(r"\b(?:assumes?|headwind|growth)\b", line, re.I):
                continue
            dated = outlook_period(line)
            if dated:
                heading, subperiod = line, None
            elif not in_outlook:
                heading, subperiod = "", None
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
        m = prose_range(quote)
        if not m and i + 1 < len(lines) and "$" in line and not re.match(r"[•◦▪●*]", lines[i + 1]):
            quote = line + "\n" + lines[i + 1]
            m = prose_range(quote)
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
                forecast_period=subperiod,
            )
        elif not re.match(r"^[•◦▪●*]", line) and re.match(r"^[A-Z][A-Za-z &/-]{2,70}:?$", line):
            heading = ""


def measure_caption(row):
    if row.scope_quote:
        return row.section
    for line in reversed([row.section, *row.header.splitlines()]):
        title = line.strip().rstrip(":")
        if CAPTION.fullmatch(title):
            return title
        if re.fullmatch(
            r"(?:[A-Z][\w&-]+ )?(?:revenue|sales) (?:streams|by segment)\d*", title, re.I
        ):
            return title
    return ""


def trailing_statement_unit(page):
    """PDF text order can put a single statement's title and units after its printed page number."""
    lines = [line.strip() for line in page["text"].splitlines() if line.strip()]
    if len(lines) < 4:
        return ""
    unit = lines[-1]
    if not re.fullmatch(
        r"\((?:amounts |dollars )?in (?:millions|billions|thousands)(?:,? except (?:for )?per share (?:data|amounts))?\)",
        unit, re.I,
    ):
        return ""
    for count in (1, 2, 3):
        if len(lines) < count + 3 or not lines[-count-2].isdigit():
            continue
        title = " ".join(lines[-count-1:-1])
        if re.fullmatch(
            r"(?:unaudited )?(?:consolidated |combined )?(?:statements? of (?:operations|income|earnings|cash flows)|balance sheets?)",
            title, re.I,
        ):
            body = lines[:-count-2]
            # A shared page can contain multiple, independently scaled tables.
            if sum(bool(YEAR_BAND.fullmatch(compact(line)) and len(line.split()) > 1) for line in body) != 1:
                return ""
            if any(SCALE.search(line) for line in body):
                return ""
            return unit
    return ""


RECON_HEADING = re.compile(r"^RECONCILIATION OF\b", re.I)
RECON_UNIT = re.compile(
    r"\((?:amounts |dollars )?in (?:millions|billions|thousands)(?:,? except (?:for )?per share (?:data|amounts))?\)(?:\(\d+\))*", re.I
)
FOREIGN_UNIT = re.compile(r"(?<![A-Za-z])(?:C|CA|A|HK|NT|S)\$|\b(?:CAD|AUD|HKD|TWD|SGD|EUR)\b")


@dataclass
class ReconciliationBlock:
    title: str
    header: str
    rows: dict


def reconciliation_blocks(lines):
    """Bind each bridge to the dated header that starts it, not wrapped adjustment names."""
    starts = [i for i,line in enumerate(lines) if RECON_HEADING.search(line)]
    blocks = []
    for start,end in zip(starts,[*starts[1:],len(lines)]):
        entries = lines[start:end]
        year_band = next((i for i,s in enumerate(entries[:11]) if YEAR_BAND.fullmatch(compact(s)) and len(s.split())>1),None)
        if year_band is None:
            continue
        period_start = next((i for i,s in enumerate(entries[:year_band]) if re.search(r"\bmonths? ended|fiscal year ended|years? ended",s,re.I)),None)
        if period_start is None:
            continue
        rows = {}
        for line in entries[year_band+1:]:
            if (re.match(r"^(?:notes?:|\(\d+\)\s+[A-Za-z]|(?:actual|financial) results\b|consolidated statements? of\b|(?:three|six|nine|twelve) months? ended\b)",line,re.I)
                    or line.isdigit() or YEAR_BAND.fullmatch(compact(line))):
                break
            parsed = data_line(line)
            if parsed and not parsed[2] and len(parsed[1]) == len(entries[year_band].split()):
                rows[line] = parsed
        blocks.append(ReconciliationBlock("\n".join(entries[:period_start]), "\n".join(entries[period_start:year_band+1]),rows))
    return blocks


def reconciliation_totals(pages):
    """Recover the scale of a continued non-GAAP reconciliation, with a cited prior page."""
    prior_page = None
    prior_blocks = []
    previous_unit = ""
    for page in pages:
        lines = [s.strip() for s in page["text"].splitlines() if s.strip()]
        blocks = reconciliation_blocks(lines)
        explicit_units = [s for s in lines if RECON_UNIT.fullmatch(s)]
        # The scale belongs to the reconciliation schedule as a whole only when
        # the document prints it under that schedule's title adjacent to the unit.
        schedule_unit = next((s for i,s in enumerate(lines) if s in explicit_units and re.search(
            r"reconciliation of (?:gaap to non.gaap|non.gaap) financial (?:information|measures)$",
            compact(" ".join(lines[max(0,i-2):i])),re.I)), "")
        scales = {match[1].lower() for match in SCALE.finditer(page["text"])}
        clean = bool(blocks and lines and RECON_HEADING.search(lines[0])
                     and not FOREIGN_UNIT.search(page["text"]) and len(scales)<=1)
        applicable = ""
        unit_page = page["number"]
        if clean and schedule_unit and len(set(explicit_units)) == 1:
            applicable = schedule_unit
        elif clean and prior_page is not None and prior_page+1 == unit_page and previous_unit and not any(SCALE.search(s) for s in lines):
            # A matching fiscal header and the same multi-period, dollar-valued GAAP
            # anchor prevent carrying a scale from a neighbouring, unrelated table.
            anchor_headers = {
                b.header for b in blocks for prior in prior_blocks if b.header==prior.header
                and any(line in prior.rows and "$" in line and re.fullmatch(
                    r"(?:net income|net loss|total revenues?|income before taxes|net (?:income|cash) provided by operating activities)",
                    parsed[0],re.I) for line,parsed in b.rows.items())
            }
            if anchor_headers and all(b.header in anchor_headers for b in blocks):
                applicable,unit_page = previous_unit,prior_page
        if applicable:
            for block in blocks:
                for line,(label,cells,_) in block.rows.items():
                    if not re.fullmatch(r"adjusted EBITDA|free cash flow", label,re.I):
                        continue
                    if not re.search(r"\bTO "+re.escape(label)+r"$",compact(block.title),re.I):
                        continue
                    yield TableRow(page["number"],label,line,block.header,block.title,cells,False,
                                   dollars="$" in line,unit_quote=applicable,unit_page=unit_page,
                                   reconciliation_total=True)
        prior_page = page["number"]
        prior_blocks = blocks
        previous_unit = schedule_unit if clean and len(set(explicit_units))==1 else ""


def source_rows(pages, *, calendar_year=False):
    """Keep a table's local header until another printed header starts a new table."""
    result = []
    for page in pages:
        unit_quote = trailing_statement_unit(page)
        result.extend(prose_outlook_rows(page))
        result.extend(quarterly_grid_rows(page))
        result.extend(metric_grid_rows(page, data_line, TableRow))
        result.extend(metric_outlook_rows(page, TableRow))
        if calendar_year:
            result.extend(low_high_outlook(page, data_line, TableRow))
        pending = []
        header = ""
        section = ""
        block = []
        dollar_block = False
        expense_heading = per_share_heading = revenue_heading = statement_title = ""
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
                    expense_heading = per_share_heading = revenue_heading = ""
                    dollar_block = bool(re.search(r"\b(?:USD|U\.?S\.? dollars)\b", header, re.I))
                elif len(pending) <= 2 and (
                    label.startswith("(") or label.lower() in {"diluted", "basic"}
                ):
                    label = compact(gap + " " + label)
                elif len(pending) <= 2 and re.search(
                    r"(?:revenue|sales) (?:information|streams)|\bsegments?\b", gap, re.I
                ):
                    section = gap
                for h in pending:
                    if INCOME_STATEMENT.fullmatch(h):
                        statement_title = h
                    elif re.search(
                        r"reconciliation|statements? of|balance sheets?|cash flow statements?|"
                        r"financial highlights|operating statistics", h, re.I,
                    ):
                        statement_title = revenue_heading = ""
                    if REVENUE_HEADING.fullmatch(h):
                        revenue_heading = h
                        expense_heading = ""
                    if re.fullmatch(
                        r"(?:operating |total )?(?:costs and expenses|operating expenses|expenses)\s*:?",
                        h,
                        re.I,
                    ):
                        expense_heading = h
                        revenue_heading = ""
                if label.split()[-1].casefold() in {"basic", "diluted"}:
                    per_share_heading = (
                        gap
                        if re.search(r"per share|weighted.average shares|shares used", gap, re.I)
                        else ""
                    )
                pending = []
            # A parenthesized first amount can be a negative. Strip it only if an
            # extra column AND a matching source footnote identify a reference.
            years_line = header.splitlines()[-1] if header else ""
            if (
                cells
                and re.fullmatch(r"\(\d{1,2}\)", cells[0])
                and len(cells) == len(SLOTS.findall(years_line)) + 1
                and re.search(r"(?m)^\s*" + re.escape(cells[0]) + r"\s+[A-Za-z]", page["text"])
            ):
                label = label + " " + cells[0]
                cells = cells[1:]
            item = TableRow(
                page["number"],
                label,
                s,
                header,
                section,
                cells,
                ranged,
                expense_heading=expense_heading,
                per_share_heading=per_share_heading,
                unit_quote=unit_quote,
                revenue_heading=revenue_heading,
                statement_title=statement_title,
            )
            if grid_columns(header):
                continue  # This table was already parsed with its multiline labels intact.
            block.append(item)
            result.append(item)
            if not dollar_block and "$" in s:
                dollar_block = True
                for r in block:
                    r.dollars = True
            item.dollars = dollar_block
            if re.fullmatch(r"(?:total (?:revenues?|net sales|sales)|net revenues?)", label, re.I):
                revenue_heading = ""
    result.extend(reconciliation_totals(pages))
    return result


def column_labels(row, release_q):
    """Map groups of repeated year/change columns only when the printed cycles agree."""
    header = row.header
    w = len(row.cells)
    if row.ranged:
        period = row.forecast_period or outlook_period(header)
        return [(*period, None, False)] if period else []
    if row.period_columns:
        return row.period_columns
    grid = grid_columns(header)
    if grid:
        return grid if len(grid) == w else []
    # Summary tables with one amount and a variance column often follow narrative
    # text that mentions earlier fiscal years. Those years are not column labels.
    lines = header.splitlines()
    if lines and re.fullmatch(
        r"\s*\(#\)\s*\(\s*(?:Δ|change)\s*(?:Y/Y|YoY)\s*\)\s*", lines[-1], re.I
    ):
        period = re.fullmatch(r"Q([1-4])\s+(20\d{2})", lines[-2].strip(), re.I) if len(lines) > 1 else None
        if not period or w != 2:
            return []
        return [(int(period[2]), int(period[1]), None, False), (None, None, None, True)]
    # Only the last full column cycle belongs to this table.
    slots = list(SLOTS.finditer(header))
    last_line = header.rsplit("\n", 1)[-1]
    if re.match(r"^(?:metric|measure|item)\s+Q[1-4]\b", last_line, re.I):
        named = re.findall(r"\bQ[1-4]\s+20\d{2}\b", last_line, re.I)
        if len(named) != len(set(s.upper() for s in named)):
            return []
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
        if INCOME_STATEMENT.fullmatch(line.strip()):
            # An uppercase company heading can precede the statement title.
            # Only labels inside the table may name segment columns.
            groups = []
            continue
        tags = line.split()
        if (
            len(tags) >= 2
            and not re.search(r"\b(?:statements? of|reconciliations? of|net income|adjusted EBITDA)\b", line, re.I)
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
            r"(?:Three|Six|Nine|Twelve) Months Ended|(?:Full |Fiscal )?Years? Ended",
            compact(lead),
            re.I,
        )
        # Multiple quarter-end dates in a single historical series cannot all
        # inherit the release quarter. The dated series needs individual bindings.
        if (
            len(
                set(
                    re.findall(
                        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}\b",
                        compact(header),
                        re.I,
                    )
                )
            )
            > 1
            and spans
        ):
            return []
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


def resolve_sources(pages, req, rows=None, *, cited_cash_flow=False, calendar_year=False):
    """Produce eligible original cells. A model can select an ID, never supply an amount."""
    if req.qualified:
        return []
    if req.guidance and req.quarter is None and req.metric in {"revpar", "ebitda"}:
        revised = revised_annual_cells(pages, req)
        if revised or req.outlook_version == "prior":
            return revised
    if req.metric in HOTEL_METRICS:
        return operating_cells(pages, req, calendar_year)
    if req.growth_basis:
        found = growth_guidance_cells(pages, req)
        if found or req.growth_basis != "reported" or req.groups or req.products:
            return found
        rows = source_rows(pages) if rows is None else rows
        if not any(row.growth_line for row in rows):
            return []
        money = replace(req, guidance=True, growth_basis="", unit="百万美元")
        outlook = resolve_sources(pages, money, rows)
        prior = resolve_sources(pages, replace(money, guidance=False, year=req.year - 1), rows)
        return supported_growth(outlook, prior)
    release_q = qnum(compact(pages[0]["text"][:400])) if pages else None
    if not release_q:
        for page in pages[:3]:
            title = re.search(
                r"(?im)^\s*(Q[1-4])\s+(?:FY\s*)?20\d{2}\s+(?:shareholder letter|earnings (?:release|report)|financial results)\b",
                page["text"][:600],
            )
            if title:
                release_q = int(title[1][1])
                break
    result = schedule_cells(pages, req, SCALE_FACTORS, OUTPUT_UNITS)
    for row in source_rows(pages, calendar_year=calendar_year) if rows is None else rows:
        if req.metric=="free_cash_flow" and not (row.reconciliation_total or cited_cash_flow):
            continue
        if req.guidance != row.ranged:
            continue
        caption = (
            measure_caption(row)
            if req.products
            or any(re.search(r"\b" + re.escape(g) + r"\b", row.label, re.I) for g in req.groups)
            else ""
        )
        statement = row.statement_title
        if req.revenue_line:
            if (not statement or not row.revenue_heading
                    or compact(row.label).casefold() != req.revenue_line.casefold()):
                continue
            caption = row.revenue_heading
        if req.metric in {"interest_expense", "total_expenses"} and not statement:
            continue
        if req.income_before_nci and (not statement or not re.fullmatch(
            r"(?:consolidated )?net (?:income|earnings|profit|loss)(?: \(loss\))?", row.label, re.I
        )):
            continue
        if req.metric == "operating" and re.search(r"\bnon[- ]?operating\b", row.label, re.I):
            continue
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
        if req.parent_income and (
            not re.search(r"\b(?:attributable|available) to\b", row.label, re.I)
            or re.search(r"non[- ]?controlling|minority", row.label, re.I)
        ):
            continue
        if req.metric == "eps" and row.label.casefold() == "diluted":
            if re.search(r"weighted.average|shares used", row.per_share_heading, re.I) or (
                not row.per_share_heading and not all("$" in cell for cell in row.cells)
            ):
                continue
        if req.metric == "development_expense" and not row.expense_heading:
            continue
        if req.metric != "eps" and re.search(
            r"\bper(?: basic| diluted| common| ordinary)* share\b", row.label, re.I
        ):
            continue
        if (
            req.metric == "bookings"
            and not (req.products or req.groups)
            and not re.fullmatch(
                r"(?:total |consolidated )?gross booking(?:s| value)?", row.label, re.I
            )
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
                not (req.groups or req.products or req.revenue_line)
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
            scale = SCALE.search(compact(row.header)) or SCALE.search(row.unit_quote)
            count_metric = req.metric in {"booked_count", "room_nights"}
            if (not row.dollars and not count_metric) or re.search(
                r"(?<![A-Za-z])(?:C|CA|A|HK|NT|S)\$|\b(?:CAD|AUD|HKD|TWD|SGD|EUR)\b",
                " ".join((row.header, row.line, row.unit_quote)),
            ):
                continue
            if count_metric and any("$" in value for value in raw):
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
                    if req.metric in {"eps", "adr"}:
                        break
                    factor = {
                        "b": Decimal(10**9),
                        "m": Decimal(10**6),
                        "t": Decimal(1000),
                        "k": Decimal(1000),
                    }[magnitude[1][0].lower()]
                elif req.metric in {"eps", "adr"}:
                    factor = Decimal(1)
                elif scale:
                    factor = SCALE_FACTORS[scale[1].lower()]
                elif count_metric:
                    factor = Decimal(1)
                else:
                    break
                try:
                    printed = numeric(token)
                    target_unit = OUTPUT_UNITS.get(req.unit, Decimal(1))
                    if req.exact_amount and factor * Decimal(10) ** printed.as_tuple().exponent > target_unit:
                        break
                    amount = printed * factor / target_unit
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
            evidence_context = ""
            if req.metric == "development_expense":
                evidence_context = row.expense_heading
            elif req.revenue_line:
                evidence_context = row.revenue_heading
            elif req.metric in {"interest_expense", "total_expenses"} or req.income_before_nci:
                evidence_context = row.statement_title if row.statement_title not in row.header else ""
            elif req.metric == "eps" and row.label.casefold() == "diluted":
                evidence_context = row.per_share_heading
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
                    **({"unit_quote": row.unit_quote} if row.unit_quote else {}),
                    **({"unit_page": row.unit_page} if row.unit_page is not None else {}),
                    **({"context_quote": row.scope_quote} if row.scope_quote else {}),
                    **({"growth_line": row.growth_line} if row.growth_line else {}),
                    **({"context_quote": row.section} if row.reconciliation_total else {}),
                    **({"context_quote": evidence_context} if evidence_context else {}),
                }
            )
    if req.diluted_eps:
        # When both captions exist, select the original explicitly diluted measure.
        diluted = [item for item in result if re.search(r"\bdiluted\b", item["label"], re.I)]
        if diluted:
            result = diluted
    return sorted(result, key=lambda c: (-c["priority"], c["page"], c["column"]))
