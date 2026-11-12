import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.studio_splits import extract_bill_fields, source_split, split_quote

FIXTURE = json.loads(Path(__file__).with_name("member_split_cases.json").read_text(encoding="utf-8"))
MEMBERS = {member["id"]: member["name"] for member in FIXTURE["roster"]}


@pytest.mark.parametrize("sentence,payer,amounts", FIXTURE["cases"])
def test_member_allocations(sentence, payer, amounts):
    data = extract_bill_fields(sentence, MEMBERS)
    assert data.payer == payer
    split = source_split(sentence, MEMBERS)
    if split is not None:
        data.split_mode, data.people, data.split_values = split
    if amounts is None:
        with pytest.raises(HTTPException):
            split_quote(data, MEMBERS)
    else:
        shares = split_quote(data, MEMBERS)["shares"]
        assert {str(s["id"]): s["cents"] for s in shares} == amounts


def test_empty_archived_and_duplicate_member_names():
    sentence = FIXTURE["cases"][0][0]
    data = extract_bill_fields(sentence, MEMBERS)
    active = {uid: name for uid, name in MEMBERS.items() if uid != 61}
    assert extract_bill_fields(sentence, active).payer is None
    assert extract_bill_fields(sentence, {}).people == []
    with pytest.raises(HTTPException):
        split_quote(data, active)
    assert split_quote(data, MEMBERS)["cents"] == 1001
    assert extract_bill_fields("Ann付了10元晚餐，全组均分。", {**MEMBERS, 100: "ＡＮＮ"}).payer is None
