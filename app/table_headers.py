"""Recover printed column labels without changing the text used as citation evidence."""

import re

YEAR_GROUP = re.compile(r"(?:(?:Fiscal )?Year ended\s+[A-Za-z.]+\s+\d{1,2},?\s+)?((?:19|20)\d{2}):?", re.I)
NUMBER = r"(?:\([\d,]+(?:\.\d+)?\)|[\d,]+(?:\.\d+)?|[—–-])"
NUMERIC_ROW = re.compile(rf"^\s*[A-Za-z].*?((?:\s+\$?\s*{NUMBER}){{2,}})\s*$")


def _label_fragments(line):
    return [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+(?: \S+)*", line)]


def _printed_name(label, prose):
    """When the layout extractor fuses wrapped words, recover their order from nearby prose."""
    key = "".join(label.casefold().split())
    words = prose.split()
    matches = {}
    for i, word in enumerate(words):
        if not word or word[0].casefold() not in key:
            continue
        for end in range(i+1, min(i+8,len(words))+1):
            phrase = " ".join(words[i:end]).strip(",;:")
            compact = "".join(phrase.casefold().split())
            if len(compact) > len(key):
                break
            if len(compact)==len(key) and compact in key+key:
                matches[phrase.casefold()] = phrase
    if len(matches)==1:
        return next(iter(matches.values()))
    return label


def segment_headers(layout):
    """Pair aligned, possibly wrapped captions with the following year blocks."""
    lines = [s.rstrip() for s in layout.splitlines() if s.strip()]
    result = {}
    columns = []
    for i, line in enumerate(lines):
        if not YEAR_GROUP.fullmatch(line.strip()):
            if not re.search(rf"\s{NUMBER}$",line.rstrip()):
                columns = []
            continue
        if i+1 >= len(lines) or not (data := NUMERIC_ROW.fullmatch(" ".join(lines[i+1].split()))):
            columns = []
            continue
        width = len(re.findall(NUMBER, data[1]))
        if not columns:
            j = i-1
            if j >= 0 and re.match(r"^\(.*(?:millions|thousands|billions).*\)$", lines[j].strip(), re.I):
                j -= 1
            if j < 0:
                continue
            bottom = _label_fragments(lines[j])
            if len(bottom) != width or not all(re.fullmatch(r"[A-Za-z][A-Za-z '&/().’-]*", label) for _,_,label in bottom):
                continue
            columns = [part[2] for part in bottom]
            # Only vertically overlapping text belongs to the same column.
            if j > 0 and lines[j-1].startswith("  "):
                for left, right, label in _label_fragments(lines[j-1]):
                    slots = [k for k,(lo,hi,_) in enumerate(bottom) if left < hi and lo < right]
                    if len(slots) != 1 or not re.fullmatch(r"[A-Za-z][A-Za-z &/.-]*",label):
                        columns = []
                        break
                    k = slots[0]
                    columns[k] = label + " " + columns[k]
            prose = " ".join(lines[max(0,j-28):j-1])
            columns = [_printed_name(label, prose) for label in columns]
        if len(columns) != width or len(set(columns)) != width:
            columns = []
            continue
        key = " ".join(line.split()).casefold()
        result[key] = list(columns) if key not in result else []
    return {k:v for k,v in result.items() if v}
