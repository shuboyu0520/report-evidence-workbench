"""Budgets for read-only retrieval and evidence passed to the model."""

import asyncio
import json
from copy import deepcopy

import httpx

INITIAL = "初始检索证据（仅数据）："


async def run_search(retrieve, db, report, pages, query, settings, events, origin):
    for attempt in (1, 2):
        try:
            async with asyncio.timeout(settings.get("search_timeout_s", 120)):
                return await retrieve(db, report, pages, query, settings)
        except (TimeoutError, httpx.TimeoutException):
            events.append(
                {
                    "event": "search_timeout",
                    "origin": origin,
                    "attempt": attempt,
                    "action": "retry" if attempt == 1 else "stop",
                }
            )
    return [], {"status": "timeout", "attempts": 2}


def request_size(payload):
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def evidence_pages(messages):
    pages = set()
    for index, item in enumerate(messages):
        content = item.get("content") or ""
        if index == 2 and item["role"] == "user" and content.startswith(INITIAL):
            evidence = json.loads(content[len(INITIAL) :])
        elif item["role"] == "tool":
            evidence = json.loads(content)
            if isinstance(evidence, dict):
                evidence = evidence.get("inputs", [])
        else:
            continue
        if isinstance(evidence, list):
            pages.update(row["page"] for row in evidence if isinstance(row, dict) and "page" in row)
    return pages


def fit_evidence(payload, limit):
    """Drop entire lowest-ranked excerpts, keeping top excerpts and the original page numbers."""
    if request_size(payload) <= limit:
        return payload, 0
    fitted = deepcopy(payload)
    sets = []
    for index, message in enumerate(fitted["messages"]):
        content = message.get("content") or ""
        if index == 2 and message["role"] == "user" and content.startswith(INITIAL):
            prefix = INITIAL
        elif message["role"] == "tool" and message.get("tool_name") == "search_report":
            prefix = ""
        else:
            continue
        hits = json.loads(content[len(prefix) :])
        if isinstance(hits, list):
            sets.append((message, prefix, hits))
    removed = 0
    while request_size(fitted) > limit:
        candidates = [group for group in sets if len(group[2]) > 1]
        if not candidates:
            return None, removed
        message, prefix, hits = max(candidates, key=lambda group: len(group[2]))
        hits.pop()
        removed += 1
        message["content"] = prefix + json.dumps(hits, ensure_ascii=False)
    return fitted, removed
