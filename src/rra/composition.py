"""의존성 조립. 전 계층을 아는 유일한 모듈."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from rra.settings import Settings, load_settings

__all__ = [
    "Settings",
    "SOURCE_NAMES",
    "alio_inbox_status",
    "alio_summary_inbox_status",
    "build_alio_catalog",
    "build_alio_source",
    "build_alio_summary_source",
    "LOCAL_USER",
    "build_embedding",
    "build_generate",
    "build_ingest",
    "build_list_missing",
    "build_llm",
    "build_openalex_source",
    "build_precheck",
    "build_prompt_library",
    "build_repository",
    "build_run_manager",
    "build_ntis_source",
    "build_scienceon_source",
    "build_sources",
    "check_sources",
    "credential_status",
    "institutions",
    "own_unit",
    "MissingCredential",
    "check_served_model",
    "fetch_alio_catalog",
    "lint_rules",
    "llm_config",
    "load_settings",
    "read_config",
    "sandbox_limits",
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
        "served_model": str(cfg.get("served_model") or "").strip() or None,
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


async def check_served_model(cfg: dict[str, Any], llm) -> str | None:
    """llm-check 용 진단. served_model 이 서버 /v1/models 목록에 없으면 경고 문구, 괜찮으면 None.

    목록은 HF 캐시 스캔이라 '로드된' 모델을 특정하지 못한다 — 오타·엉뚱한 이름만 거른다.
    기동을 막지 않는다 (경고만).
    """
    from rra.adapters.llm._endpoint import served_model_listed

    served = cfg.get("served_model")
    if not served:
        return "llm.yaml 에 served_model 이 없습니다 — manifest 에 요청용 모델 이름이 남습니다."
    lister = getattr(llm, "list_models", None)
    if lister is None:
        return None
    try:
        listed = await lister()
    except Exception as exc:  # 진단일 뿐 — 실패해도 왕복 확인은 계속한다
        return f"/v1/models 조회 실패 ({type(exc).__name__}) — served_model 을 확인하지 못했습니다."
    candidates = {served}
    path = Path(served).expanduser()
    if path.exists():  # 로컬 경로로 띄운 경우 서버는 절대경로를 싣는다
        candidates.add(str(path.resolve()))
    if served_model_listed(candidates, listed):
        return None
    shown = ", ".join(listed[:5]) + (" …" if len(listed) > 5 else "") if listed else "(비어 있음)"
    return (
        f"served_model {served!r} 이 서버 /v1/models 목록에 없습니다 — 오타이거나 다른 모델입니다. "
        f"목록: {shown}"
    )


def build_openalex_source(settings: Settings | None = None, *, transport=None):
    """OpenAlexSource. 허용목록은 security.yaml, 요청 정책은 sources.yaml 에서 읽는다 (보안 C)."""
    import httpx

    from rra.adapters.sources import GuardedClient, OpenAlexSource

    settings = settings or load_settings()
    security = read_config("security.yaml", settings)
    cfg = read_config("sources.yaml", settings).get("openalex") or {}
    timeout = cfg.get("timeout") or {}
    client = GuardedClient(
        security.get("allowed_domains") or [],
        timeout=httpx.Timeout(
            float(timeout.get("connect", 10)), read=float(timeout.get("read", 30))
        ),
        max_redirects=int(cfg.get("max_redirects", 3)),
        max_response_bytes=int(float(cfg.get("max_response_mb", 20)) * 1024 * 1024),
        rate_limit=float(cfg["rate_limit"]) if cfg.get("rate_limit") else None,
        retries=int(cfg.get("retries", 3)),
        transport=transport,
    )
    limits = security.get("input_limits") or {}
    return OpenAlexSource(
        client,
        base_url=str(cfg.get("base_url", "https://api.openalex.org")),
        per_page=int(cfg.get("per_page", 100)),
        default_query=str(cfg.get("default_query", "railway")),
        lookback_days=int(cfg.get("lookback_days", 7)),
        query_max_chars=int(limits.get("query_max_chars", 500)),
        mailto=cfg.get("mailto") or None,
    )


def sandbox_limits(settings: Settings):
    """B. 파서 격리 상한 — config/security.yaml 의 file_limits."""
    from rra.adapters.sources._sandbox import SandboxLimits

    return SandboxLimits.from_security_config(read_config("security.yaml", settings))


def _alio_config(settings: Settings) -> dict[str, Any]:
    return read_config("sources.yaml", settings).get("alio") or {}


def build_alio_catalog(settings: Settings | None = None):
    """CatalogPort 구현체 (data/catalog 의 최신 CSV)."""
    from rra.adapters.sources.alio import FileCatalog

    settings = settings or load_settings()
    cfg = _alio_config(settings)
    return FileCatalog(
        Path(cfg.get("catalog_dir", "data/catalog")),
        limits=sandbox_limits(settings),
        institutions=institutions(settings),
        columns=(cfg.get("catalog") or {}).get("columns") or None,
    )


def build_alio_source(settings: Settings | None = None):
    """AlioSource (filedrop). 카탈로그가 있으면 파일명 stem 으로 메타데이터를 붙인다."""
    from rra.adapters.sources.alio import AlioSource

    settings = settings or load_settings()
    cfg = _alio_config(settings)
    return AlioSource(
        Path(cfg.get("inbox_dir", "data/inbox/alio")),
        limits=sandbox_limits(settings),
        catalog=build_alio_catalog(settings),
    )


def _alio_summary_config(settings: Settings) -> dict[str, Any]:
    return _alio_config(settings).get("summary") or {}


def build_alio_summary_source(settings: Settings | None = None):
    """AlioSummarySource (원문 비공개 보고서의 공개 요약 .txt). 파일명 stem 으로 카탈로그 매칭."""
    from rra.adapters.sources.alio import AlioSummarySource

    settings = settings or load_settings()
    cfg = _alio_summary_config(settings)
    return AlioSummarySource(
        Path(cfg.get("inbox_dir", "data/inbox/alio_summary")),
        limits=sandbox_limits(settings),
        institutions=institutions(settings),
        catalog=build_alio_catalog(settings),
        labels=cfg.get("labels") or None,
        max_bytes=int(cfg.get("max_file_kb", 256)) * 1024,
        default_org=cfg.get("default_org") or None,
    )


async def fetch_alio_catalog(
    settings: Settings | None = None, *, transport=None, resolver=None
) -> Path:
    """sources.yaml 의 fetch_url 을 GuardedClient 로 받아 catalog_dir 에 저장 (보안 C·B)."""
    from rra.adapters.sources import GuardedClient
    from rra.adapters.sources.alio import fetch_catalog

    settings = settings or load_settings()
    cfg = _alio_config(settings)
    catalog_cfg = cfg.get("catalog") or {}
    url = str(catalog_cfg.get("fetch_url") or "")
    if not url:
        raise ValueError("config/sources.yaml 의 alio.catalog.fetch_url 이 비어 있습니다.")
    max_bytes = int(float(catalog_cfg.get("max_response_mb", 50)) * 1024 * 1024)
    security = read_config("security.yaml", settings)
    async with GuardedClient(
        security.get("allowed_domains") or [],
        max_response_bytes=max_bytes,
        transport=transport,
        **({"resolver": resolver} if resolver else {}),
    ) as client:
        return await fetch_catalog(
            client, url, Path(cfg.get("catalog_dir", "data/catalog")), max_bytes=max_bytes
        )


def alio_inbox_status(settings: Settings | None = None) -> dict[str, int]:
    from rra.adapters.sources.alio import inbox_status

    settings = settings or load_settings()
    return inbox_status(Path(_alio_config(settings).get("inbox_dir", "data/inbox/alio")))


def alio_summary_inbox_status(settings: Settings | None = None) -> dict[str, int]:
    from rra.adapters.sources.alio import inbox_status

    settings = settings or load_settings()
    return inbox_status(
        Path(_alio_summary_config(settings).get("inbox_dir", "data/inbox/alio_summary"))
    )


def build_list_missing(settings: Settings | None = None, repo=None):
    """ListMissing 유스케이스. repo 를 주면 그대로 쓴다(테스트용)."""
    from rra.application.usecases.list_missing import ListMissing

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    return ListMissing(build_alio_catalog(settings), repo)


def own_unit(settings: Settings):
    """own 티어 기준 (sources.yaml own_unit). 설정이 없으면 None → own 티어 없음."""
    from rra.domain.rules.overlap import OwnUnit

    cfg = read_config("sources.yaml", settings).get("own_unit")
    if not cfg:
        return None
    return OwnUnit(
        org=str(cfg.get("org") or "korail"),
        departments=frozenset(str(d).strip() for d in cfg.get("departments") or [] if d),
    )


def institutions(settings: Settings) -> list[dict[str, Any]]:
    """대상 기관 목록 (sources.yaml 최상위). 예전 위치(alio.institutions)도 읽는다."""
    cfg = read_config("sources.yaml", settings)
    return list(cfg.get("institutions") or (cfg.get("alio") or {}).get("institutions") or [])


class MissingCredential(ValueError):
    """요청한 소스의 키가 .env 에 없다. 메시지에는 변수 이름만 (값 없음)."""


# 소스별 필요한 .env 변수 → Settings 필드
CREDENTIALS: dict[str, dict[str, str]] = {
    "scienceon": {
        "RRA_SCIENCEON_CLIENT_ID": "scienceon_client_id",
        "RRA_SCIENCEON_KEY": "scienceon_key",
        "RRA_SCIENCEON_MAC": "scienceon_mac",
    },
    "ntis": {"RRA_NTIS_KEY": "ntis_key"},
}


def credential_status(settings: Settings, source: str) -> dict[str, bool]:
    """{변수 이름: 값이 있는지}. 값 자체는 돌려주지 않는다."""
    out = {}
    for env, field in CREDENTIALS.get(source, {}).items():
        secret = getattr(settings, field)
        out[env] = bool(secret is not None and secret.get_secret_value().strip())
    return out


def _require(settings: Settings, source: str) -> None:
    missing = [env for env, ok in credential_status(settings, source).items() if not ok]
    if missing:
        raise MissingCredential(
            f"{source} 수집에 필요한 키가 .env 에 없습니다: {', '.join(missing)} "
            "(README 발급 절차 참고)"
        )


def _guarded(settings: Settings, cfg: dict[str, Any], *, transport=None, resolver=None):
    import httpx

    from rra.adapters.sources import GuardedClient

    security = read_config("security.yaml", settings)
    timeout = cfg.get("timeout") or {}
    return GuardedClient(
        security.get("allowed_domains") or [],
        timeout=httpx.Timeout(
            float(timeout.get("connect", 10)), read=float(timeout.get("read", 30))
        ),
        max_redirects=int(cfg.get("max_redirects", 3)),
        max_response_bytes=int(float(cfg.get("max_response_mb", 20)) * 1024 * 1024),
        rate_limit=float(cfg["rate_limit"]) if cfg.get("rate_limit") else None,
        max_requests=int(cfg["max_requests_per_run"]) if cfg.get("max_requests_per_run") else None,
        retries=int(cfg.get("retries", 3)),
        max_backoff_sec=float(cfg.get("max_backoff_sec", 30)),
        transport=transport,
        **({"resolver": resolver} if resolver else {}),
    )


def build_scienceon_source(settings: Settings | None = None, *, transport=None, resolver=None):
    """ScienceONSource. 키 3종(.env) 없으면 MissingCredential. 레이트리밋은 sources.yaml."""
    from rra.adapters.sources.scienceon import ScienceOnSource, TokenManager

    settings = settings or load_settings()
    _require(settings, "scienceon")
    cfg = read_config("sources.yaml", settings).get("scienceon") or {}
    base_url = str(cfg.get("base_url", "https://apigateway.kisti.re.kr"))
    client = _guarded(settings, cfg, transport=transport, resolver=resolver)
    tokens = TokenManager(
        client,
        base_url,
        client_id=settings.scienceon_client_id,
        auth_key=settings.scienceon_key,
        mac=settings.scienceon_mac,
    )
    return ScienceOnSource(
        client,
        tokens,
        base_url=base_url,
        targets=list(cfg.get("targets") or ["ARTI"]),
        queries=list(cfg.get("queries") or ["철도"]),
        search_field=str(cfg.get("search_field", "BI")),
        row_count=int(cfg.get("row_count", 50)),
        max_consecutive_429=int(cfg.get("max_consecutive_429", 2)),
    )


def build_ntis_source(settings: Settings | None = None, *, transport=None, resolver=None):
    """NtisProjectSource (과제검색). RRA_NTIS_KEY 없으면 MissingCredential."""
    from rra.adapters.sources.ntis import NtisProjectSource

    settings = settings or load_settings()
    _require(settings, "ntis")
    cfg = read_config("sources.yaml", settings).get("ntis") or {}
    return NtisProjectSource(
        _guarded(settings, cfg, transport=transport, resolver=resolver),
        apprv_key=settings.ntis_key,
        base_url=str(cfg.get("base_url", "https://www.ntis.go.kr")),
        project_path=str(cfg.get("project_path", "/rndopen/openApi/public_project")),
        queries=list(cfg.get("queries") or ["철도"]),
        institutions=institutions(settings),
        search_field=str(cfg.get("search_field", "BI")),
        display_count=int(cfg.get("display_count", 100)),
        record_tag=str(cfg.get("record_tag") or "") or None,
    )


KEYED_SOURCES = ("scienceon", "ntis")


async def check_sources(
    settings: Settings | None = None, names=KEYED_SOURCES, *, transport=None, resolver=None
) -> list[dict[str, Any]]:
    """rra sources check — 소스별 키 유무(값 없음)·허용목록·왕복 1회. 실패는 예외 클래스명과 메시지.

    메시지는 FetchError 계열이라 비밀이 제거된 URL 만 담는다.
    """
    from urllib.parse import urlsplit

    settings = settings or load_settings()
    allowed = set(read_config("security.yaml", settings).get("allowed_domains") or [])
    builders = {"scienceon": build_scienceon_source, "ntis": build_ntis_source}
    results = []
    for name in names:
        cfg = read_config("sources.yaml", settings).get(name) or {}
        host = urlsplit(str(cfg.get("base_url", ""))).hostname or ""
        row: dict[str, Any] = {
            "source": name,
            "credentials": credential_status(settings, name),
            "host": host,
            "host_allowed": host in allowed,
            "roundtrip": "skipped",
        }
        if all(row["credentials"].values()) and row["host_allowed"]:
            source = builders[name](settings, transport=transport, resolver=resolver)
            try:
                row["result"] = await source.probe()
                row["roundtrip"] = "ok"
            except Exception as exc:  # 진단 — 다음 소스도 확인한다
                row["roundtrip"] = type(exc).__name__
                row["error"] = str(exc)[:300]
            finally:
                await source.aclose()
        results.append(row)
    return results


_SOURCE_BUILDERS = {
    "openalex": build_openalex_source,
    "alio": build_alio_source,
    "alio_summary": build_alio_summary_source,
    "scienceon": build_scienceon_source,
    "ntis": build_ntis_source,
}
SOURCE_NAMES = tuple(_SOURCE_BUILDERS)


def build_sources(names: list[str], settings: Settings | None = None) -> list:
    """이름 목록 → SourcePort 구현체 목록. 모르는 이름은 KeyError."""
    unknown = [n for n in names if n not in _SOURCE_BUILDERS]
    if unknown:
        raise KeyError(f"알 수 없는 소스: {unknown} (가능: {list(SOURCE_NAMES)})")
    settings = settings or load_settings()
    return [_SOURCE_BUILDERS[n](settings) for n in names]


def build_ingest(settings: Settings | None = None, *, sources, repo=None, limit: int = 200):
    """IngestSources 유스케이스. repo 를 주면 그대로 쓴다(테스트용)."""
    from rra.application.usecases.ingest_sources import IngestSources

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    return IngestSources(sources, repo, limit=limit, own=own_unit(settings))


TEMPLATE = "proposal_korail"
LOCAL_USER = "local"  # stdio·CLI: 프로세스 소유자 = 사용자. 다중 사용자는 Step 10 (REST 인증)


def lint_rules(settings: Settings):
    """config/templates/<TEMPLATE>.rules.yaml → LintRules. 섹션 순서 = required_sections."""
    from rra.domain.rules.lint import LintRules

    data = read_config(f"templates/{TEMPLATE}.rules.yaml", settings)
    if not data.get("required_sections"):
        raise KeyError(f"templates/{TEMPLATE}.rules.yaml 에 required_sections 가 없습니다.")
    return LintRules.model_validate(data)


def build_generate(settings: Settings | None = None, *, repo=None, llm=None):
    """GenerateProposal 유스케이스. repo·llm 을 주면 그대로 쓴다(테스트용)."""
    from rra.application.usecases.generate_proposal import GenerateProposal

    settings = settings or load_settings()
    rules = lint_rules(settings)
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    if llm is None:
        llm = build_llm(settings, stage="compose")
    return GenerateProposal(
        llm, repo, build_prompt_library(settings), rules, list(rules.required_sections)
    )


class _Lazy:
    """처음 쓰일 때 만든다. `rra runs list` 처럼 상태만 읽을 때 임베딩 모델·LLM 클라이언트를
    띄우지 않기 위함."""

    def __init__(self, factory):
        self._factory = factory
        self._obj = None

    def __getattr__(self, name):
        if self._obj is None:
            self._obj = self._factory()
        return getattr(self._obj, name)

    async def aclose(self) -> None:
        if self._obj is not None and hasattr(self._obj, "aclose"):
            await self._obj.aclose()


def build_run_manager(settings: Settings | None = None, *, repo=None, llm=None):
    """RunManager — 파일 저장소(runs/), 프로세스 간 슬롯, manifest 로그.

    repo·llm 을 안 주면 처음 쓰일 때 만든다 (상태 조회만 할 때는 로드하지 않음).
    """
    from rra.adapters.runs import FileRunLog, FileRunStore, FlockSlot
    from rra.application.services import RunManager

    settings = settings or load_settings()
    limits = read_config("security.yaml", settings).get("input_limits") or {}
    root = Path(settings.runs_dir)
    compose_cfg = llm_config(settings, "compose")
    # manifest 에는 선언된 실제 모델명(served_model)을, 없으면 요청용 이름을 남긴다
    model = compose_cfg["served_model"] or compose_cfg["model"]
    if repo is None:
        repo = _Lazy(lambda: build_repository(build_embedding(settings), settings))
    if llm is None:
        llm = _Lazy(lambda: build_llm(settings, stage="compose"))
    return RunManager(
        build_generate(settings, repo=repo, llm=llm),
        FileRunStore(root),
        FlockSlot(root / ".generate.lock"),
        FileRunLog(root),
        max_queued=int(limits.get("max_queued_runs", 3)),
        model=model,
    )


def build_precheck(settings: Settings | None = None, repo=None):
    """PrecheckOverlap 유스케이스. repo 를 주면 그대로 쓴다(테스트·MCP 조립용)."""
    from rra.application.usecases.precheck_overlap import PrecheckOverlap

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    return PrecheckOverlap(repo, own=own_unit(settings))
