from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from rra.domain.models import Chunk, Document


class FakeLLM:
    def __init__(self, responses: list[str] | None = None):
        self.responses = list(responses or [])
        self.calls: list[str] = []

    async def complete(self, prompt, *, system=None, max_tokens=None, json_mode=False) -> str:
        self.calls.append(prompt)
        return self.responses.pop(0) if self.responses else "[]"


class FakeEmbedding:
    dim = 4

    def embed(self, texts):
        return [[float(len(t) % 7), 0.0, 0.0, 0.0] for t in texts]

    def embed_query(self, texts):
        return self.embed(texts)


class DeterministicEmbedding:
    """토큰 해시 백오브워즈. 모델 없이도 '의미 있는' 순서를 만드는 임베딩.

    같은 토큰을 공유할수록 코사인 유사도가 높아지므로 검색 순위 검증에 쓸 수 있다.
    """

    _TOKEN = re.compile(r"[^\W_]+", re.UNICODE)

    def __init__(self, dim: int = 32):
        self.dim = dim

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in self._TOKEN.findall(text.lower()):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            vec[int.from_bytes(digest[:4], "big") % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec

    def embed(self, texts):
        return [self._vector(t) for t in texts]

    def embed_query(self, texts):
        return self.embed(texts)


class InMemoryRepository:
    def __init__(self):
        self.docs: dict[str, Document] = {}
        self.chunks: list[Chunk] = []
        self.similar: list[tuple[Document, float]] = []

    def upsert(self, docs, chunks):
        for d in docs:
            self.docs[d.doc_id] = d
        self.chunks.extend(chunks)

    def hybrid_search(self, queries, *, k=20, orgs=None):
        return self.chunks[:k]

    def find_similar(self, text, *, k=10):
        return self.similar[:k]

    def get_document(self, doc_id):
        return self.docs.get(doc_id)


class FakeRenderer:
    def render(self, draft) -> bytes:
        return json.dumps({s.key: s.text for s in draft.sections}, ensure_ascii=False).encode()


class FakeRunLog:
    def __init__(self):
        self.records: list[tuple[str, dict[str, Any]]] = []

    def record(self, run_id, manifest):
        self.records.append((run_id, manifest))
