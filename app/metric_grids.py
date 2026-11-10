"""Financial metric grids with printed quarter columns and outlook ranges."""

import re
from decimal import ROUND_HALF_UP, Decimal

from .table_lookup import SCALE

QUARTER = re.compile(r"\bQ([1-4])(?:\s+|[-'’])(20\d{2}|\d{2})\b", re.I)
GROWTH = re.compile(r"^(?:y/y|yoy|year.over.year)\s+growth$", re.I)
SUMMARY = re.compile(
    r"(?:metric|measure|item)\s+(?:Q[1-4]\s+20\d{2}\s+){2,}(?:Δ\s*)?(?:Y/Y|YoY|% change)", re.I
)
SEGMENTS = re.compile(r"by segment(?:\s+Q[1-4]-\d{2,4}){3,}", re.I)
PARENT = re.compile(
    r"(?:total )?(?:revenues?|net sales|gross bookings?|operating income|adjusted EBITDA)(?:\s*\(\d+\))?",
    re.I,
)
BY = re.compile(
    r"(?P<metric>(?:net |total )?revenues?|net sales|gross bookings?) by (?P<scope>product|segment|business model|geography)",
    re.I,
)
VARIANCE = (None, None, None, True)
MONEY_RANGE = re.compile(
    r"(?P<label>[a-z][a-z &/-]*?\*{0,3})\s+(?P<lo>\$\s*\d[\d,]*(?:\.\d+)?[BMK]?)"
    r"\s*(?:[-–—]|to)\s*(?P<hi>\$\s*\d[\d,]*(?:\.\d+)?[BMK]?)",
    re.I,
)
PCT_RANGE = re.compile(
    r"(?P<lo>[+-]?\d+(?:\.\d+)?)\s*%?\s*(?:[-–—]|to)\s*(?P<hi>[+-]?\d+(?:\.\d+)?)\s*%"
)


def _periods(text):
    return [(int(y) if len(y) == 4 else 2000 + int(y), int(q)) for q, y in QUARTER.findall(text)]


def _columns(periods):
    return tuple((y, q, None, False) for y, q in periods) + (VARIANCE,)


def _footer_columns(years, quarters):
    """Validate the full sequence before applying an out-of-order PDF header."""
    if not re.fullmatch(r"(?:20\d\d\s+)+Y/Y", years, re.I):
        return ()
    if not re.fullmatch(r"(?:Q[1-4]\s+){2,}Growth", quarters, re.I):
        return ()
    bands = [int(v) for v in years.split()[:-1]]
    ticks = [int(v[1]) for v in quarters.split()[:-1]]
    periods = [(bands[0], ticks[0])]
    for tick in ticks[1:]:
        year, old = periods[-1]
        if tick != old % 4 + 1:
            return ()
        periods.append((year + (tick == 1), tick))
    if sorted({year for year, _ in periods}) != bands:
        return ()
    return _columns(periods)


def _monetary_unit(lines):
    # Use an actual table caption, excluding narrative mentions of orders of magnitude.
    units = [
        s
        for s in lines
        if re.search(
            r"\((?:all figures |amounts |dollars )?in (?:millions|billions|thousands)\b", s, re.I
        )
    ]
    if not units or len({SCALE.search(s)[1].lower() for s in units}) != 1:
        return ""
    return units[-1]


def _grid_data(line, columns, parse_row):
    row = parse_row(line)
    if not row or row[2] or len(row[1]) != len(columns):
        return None
    label, cells, _ = row
    if "%" not in cells[-1] or any("%" in v for v in cells[:-1]):
        return None
    return label, cells


def metric_grid_rows(page, parse_row, make_row):
    lines = [line.strip() for line in page["text"].splitlines() if line.strip()]
    for i, line in enumerate(lines):
        segments = SEGMENTS.fullmatch(line) and i and GROWTH.fullmatch(lines[i - 1])
        if not segments and not SUMMARY.fullmatch(line):
            continue
        periods = _periods(line)
        header = line
        if segments:
            if periods[-1] != periods[-2]:
                continue
            periods.pop()
            header = lines[i - 1] + "\n" + line
        if len(periods) != len(set(periods)):
            continue
        columns = _columns(periods)
        unit = _monetary_unit(lines[max(0, i - 4) : i])
        if not unit:
            continue
        parent = parent_quote = ""
        for raw in lines[i + 1 :]:
            if not (parsed := _grid_data(raw, columns, parse_row)):
                break
            label, cells = parsed
            is_parent = PARENT.fullmatch(label)
            is_subrow = segments and not is_parent
            # Other expense or margin sections end the current parent. Only
            # segment identifiers under a printed measure can inherit its meaning.
            if is_subrow and not re.fullmatch(r"[A-Za-z][A-Za-z\d&-]*(?:\s*\(\d+\))?", label):
                parent = parent_quote = ""
            if not is_subrow or parent:
                yield make_row(
                    page["number"],
                    label,
                    raw,
                    header,
                    parent if is_subrow else "",
                    cells,
                    False,
                    dollars="$" in raw or (is_subrow and "$" in parent_quote),
                    period_columns=columns,
                    unit_quote=unit,
                    scope_quote=parent_quote if is_subrow else "",
                )
            if is_parent:
                parent, parent_quote = label, raw

    # Some PDFs emit one chart's year / quarter spanners after all the data.
    # Require a unique band pair and an explicit measure heading for every section.
    footers = [
        (i, cols) for i in range(1, len(lines)) if (cols := _footer_columns(lines[i - 1], lines[i]))
    ]
    if len(footers) != 1:
        return
    i, columns = footers[0]
    unit = _monetary_unit(lines[: i - 1])
    if not unit:
        return
    header = lines[i - 1] + "\n" + lines[i]
    section = ""
    for raw in lines[: i - 1]:
        if BY.fullmatch(raw):
            section = raw
            continue
        parsed = _grid_data(raw, columns, parse_row)
        if not parsed:
            section = ""
        elif section:
            label, cells = parsed
            yield make_row(
                page["number"],
                label,
                raw,
                header,
                section,
                cells,
                False,
                dollars="$" in raw,
                period_columns=columns,
                unit_quote=unit,
                scope_quote=section,
            )


def metric_outlook_rows(page, make_row):
    """Bind dollar and percentage lines within one explicitly dated outlook column."""
    lines = [line.strip() for line in page["text"].splitlines() if line.strip()]
    for i, caption in enumerate(lines):
        if not re.fullmatch(
            r"(?:business |financial )?(?:outlook|guidance|forecast):?", caption, re.I
        ):
            continue
        if i + 1 == len(lines):
            continue
        header = lines[i + 1]
        period = re.fullmatch(r"(?:metric|measure|item)\s+Q([1-4])\s+(20\d\d)", header, re.I)
        if not period:
            continue
        j = i + 2
        while j < len(lines) and (match := MONEY_RANGE.match(lines[j])):
            quote = lines[j]
            rate = quote[match.end() :].strip()
            if rate and not PCT_RANGE.fullmatch(rate):
                break
            j += 1
            if not rate and j < len(lines) and PCT_RANGE.fullmatch(lines[j]):
                rate = lines[j]
                quote += "\n" + rate
                j += 1
            yield make_row(
                page["number"],
                match["label"].rstrip("*").strip(),
                quote,
                header,
                "",
                (match["lo"], match["hi"]),
                True,
                dollars=True,
                forecast_period=(int(period[2]), int(period[1])),
                scope_quote=caption,
                growth_line=rate,
            )


def supported_growth(outlook, prior):
    """Confirm an unlabelled rate's YoY basis against the same metric a year earlier."""
    bases = {Decimal(c["amounts"][0].replace(",", "")) for c in prior}
    if len(bases) != 1 or (base := bases.pop()) <= 0:
        return []
    reference = prior[0]
    evidence = [
        {"page": reference["page"], "quote": reference[k]}
        for k in ("quote", "header", "unit_quote")
        if reference.get(k)
    ]
    found = []
    for cell in outlook:
        if not (match := PCT_RANGE.fullmatch(cell.get("growth_line", ""))):
            continue
        printed = [Decimal(match["lo"]), Decimal(match["hi"])]
        computed = [100 * (Decimal(v.replace(",", "")) / base - 1) for v in cell["amounts"]]
        if printed[0] > printed[1] or any(
            real.quantize(shown, rounding=ROUND_HALF_UP) != shown
            for real, shown in zip(computed, printed, strict=True)
        ):
            continue
        found.append(
            {
                **cell,
                "amounts": [str(n) for n in printed],
                "unit": "%",
                "raw_cell": [match["lo"], match["hi"]],
                "basis": "报告口径同比",
                "basis_evidence": evidence,
            }
        )
    return found
