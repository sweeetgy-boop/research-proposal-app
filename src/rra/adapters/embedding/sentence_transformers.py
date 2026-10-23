"""EmbeddingPort 구현 — sentence-transformers.

- 라이브러리 유무만 생성자에서 확인하고, 모델은 첫 embed/dim 호출 때 올린다 (지연 로딩).
  `rra runs list` 처럼 상태만 읽는 명령이 수 GB 모델을 띄우지 않게 하기 위함.
- 모듈 import 에 torch 가 필요 없다.
- H 연장선: safetensors 만, `trust_remote_code=False`, 오프라인 스위치.
- 접두어 부착·길이 절단은 순수 함수라 모델 없이 테스트한다.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
from typing import Any

DEFAULT_MODEL = "intfloat/multilingual-e5-base"
DEFAULT_QUERY_PREFIX = "query: "
DEFAULT_PASSAGE_PREFIX = "passage: "
DEFAULT_MAX_CHARS = 8000


def prepare(texts: list[str], prefix: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    """접두어 부착 + 길이 절단. 순수 함수."""
    if max_chars < 1:
        raise ValueError("max_chars must be >= 1")
    return [f"{prefix}{(t or '').strip()[:max_chars]}" for t in texts]


def library_available() -> bool:
    """sentence-transformers 가 import 가능한지 — 실제로 import 하지는 않는다 (torch 로드 회피)."""
    if "sentence_transformers" in sys.modules:
        return sys.modules["sentence_transformers"] is not None
    try:
        return importlib.util.find_spec("sentence_transformers") is not None
    except (ImportError, ValueError):
        return False


def embedding_dimension(model) -> int:
    """임베딩 차원. 신버전 `get_embedding_dimension` 우선, 구버전 이름으로 폴백."""
    getter = getattr(model, "get_embedding_dimension", None)
    if getter is None:
        getter = model.get_sentence_embedding_dimension
    return int(getter())


class SentenceTransformerEmbedding:
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        device: str | None = None,
        batch_size: int = 32,
        query_prefix: str = DEFAULT_QUERY_PREFIX,
        passage_prefix: str = DEFAULT_PASSAGE_PREFIX,
        max_chars: int = DEFAULT_MAX_CHARS,
        local_files_only: bool = False,
    ):
        if not library_available():
            raise RuntimeError(
                "sentence-transformers 가 설치되어 있지 않습니다. "
                'uv pip install -e ".[embedding]" 로 설치하세요.'
            )
        self.model_name = model_name
        self.device = device
        self.local_files_only = local_files_only
        self.batch_size = batch_size
        self.query_prefix = query_prefix
        self.passage_prefix = passage_prefix
        self.max_chars = max_chars
        self._model: Any = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def model(self) -> Any:
        """첫 접근 때 모델을 올린다. 스레드 안전 (워커가 여럿이어도 한 번만 로드)."""
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    self._model = SentenceTransformer(
                        self.model_name,
                        device=self.device,
                        trust_remote_code=False,  # 원격 코드 실행 금지
                        local_files_only=self.local_files_only,
                        model_kwargs={"use_safetensors": True},  # H: safetensors 만
                    )
        return self._model

    @property
    def dim(self) -> int:
        return embedding_dimension(self.model)

    def _encode(self, texts: list[str], prefix: str) -> list[list[float]]:
        if not texts:
            return []
        vectors = self.model.encode(
            prepare(texts, prefix, max_chars=self.max_chars),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [[float(v) for v in row] for row in vectors]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts, self.passage_prefix)

    def embed_query(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts, self.query_prefix)
