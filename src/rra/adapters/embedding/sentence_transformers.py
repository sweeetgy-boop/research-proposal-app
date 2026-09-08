"""EmbeddingPort 구현 — sentence-transformers.

- 라이브러리 import 는 생성자 안에서만 (모듈 import 에 torch 가 필요 없도록).
- H 연장선: safetensors 만, `trust_remote_code=False`, 오프라인 스위치.
- 접두어 부착·길이 절단은 순수 함수라 모델 없이 테스트한다.
"""

from __future__ import annotations

DEFAULT_MODEL = "intfloat/multilingual-e5-base"
DEFAULT_QUERY_PREFIX = "query: "
DEFAULT_PASSAGE_PREFIX = "passage: "
DEFAULT_MAX_CHARS = 8000


def prepare(texts: list[str], prefix: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    """접두어 부착 + 길이 절단. 순수 함수."""
    if max_chars < 1:
        raise ValueError("max_chars must be >= 1")
    return [f"{prefix}{(t or '').strip()[:max_chars]}" for t in texts]


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
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - 설치 환경에 따라 분기
            raise RuntimeError(
                "sentence-transformers 가 설치되어 있지 않습니다. "
                'uv pip install -e ".[embedding]" 로 설치하세요.'
            ) from exc

        self.model_name = model_name
        self.batch_size = batch_size
        self.query_prefix = query_prefix
        self.passage_prefix = passage_prefix
        self.max_chars = max_chars
        self.model = SentenceTransformer(
            model_name,
            device=device,
            trust_remote_code=False,  # 원격 코드 실행 금지
            local_files_only=local_files_only,
            model_kwargs={"use_safetensors": True},  # H: safetensors 만
        )
        self.dim = int(self.model.get_sentence_embedding_dimension())

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
