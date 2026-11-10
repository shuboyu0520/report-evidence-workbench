"""Check a replay of the preregistered Wyndham questions against the original PDF."""

import re

from scripts.grade_expedia_replay import compact, main
from scripts.grade_hilton_replay import grade as grade_table

LABELS = {
    "W01": ("net revenues",),
    "W02": ("net revenues",),
    "W03": ("operating income",),
    "W04": ("diluted",),
    "W05": ("adjusted ebitda",),
    "W06": ("net income",),
    "W07": ("royalties and franchise fees", "net revenues"),
    "W08": ("marketing, reservation and loyalty", "net revenues"),
    "W09": ("interest expense, net",),
    "W10": ("corporate", "adjusted ebitda"),
    "W11": ("free cash flow",),
    "W12": ("greater china", "revpar"),
    "W13": ("global revpar", r"constant[\s-]+currency", "outlook"),
    "W14": ("adjusted ebitda", "outlook"),
}


def grade(case, row, pages, cutoff):
    passed, note = grade_table(case, row, pages, cutoff, labels=LABELS)
    if not passed or case["kind"] in {"missing", "future"}:
        return passed, note
    refs = row["citations"]
    if case["id"] in {"W13", "W14"}:
        evidence = " ".join(compact(c["quote"]) for c in refs)
        # A correct revision needs the printed update or the current outlook with its year.
        if not re.search(r"updated outlook|2026 (?:full.year )?outlook", evidence):
            return False, "引文未标明更新后或当年展望的口径。"
        if case["id"] == "W13":
            return True, "第 5 页将全年全球 RevPAR 固定汇率同比增幅的下限由 0.0% 调至 0.5%，上限保持 1.0%。答复与更新栏相符。"
        return True, "第 5 页全年调整后 EBITDA 的旧区间为 735–745 百万美元，更新栏为 740–745 百万美元。答复的两个端点均与更新栏相符。"
    if case["id"] == "W09" and not any(
        c["page"] == 8 and "interest expense, net" in compact(c["quote"]) for c in refs
    ):
        return False, "需指定利润表的原行确认列示符号。"
    return True, note


if __name__ == "__main__":
    main(grade, __doc__)
