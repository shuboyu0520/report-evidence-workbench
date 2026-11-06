import json
from pathlib import Path

from .reader import DATA


def reader_html(live=False):
    template = (Path(__file__).parent / "static" / "reader.html").read_text("utf8")
    market = json.loads((DATA / "market.json").read_text("utf8"))
    snapshot = DATA / "reader_examples.json"
    market["examples"] = json.loads(snapshot.read_text("utf8")) if snapshot.is_file() else []
    payload = json.dumps(market, ensure_ascii=False).replace("<", "\\u003c")
    return template.replace("__SOURCE_DATA__", payload).replace("__IS_LIVE__", json.dumps(live))
