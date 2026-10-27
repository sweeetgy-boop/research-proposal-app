"""의존성 조립. 전 계층을 아는 유일한 모듈.

여기에는 build_* (포트 ↔ 어댑터 연결)만 둔다. 설정 읽기·병합은 rra/config_loader.py,
진단 로직은 application/usecases/diagnostics.py. 이 모듈은 로더 결과를 받아 객체를 만들 뿐이다.
"""

from __future__ import annotations

import logging
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
    korail_web_config,
    lint_rules,
    llm_config,
    llm_key_present,
    molit_config,
    own_unit,
    pipeline_config,
    read_config,
    recommend_policy,
    relevance_floor,
    render_slots,
    render_template_path,
    require_credentials,
    retention_days,
    retrieval_mix,
    review_policy,
    section_checklists,
    security_config,
    served_model_aliases,
    source_config,
    strategy_catalog,
    usability_config,
    vision_config,
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
    "relevance_floor",
    "lint_rules",
    "llm_config",
    "load_settings",
    "own_unit",
    "read_config",
    "strategy_catalog",
    "usability_config",
    # 조립
    "build_alio_catalog",
    "build_alio_catalog_fetcher",
    "build_alio_source",
    "build_alio_summary_source",
    "build_available_sources",
    "build_kipris_source",
    "build_korail_web_crawler",
    "build_korail_web_source",
    "build_molit_source",
    "build_strategy_drafter",
    "build_own_docs_source",
    "build_own_projects_source",
    "build_api",
    "build_assistant",
    "build_briefer",
    "build_comparer",
    "build_differentiator",
    "build_embedding",
    "build_eval",
    "build_generate",
    "build_ingest",
    "build_list_missing",
    "build_llm",
    "build_ntis_insights",
    "build_ntis_report_source",
    "build_ntis_source",
    "build_openalex_source",
    "build_policy_suggest",
    "build_precheck",
    "build_prompt_library",
    "build_purge_runs",
    "build_renderer",
    "build_reranker",
    "build_outliner",
    "build_clarifier",
    "build_repository",
    "build_run_manager",
    "build_scienceon_source",
    "build_served_model_check",
    "build_sources",
    "build_sources_check",
    "build_structurer",
    "build_usage_report",
    "sandbox_limits",
]

LOCAL_USER = "local"  # stdio·CLI: 프로세스 소유자 = 사용자. 다중 사용자는 Step 10 (REST 인증)
logger = logging.getLogger("rra.composition")
_RERANKERS: dict[str, Any] = {}  # 모델 경로 → 인스턴스 (한 프로세스에 한 번만 올린다)


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


def build_db_maintenance(settings: Settings | None = None, *, repo=None):
    """DB 유지보수 유스케이스 (재색인, 백업). repo 를 주면 그대로 쓴다(테스트용)."""
    from rra.application.usecases.maintain_db import BackupDatabase, ReindexDocuments

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    return ReindexDocuments(repo), BackupDatabase(
        repo, extra_files=_korail_web_backup_files(settings)
    )


def _korail_web_backup_files(settings: Settings) -> list[Path]:
    """`rra db backup` 이 DB 사본 옆에 함께 두는 스냅샷 기록 — index.json + 최신 manifest.jsonl.
    내려받은 파일 본체는 백업하지 않는다(다시 받을 수 있다)."""
    from rra.adapters.sources.korail_web.snapshot import INDEX, latest_snapshot

    root = _korail_web_root(settings, korail_web_config(settings))
    out = [p for p in [root / INDEX] if p.is_file()]
    snap = latest_snapshot(root)
    if snap is not None:
        out.append(snap.manifest)
    return out


def build_prompt_library(settings: Settings | None = None):
    """PromptLibraryPort 구현체. config/prompts/ 가 있으면 패키지 기본 프롬프트를 덮어쓴다."""
    from rra.adapters.llm import FilePromptLibrary

    settings = settings or load_settings()
    override = Path(settings.config_dir) / "prompts"
    return FilePromptLibrary(override if override.is_dir() else None)


class LLMUnavailable(RuntimeError):
    """이 단계의 LLM 을 만들 수 없다 (키 없음 등). 메시지에 변수 이름만, 값 없음."""


def llm_available(settings: Settings, *, stage: str = DEFAULT_STAGE) -> bool:
    """단계의 provider 키가 있는지(없으면 검토 건너뜀 등). 네트워크 접속은 하지 않는다."""
    try:
        return llm_key_present(settings, llm_config(settings, stage))
    except (KeyError, ValueError):
        return False


def build_llm(
    settings: Settings | None = None, *, stage: str = DEFAULT_STAGE, provider: str | None = None
):
    """LLMPort 구현체. 단계별 model·max_tokens 에 바인딩된 인스턴스를 돌려준다.

    보안 H: provider 가 로컬인데 base_url 이 루프백이 아니면 여기서 예외가 나며 기동하지 않는다.
    보안 C: 원격 provider(gemini·openai)는 base_url 호스트가 allowed_domains 에 있어야 한다.
    보안 D: 키는 provider 별 Settings 필드(SecretStr)에서만. 없으면 LLMUnavailable (변수 이름만).
    """
    from rra.adapters.llm import OpenAICompatLLM

    return _build_openai_compat(OpenAICompatLLM, settings, stage=stage, provider=provider)


def _build_openai_compat(
    cls, settings: Settings | None, *, stage: str, provider: str | None, **extra
):
    """OpenAI 호환 어댑터 공용 조립 — 텍스트(build_llm)·이미지(build_vision_reader). 원격 provider
    는
    provider 별 공유 호출 제한기(rate)를 붙인다 (프로세스 내, adapters/llm/rate_limiter)."""
    import httpx

    from rra.adapters.llm import RetryPolicy
    from rra.adapters.llm.rate_limiter import limiter_for

    settings = settings or load_settings()
    cfg = llm_config(settings, stage, provider=provider)
    if not llm_key_present(settings, cfg):
        env = f"RRA_{cfg['api_key_field'].upper()}"
        raise LLMUnavailable(f"provider={cfg['provider']} 의 키가 .env 에 없습니다: {env}")
    key = (
        getattr(settings, cfg["api_key_field"]).get_secret_value() if cfg["api_key_field"] else None
    )
    limiter = limiter_for(cfg["provider"], **cfg["rate"]) if cfg.get("rate") else None
    return cls(
        cfg["base_url"],
        cfg["model"],
        provider=cfg["provider"],
        api_key=key,
        allowed_hosts=allowed_domains(settings),
        reasoning_effort=cfg["reasoning_effort"],
        system_role=cfg["system_role"],
        stop=cfg["stop"],
        max_tokens=cfg["max_tokens"],
        max_tokens_cap=cfg["max_tokens_cap"],
        prompt_max_chars=cfg["prompt_max_chars"],
        temperature=cfg["temperature"],
        json_mode=cfg["json_mode"],
        timeout=httpx.Timeout(**cfg["timeout"]),
        retry=RetryPolicy(**cfg["retry"]),
        limiter=limiter,
        **extra,
    )


# ── 이미지 판독 (P3) ───────────────────────────────────────
def build_vision_reader(settings: Settings | None = None):
    """VisionReaderPort (stage=vision, 기본 gemini). 키가 없으면 LLMUnavailable."""
    from rra.adapters.llm.vision_reader import OpenAICompatVisionReader

    settings = settings or load_settings()
    vcfg = vision_config(settings)
    return _build_openai_compat(
        OpenAICompatVisionReader,
        settings,
        stage="vision",
        provider=None,
        max_image_bytes=vcfg["image_max_bytes"],
    )


def build_vision_ocr(settings: Settings | None = None):
    """OcrPort — macOS Vision (격리 자식). 엔진이 없으면 None 을 돌려주고 파이프라인은
    'OCR 없음' 으로 간다."""
    from dataclasses import replace

    from rra.adapters.vision import MacVisionOcr, ocr_available

    settings = settings or load_settings()
    if not ocr_available():
        return None
    ocr_cfg = vision_config(settings)["ocr"]
    limits = replace(sandbox_limits(settings), timeout_sec=ocr_cfg["timeout_sec"])
    return MacVisionOcr(
        limits=limits,
        languages=tuple(ocr_cfg["languages"]),
        max_bytes=ocr_cfg["max_bytes"],
        max_pixels=ocr_cfg["max_pixels"],
    )


def build_vision_store(settings: Settings | None = None):
    from rra.adapters.vision import FileVisionStore

    settings = settings or load_settings()
    return FileVisionStore(Path(vision_config(settings)["store_dir"]))


def build_vision_snapshot(settings: Settings | None = None, *, snapshot: str | None = None):
    from rra.adapters.vision import SnapshotImages

    settings = settings or load_settings()
    vcfg = vision_config(settings)
    return SnapshotImages(
        Path(vcfg["snapshots_dir"]),
        snapshot,
        max_bytes=int(vcfg["filter"].get("max_bytes", 15728640)),
    )


def build_extract_attachment_images(
    settings: Settings | None = None, *, snapshot: str | None = None
):
    """첨부 속 내장 이미지 추출(`rra vision extract`) — 격리 자식, 같은 해시 하나,
    attachment_images.jsonl 에 기록."""
    from rra.adapters.vision import ExtractAttachmentImages

    settings = settings or load_settings()
    acfg = vision_config(settings)["attachments"]
    return ExtractAttachmentImages(
        build_vision_snapshot(settings, snapshot=snapshot),
        sandbox_limits(settings),
        formats=frozenset(acfg["formats"]),
        max_images_per_file=acfg["max_images_per_file"],
        max_image_bytes=acfg["max_image_bytes"],
        min_pixels=acfg["min_pixels"],
    )


def build_read_images(
    settings: Settings | None = None,
    *,
    snapshot: str | None = None,
    cap: int | None = None,
    with_reader: bool = True,
    reader=None,
    ocr=None,
    store=None,
):
    """ReadImages 유스케이스. 판독기 키가 없으면 OCR 만 (reader=None). with_reader=False 는
    dry-run·시험용."""
    from rra.application.usecases.read_images import ReadImages
    from rra.domain.rules.image_filter import ImageFilterConfig
    from rra.domain.rules.vision_plan import group_keywords

    settings = settings or load_settings()
    vcfg = vision_config(settings)
    if reader is None and with_reader:
        try:
            reader = build_vision_reader(settings)
        except LLMUnavailable:
            reader = None
    if ocr is None:
        ocr = build_vision_ocr(settings)
    prompts = build_prompt_library(settings)
    stage = llm_config(settings, "vision")
    return ReadImages(
        build_vision_snapshot(settings, snapshot=snapshot),
        store or build_vision_store(settings),
        ocr=ocr,
        reader=reader,
        prompt=prompts.vision(),
        system=prompts.system(),
        filter_config=ImageFilterConfig.from_dict(vcfg["filter"]),
        cap=cap if cap is not None else vcfg["cap"],
        keywords=group_keywords(vcfg["order_keywords"]),
        max_tokens=stage["max_tokens"],
    )


def build_ingest_image_readings(
    settings: Settings | None = None, *, snapshot: str | None = None, repo=None, store=None
):
    """판독 캐시 → DB 적재 (Argon 호출 없음). repo 를 주면 그대로 쓴다(테스트용)."""
    from rra.application.usecases.ingest_image_readings import IngestImageReadings

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    reader = build_read_images(settings, snapshot=snapshot, with_reader=False, store=store)
    return IngestImageReadings(reader, repo)


def build_reviewer(settings: Settings | None = None, *, llm=None, pipeline=None):
    """검토 유스케이스(ReviewDraft). review 단계 LLM(gemini) 키가 없으면 None → 검토 건너뜀.
    Q5 체크리스트(config/templates/section_checklists.yaml)·additions(pipeline.additions)를
    넣는다."""
    from rra.application.usecases.review_draft import ReviewDraft

    settings = settings or load_settings()
    if llm is None:
        if not llm_available(settings, stage="review"):
            return None
        llm = build_llm(settings, stage="review")
    cfg = llm_config(settings, "review")
    policy = review_policy(settings)
    pipeline = pipeline or pipeline_config(settings)
    return ReviewDraft(
        llm,
        build_prompt_library(settings),
        lint_rules(settings),
        strategy=strategy_catalog(settings),
        include_internal=policy["include_internal"],
        prompt_max_chars=cfg["prompt_max_chars"],
        provider=cfg["provider"],
        model=cfg["served_model"] or cfg["model"],
        support=usability_config(settings).evidence_support,
        checklists=section_checklists(settings),
        additions=pipeline.additions,
    )


def build_reranker(settings: Settings | None = None):
    """Q8 RerankerPort 구현체(CrossEncoderReranker) — llm.yaml reranker 섹션. 모델 폴더가 없으면
    경고만 남기고 None(reranker 없이 진행). 같은 경로는 한 프로세스에 한 번만 올린다."""
    from rra.adapters.reranking import CrossEncoderReranker, RerankerUnavailable

    settings = settings or load_settings()
    cfg = read_config("llm.yaml", settings).get("reranker") or {}
    path = str(cfg.get("model") or "~/models/bge-reranker-v2-m3")
    if path in _RERANKERS:
        return _RERANKERS[path]
    try:
        reranker = CrossEncoderReranker(
            path,
            max_length=int(cfg.get("max_length", 512)),
            device=cfg.get("device") or None,
            batch_size=int(cfg.get("batch_size", 16)),
        )
    except RerankerUnavailable as exc:
        logger.warning("reranker.unavailable reason=%s", type(exc).__name__)
        return None
    _RERANKERS[path] = reranker
    return reranker


def build_outliner(settings: Settings | None = None, *, llm=None):
    """Q2 섹션 설계도 유스케이스(OutlineSections) — outline 단계(로컬 모델)."""
    from rra.application.usecases.outline import OutlineSections

    settings = settings or load_settings()
    rules = lint_rules(settings)
    return OutlineSections(
        llm if llm is not None else build_llm(settings, stage="outline"),
        build_prompt_library(settings),
        list(rules.order),
        dict(rules.titles),
    )


def build_bench(settings: Settings | None = None, *, label: str, repo=None, llm=None):
    """로컬 작성 모델 벤치 (`rra llm-bench`). 현재 compose 단계 설정(프로필)으로 돈다."""
    from rra.adapters.llm.server_stats import server_rss_mb
    from rra.application.usecases.bench import BenchGenerate

    settings = settings or load_settings()
    cfg = llm_config(settings, "compose")
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    if llm is None:
        llm = build_llm(settings, stage="compose")
    return BenchGenerate(
        build_generate(settings, repo=repo, llm=llm),
        label=label,
        model=cfg["served_model"] or cfg["model"],
        profile=cfg["profile"],
        context_length=cfg["context_length"],
        rss_sampler=server_rss_mb,
    )


def build_eval(
    settings: Settings | None = None,
    *,
    label: str,
    pipeline,
    runs_dir: Path | str,
    repo=None,
    llm=None,
    expected=None,
):
    """초안 품질 강화 측정 유스케이스(`rra eval`, Q9) — 주어진 pipeline 구성으로 조립한 RunManager·
    precheck 로 골든셋을 돌린다. run 은 runs_dir 아래에 남는다(운영 runs/ 와 분리)."""
    from rra.adapters.llm.server_stats import server_rss_mb
    from rra.application.usecases.evaluate import EvaluateQuality

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    if llm is None:
        llm = build_llm(settings, stage="compose")
    reranker = build_reranker(settings) if pipeline.reranker else None
    manager = build_run_manager(settings, repo=repo, llm=llm, pipeline=pipeline, runs_dir=runs_dir)
    compose_cfg = llm_config(settings, "compose")
    review_cfg = llm_config(settings, "review")
    return EvaluateQuality(
        manager,
        build_precheck(settings, repo=repo, reranker=reranker, pipeline=pipeline),
        label=label,
        pipeline=pipeline.model_dump(),
        user=LOCAL_USER,
        model=compose_cfg["served_model"] or compose_cfg["model"],
        review_model=review_cfg["served_model"] or review_cfg["model"]
        if llm_available(settings, stage="review")
        else None,
        rss_sampler=server_rss_mb,
        reranker=reranker,
        keywords=keyword_rule(settings),
        expected=expected,
    )


def build_served_model_check(
    settings: Settings, llm, *, stage: str = DEFAULT_STAGE, provider: str | None = None
):
    """llm-check 진단 코루틴. served_model(llm.yaml) 이 서버 목록에 있는지 — 경고 문구 또는 None."""
    from rra.application.usecases.diagnostics import check_served_model

    served = llm_config(settings, stage, provider=provider).get("served_model")
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
        mailto=(settings.openalex_mailto or "").strip() or cfg.get("mailto") or None,
        queries=list(cfg.get("queries") or []),
        backfill_years=int(cfg.get("backfill_years", 10)),
        per_query_limit=int(cfg.get("per_query_limit", 200)),
        require_abstract=bool(cfg.get("require_abstract", True)),
        api_key=settings.openalex_api_key,
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
        per_query_limit=int(cfg["per_query_limit"]) if cfg.get("per_query_limit") else None,
        institutions=institutions(settings),
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


def build_ntis_report_source(settings: Settings | None = None, *, transport=None, resolver=None):
    """NtisReportSource (연구보고서 검색, doc_type report). 같은 RRA_NTIS_KEY (서비스별 활용신청은
    따로)."""
    from rra.adapters.sources.ntis import NtisReportSource

    settings = settings or load_settings()
    require_credentials(settings, "ntis")
    cfg = source_config(settings, "ntis")
    return NtisReportSource(
        _guarded(settings, cfg, transport=transport, resolver=resolver),
        apprv_key=settings.ntis_key,
        base_url=str(cfg.get("base_url", "https://www.ntis.go.kr")),
        report_path=str(cfg.get("report_path", "/rndopen/openApi/rresearchpdf/")),
        queries=list(cfg.get("report_queries") or cfg.get("queries") or ["철도"]),
        institutions=institutions(settings),
        search_field=str(cfg.get("search_field", "BI")),
        display_count=int(cfg.get("display_count", 100)),
        record_tag=str(cfg.get("record_tag") or "") or None,
        per_query_limit=int(cfg["per_query_limit"]) if cfg.get("per_query_limit") else None,
    )


def build_ntis_insights(
    settings: Settings | None = None, *, repo=None, transport=None, resolver=None
):
    """NtisProjectInsights 유스케이스 (성과검색·연관콘텐츠, 과제번호 파일 캐시). 키가 없으면 포트
    없이(enabled=False)."""
    from rra.adapters.persistence.file_cache import FileCache
    from rra.application.usecases.ntis_insights import NtisProjectInsights

    settings = settings or load_settings()
    cfg = source_config(settings, "ntis")
    insights = cfg.get("insights") or {}
    source = None
    if (
        settings.ntis_key
        and settings.ntis_key.get_secret_value().strip()
        and insights.get("enabled", True)
    ):
        from rra.adapters.sources.ntis import NtisInsightSource

        source = NtisInsightSource(
            _guarded(settings, cfg, transport=transport, resolver=resolver),
            apprv_key=settings.ntis_key,
            base_url=str(cfg.get("base_url", "https://www.ntis.go.kr")),
            outcome_path=str(cfg.get("outcome_path", "/rndopen/openApi/public_result")),
            related_path=str(cfg.get("related_path", "/rndopen/openApi/ConnectionContent")),
            record_tag=str(cfg.get("record_tag") or "HIT"),
            display_count=int(insights.get("max_items", 10)),
        )
    cache_dir = Path(str(insights.get("cache_dir", "data/cache/ntis")))
    cache = FileCache(cache_dir, ttl_sec=float(insights.get("cache_ttl_days", 7)) * 86400)
    return NtisProjectInsights(
        source, source, cache=cache, repo=repo, max_projects=int(insights.get("max_projects", 3))
    )


def build_kipris_source(settings: Settings | None = None, *, transport=None, resolver=None):
    """KiprisPatentSource (KIPRIS Plus 자유검색). RRA_KIPRIS_KEY 없으면 MissingCredential."""
    from rra.adapters.sources.kipris import KiprisPatentSource

    settings = settings or load_settings()
    require_credentials(settings, "kipris")
    cfg = source_config(settings, "kipris")
    return KiprisPatentSource(
        _guarded(settings, cfg, transport=transport, resolver=resolver),
        access_key=settings.kipris_key,
        base_url=str(cfg.get("base_url", "https://plus.kipris.or.kr")),
        search_path=str(
            cfg.get("search_path") or "/openapi/rest/patUtiModInfoSearchSevice/freeSearchInfo"
        ),
        queries=list(cfg.get("queries") or ["철도"]),
        institutions=institutions(settings),
        docs_count=int(cfg.get("docs_count", 50)),
        record_tag=str(cfg.get("record_tag") or "PatentUtilityInfo"),
        include_utility=bool(cfg.get("include_utility", True)),
        key_param=str(cfg.get("key_param") or "accessKey"),
    )


def build_own_projects_source(settings: Settings | None = None):
    """OwnProjectsSource — 사내 과제 현황 엑셀 (data/inbox/own). 샌드박스 xls·xlsx 파서."""
    from rra.adapters.sources.own import OwnProjectsSource

    settings = settings or load_settings()
    cfg = source_config(settings, "own")
    return OwnProjectsSource(
        Path(cfg.get("projects_inbox", "data/inbox/own")), limits=sandbox_limits(settings)
    )


def build_own_docs_source(settings: Settings | None = None):
    """OwnDocsSource — 공시완료 폴더의 공시용 요약문 (data/inbox/own_docs). 라벨은 alio 공용."""
    from rra.adapters.sources.own import OwnDocsSource

    settings = settings or load_settings()
    cfg = source_config(settings, "own")
    summary_cfg = source_config(settings, "alio").get("summary") or {}
    return OwnDocsSource(
        Path(cfg.get("docs_inbox", "data/inbox/own_docs")),
        limits=sandbox_limits(settings),
        institutions=institutions(settings),
        labels=summary_cfg.get("labels") or None,
        default_org=cfg.get("default_org") or "korail",
    )


def _korail_web_root(settings: Settings, cfg: dict[str, Any]) -> Path:
    return Path(str(cfg.get("snapshot_dir") or "data/korail_web"))


def build_korail_web_crawler(settings: Settings | None = None, *, transport=None, resolver=None):
    """KorailWebCrawler — config/korail_web.yaml. 2초 간격·동시 1·robots 준수.
    PDF 텍스트 레이어 probe 는 샌드박스."""
    from rra.adapters.sources import GuardedClient
    from rra.adapters.sources._sandbox import SandboxError, run_parser
    from rra.adapters.sources.alio._models import ExtractResult
    from rra.adapters.sources.alio.filecheck import FileRejected, open_validated
    from rra.adapters.sources.korail_web import CrawlConfig, KorailWebCrawler

    settings = settings or load_settings()
    raw = korail_web_config(settings)
    cfg = CrawlConfig.from_config(raw)
    interval = float(raw.get("min_interval_sec", 2) or 2)
    client = GuardedClient(
        allowed_domains(settings),
        rate_limit=1.0 / max(interval, 0.1),
        max_response_bytes=cfg.max_file_bytes,
        retries=0,  # 백오프·보류는 크롤러가 관리한다
        transport=transport,
        user_agent=cfg.user_agent,
        accept="text/html,application/xhtml+xml,*/*;q=0.8",
        **({"resolver": resolver} if resolver else {}),
    )
    limits = sandbox_limits(settings)

    async def pdf_probe(path: Path):
        try:
            vf = open_validated(
                path, max_bytes=int(limits.max_input_mb * 1024 * 1024), allowed=frozenset({"pdf"})
            )
        except FileRejected:
            return None
        with vf:
            try:
                result = ExtractResult.model_validate(await run_parser(vf.fd, vf.fmt, limits))
            except (SandboxError, ValueError):
                return None
        return {"pages": result.pages or 0, "text_chars": len(result.text.strip())}

    return KorailWebCrawler(client, cfg, _korail_web_root(settings, raw), pdf_probe=pdf_probe)


def build_strategy_drafter(settings: Settings | None = None, *, transport=None, resolver=None):
    """`rra strategy draft` — 중장기 경영목표 페이지 1건(GuardedClient) → 전략체계 초안 dict."""
    from rra.adapters.sources.korail_web import strategy_draft_from_html

    settings = settings or load_settings()
    crawler = build_korail_web_crawler(settings, transport=transport, resolver=resolver)

    async def draft(key: str, snapshot: str | None) -> dict[str, Any]:
        try:
            html, url = await crawler.fetch_contents(key)
        finally:
            await crawler.aclose()
        return strategy_draft_from_html(html, url=url, snapshot=snapshot)

    return draft


def build_molit_source(settings: Settings | None = None, *, transport=None, resolver=None):
    """MolitPolicySource — config/molit.yaml 질의로 국토교통부 정책자료 철도 계획 문서 (P2-1)."""
    from rra.adapters.sources.molit import MolitPolicySource

    settings = settings or load_settings()
    cfg = molit_config(settings)
    client = _guarded(settings, cfg, transport=transport, resolver=resolver)
    client._client.headers["Accept"] = "text/html,application/xhtml+xml,*/*;q=0.8"
    return MolitPolicySource(
        client,
        base_url=str(cfg.get("base_url") or "https://www.molit.go.kr"),
        list_path=str(cfg.get("list_path") or "/USR/policyData/m_34681/lst.jsp"),
        queries=[str(q) for q in cfg.get("queries") or ["철도"]],
        store_dir=Path(str(cfg.get("store_dir") or "data/molit")),
        limits=sandbox_limits(settings),
        max_pages=int(cfg.get("max_pages", 5)),
        max_file_bytes=int(float(cfg.get("max_file_mb", 50)) * 1024 * 1024),
    )


def build_korail_web_source(settings: Settings | None = None):
    """KorailWebSource — 최신 스냅샷(data/korail_web/snapshots/<날짜>/) → Document.
    첨부는 샌드박스 파싱."""
    from rra.adapters.sources.korail_web import CrawlConfig, KorailWebSource

    settings = settings or load_settings()
    raw = korail_web_config(settings)
    cfg = CrawlConfig.from_config(raw)
    return KorailWebSource(
        _korail_web_root(settings, raw),
        limits=sandbox_limits(settings),
        menus={m.id: m for m in cfg.menus},
    )


_SOURCE_BUILDERS = {
    "openalex": build_openalex_source,
    "alio": build_alio_source,
    "alio_summary": build_alio_summary_source,
    "own_projects": build_own_projects_source,
    "own_docs": build_own_docs_source,
    "scienceon": build_scienceon_source,
    "ntis": build_ntis_source,
    "ntis_reports": build_ntis_report_source,
    "kipris": build_kipris_source,
    "korail_web": build_korail_web_source,
    "molit": build_molit_source,
}
SOURCE_NAMES = tuple(_SOURCE_BUILDERS)


def build_sources(names: list[str], settings: Settings | None = None) -> list:
    """이름 목록 → SourcePort 구현체 목록. 모르는 이름은 KeyError."""
    unknown = [n for n in names if n not in _SOURCE_BUILDERS]
    if unknown:
        raise KeyError(f"알 수 없는 소스: {unknown} (가능: {list(SOURCE_NAMES)})")
    settings = settings or load_settings()
    return [_SOURCE_BUILDERS[n](settings) for n in names]


def build_available_sources(
    names: list[str], settings: Settings | None = None
) -> tuple[list, list[tuple[str, str]]]:
    """이름 목록 → (만들 수 있는 소스, [(건너뛴 이름, 사유)]).

    키가 없는 소스(MissingCredential)는 건너뛴다 — 야간 적재(com.rra.ingest.plist)가 키 유무와
    무관하게 돌도록. 모르는 이름은 KeyError."""
    unknown = [n for n in names if n not in _SOURCE_BUILDERS]
    if unknown:
        raise KeyError(f"알 수 없는 소스: {unknown} (가능: {list(SOURCE_NAMES)})")
    settings = settings or load_settings()
    sources, skipped = [], []
    for name in names:
        try:
            sources.append(_SOURCE_BUILDERS[name](settings))
        except MissingCredential as exc:
            skipped.append((name, str(exc)))
    return sources, skipped


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
    builders = {
        "scienceon": build_scienceon_source,
        "ntis": build_ntis_source,
        "ntis_reports": build_ntis_report_source,
        "kipris": build_kipris_source,
    }
    targets = []
    for name in names:
        if name not in builders:
            raise KeyError(f"연결 확인을 지원하지 않는 소스: {name} (가능: {list(builders)})")
        cfg_name = (
            "ntis" if name == "ntis_reports" else name
        )  # 연구보고서는 과제검색 설정·키를 같이 쓴다
        host = urlsplit(str(source_config(settings, cfg_name).get("base_url", ""))).hostname or ""
        creds = credential_status(settings, cfg_name)
        ready = host in allowed and all(creds.values())

        def connect(_build=builders[name]):
            return _build(settings, transport=transport, resolver=resolver)

        targets.append(SourceTarget(name, host, host in allowed, creds, connect if ready else None))
    return CheckSources(targets)


# ── 렌더러 (Step 8) ───────────────────────────────────────
def build_renderer(settings: Settings | None = None):
    """RendererPort 구현체 — HWPX. config/templates/proposal_korail.hwpx 가 있으면 템플릿 모드."""
    from rra.adapters.rendering import HwpxRenderer, SlotMap

    settings = settings or load_settings()
    rules = lint_rules(settings)
    return HwpxRenderer(
        SlotMap.from_config(render_slots(settings)),
        titles=rules.titles,
        strategy=strategy_catalog(settings),
        template_path=render_template_path(settings),
    )


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


def build_precheck(settings: Settings | None = None, repo=None, *, reranker=None, pipeline=None):
    """PrecheckOverlap 유스케이스. repo 를 주면 그대로 쓴다(테스트·MCP 조립용).
    pipeline.reranker 가 켜져 있으면 Q8 reranker 로 k×4 를 다시 순위 매긴다."""
    from rra.application.usecases.precheck_overlap import PrecheckOverlap

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    if reranker is None and (pipeline or pipeline_config(settings)).reranker:
        reranker = build_reranker(settings)
    return PrecheckOverlap(
        repo,
        own=own_unit(settings),
        keywords=keyword_rule(settings),
        reranker=reranker,
        mix=retrieval_mix(settings),
    )


def build_policy_suggest(settings: Settings | None = None, repo=None):
    """PolicySuggest 유스케이스 — korail_web policy 문서에서 정책 문구 3~5개 (LLM 없음)."""
    from rra.application.usecases.policy_suggest import PolicySuggest

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    return PolicySuggest(repo, keywords=keyword_rule(settings))


def build_generate(
    settings: Settings | None = None, *, repo=None, llm=None, reranker=None, pipeline=None
):
    """GenerateProposal 유스케이스. repo·llm 을 주면 그대로 쓴다(테스트용).
    [Q] 품질 단계(section_search·exemplars·rule_check·reranker)는 config/pipeline.yaml 을 따른다."""
    from rra.application.usecases.generate_proposal import GenerateProposal

    settings = settings or load_settings()
    rules = lint_rules(settings)
    pipeline = pipeline or pipeline_config(settings)
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    if llm is None:
        llm = build_llm(settings, stage="compose")
    if reranker is None and pipeline.reranker:
        reranker = build_reranker(settings)
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
        relevance=relevance_floor(settings),
        reranker=reranker,
        section_search=pipeline.section_search,
        exemplars=pipeline.exemplars,
        rule_check=pipeline.rule_check,
        mix=retrieval_mix(settings),
        schedule_metrics=usability_config(settings).schedule_metrics,
    )


def build_run_manager(
    settings: Settings | None = None,
    *,
    repo=None,
    llm=None,
    runner=None,
    renderer=None,
    reviewer=None,
    review_llm=None,
    store=None,
    run_log=None,
    pipeline=None,
    runs_dir=None,
):
    """RunManager — 파일 저장소(runs/), 프로세스 간 슬롯, manifest 로그, 실행기, HWPX 렌더러,
    검토 유스케이스(review 단계 키가 있을 때만; 없으면 None → review_skipped).
    pipeline·runs_dir 는 측정(`rra eval`)이 설정과 다른 구성·별도 폴더로 돌릴 때 준다.

    repo·llm 은 바로 만든다. 임베딩 모델은 어댑터가 첫 호출 때 올리므로 상태 조회만 할 때는
    로드되지 않는다 (SentenceTransformerEmbedding.loaded).
    """
    from rra.adapters.logging import FileRunLog
    from rra.adapters.runs import AsyncioTaskRunner, FileRunStore, FlockSlot
    from rra.application.services import RunManager

    settings = settings or load_settings()
    root = Path(runs_dir or settings.runs_dir)
    compose_cfg = llm_config(settings, "compose")
    pipeline = pipeline or pipeline_config(settings)
    # manifest 에는 선언된 실제 모델명(served_model)을, 없으면 요청용 이름을 남긴다
    model = compose_cfg["served_model"] or compose_cfg["model"]
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    if llm is None:
        llm = build_llm(settings, stage="compose")
    return RunManager(
        build_generate(settings, repo=repo, llm=llm, pipeline=pipeline),
        store or FileRunStore(root),
        FlockSlot(root / ".generate.lock"),
        run_log or FileRunLog(root),
        runner or AsyncioTaskRunner(),
        max_queued=int(input_limits(settings).get("max_queued_runs", 3)),
        model=model,
        renderer=renderer or build_renderer(settings),
        line_limits=render_slots(settings).get("line_limits") or {},
        reviewer=reviewer
        if reviewer is not None
        else build_reviewer(settings, llm=review_llm, pipeline=pipeline),
        review_auto=review_policy(settings)["auto"],
        pipeline=pipeline,
        outliner=build_outliner(settings, llm=llm) if pipeline.outline else None,
        usability=usability_config(settings),
        checklists=section_checklists(settings),
    )


# ── REST API (Step 10, 보안 G) ────────────────────────────
class ApiTokenMissing(RuntimeError):
    """RRA_API_TOKEN 이 없다 — 인증 없는 API 는 띄우지 않는다."""


def build_sessions(settings: Settings | None = None):
    """세션 쿠키 저장소 (프론트엔드 로그인). 미들웨어와 /v1/session 라우트가 같은 것을 쓴다."""
    from rra.adapters.security import SessionStore

    return SessionStore()


def api_middlewares(
    settings: Settings, token: str, *, sessions=None
) -> list[tuple[type, dict[str, Any]]]:
    """등록 순서(안쪽부터): 인증 → 본문 상한 → 헤더.

    FastAPI.add_middleware 는 마지막에 넣은 것이 바깥이 된다.
    → 헤더가 가장 바깥에서 모든 응답에 붙는다.
    """
    from rra.adapters.security import (
        BodyLimitMiddleware,
        SecurityHeadersMiddleware,
        TokenAuthMiddleware,
    )

    limits = input_limits(settings)
    outer_to_inner = [
        (SecurityHeadersMiddleware, {}),
        (BodyLimitMiddleware, {"max_bytes": int(limits.get("api_max_body_bytes", 64 * 1024))}),
        (TokenAuthMiddleware, {"token": token, "sessions": sessions}),
    ]
    return list(reversed(outer_to_inner))


FAKE_MODE_WARNING = (
    "="
    * 72
    + "\n!!  RRA_FAKE_LLM=1 — 가짜 모드. 가짜 LLM(작성·검토)·메모리 저장소. 결과는 더미이며\n"
    "!!  어떤 자료도 검색·저장하지 않는다. e2e 테스트·스키마 추출 전용. 운영 기동 금지.\n"
    + "="
    * 72
)


def build_fake_parts(settings: Settings):
    """가짜 모드(RRA_FAKE_LLM=1) 부품 — 가짜 LLM·메모리 저장소·시드 문서. adapters/fake."""
    from rra.adapters.fake import (
        InMemoryDocumentRepository,
        InMemoryRunStore,
        NoopRunLog,
        ScriptedComposeLLM,
        ScriptedReviewLLM,
    )
    from rra.domain.models import Chunk, Document

    repo = InMemoryDocumentRepository()
    repo.seed(
        [
            Document(
                doc_id="alio:fake-1",
                source="alio",
                doc_type="internal_report",
                title="궤도 상태 자동 감지 연구 (가짜)",
                body="궤도 틀림을 자동으로 감지하는 사내 연구 요약",
                orgs=["korail"],
                department="철도연구원",
                text_basis="summary",
                visibility="internal",
            ),
            Document(
                doc_id="openalex:fake-1",
                source="openalex",
                doc_type="paper",
                title="Track geometry degradation (fake)",
                abstract="Track geometry degradation rate from inspection history",
                orgs=["external"],
                text_basis="abstract",
            ),
        ],
        [
            Chunk(
                chunk_id="alio:fake-1#0",
                doc_id="alio:fake-1",
                ordinal=0,
                text="궤도 틀림을 자동으로 감지하는 사내 연구 요약",
                basis="summary",
                visibility="internal",
            ),
            Chunk(
                chunk_id="openalex:fake-1#0",
                doc_id="openalex:fake-1",
                ordinal=0,
                text="Track geometry degradation rate from inspection history",
                basis="abstract",
            ),
        ],
        when="2026-10-26",
    )
    return {
        "repo": repo,
        "llm": ScriptedComposeLLM(),
        "review_llm": ScriptedReviewLLM(),
        "store": InMemoryRunStore(),
        "run_log": NoopRunLog(),
    }


def build_api(
    settings: Settings | None = None,
    *,
    repo=None,
    llm=None,
    runner=None,
    static_dir: Path | None = None,
    sse_poll_sec: float = 1.0,
):
    """FastAPI 앱. 토큰이 없으면 ApiTokenMissing (G: 인증 필수). RRA_FAKE_LLM=1 이면 가짜 부품."""
    from rra.entrypoints.api import create_app
    from rra.entrypoints.api.app import SessionAuth

    settings = settings or load_settings()
    token = settings.api_token.get_secret_value().strip() if settings.api_token else ""
    if not token:
        raise ApiTokenMissing(
            "RRA_API_TOKEN 이 없습니다 — .env 에 넣고 다시 실행하십시오 (보안 G)."
        )
    fake = build_fake_parts(settings) if settings.fake_llm else None
    if fake is not None:
        repo = repo or fake["repo"]
        llm = llm or fake["llm"]
        manager = build_run_manager(
            settings,
            repo=repo,
            llm=llm,
            runner=runner,
            review_llm=fake["review_llm"],
            store=fake["store"],
            run_log=fake["run_log"],
        )
    else:
        if repo is None:
            repo = build_repository(build_embedding(settings), settings)
        manager = build_run_manager(settings, repo=repo, llm=llm, runner=runner)
    sessions = build_sessions(settings)
    static = static_dir if static_dir is not None else Path(settings.static_dir)
    precheck = build_precheck(settings, repo=repo)
    pipeline = pipeline_config(settings)
    return create_app(
        manager=manager,
        precheck=precheck,
        policy_suggest=build_policy_suggest(settings, repo=repo),
        differentiate=build_differentiator(settings, repo=repo, llm=llm),
        recommend=build_recommender(settings, repo=repo, llm=llm, precheck=precheck),
        recommend_auto=recommend_policy(settings)["auto"],
        clarify=build_clarifier(settings, llm=llm) if pipeline.clarify else None,
        structure=build_structurer(settings, llm=llm),
        compare=build_comparer(settings, repo=repo, precheck=precheck),
        brief=build_briefer(settings, repo=repo, llm=llm),
        ntis_insights=build_ntis_insights(settings, repo=repo),
        repo=repo,
        user=LOCAL_USER,
        middlewares=api_middlewares(settings, token, sessions=sessions),
        query_max_chars=int(input_limits(settings).get("query_max_chars", 500)),
        on_shutdown=manager.generate.llm.aclose,
        session_auth=SessionAuth(token, sessions),
        static_dir=static,
        sse_poll_sec=sse_poll_sec,
        fake_mode=fake is not None,
        snapshot_status=build_korail_web_source(settings).status,
    )


def build_api_schema(settings: Settings | None = None) -> dict[str, Any]:
    """OpenAPI 스키마 (프론트 타입 생성용). 가짜 부품으로 앱을 만들어 토큰·DB 없이 추출한다."""
    from pydantic import SecretStr

    settings = settings or load_settings()
    schema_settings = settings.model_copy(
        update={"fake_llm": True, "api_token": SecretStr("schema-only-not-a-token")}
    )
    return build_api(schema_settings).openapi()


def build_usage_report(settings: Settings | None = None, *, store=None):
    """UsageReport — runs/ 의 usage.json 집계 (`rra usage report`). store 를 주면 그대로(테스트)."""
    from rra.adapters.runs import FileRunStore
    from rra.application.usecases.usage_report import UsageReport

    settings = settings or load_settings()
    return UsageReport(store or FileRunStore(Path(settings.runs_dir)))


def build_purge_runs(settings: Settings | None = None, *, clock=None):
    """PurgeRuns — security.yaml retention_days 로 만료 run 폴더 삭제 (`rra runs purge`)."""
    from rra.adapters.runs import FileRunStore
    from rra.application.usecases.purge_runs import PurgeRuns

    settings = settings or load_settings()
    kwargs = {"clock": clock} if clock is not None else {}
    return PurgeRuns(FileRunStore(Path(settings.runs_dir)), retention_days(settings), **kwargs)


def build_differentiator(settings: Settings | None = None, *, repo=None, llm=None):
    """기능 2 유스케이스(Differentiate). differentiate 단계 LLM(기본 gemini) 키가 없으면
    compose(로컬) 모델로 대신하고 fallback_local=True. llm 을 주면 그대로 쓴다(테스트용)."""
    from rra.application.usecases.differentiate import Differentiate

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    stage, fallback = "differentiate", False
    try:
        available = llm_available(settings, stage=stage)
    except KeyError:
        available = False
    if not available:
        stage, fallback = "compose", True
    cfg = llm_config(settings, stage)
    if llm is None:
        llm = build_llm(settings, stage=stage)
    return Differentiate(
        llm,
        build_prompt_library(settings),
        repo,
        include_internal=review_policy(settings)["include_internal"],
        provider=cfg["provider"],
        model=cfg["served_model"] or cfg["model"],
        fallback_local=fallback,
    )


def _stage_or_local(settings: Settings, stage: str) -> tuple[str, bool]:
    """단계 키가 없으면 compose(로컬)로 — (실제 단계, fallback_local)."""
    try:
        available = llm_available(settings, stage=stage)
    except KeyError:
        available = False
    return (stage, False) if available else ("compose", True)


def build_structurer(settings: Settings | None = None, *, llm=None):
    """U2 간편 입력(StructureIdea) — compose(로컬) 모델. usability.quick_input 이 꺼지면 None."""
    from rra.application.usecases.structure_idea import StructureIdea

    settings = settings or load_settings()
    if not usability_config(settings).quick_input:
        return None
    cfg = llm_config(settings, "compose")
    if llm is None:
        llm = build_llm(settings, stage="compose")
    return StructureIdea(
        llm,
        build_prompt_library(settings),
        provider=cfg["provider"],
        model=cfg["served_model"] or cfg["model"],
    )


def build_comparer(settings: Settings | None = None, *, repo=None, precheck=None):
    """U4 차별성 비교표(CompareProjects) — LLM 없음. usability.comparison 이 꺼지면 None."""
    from rra.application.usecases.compare_projects import CompareProjects

    settings = settings or load_settings()
    if not usability_config(settings).comparison:
        return None
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    return CompareProjects(repo, precheck=precheck or build_precheck(settings, repo=repo))


def build_briefer(settings: Settings | None = None, *, repo=None, llm=None):
    """U5 선행연구 브리핑(BriefPriorWork) — stage brief(기본 gemini), 키 없으면 compose(로컬)로
    fallback_local=True. usability.brief 가 꺼지면 None. llm 을 주면 그대로 쓴다(테스트용)."""
    from rra.application.usecases.brief_prior_work import BriefPriorWork

    settings = settings or load_settings()
    if not usability_config(settings).brief:
        return None
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    stage, fallback = _stage_or_local(settings, "brief")
    cfg = llm_config(settings, stage)
    if llm is None:
        llm = build_llm(settings, stage=stage)
    generate = build_generate(settings, repo=repo, llm=llm)  # retrieve 만 쓴다
    return BriefPriorWork(
        llm,
        build_prompt_library(settings),
        repo,
        retrieve=generate.retrieve,
        include_internal=review_policy(settings)["include_internal"],
        provider=cfg["provider"],
        model=cfg["served_model"] or cfg["model"],
        fallback_local=fallback,
        keywords=keyword_rule(settings),
    )


def build_clarifier(settings: Settings | None = None, *, llm=None):
    """③ 입력 보강 질문 유스케이스(Q1, ClarifyInput) — clarify 단계(로컬 모델). 호출자는
    pipeline.clarify 가 켜져 있을 때만 부른다(꺼져 있으면 질문 0개)."""
    from rra.application.usecases.clarify_input import ClarifyInput

    settings = settings or load_settings()
    return ClarifyInput(
        llm if llm is not None else build_llm(settings, stage="clarify"),
        build_prompt_library(settings),
    )


def build_recommender(settings: Settings | None = None, *, repo=None, llm=None, precheck=None):
    """차별화 과제 추천 유스케이스(RecommendProjects, ADR 0012).

    recommend 단계 LLM(기본 gemini) 키가 없으면 compose(로컬) 모델로 대신하고 fallback_local=True.
    근거 검색은 GenerateProposal.retrieve(관련도 하한·자료원별 최소 보장), 자기 중복 검사는
    precheck.
    llm 을 주면 그대로 쓴다(테스트용).
    """
    from rra.application.usecases.recommend_projects import RecommendProjects

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    stage, fallback = "recommend", False
    try:
        available = llm_available(settings, stage=stage)
    except KeyError:
        available = False
    if not available:
        stage, fallback = "compose", True
    cfg = llm_config(settings, stage)
    if llm is None:
        llm = build_llm(settings, stage=stage)
    generate = build_generate(settings, repo=repo, llm=llm)  # retrieve 만 쓴다 (LLM 호출 없음)
    return RecommendProjects(
        llm,
        build_prompt_library(settings),
        repo,
        precheck=precheck or build_precheck(settings, repo=repo),
        retrieve=generate.retrieve,
        include_internal=review_policy(settings)["include_internal"],
        provider=cfg["provider"],
        model=cfg["served_model"] or cfg["model"],
        fallback_local=fallback,
        self_overlap_mode=recommend_policy(settings)["self_overlap"],
    )


def build_assistant(settings: Settings | None = None, *, repo=None, llm=None):
    """Agent(ProposalAssistant) — precheck·RunManager·검색이 같은 repo 를 쓴다.

    sqlite 연결은 만든 스레드에서만 쓸 수 있으므로 호출자(UI 워커)는 조립과 모든 호출을
    한 스레드에서 한다.
    """
    from rra.application.services import ProposalAssistant

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    manager = build_run_manager(settings, repo=repo, llm=llm)
    precheck = build_precheck(settings, repo=repo)
    return ProposalAssistant(
        precheck,
        manager,
        repo,
        user=LOCAL_USER,
        differentiate=build_differentiator(settings, repo=repo, llm=llm),
        recommend=build_recommender(settings, repo=repo, llm=llm, precheck=precheck),
        recommend_auto=recommend_policy(settings)["auto"],
        clarify=build_clarifier(settings, llm=llm) if pipeline_config(settings).clarify else None,
    )
