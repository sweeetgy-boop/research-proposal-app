from __future__ import annotations

import json
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
