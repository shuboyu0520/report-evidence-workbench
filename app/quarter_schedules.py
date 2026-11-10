"""Read fiscal-year rows under named segments and explicit quarter columns."""

import re

from .finance import numeric

QUARTERS = re.compile(
    r"(?:First Quarter Second Quarter Third Quarter Fourth Quarter|Q1 Q2 Q3 Q4) Full Year", re.I
)
SCHEDULE = re.compile(r"(?:historical )?.+\bby (?:business )?segment\b", re.I)
MEASURE = re.compile(r"(?:net |total )?revenues?|adjusted EBITDA|net income(?:/\(loss\))?", re.I)
UNIT = re.compile(r"\((?:dollars |amounts )?in (thousands|millions|billions)\)", re.I)
TOTAL = re.compile(r"total (?:company|group|consolidated)|consolidated total", re.I)
FIGURE = re.compile(r"\$?\s*(?:\(\s*[\d,]+(?:\.\d+)?\s*\)|[-+]?\d[\d,]*(?:\.\d+)?|n/a|[—–-])", re.I)
FOREIGN = re.compile(r"\b(?:CAD|EUR|GBP|AUD|HKD|TWD|CNY|JPY)\b|[€£¥]|(?:CA|HK|NT|AU)\$", re.I)


def _figures(text):
    if FIGURE.sub("", text).strip():
        return ()
    return tuple(m[0].strip() for m in FIGURE.finditer(text))


def _number(raw):
    if not raw:
        return None
    try:
        return numeric(raw.replace("$", "").replace(" ", ""))
    except ValueError:
        return None


def _header(lines):
    for end, line in enumerate(lines):
        if not re.search(r"\byear$", line, re.I):
            continue
        for start in range(max(0, end - 10), end + 1):
            header = "\n".join(lines[start : end + 1])
            if QUARTERS.fullmatch(" ".join(header.split())):
                return start, end, header
    return None


def _scale(lines):
    captions = [line for line in lines if UNIT.fullmatch(line)]
    if len(set(captions)) == 1 and not any(FOREIGN.search(s) for s in lines):
        return captions[0]
    return ""


def _rows(lines, start, year):
    """A year alone cannot name a metric; both preceding headings must be in scope."""
    scope = metric = ""
    for line in lines[start:]:
        if re.match(r"(?:note\b|table\s*\d+\b|\(\w+\)\s+)", line, re.I):
            break
        dated = re.fullmatch(r"(20\d{2})\s+(.+)", line)
        if dated:
            if scope and metric and int(dated[1]) == year:
                figures = _figures(dated[2])
                if len(figures) == 5 and "$" in line:
                    yield scope, metric, line, figures
        elif MEASURE.fullmatch(line):
            metric = line
        else:
            scope = line if re.fullmatch(r"[A-Za-z][\w&., /'-]{0,70}", line) else ""
            metric = ""


def _linked_scale(pages, text, anchors, year):
    """An unscaled table must cite a scaled schedule AND reproduce its company totals."""
    ref = re.search(
        r"\bsee (Table \d+) for reconciliations? of (?:total company|consolidated|group)\b",
        text,
        re.I,
    )
    if not ref or len(anchors) != 1:
        return None
    _, metric, anchor_line, values = anchors[0]
    amounts = [_number(v) for v in values]
    while amounts and amounts[-1] is None:
        amounts.pop()
    if len(amounts) < 2 or None in amounts:
        return None
    matches = []
    for page in pages:
        lines = [s.strip() for s in page["text"].splitlines() if s.strip()]
        if not any(s.casefold() == ref[1].casefold() for s in lines[:4]):
            continue
        header = _header(lines)
        if not header or not (unit := _scale(lines[: header[0]])):
            continue
        if unit != _scale(lines) or not any(
            re.fullmatch(r"reconciliation of .+ to " + re.escape(metric) + r":?", s, re.I)
            for s in lines[: header[0]]
        ):
            continue
        this_year = False
        for line in lines[header[1] + 1 :]:
            if re.fullmatch(r"20\d{2}", line):
                this_year = int(line) == year
                continue
            if this_year and line.casefold().startswith(metric.casefold() + " "):
                check = [_number(s) for s in _figures(line[len(metric) :].strip())]
                if check == amounts:
                    matches.append((page["number"], unit, line, anchor_line, ref[0]))
    return matches[0] if len(matches) == 1 else None


def schedule_cells(pages, req, scale_factors, output_units):
    if req.metric != "ebitda" or req.guidance:
        return []
    cells = []
    for page in pages:
        lines = [s.strip() for s in page["text"].splitlines() if s.strip()]
        if not any(SCHEDULE.fullmatch(s) for s in lines[:8]):
            continue
        header = _header(lines)
        if not header or any(FOREIGN.search(s) for s in lines):
            continue
        rows = [
            row
            for row in _rows(lines, header[1] + 1, req.year)
            if re.fullmatch(req.pattern, row[1], re.I)
        ]
        local_unit = _scale(lines[: header[0]])
        linked = None
        if not local_unit:
            if any(
                re.search(r"\bin (?:thousands|millions|billions)\b", s, re.I)
                for s in lines[: header[0]]
            ):
                continue
            linked = _linked_scale(
                pages, page["text"], [r for r in rows if TOTAL.fullmatch(r[0])], req.year
            )
            if not linked:
                continue
        unit_page, unit = (page["number"], local_unit) if local_unit else linked[:2]
        scale = scale_factors[UNIT.fullmatch(unit)[1].lower()]
        column = req.quarter or 5
        for scope, metric, line, raw in rows:
            if req.groups or req.products:
                if not all(re.fullmatch(re.escape(group), scope, re.I) for group in req.groups):
                    continue
                if not all(re.fullmatch(pattern, scope, re.I) for pattern in req.products):
                    continue
            elif not TOTAL.fullmatch(scope):
                continue
            value = _number(raw[column - 1])
            divisor = output_units.get(req.unit)
            if value is None or not divisor:
                continue
            amount = value * scale / divisor
            refs = [{"page": page["number"], "quote": metric}]
            if linked:
                refs.extend(
                    [
                        {"page": page["number"], "quote": linked[4]},
                        {"page": page["number"], "quote": linked[3]},
                        {"page": unit_page, "quote": linked[2]},
                    ]
                )
            cells.append(
                {
                    "page": page["number"],
                    "label": metric,
                    "scope": scope,
                    "measure_caption": scope,
                    "basis": "非 GAAP",
                    "year": req.year,
                    "quarter": req.quarter,
                    "column": column,
                    "raw_cell": [raw[column - 1]],
                    "amounts": [f"{amount:,f}"],
                    "unit": req.unit,
                    "quote": line,
                    "header": header[2],
                    "context_quote": scope,
                    "unit_quote": unit,
                    "unit_page": unit_page,
                    "basis_evidence": refs,
                    "priority": 0,
                }
            )
    return cells
