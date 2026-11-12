"""Validated, integer-minor-unit allocation rules for the three-member demo."""

import re
import unicodedata
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field, StrictInt

MEMBERS = {11: "小林", 12: "小周", 13: "小陈"}
Mode = Literal["", "equal", "percentage", "ratio", "exact"]


class DraftFields(BaseModel):
    description: str = Field(default="", max_length=100)
    amount: str = Field(default="", max_length=14)
    currency: Literal["AUD", "CNY", "USD", ""] = ""
    payer: StrictInt | None = None
    people: list[StrictInt] = Field(default_factory=list, max_length=3)
    split_mode: Mode = "equal"
    split_values: dict[str, str] = Field(default_factory=dict, max_length=3)


def hundredths(value):
    parts = re.fullmatch(r"([0-9]{1,8})(?:\.([0-9]{1,2}))?", value)
    if not parts:
        raise HTTPException(422, "请填写非负数，最多两位小数。")
    return int(parts[1]) * 100 + int((parts[2] or "").ljust(2, "0"))


def split_quote(data: DraftFields):
    if not data.description.strip() or not data.currency or data.payer not in MEMBERS:
        raise HTTPException(422, "请核对费用说明、付款人和币种。")
    ids = sorted(data.people)
    if not ids or len(set(ids)) != len(ids) or set(ids) - MEMBERS.keys():
        raise HTTPException(422, "请选择不同的小组成员参与分摊。")
    total = hundredths(data.amount)
    if not total:
        raise HTTPException(422, "账单总金额必须大于零。")
    if not data.split_mode:
        raise HTTPException(422, "请选择分摊方式，并核对每人的份额。")
    if data.split_mode == "equal":
        if data.split_values:
            raise HTTPException(422, "均分无需填写指定份额。")
        weights = [1] * len(ids)
    else:
        if set(data.split_values) != {str(i) for i in ids}:
            raise HTTPException(422, "请为每位参与人填写分摊值。")
        values = [data.split_values[str(i)] for i in ids]
        if data.split_mode == "ratio":
            if any(not re.fullmatch(r"[1-9][0-9]{0,5}", v) for v in values):
                raise HTTPException(422, "份数应为 1 至 999999 的整数。")
            weights = [int(v) for v in values]
        else:
            weights = [hundredths(v) for v in values]
            if data.split_mode == "exact" and sum(weights) != total:
                raise HTTPException(422, "指定金额的合计必须等于账单总额。")
            if data.split_mode == "percentage" and sum(weights) != 10000:
                raise HTTPException(422, "百分比合计必须为 100%。")
    denominator = sum(weights)
    pieces = [divmod(total * weight, denominator) for weight in weights]
    shares = [base for base, _ in pieces]
    # IDs are sorted first, so equal remainders have a deterministic tie-break.
    order = sorted(range(len(ids)), key=lambda i: -pieces[i][1])
    for i in order[: total - sum(shares)]:
        shares[i] += 1
    return {
        "cents": total,
        "shares": [{"id": uid, "cents": v} for uid, v in zip(ids, shares, strict=True)],
    }


NAME = r"[小阿老][\u3400-\u9fff]"
NUMBER = r"[0-9]+(?:\.[0-9]+)?"
UNIT = r"元人民币|人民币|澳元|澳币|美元|美金|元|AUD|USD|CNY|RMB"
ASSIGN = r"(?:各自|各)?\s*(?:承担|负担|分担|应付|分摊|占比?|算|为|出|付|分得)?\s*[:：]?\s*"
PAIR = re.compile(rf"({NAME}){ASSIGN}({NUMBER})\s*(%|份|{UNIT})?", re.I)
UNEVEN = re.compile(
    r"不均[分摊]|不平[摊分均]|非均[分摊]|不一样|不[按是]均[分摊]|按(?:照)?比例|按份|份额|配比|[一二三四六七八九五]{2}开|按金额|按人数以外|指定金额|分别承担|百分[比率]|按占比|承担\s*\d|[0-9]\s*[%份]|[0-9]\s*:\s*[0-9]"
)
MEMBER_IDS = {name: uid for uid, name in MEMBERS.items()}
PAYER = re.compile(
    rf"({NAME})\s*(?:先|已)?(?:垫付?|支付|付|买单|结账)(?:了|款)?\s*(?=(?:{NUMBER}|澳元|美元|人民币|AUD|USD|CNY|RMB|[¥$]))",
    re.I,
)
TOTAL = re.compile(
    rf"(?:总(?:额|共|计)|合计|共计|一共|共花|付款|支付|付了|垫付了?|垫了|花了)\s*(?:AUD|USD|CNY|RMB|A\$|US\$|¥|人民币|澳元|美元)?\s*({NUMBER})(?![\d.%份:])",
    re.I,
)


def normalize_bill(raw):
    """Only strip commas when the whole numeric token is correctly grouped."""
    text = unicodedata.normalize("NFKC", raw).strip()

    def grouped(match):
        token = match[0]
        return (
            token.replace(",", "")
            if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", token)
            else token
        )

    return re.sub(r"\d+(?:,\d+)+(?:\.\d+)?", grouped, text)


def clarification_reason(text):
    if len(TOTAL.findall(text)) > 1:
        return "识别到多个支付金额，请每次只描述一笔支出。"
    if re.search(r"\d\s*[,，]\s*\d|\d\s*(?:[十百千万亿]|[kKmM](?![a-zA-Z]))", text):
        return "请用完整数字填写金额，例如 12,000 或 12000。"
    if re.search(r"分(?:成)?[两二2]笔|分开记|退款|退还|返现|[-−]\s*\d|不是.*付|没(?:有)?付", text):
        return "请单独填写一笔已支付的正金额支出。"
    if re.search(
        r"不参加|不参与|不[承分]担|不算|不含|除[了去外]|排除|不摊|待定|未定|还没定|没说|尚未确定|改[为成]|或者|还是",
        text,
    ):
        return "这笔费用的参与人或份额需要核对，请写出最终参加的成员和分摊值。"
    sharing = re.split(r"[,。;!]", text)
    for clause in sharing:
        if re.search(
            r"均[摊分]|平[摊分]|各一半|承担|分[摊担]|按份|按比例|占\s*\d|\d\s*[%份]|另有|也一起|加上", clause
        ):
            names = re.findall(NAME, clause)
            if any(
                n not in MEMBER_IDS and n not in {"小组", "小计", "小数", "小票", "小吃"}
                for n in names
            ):
                return "分摊名单包含暂未识别的成员，请核对实际参与人。"
    return ""


def extract_bill_fields(text):
    clauses = re.split(r"[,。;!]", text)
    total_clause = next((s for s in clauses if TOTAL.search(s)), "")
    totals = [m[1] for s in clauses for m in TOTAL.finditer(s)]
    if not totals:
        # A standalone “房租 120 元” heading is common; assignment clauses never supply the total.
        heading = re.search(rf"({NUMBER})\s*(?:{UNIT})", clauses[0], re.I)
        if heading and not PAIR.search(PAYER.sub("付款 ", clauses[0])):
            totals = [heading[1]]
            total_clause = clauses[0]
    currencies = {
        key
        for key, pattern in [
            ("CNY", r"人民币|CNY|RMB|¥"),
            ("AUD", r"澳[元币]|\bAUD\b|A\$"),
            ("USD", r"美[元金]|\bUSD\b|US\$"),
        ]
        if re.search(pattern, text, re.I)
    }
    if not currencies and re.search(r"[0-9]\s*元", total_clause):
        currencies.add("CNY")
    if re.search(r"港[币元]|日[币元]|欧元|英镑|加元|新加坡元|韩元", text):
        currencies.clear()
    payers = {m[1] for m in PAYER.finditer(text)}
    proxy = re.search(rf"({NAME})\s*[替帮为]", text)
    if proxy:
        payers = {proxy[1]}
    if not payers:
        payers = set(re.findall(rf"({NAME})\s*(?:先|已)?(?:垫付|买单|结账)", text))
    label = re.search(
        r"晚[餐饭]|午[餐饭]|早[餐饭]|打车|车费|超市|食材|咖啡|住宿|房租|门票|电影|停车|奶茶|酒店|民宿|水电[费]?|聚餐|机票|水果|披萨",
        text,
    )
    group = re.search(r"全[组员部]|所有人|三个人|三人", text)
    equal = re.search(r"均[分摊]|平[摊分]|各一半", text)
    people = []
    if equal:
        equal_clause = next(s for s in clauses if equal[0] in s)
        people = list(MEMBERS) if group else [i for i, n in MEMBERS.items() if n in equal_clause]
    return DraftFields(
        description=label[0] if label else "",
        people=people,
        amount=totals[0] if len(totals) == 1 else "",
        currency=currencies.pop() if len(currencies) == 1 else "",
        payer=MEMBER_IDS.get(payers.pop()) if len(payers) == 1 else None,
    )


def source_split(text):
    """Read explicitly assigned amounts, percentages or parts. Never invent missing values."""
    text = unicodedata.normalize("NFKC", text)
    # A payer prefix gives the transaction total, not an amount assigned to that person.
    spoken = re.sub(
        rf"({NAME})\s*(?:先|已)?(?:垫付?|支付|付)了?\s*(?=(?:{NUMBER}|AUD|USD|CNY))", "付款 ", text
    )
    pairs = list(PAIR.finditer(spoken))
    if not UNEVEN.search(text) and not pairs:
        return None
    vectors = list(re.finditer(r"(?<![\d.])(\d+(?:\s*:\s*\d+){1,})(?![\d.])", spoken))
    if len(vectors) > 1:
        return "", [], {}
    vector = vectors[0] if vectors else None
    if vector:
        pairs = [m for m in pairs if m.start(2) != vector.start()]
        if pairs or "%" in spoken:
            return "", [], {}
    if "%" in spoken or "百分比" in spoken or "按占比" in spoken:
        mode = "percentage"
    elif vector or re.search(r"份数|按份|\d\s*份|按(?:照)?比例", spoken):
        mode = "ratio"
    elif pairs or re.search(r"指定金额|按金额", spoken):
        mode = "exact"
    else:
        mode = ""
    expected = re.compile(
        {"exact": rf"(?:{UNIT})?", "percentage": "%", "ratio": "份?"}.get(mode, r"(?!)"), re.I
    )
    ids, values = [], {}
    # Look for any unrecognised names explicitly associated with a value.
    for item in pairs:
        uid = MEMBER_IDS.get(item[1])
        if not uid or uid in ids or not expected.fullmatch(item[3] or ""):
            return mode, [], {}
        ids.append(uid)
        values[str(uid)] = item[2]
    if vector and not pairs:
        member_list = rf"{NAME}(?:\s*(?:、|和|与|及|跟|,|\+)\s*{NAME})+"
        before = re.search(
            rf"({member_list})\s*(?:(?:两|三|二)人)?\s*(?:按(?:照)?|以)?\s*(?:比例|份数)?\s*(?:为)?\s*$",
            spoken[: vector.start()],
        )
        after = re.match(
            rf"\s*(?:的?比例)?\s*[,，]?\s*(?:分别)?(?:由|给)?\s*({member_list})",
            spoken[vector.end() :],
        )
        match = before or after
        ordered = re.findall(NAME, match[1]) if match else []
        if all(n in MEMBER_IDS for n in ordered) and len(set(ordered)) == len(ordered):
            ids = [MEMBER_IDS[n] for n in ordered]
            parts = re.split(r"\s*:\s*", vector[1])
            if len(ids) == len(parts):
                values = {str(uid): part for uid, part in zip(ids, parts, strict=True)}
    split_clauses = [s for s in re.split(r"[,。;!]", spoken) if s and not TOTAL.search(s)]
    beneficiaries = {m for s in split_clauses for m in re.findall(NAME, s) if m in MEMBER_IDS}
    if re.search(r"(?:三[个]?人|全组|所有人)", spoken):
        beneficiaries.update(MEMBER_IDS)
    missing = {MEMBER_IDS[name] for name in beneficiaries} - set(ids)
    if missing:
        ids.extend(sorted(missing))
    if re.search(r"待定|不清楚|没说|不确定|未确定|没确定|组外|剩[下余]", spoken):
        values = {}
    return mode, ids, values
