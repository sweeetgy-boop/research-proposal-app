"""GPU(MPS/Metal) 잠금은 프로세스에 하나 — 임베딩·reranker 가 같은 잠금을 잡는다 (동시 run 3건에서
두 모델이 다른 스레드로 Metal 을 동시에 쓰면 SIGABRT, 2026-10-28)."""

import threading

import pytest

from rra.adapters._gpu import GPU_LOCK


def test_embedding_and_reranker_share_the_process_gpu_lock(tmp_path, monkeypatch):
    pytest.importorskip("sentence_transformers")
    from rra.adapters.embedding.sentence_transformers import SentenceTransformerEmbedding
    from rra.adapters.reranking.cross_encoder import CrossEncoderReranker

    emb = SentenceTransformerEmbedding("dummy")
    (tmp_path / "rr").mkdir()
    rr = CrossEncoderReranker(tmp_path / "rr")
    assert emb._lock is GPU_LOCK and emb._encode_lock is GPU_LOCK and rr._lock is GPU_LOCK


def test_gpu_lock_serializes_two_models_across_threads():
    active = 0
    peak = 0
    guard = threading.Lock()

    def work():
        nonlocal active, peak
        with GPU_LOCK:
            with guard:
                active += 1
                peak = max(peak, active)
            threading.Event().wait(0.02)
            with guard:
                active -= 1

    threads = [threading.Thread(target=work) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak == 1
    with GPU_LOCK:  # RLock — 같은 스레드 중첩(적재 안의 계산) 허용
        with GPU_LOCK:
            pass
