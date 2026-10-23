"""의존성 조립. 전 계층을 아는 유일한 모듈.

여기에는 build_* (포트 ↔ 어댑터 연결)만 둔다. 설정 읽기·병합은 rra/config_loader.py,
진단 로직은 application/usecases/diagnostics.py. 이 모듈은 로더 결과를 받아 객체를 만들 뿐이다.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from rra.config_loader import (
    CREDENTIALS,
    DEFAULT_STAGE,
    KEYED_SOURCES,
    MissingCredential,
    allowed_domains,
    credential_status,
    input_limits,
    institutions,
    keyword_rule,
    lint_rules,
    llm_config,
    own_unit,
    read_config,
    require_credentials,
    security_config,
    served_model_aliases,
    source_config,
    strategy_catalog,
)
from rra.settings import Settings, load_settings

__all__ = [
    # 재수출 — 진입점은 composition 만 import 한다
    "CREDENTIALS",
    "KEYED_SOURCES",
    "LOCAL_USER",
    "MissingCredential",
    "SOURCE_NAMES",
    "Settings",
    "credential_status",
    "institutions",
    "keyword_rule",
    "lint_rules",
    "llm_config",
    "load_settings",
    "own_unit",
    "read_config",
    "strategy_catalog",
    # 조립
    "build_alio_catalog",
    "build_alio_catalog_fetcher",
    "build_alio_source",
    "build_alio_summary_source",
    "build_assistant",
    "build_embedding",
    "build_generate",
    "build_ingest",
    "build_list_missing",
    "build_llm",
    "build_ntis_source",
    "build_openalex_source",
    "build_precheck",
    "build_prompt_library",
    "build_repository",
    "build_run_manager",
    "build_scienceon_source",
    "build_served_model_check",
    "build_sources",
    "build_sources_check",
    "sandbox_limits",
]

LOCAL_USER = "local"  # stdio·CLI: 프로세스 소유자 = 사용자. 다중 사용자는 Step 10 (REST 인증)


# ── 임베딩·저장소·프롬프트·LLM ──────────────────────────────
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
    return SQLiteDocumentRepository(
        settings.db_path,
        embedding,
        max_query_chars=int(input_limits(settings).get("query_max_chars", 500)),
    )


def build_prompt_library(settings: Settings | None = None):
    """PromptLibraryPort 구현체. config/prompts/ 가 있으면 패키지 기본 프롬프트를 덮어쓴다."""
    from rra.adapters.llm import FilePromptLibrary

    settings = settings or load_settings()
    override = Path(settings.config_dir) / "prompts"
    return FilePromptLibrary(override if override.is_dir() else None)


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


def build_served_model_check(settings: Settings, llm, *, stage: str = DEFAULT_STAGE):
    """llm-check 진단 코루틴. served_model(llm.yaml) 이 서버 목록에 있는지 — 경고 문구 또는 None."""
    from rra.application.usecases.diagnostics import check_served_model

    served = llm_config(settings, stage).get("served_model")
    return check_served_model(llm, served, served_model_aliases(served))


# ── 아웃바운드 클라이언트 (보안 C) ─────────────────────────
def _guarded(settings: Settings, cfg: dict[str, Any], *, transport=None, resolver=None):
    import httpx

    from rra.adapters.sources import GuardedClient

    timeout = cfg.get("timeout") or {}
    return GuardedClient(
        allowed_domains(settings),
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


# ── 자료원 ─────────────────────────────────────────────────
def build_openalex_source(settings: Settings | None = None, *, transport=None):
    """OpenAlexSource. 허용목록은 security.yaml, 요청 정책은 sources.yaml 에서 읽는다 (보안 C)."""
    from rra.adapters.sources import OpenAlexSource

    settings = settings or load_settings()
    cfg = source_config(settings, "openalex")
    return OpenAlexSource(
        _guarded(settings, cfg, transport=transport),
        base_url=str(cfg.get("base_url", "https://api.openalex.org")),
        per_page=int(cfg.get("per_page", 100)),
        default_query=str(cfg.get("default_query", "railway")),
        lookback_days=int(cfg.get("lookback_days", 7)),
        query_max_chars=int(input_limits(settings).get("query_max_chars", 500)),
        mailto=cfg.get("mailto") or None,
    )


def sandbox_limits(settings: Settings):
    """B. 파서 격리 상한 — config/security.yaml 의 file_limits."""
    from rra.adapters.sources._sandbox import SandboxLimits

    return SandboxLimits.from_security_config(security_config(settings))


def build_alio_catalog(settings: Settings | None = None):
    """CatalogPort 구현체 (data/catalog 의 최신 CSV)."""
    from rra.adapters.sources.alio import FileCatalog

    settings = settings or load_settings()
    cfg = source_config(settings, "alio")
    return FileCatalog(
        Path(cfg.get("catalog_dir", "data/catalog")),
        limits=sandbox_limits(settings),
        institutions=institutions(settings),
        columns=(cfg.get("catalog") or {}).get("columns") or None,
    )


def build_alio_catalog_fetcher(settings: Settings | None = None, *, transport=None, resolver=None):
    """CatalogFetcher — sources.yaml 의 fetch_url 을 GuardedClient 로 받아 catalog_dir 에 저장."""
    from rra.adapters.sources import GuardedClient
    from rra.adapters.sources.alio import CatalogFetcher

    settings = settings or load_settings()
    cfg = source_config(settings, "alio")
    catalog_cfg = cfg.get("catalog") or {}
    url = str(catalog_cfg.get("fetch_url") or "")
    if not url:
        raise ValueError("config/sources.yaml 의 alio.catalog.fetch_url 이 비어 있습니다.")
    max_bytes = int(float(catalog_cfg.get("max_response_mb", 50)) * 1024 * 1024)
    client = GuardedClient(
        allowed_domains(settings),
        max_response_bytes=max_bytes,
        transport=transport,
        **({"resolver": resolver} if resolver else {}),
    )
    return CatalogFetcher(
        client, url, Path(cfg.get("catalog_dir", "data/catalog")), max_bytes=max_bytes
    )


def build_alio_source(settings: Settings | None = None):
    """AlioSource (filedrop). 카탈로그가 있으면 파일명 stem 으로 메타데이터를 붙인다."""
    from rra.adapters.sources.alio import AlioSource

    settings = settings or load_settings()
    cfg = source_config(settings, "alio")
    return AlioSource(
        Path(cfg.get("inbox_dir", "data/inbox/alio")),
        limits=sandbox_limits(settings),
        catalog=build_alio_catalog(settings),
    )


def build_alio_summary_source(settings: Settings | None = None):
    """AlioSummarySource (원문 비공개 보고서의 공개 요약 .txt). 파일명 stem 으로 카탈로그 매칭."""
    from rra.adapters.sources.alio import AlioSummarySource

    settings = settings or load_settings()
    cfg = source_config(settings, "alio").get("summary") or {}
    return AlioSummarySource(
        Path(cfg.get("inbox_dir", "data/inbox/alio_summary")),
        limits=sandbox_limits(settings),
        institutions=institutions(settings),
        catalog=build_alio_catalog(settings),
        labels=cfg.get("labels") or None,
        max_bytes=int(cfg.get("max_file_kb", 256)) * 1024,
        default_org=cfg.get("default_org") or None,
    )


def build_scienceon_source(settings: Settings | None = None, *, transport=None, resolver=None):
    """ScienceONSource. 키 3종(.env) 없으면 MissingCredential. 레이트리밋은 sources.yaml."""
    from rra.adapters.sources.scienceon import ScienceOnSource, TokenManager

    settings = settings or load_settings()
    require_credentials(settings, "scienceon")
    cfg = source_config(settings, "scienceon")
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
    require_credentials(settings, "ntis")
    cfg = source_config(settings, "ntis")
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


def build_sources_check(
    settings: Settings | None = None,
    names: Sequence[str] = KEYED_SOURCES,
    *,
    transport=None,
    resolver=None,
):
    """CheckSources 유스케이스 (`rra sources check`). 대상마다 키 유무·호스트·연결 공장을 묶는다."""
    from rra.application.usecases.diagnostics import CheckSources, SourceTarget

    settings = settings or load_settings()
    allowed = set(allowed_domains(settings))
    builders = {"scienceon": build_scienceon_source, "ntis": build_ntis_source}
    targets = []
    for name in names:
        if name not in builders:
            raise KeyError(f"연결 확인을 지원하지 않는 소스: {name} (가능: {list(builders)})")
        host = urlsplit(str(source_config(settings, name).get("base_url", ""))).hostname or ""
        creds = credential_status(settings, name)
        ready = host in allowed and all(creds.values())

        def connect(_build=builders[name]):
            return _build(settings, transport=transport, resolver=resolver)

        targets.append(SourceTarget(name, host, host in allowed, creds, connect if ready else None))
    return CheckSources(targets)


# ── 유스케이스 ─────────────────────────────────────────────
def build_list_missing(settings: Settings | None = None, repo=None):
    """ListMissing 유스케이스. repo 를 주면 그대로 쓴다(테스트용)."""
    from rra.application.usecases.list_missing import ListMissing

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    return ListMissing(build_alio_catalog(settings), repo)


def build_ingest(settings: Settings | None = None, *, sources, repo=None, limit: int = 200):
    """IngestSources 유스케이스. repo 를 주면 그대로 쓴다(테스트용)."""
    from rra.application.usecases.ingest_sources import IngestSources

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    return IngestSources(sources, repo, limit=limit, own=own_unit(settings))


def build_precheck(settings: Settings | None = None, repo=None):
    """PrecheckOverlap 유스케이스. repo 를 주면 그대로 쓴다(테스트·MCP 조립용)."""
    from rra.application.usecases.precheck_overlap import PrecheckOverlap

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    return PrecheckOverlap(repo, own=own_unit(settings), keywords=keyword_rule(settings))


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
        llm,
        repo,
        build_prompt_library(settings),
        rules,
        rules.order,
        strategy=strategy_catalog(settings),
        own=own_unit(settings),
        check_overlap=True,
        keywords=keyword_rule(settings),
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
        max_queued=int(input_limits(settings).get("max_queued_runs", 3)),
        model=model,
    )


def build_assistant(settings: Settings | None = None, *, repo=None, llm=None):
    """Agent(ProposalAssistant) — precheck·RunManager·검색이 같은 repo 를 쓴다.

    repo 는 처음 쓰일 때 만든다. sqlite 연결은 만든 스레드에서만 쓸 수 있으므로 호출자(UI 워커)는
    모든 호출을 한 스레드에서 한다.
    """
    from rra.application.services import ProposalAssistant

    settings = settings or load_settings()
    if repo is None:
        repo = _Lazy(lambda: build_repository(build_embedding(settings), settings))
    manager = build_run_manager(settings, repo=repo, llm=llm)
    return ProposalAssistant(build_precheck(settings, repo=repo), manager, repo, user=LOCAL_USER)
