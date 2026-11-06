"""Page-preserving chunks, BM25 and local dense retrieval with reciprocal rank fusion."""

import math
import re
from array import array
from collections import Counter
from dataclasses import dataclass

import httpx

VERSION = "page-800-overlap-120-v1"
MODEL = "qwen3-embedding:0.6b"


@dataclass(frozen=True)
class Chunk:
    page: int
    start: int
    text: str


def chunks_for(pages):
    chunks = []
    for page in pages:
        text = page["text"]
        start = 0
        while start < len(text):
            end = min(len(text), start + 800)
            if end < len(text):
                boundary = text.rfind("\n", start + 480, end)
                if boundary != -1:
                    end = boundary + 1
            if text[start:end].strip():
                chunks.append(Chunk(page["number"], start, text[start:end]))
            if end == len(text):
                break
            start = end - 120
    return chunks


def terms(text):
    tokens = []
    for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", text.casefold()):
        if "\u4e00" <= token[0] <= "\u9fff" and len(token) > 1:
            tokens.extend(token[i : i + 2] for i in range(len(token) - 1))
        else:
            tokens.append(token)
    return tokens


def normalized(values):
    vec = array("f", values)
    length = math.sqrt(sum(v * v for v in vec))
    if not math.isfinite(length) or length == 0:
        raise ValueError("向量为空或包含非法数值")
    return array("f", (v / length for v in vec))


class HybridIndex:
    def __init__(self, chunks, vectors):
        if len(chunks) != len(vectors) or not chunks:
            raise ValueError("报告片段与向量数量不一致或为空")
        self.chunks = chunks
        self.vectors = vectors
        self.words = [Counter(terms(c.text)) for c in chunks]
        self.lengths = [sum(c.values()) for c in self.words]
        self.avg = max(1, sum(self.lengths) / len(chunks))
        self.df = Counter(term for counts in self.words for term in counts)

    def rank(self, query, query_vector, limit=5):
        if len(query_vector) != len(self.vectors[0]):
            raise ValueError("查询与索引向量维度不一致")
        words = set(terms(query))
        n = len(self.chunks)
        bm, dense = {}, {}
        for i, counts in enumerate(self.words):
            score = 0.0
            for t in words.intersection(counts):
                idf = math.log1p((n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                score += (
                    idf
                    * counts[t]
                    * 2.2
                    / (counts[t] + 1.2 * (0.25 + 0.75 * self.lengths[i] / self.avg))
                )
            if score > 0:
                bm[i] = score
            dense[i] = sum(x * y for x, y in zip(self.vectors[i], query_vector, strict=True))
        lexical_order = sorted(bm, key=bm.get, reverse=True)
        dense_order = sorted(dense, key=dense.get, reverse=True)
        fused = Counter()
        for order in (lexical_order, dense_order):
            for rank, i in enumerate(order[:40], 1):
                fused[i] += 1 / (60 + rank)

        def results(order, scores):
            return [
                {
                    "page": self.chunks[i].page,
                    "start": self.chunks[i].start,
                    "quote": self.chunks[i].text,
                    "score": round(scores[i], 6),
                }
                for i in order[:limit]
            ]

        return {
            "bm25": results(lexical_order, bm),
            "dense": results(dense_order, dense),
            "hybrid": results(sorted(fused, key=fused.get, reverse=True), fused),
        }


async def embed(client, url, model, inputs):
    response = await client.post(
        url + "/api/embed", json={"model": model, "input": inputs, "truncate": False}
    )
    response.raise_for_status()
    vectors = [normalized(v) for v in response.json()["embeddings"]]
    if len(vectors) != len(inputs) or len({len(v) for v in vectors}) != 1:
        raise ValueError("嵌入服务返回了不完整的向量")
    return vectors


async def get_index(client, db, report, pages, url, model):
    tags = await client.get(url + "/api/tags")
    tags.raise_for_status()
    digest = next((m["digest"] for m in tags.json()["models"] if m["name"] == model), None)
    if not digest:
        raise ValueError("请先使用 ollama pull 安装配置的嵌入模型")
    key = f"{report['digest']}:{digest}:{VERSION}"
    chunks = chunks_for(pages)
    with db.connect() as conn:
        row = conn.execute(
            "SELECT dim, vectors FROM rag_indexes WHERE report_id=? AND cache_key=?",
            (report["id"], key),
        ).fetchone()
    if row:
        packed = array("f")
        packed.frombytes(row["vectors"])
        dim = row["dim"]
        if dim > 0 and len(packed) == len(chunks) * dim:
            return HybridIndex(
                chunks, [packed[i : i + dim] for i in range(0, len(packed), dim)]
            ), digest
    vectors = []
    for start in range(0, len(chunks), 16):
        vectors.extend(
            await embed(client, url, model, [c.text for c in chunks[start : start + 16]])
        )
    if not vectors or len({len(v) for v in vectors}) != 1:
        raise ValueError("无法索引此报告")
    packed = b"".join(v.tobytes() for v in vectors)
    # Write only a complete index. Concurrent builds may duplicate work but cannot mix vectors.
    with db.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO rag_indexes(report_id,cache_key,dim,vectors) VALUES(?,?,?,?)",
            (report["id"], key, len(vectors[0]), packed),
        )
    return HybridIndex(chunks, vectors), digest


async def retrieve(db, report, pages, query, settings):
    model = settings.get("embedding_model") or MODEL
    url = settings["ollama_url"].rstrip("/")
    async with httpx.AsyncClient(timeout=120) as client:
        index, digest = await get_index(client, db, report, pages, url, model)
        instruction = (
            "Instruct: Retrieve the annual report passage that supports the question.\nQuery: "
        )
        vector = (await embed(client, url, model, [instruction + query]))[0]
    # English disclosures and Chinese paraphrases share few lexical terms.
    sample = " ".join(p["text"][:400] for p in pages[:8])
    cross_language = bool(re.search(r"[\u4e00-\u9fff]", query)) and (
        len(re.findall(r"[A-Za-z]", sample)) > 3 * len(re.findall(r"[\u4e00-\u9fff]", sample))
    )
    strategy = "dense" if cross_language else "hybrid"
    hits = index.rank(query, vector)[strategy]
    return hits, {
        "algorithm": "dense / cosine" if cross_language else "BM25 + dense / RRF",
        "strategy": strategy,
        "embedding_model": model,
        "digest": digest,
        "chunks": len(index.chunks),
        "chunking": VERSION,
    }
