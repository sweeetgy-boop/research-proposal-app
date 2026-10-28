"""프로세스 하나에 GPU(MPS/Metal) 잠금 하나 — 임베딩·reranker 등 로컬 모델의 적재·계산 공용.

모델마다 따로 잠그면 서로 다른 스레드(asyncio.to_thread)에서 두 모델이 동시에 Metal 명령을 보내
`failed assertion _status < MTLCommandBufferStatusCommitted` 로 프로세스가 SIGABRT 로 죽는다
(2026-10-28 [5] 동시 3건 측정에서 재현 — 운영 api 면 api 가 통째로 죽는다). 그래서 GPU 를 쓰는
코드는 모두 이 잠금 하나를 잡는다. 같은 스레드 안의 중첩(적재 안의 계산 등)을 위해 RLock.
"""

from __future__ import annotations

import threading

GPU_LOCK = threading.RLock()
