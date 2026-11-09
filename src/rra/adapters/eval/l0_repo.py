"""L0 합성 코퍼스 메모리 저장소 (계약 §4 L0) — 임베딩 모델·운영 DB 없이 CI 에서 돈다.

`tests/eval/l0_corpus.jsonl`(Document 필드 한 줄씩, 합성·공개 자료만)을 읽어 DocumentRepository +
CorpusAccessPort 를 흉내 낸다. 유사도는 어절 해시 백오브워즈 벡터의 코사인을 e5 의 압축된 분포에
맞춰 보정한 값 `SIM_FLOOR + (1 - SIM_FLOOR) × cos` — 무관한 한국어 문서도 0.79 근처가 나오는 실제
분포(architecture §4.7)처럼 own 임계치 0.80·키워드 조건이 뜻을 갖게 한다. 검색 규칙·풀·판정 규칙의
회귀를 재는 용도이지 실제 e5 품질을 대신하지 않는다(실제 e5 는 `rra eval run --suite l0 --real`).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

from rra.domain.models import Chunk, Document

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
SIM_FLOOR = 0.78
DIM = 256


def load_corpus(path: str | Path) -> list[Document]:
    docs: list[Document] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            docs.append(Document.model_validate(json.loads(line)))
    return docs


def _vector(text: str) -> list[float]:
    vec = [0.0] * DIM
    for tok in _TOKEN.findall(text.lower()):
        digest = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
        vec[int.from_bytes(digest[:4], "big") % DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec


def _text(doc: Document) -> str:
    return " ".join(p for p in (doc.title, doc.abstract, doc.body) if p)


class L0Repository:
    def __init__(self, docs: Iterable[Document] = ()):
        self.docs: dict[str, Document] = {}
        self._vectors: dict[str, list[float]] = {}
        self.chunks: list[Chunk] = []
        for d in docs:
            self._add(d)

    def _add(self, doc: Document) -> None:
        self.docs[doc.doc_id] = doc
        self._vectors[doc.doc_id] = _vector(_text(doc))

    async def upsert(self, docs, chunks) -> None:
        for d in docs:
            self._add(d)
        self.chunks.extend(chunks)

    async def hybrid_search(self, queries, *, k=20, orgs=None, sources=None):
        return []  # 생성 근거 검색은 L0 범위 밖 (검색·판정만)

    async def find_similar(self, text, *, k=10, sources=None):
        q = _vector(text or "")
        if not any(q):
            return []
        today = date.today()
        scored: list[tuple[Document, float]] = []
        for doc_id, vec in self._vectors.items():
            doc = self.docs[doc_id]
            if sources and doc.source not in sources:
                continue
            if not doc.is_valid_on(today):
                continue
            cos = sum(a * b for a, b in zip(q, vec, strict=True))
            scored.append((doc, round(SIM_FLOOR + (1.0 - SIM_FLOOR) * max(0.0, cos), 4)))
        scored.sort(key=lambda ds: (-ds[1], ds[0].doc_id))
        return scored[: max(0, int(k))]

    async def get_document(self, doc_id):
        return self.docs.get(doc_id)

    async def count_by_source(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for d in self.docs.values():
            out[d.source] = out.get(d.source, 0) + 1
        return out

    async def source_status(self) -> dict[str, dict[str, Any]]:
        return {
            s: {"count": n, "last_ingested": None}
            for s, n in (await self.count_by_source()).items()
        }

    # ── CorpusAccessPort ──
    async def sample_chunks(self, limit: int) -> list[Chunk]:
        return list(self.chunks)[: max(0, limit)]

    async def documents_of(self, source: str, *, limit: int | None = None) -> list[Document]:
        docs = sorted((d for d in self.docs.values() if d.source == source), key=lambda d: d.doc_id)
        return docs if limit is None else docs[: max(0, limit)]
