import httpx
import pytest

from app.db import Database
from app.retrieval import chunks_for, get_index


def test_chunks_keep_page_and_exact_original_offsets():
    pages = [
        {"number": 1, "text": ("原文第一行\n" * 180)},
        {"number": 2, "text": "Second page, separate report evidence."},
    ]
    chunks = chunks_for(pages)
    assert len(chunks) >= 3
    for chunk in chunks:
        text = pages[chunk.page - 1]["text"]
        assert text[chunk.start : chunk.start + len(chunk.text)] == chunk.text
    assert chunks[1].start < len(chunks[0].text)


def test_partial_build_is_retried_and_complete_cache_reused(tmp_path):
    import asyncio

    db = Database(tmp_path / "cache.db")
    pages = [{"number": 1, "text": "page data " * 1800}]
    report = {"id": "r", "digest": "signed"}
    with db.connect() as conn:
        conn.execute("INSERT INTO reports(id,company,filename,digest) VALUES('r','a','a','signed')")
    calls = []

    def respond(req):
        import json

        if req.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "test", "digest": "v1"}]})
        batch = json.loads(req.content)["input"]
        calls.append(len(batch))
        if len(calls) == 2:
            return httpx.Response(503)
        return httpx.Response(200, json={"embeddings": [[1.0, 0.0] for _ in batch]})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with pytest.raises(httpx.HTTPStatusError):
                await get_index(client, db, report, pages, "http://test", "test")
            with db.connect() as conn:
                assert conn.execute("SELECT COUNT(*) FROM rag_indexes").fetchone()[0] == 0
            built, _ = await get_index(client, db, report, pages, "http://test", "test")
            count = len(calls)
            cached, _ = await get_index(client, db, report, pages, "http://test", "test")
            assert count == len(calls)
            assert built.rank("page data", [1, 0]) == cached.rank("page data", [1, 0])

    asyncio.run(scenario())
