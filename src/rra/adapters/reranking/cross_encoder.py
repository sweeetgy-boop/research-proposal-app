"""Q8 cross-encoder reranker 어댑터 — sentence-transformers CrossEncoder.

예: BAAI/bge-reranker-v2-m3(MIT). 모델은 ~/models/<이름> 로컬 경로에서만 올린다(저장소에 넣지
않는다). 첫 호출 때 지연 로딩, 계산은 to_thread. 집계 속성(calls·seconds·max_batch)은 Q9 측정이
읽는다.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from rra.domain.models import Chunk, Document
from rra.domain.rules.overlap import document_text


class RerankerUnavailable(RuntimeError):
    """모델 경로가 없거나 올릴 수 없다 — 조립이 reranker 없이 진행한다."""


class CrossEncoderReranker:
    def __init__(
        self,
        model_path: str | Path,
        *,
        max_length: int = 512,
        device: str | None = None,
        batch_size: int = 16,
        max_doc_chars: int = 1200,
    ):
        self.model_path = Path(model_path).expanduser()
        if not self.model_path.is_dir():
            raise RerankerUnavailable(f"reranker 모델 폴더가 없습니다: {self.model_path}")
        self.model_name = self.model_path.name
        self.max_length = max_length
        self.device = device
        self.batch_size = batch_size
        self.max_doc_chars = max_doc_chars
        self._model: Any = None
        self.calls = 0
        self.seconds = 0.0
        self.max_batch = 0

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _load(self) -> Any:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(
                str(self.model_path), max_length=self.max_length, device=self.device
            )
        return self._model

    def _scores(self, query: str, texts: list[str]) -> list[float]:
        model = self._load()
        pairs = [(query, t[: self.max_doc_chars]) for t in texts]
        started = time.perf_counter()
        scores = model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False)
        self.seconds += time.perf_counter() - started
        self.calls += 1
        self.max_batch = max(self.max_batch, len(pairs))
        return [float(s) for s in scores]

    async def rerank(self, query: str, chunks: list[Chunk], *, k: int | None = None) -> list[Chunk]:
        if not chunks or not query.strip():
            return list(chunks)[:k] if k else list(chunks)
        scores = await asyncio.to_thread(self._scores, query, [c.text for c in chunks])
        order = sorted(range(len(chunks)), key=lambda i: -scores[i])
        out = [chunks[i] for i in order]
        return out[:k] if k else out

    async def rerank_documents(
        self, query: str, docs: list[tuple[Document, float]], *, k: int | None = None
    ) -> list[tuple[Document, float]]:
        if not docs or not query.strip():
            return list(docs)[:k] if k else list(docs)
        texts = [document_text(d) for d, _ in docs]
        scores = await asyncio.to_thread(self._scores, query, texts)
        order = sorted(range(len(docs)), key=lambda i: -scores[i])
        out = [docs[i] for i in order]
        return out[:k] if k else out
