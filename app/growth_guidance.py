"""Read percentage ranges in dated outlook tables with an explicit YoY header."""

import re
from decimal import Decimal


PERIOD = re.compile(r"\b(Q[1-4]|FY)\s+(20\d{2})\b", re.I)
YOY = re.compile(r"year[- ]over[- ]year|\byoy\b|\by/y\b", re.I)
GUIDANCE = re.compile(r"\b(?:guidance|outlook|forecast)\b", re.I)
PERCENT = r"[+-]?\d+(?:\.\d+)?\s*%"
CELL = re.compile(
    rf"(?P<lo>{PERCENT})\s*(?:[-–—]|to)\s*(?P<hi>{PERCENT})"
    r"|(?:low|mid|high)(?:\s+to\s+(?:low|mid|high))?[- ](?:single|double)[- ]digits?"
    r"|(?:low(?:\s+to\s+mid)?|mid|high)[- ]teens|(?:about\s+)?flat|[—–]",
    re.I,
)
LABELS = {
    "room_nights": r"room nights?",
    "bookings": r"gross bookings?",
    "revenue": r"(?:total |net )?revenues?",
    "ebitda": r"ebitda",
    "eps": r"eps",
}


def row_key(text):
    return " ".join(text.split())


def growth_column_positions(layout):
    """Locate sparse rows using the period headers' physical column centers."""
    positions = {}
    centers = []
    header = ""
    for line in layout.splitlines():
        periods = list(PERIOD.finditer(line))
        if periods and YOY.search(line):
            centers = [(m.start() + m.end()) / 2 for m in periods]
            header = row_key(line)
            continue
        if not centers or len(centers) < 2:
            continue
        cells = list(CELL.finditer(line))
        if not cells or not re.search(r"\bgrowth\b", line[: cells[0].start()], re.I):
            centers = []
            continue
        indices = []
        for cell in cells:
            center = (cell.start() + cell.end()) / 2
            col = min(range(len(centers)), key=lambda i: abs(centers[i] - center))
            separation = min(
                abs(centers[col] - other) for i, other in enumerate(centers) if i != col
            )
            if abs(centers[col] - center) >= separation / 2:
                break
            indices.append(col)
        if len(indices) == len(cells) and indices == sorted(set(indices)):
            key = header + "\n" + row_key(line)
            positions[key] = indices if positions.get(key, indices) == indices else []
    return positions


def growth_guidance_cells(pages, request):
    """Accept ranges only in the requested printed period and currency basis."""
    metric = LABELS.get(request.metric)
    if metric is None or request.groups or request.products or request.qualified:
        return []
    cc_prefix = (
        r"constant[- ]currency " if request.growth_basis == "constant" else r"(?:reported )?"
    )
    adjusted = "adjusted " if request.adjusted else ""
    label_pattern = re.compile(rf"{cc_prefix}{adjusted}{metric} growth(?:\s*\(\d{{1,2}}\))*", re.I)
    found = []
    for page in pages:
        lines = [s.strip() for s in page["text"].splitlines() if s.strip()]
        caption = ""
        for i, line in enumerate(lines):
            if (
                GUIDANCE.search(line)
                and len(line) < 180
                and (
                    re.search(r"quarter|fiscal year|full year|\b(?:FY|Q[1-4])\s*20\d\d", line, re.I)
                    or re.fullmatch(
                        r"(?:Business |Financial )?(?:Outlook|Guidance|Forecast):?", line, re.I
                    )
                )
            ):
                caption = line
            elif re.match(
                r"^(?:actuals?|historical results|financial results|reconciliation)\b", line, re.I
            ):
                caption = ""
            periods = list(PERIOD.finditer(line))
            if not (caption and periods):
                continue
            if not YOY.search(line) or not re.fullmatch(
                r"(?:\([^()]+\)\s*)?(?:(?:Q[1-4]|FY)\s+20\d{2}\s*)+", line, re.I
            ):
                continue
            columns = [(int(m[2]), None if m[1].upper() == "FY" else int(m[1][1])) for m in periods]
            target = (request.year, request.quarter)
            if columns.count(target) != 1:
                continue
            column = columns.index(target)
            for raw in lines[i + 1 :]:
                # The first numeric column, including footnoted labels, is separate
                # from a later annual qualitative outlook. Never turn a phrase into a number.
                first = CELL.search(raw)
                if not first or not label_pattern.fullmatch(raw[: first.start()].strip()):
                    # Other metric rows, including wrapped captions, are still in this table.
                    if not raw.startswith("(") and (
                        not first and len(raw) < 80 and raw.lower().endswith("growth")
                    ):
                        continue
                    if first and re.search(r"\bgrowth\b", raw[: first.start()], re.I):
                        continue
                    if (
                        first
                        and raw.startswith("(")
                        and not re.search(r"[a-z]", raw[: first.start()], re.I)
                    ):
                        continue
                    break
                cells = list(CELL.finditer(raw, first.start()))
                if not cells or len(cells) > len(columns):
                    continue
                if (
                    any(raw[a.end() : b.start()].strip() for a, b in zip(cells, cells[1:]))
                    or raw[cells[-1].end() :].strip()
                ):
                    continue
                if len(cells) == len(columns):
                    index = column
                else:
                    indices = page.get("growth_columns", {}).get(
                        row_key(line) + "\n" + row_key(raw), []
                    )
                    if len(indices) != len(cells) or column not in indices:
                        continue
                    index = indices.index(column)
                cell = cells[index]
                if cell["lo"] is None:
                    continue
                values = [v.replace("%", "").strip() for v in (cell["lo"], cell["hi"])]
                if Decimal(values[0]) > Decimal(values[1]):
                    continue
                found.append(
                    {
                        "page": page["number"],
                        "label": raw[: first.start()].strip(),
                        "scope": "",
                        "measure_caption": "",
                        "basis": "固定汇率同比"
                        if request.growth_basis == "constant"
                        else "报告口径同比",
                        "year": request.year,
                        "quarter": request.quarter,
                        "column": column + 1,
                        "raw_cell": [cell["lo"], cell["hi"]],
                        "amounts": values,
                        "unit": "%",
                        "quote": raw,
                        "header": line,
                        "context_quote": caption,
                        "priority": 0,
                    }
                )
    return found
