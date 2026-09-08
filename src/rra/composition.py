"""의존성 조립. 전 계층을 아는 유일한 모듈."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from rra.settings import Settings, load_settings

__all__ = [
    "Settings",
    "build_embedding",
    "build_repository",
    "load_settings",
    "read_config",
]


def read_config(name: str, settings: Settings) -> dict[str, Any]:
    path = Path(settings.config_dir) / name
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def build_embedding(settings: Settings | None = None):
    """EmbeddingPort 구현체. config/llm.yaml 의 embedding 섹션을 따른다."""
    from rra.adapters.embedding import SentenceTransformerEmbedding

    settings = settings or load_settings()
    cfg = read_config("llm.yaml", settings).get("embedding") or {}
    return SentenceTransformerEmbedding(
        cfg.get("model", "intfloat/multilingual-e5-base"),
        device=cfg.get("device"),
        batch_size=int(cfg.get("batch_size", 32)),
        local_files_only=bool(cfg.get("local_files_only", False)),
    )


def build_repository(embedding, settings: Settings | None = None):
    """DocumentRepository 구현체. 상한값은 config/security.yaml 에서 주입한다."""
    from rra.adapters.persistence import SQLiteDocumentRepository

    settings = settings or load_settings()
    limits = read_config("security.yaml", settings).get("input_limits") or {}
    return SQLiteDocumentRepository(
        settings.db_path,
        embedding,
        max_query_chars=int(limits.get("query_max_chars", 500)),
    )
