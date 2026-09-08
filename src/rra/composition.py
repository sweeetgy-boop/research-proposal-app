"""의존성 조립. 전 계층을 아는 유일한 모듈."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from rra.settings import Settings, load_settings

__all__ = [
    "Settings",
    "build_embedding",
    "build_llm",
    "build_precheck",
    "build_prompt_library",
    "build_repository",
    "llm_config",
    "load_settings",
    "read_config",
]

DEFAULT_STAGE = "compose"


def read_config(name: str, settings: Settings) -> dict[str, Any]:
    path = Path(settings.config_dir) / name
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _env_first(settings: Settings, field: str, fallback: Any) -> Any:
    """환경변수가 실제로 설정되었으면 그 값을, 아니면 yaml 값을 쓴다."""
    if field in settings.model_fields_set:
        return getattr(settings, field)
    return fallback if fallback is not None else getattr(settings, field)


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


def build_prompt_library(settings: Settings | None = None):
    """PromptLibraryPort 구현체. config/prompts/ 가 있으면 패키지 기본 프롬프트를 덮어쓴다."""
    from rra.adapters.llm import FilePromptLibrary

    settings = settings or load_settings()
    override = Path(settings.config_dir) / "prompts"
    return FilePromptLibrary(override if override.is_dir() else None)


def llm_config(settings: Settings, stage: str = DEFAULT_STAGE) -> dict[str, Any]:
    """llm.yaml + 환경변수를 합쳐 단계별 LLM 설정을 만든다. 순수 딕셔너리 계산."""
    cfg = read_config("llm.yaml", settings)
    stages = cfg.get("stages") or {}
    if stage not in stages:
        raise KeyError(f"config/llm.yaml 의 stages 에 {stage!r} 가 없습니다: {sorted(stages)}")
    stage_cfg = stages[stage] or {}
    limits = cfg.get("limits") or {}
    timeout = cfg.get("timeout") or {}
    retries = cfg.get("retries") or {}
    return {
        "provider": _env_first(settings, "llm_provider", cfg.get("provider")),
        "base_url": _env_first(settings, "llm_base_url", cfg.get("base_url")),
        "model": stage_cfg.get("model") or "local",
        "max_tokens": int(stage_cfg.get("max_tokens", 1024)),
        "max_tokens_cap": int(limits.get("max_tokens_cap", 4096)),
        "prompt_max_chars": int(limits.get("prompt_max_chars", 60_000)),
        "temperature": float(cfg.get("temperature", 0.2)),
        "json_mode": str(cfg.get("json_mode", "auto")),
        "timeout": {
            "connect": float(timeout.get("connect", 5)),
            "read": float(timeout.get("read", 180)),
            "write": float(timeout.get("write", 10)),
            "pool": float(timeout.get("pool", 5)),
        },
        "retry": {
            "attempts": int(retries.get("attempts", 3)),
            "backoff_sec": float(retries.get("backoff_sec", 0.5)),
            "max_backoff_sec": float(retries.get("max_backoff_sec", 8)),
        },
    }


def build_llm(settings: Settings | None = None, *, stage: str = DEFAULT_STAGE):
    """LLMPort 구현체. 단계별 model·max_tokens 에 바인딩된 인스턴스를 돌려준다.

    보안 H: provider 가 로컬인데 base_url 이 루프백이 아니면 여기서 예외가 나며 기동하지 않는다.
    """
    import httpx

    from rra.adapters.llm import OpenAICompatLLM, RetryPolicy

    settings = settings or load_settings()
    cfg = llm_config(settings, stage)
    return OpenAICompatLLM(
        cfg["base_url"],
        cfg["model"],
        provider=cfg["provider"],
        api_key=settings.llm_api_key.get_secret_value(),
        max_tokens=cfg["max_tokens"],
        max_tokens_cap=cfg["max_tokens_cap"],
        prompt_max_chars=cfg["prompt_max_chars"],
        temperature=cfg["temperature"],
        json_mode=cfg["json_mode"],
        timeout=httpx.Timeout(**cfg["timeout"]),
        retry=RetryPolicy(**cfg["retry"]),
    )


def build_precheck(settings: Settings | None = None, repo=None):
    """PrecheckOverlap 유스케이스. repo 를 주면 그대로 쓴다(테스트·MCP 조립용)."""
    from rra.application.usecases.precheck_overlap import PrecheckOverlap

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    return PrecheckOverlap(repo)
