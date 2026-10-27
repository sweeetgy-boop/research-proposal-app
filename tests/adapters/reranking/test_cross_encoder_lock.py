"""cross-encoder reranker 는 모델 호출을 한 번에 하나만 — 동시 요청이 겹치지 않는다 (2026-10-27).

실제 모델 없이 `_model` 을 가짜로 바꿔 두 rerank 를 동시에 돌리고, predict 가 겹쳐 실행되지
않았는지(동시 진입 횟수 최대 1) 확인한다.
"""

import asyncio
import threading
import time

import pytest

from rra.adapters.reranking.cross_encoder import CrossEncoderReranker
from rra.domain.models import Chunk


class _SlowModel:
    def __init__(self):
        self.active = 0
        self.max_active = 0
        self._guard = threading.Lock()

    def predict(self, pairs, batch_size=16, show_progress_bar=False):
        with self._guard:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.05)
        with self._guard:
            self.active -= 1
        return [float(len(t)) for _, t in pairs]


def _chunks(n: int) -> list[Chunk]:
    return [
        Chunk(chunk_id=f"d:{i}#0", doc_id=f"d:{i}", ordinal=0, text="x" * (i + 1)) for i in range(n)
    ]


@pytest.mark.asyncio
async def test_concurrent_reranks_do_not_overlap_in_the_model(tmp_path):
    rr = CrossEncoderReranker(tmp_path)  # 폴더만 있으면 되고 모델은 지연 로딩
    model = _SlowModel()
    rr._model = model
    results = await asyncio.gather(*(rr.rerank("q", _chunks(4), k=2) for _ in range(4)))
    assert all(len(r) == 2 for r in results)
    assert model.max_active == 1
    assert rr.calls == 4
