"""의존성 조립. 전 계층을 아는 유일한 모듈.

여기에는 build_* (포트 ↔ 어댑터 연결)만 둔다. 설정 읽기·병합은 rra/config_loader.py,
진단 로직은 application/usecases/diagnostics.py. 이 모듈은 로더 결과를 받아 객체를 만들 뿐이다.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from rra.config_loader import (
    CREDENTIALS,
    DEFAULT_STAGE,
    KEYED_SOURCES,
    MissingCredential,
    allowed_domains,
    api_config,
    auth_config,
    compose_policy,
    credential_status,
    data_location,
    data_locations,
    data_path,
    figures_config,
    input_limits,
    institutions,
    keyword_rule,
    korail_web_config,
    lint_rules,
    llm_budget,
    llm_config,
    llm_fallback,
    llm_key_present,
    molit_config,
    overlap_candidates,
    own_unit,
    pipeline_config,
    public_ip_config,
    read_config,
    recommend_policy,
    relevance_floor,
    render_slots,
    render_template_path,
    require_credentials,
    rerank_rule,
    resolve_data_dir,
    retention_days,
    retrieval_mix,
    review_policy,
    rnd_notice_config,
    runs_config,
    same_judgment_config,
    section_checklists,
    security_config,
    served_model_aliases,
    source_config,
    source_ip_policy,
    strategy_catalog,
    technique_catalog,
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
    "data_locations",
    "data_path",
    "resolve_data_dir",
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
    "build_notice_match",
    "build_rnd_notice_crawler",
    "build_rnd_notice_source",
    "build_g2b_source",
    "build_bai_crawler",
    "build_bai_source",
    "build_mofe_source",
    "build_datago_source",
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
    "build_table_source",
    "build_extract_facts",
    "build_term_candidates",
    "build_outliner",
    "build_clarifier",
    "build_argon_first",
    "build_policy_cards",
    "build_section_questioner",
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
        data_location(settings, "db"),
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

    settings = settings or load_settings()
    llm = _build_openai_compat(OpenAICompatLLM, settings, stage=stage, provider=provider)
    if llm.provider == "gemini":  # 일일 전체 호출 상한 (레인 A) — 모든 gemini 단계가 같은 카운터
        budget = build_review_budget(settings)
        if budget is not None:
            from rra.adapters.llm.daily_budget import BudgetedLLM

            llm = BudgetedLLM(llm, budget, stage=stage)
    return llm


_BUDGETS: dict[tuple[str, int], Any] = {}


def build_review_budget(settings: Settings | None = None):
    """외부 LLM 일일 예산 카운터(FileDailyBudget). limit 0 이면 None(상한 없음). 같은 경로·상한은
    프로세스 안에서 하나를 공유한다."""
    from rra.adapters.llm.daily_budget import FileDailyBudget

    settings = settings or load_settings()
    cfg = llm_budget(settings)
    if cfg["limit"] <= 0:
        return None
    key = (str(cfg["path"]), cfg["limit"])
    if key not in _BUDGETS:
        _BUDGETS[key] = FileDailyBudget(cfg["path"], cfg["limit"])
    return _BUDGETS[key]


# ── 로그인 (레인 A) ─────────────────────────────────────
def build_auth_store(settings: Settings | None = None):
    """AuthStorePort 구현체 — <data_dir>/auth (config/auth.yaml store_dir)."""
    from rra.adapters.auth import FileAuthStore

    settings = settings or load_settings()
    return FileAuthStore(auth_config(settings)["store_dir"])


def build_roster_reader(settings: Settings | None = None):
    """사번 명부 파일(xlsx·csv) 읽기 — 샌드박스 한도는 security.yaml file_limits."""
    from rra.adapters.auth import RosterReader

    settings = settings or load_settings()
    return RosterReader(sandbox_limits(settings))


def build_staff_importer(settings: Settings | None = None, *, store=None):
    """사번 일괄 등록 유스케이스 (A2)."""
    from rra.application.usecases.import_staff import ImportStaff

    settings = settings or load_settings()
    return ImportStaff(store or build_auth_store(settings))


def build_login(settings: Settings | None = None, *, store=None):
    """로그인 유스케이스 — 잠금 정책은 auth.yaml lockout."""
    from rra.application.usecases.login import Login
    from rra.domain.rules.auth_policy import LockoutPolicy, LoginGuard

    settings = settings or load_settings()
    cfg = auth_config(settings)
    known = {k: v for k, v in cfg["lockout"].items() if k in LockoutPolicy.__dataclass_fields__}
    return Login(store or build_auth_store(settings), guard=LoginGuard(LockoutPolicy(**known)))


def public_repository(repo):
    """공용 계정용 — visibility=internal 을 뺀 저장소 (application/services/scoped_repository)."""
    from rra.application.services.scoped_repository import PublicOnlyRepository

    return PublicOnlyRepository(repo)


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
    from rra.domain.rules.photo_filter import PhotoRule
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
        photo_rule=PhotoRule.from_dict(vcfg.get("photo")),
        concurrency=vcfg.get("concurrency", 1),
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


# ── 표 사실(P2-8)·용어 후보(P2-9) ──────────────────────────
TABLE_SOURCES = ("korail_web", "molit", "vision")


def build_table_source(
    settings: Settings | None = None,
    *,
    source: str,
    snapshot: str | None = None,
    repo=None,
    store=None,
):
    """TableSourcePort — korail_web(스냅샷 첨부 xlsx·xls·pdf), molit(DB 문서 본문), vision(판독
    캐시 표)."""
    from rra.adapters.tables import DocumentTables, SnapshotTables, VisionTables

    settings = settings or load_settings()
    if source == "korail_web":
        return SnapshotTables(
            _korail_web_root(settings, korail_web_config(settings)),
            limits=sandbox_limits(settings),
            snapshot=snapshot,
        )
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    if source == "vision":
        return VisionTables(store or build_vision_store(settings), repo)
    if source == "molit":
        return DocumentTables(repo, source="molit")
    raise KeyError(f"표 자료원은 {', '.join(TABLE_SOURCES)} 중 하나: {source!r}")


def build_extract_facts(
    settings: Settings | None = None,
    *,
    source: str,
    snapshot: str | None = None,
    repo=None,
    store=None,
):
    """표 → 사실 적재 유스케이스. repo 를 주면 그대로 쓴다(테스트용)."""
    from rra.application.usecases.extract_facts import ExtractTableFacts

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    table_source = build_table_source(
        settings, source=source, snapshot=snapshot, repo=repo, store=store
    )
    return ExtractTableFacts(table_source, repo, repo)


def build_term_candidates(settings: Settings | None = None, *, repo=None):
    """용어 후보 유스케이스 + YAML 쓰기 함수. 후보 파일만 적는다 (overlap.yaml 은 건드리지
    않는다)."""
    from rra.adapters.terms import write_candidates
    from rra.application.usecases.term_candidates import ExtractTermCandidates

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    return ExtractTermCandidates(repo, keyword_rule(settings)), write_candidates


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


class LivePrecheck:
    """[4] 측정용 ② — REST precheck 와 같은 순서: 실시간 검색 시작(또는 이어 쓰기)·최대 wait_seconds
    대기 → 유사과제 판정. 실시간 결과는 DB 에 들어간 뒤 판정·run 검색이 함께 본다."""

    def __init__(self, precheck, live, owner: str):
        self.precheck, self.live, self.owner = precheck, live, owner

    async def __call__(self, req):
        await self.live.prepare(self.owner, req)
        return await self.precheck(req)


def build_eval(
    settings: Settings | None = None,
    *,
    label: str,
    pipeline,
    runs_dir: Path | str,
    repo=None,
    llm=None,
    expected=None,
    final_review: bool = False,
    finalize: bool = False,
    concurrent: int = 1,
    local_check: bool | None = None,
    department: str | None = None,
):
    """초안 품질 강화 측정 유스케이스(`rra eval`, Q9) — 주어진 pipeline 구성으로 조립한 RunManager·
    precheck 로 골든셋을 돌린다. run 은 runs_dir 아래에 남는다(운영 runs/ 와 분리).

    [5] final_review·finalize: ⑤·⑥ 까지 측정(HWPX 는 adapters/rendering.hwpx_ok 로 검증).
    concurrent: N건씩 한꺼번에 제출. local_check: None 이면 llm.yaml compose.local_check,
    아니면 덮어쓴다."""
    from rra.adapters.llm.server_stats import server_rss_mb
    from rra.adapters.rendering.hwpx import hwpx_ok
    from rra.application.usecases.evaluate import DEFAULT_DEPARTMENT, EvaluateQuality

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    if llm is None:
        llm = build_llm(settings, stage="compose")
    reranker = build_reranker(settings) if pipeline.reranker else None
    # [4] 실시간 검색 — 운영 REST 와 같게: run 관리자와 ② precheck 가 한 인스턴스(세션)를 같이 쓴다
    live = build_live_search(settings, repo=repo)
    live = live if live.enabled else None
    manager = build_run_manager(
        settings, repo=repo, llm=llm, pipeline=pipeline, runs_dir=runs_dir, live_search=live
    )
    if local_check is not None:  # 측정 구성 B(끔)·C(켬) — 설정 파일을 고치지 않고 덮어쓴다
        for gen in (manager.generate, manager.generate_public):
            if gen is not None:
                gen.local_check = local_check
    compose_cfg = llm_config(settings, "compose")
    review_cfg = llm_config(settings, "review")
    precheck = build_precheck(settings, repo=repo, reranker=reranker, pipeline=pipeline)
    return EvaluateQuality(
        manager,
        LivePrecheck(precheck, live, LOCAL_USER) if live is not None else precheck,
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
        final_review=final_review,
        finalize=finalize,
        department=department or DEFAULT_DEPARTMENT,
        verify_hwpx=hwpx_ok,
        concurrent=concurrent,
        config={
            "max_concurrent": runs_config(settings)["max_concurrent"]
            if manager.generate.writes_remotely
            else 1
        },
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


# ── 자료원 IP 확인 (레인 I) ─────────────────────────────────
def build_public_ip_probe(settings: Settings | None = None, *, transport=None, resolver=None):
    """PublicIpProbe — sources.yaml public_ip.lookup_url 로 현재 공인 IP 1회 조회. URL 이 비었거나
    호스트가 security.yaml allowed_domains 에 없으면 None (확인 생략, 보안 C)."""
    from rra.adapters.sources import PublicIpProbe

    settings = settings or load_settings()
    cfg = public_ip_config(settings)
    url = str(cfg.get("lookup_url") or "").strip()
    host = urlsplit(url).hostname or ""
    if not url or host not in set(allowed_domains(settings)):
        return None
    client_cfg = {"timeout": cfg.get("timeout") or {"connect": 5, "read": 10}, "retries": 1}
    return PublicIpProbe(
        _guarded(settings, client_cfg, transport=transport, resolver=resolver), url=url
    )


def build_source_availability(settings: Settings | None = None):
    """FileSourceAvailability — 자료원별 마지막 차단 안내 파일 (데이터 폴더 cache/)."""
    from rra.adapters.persistence.source_availability import FileSourceAvailability

    settings = settings or load_settings()
    return FileSourceAvailability(data_location(settings, "source_availability"))


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
        data_location(settings, "alio_catalog", cfg=cfg),
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
        client, url, data_location(settings, "alio_catalog", cfg=cfg), max_bytes=max_bytes
    )


def build_alio_source(settings: Settings | None = None):
    """AlioSource (filedrop). 카탈로그가 있으면 파일명 stem 으로 메타데이터를 붙인다."""
    from rra.adapters.sources.alio import AlioSource

    settings = settings or load_settings()
    cfg = source_config(settings, "alio")
    return AlioSource(
        data_location(settings, "alio_inbox", cfg=cfg),
        limits=sandbox_limits(settings),
        catalog=build_alio_catalog(settings),
    )


def build_alio_summary_source(settings: Settings | None = None):
    """AlioSummarySource (원문 비공개 보고서의 공개 요약 .txt). 파일명 stem 으로 카탈로그 매칭."""
    from rra.adapters.sources.alio import AlioSummarySource

    settings = settings or load_settings()
    cfg = source_config(settings, "alio").get("summary") or {}
    return AlioSummarySource(
        data_location(settings, "alio_summary_inbox", cfg=cfg),
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
        per_query_limit=int(cfg["per_query_limit"]) if cfg.get("per_query_limit") else None,
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


def build_ntis_insight_source(settings: Settings | None = None, *, transport=None, resolver=None):
    """NtisInsightSource (성과검색·연관콘텐츠 어댑터). RRA_NTIS_KEY 없으면 MissingCredential."""
    from rra.adapters.sources.ntis import NtisInsightSource

    settings = settings or load_settings()
    require_credentials(settings, "ntis")
    cfg = source_config(settings, "ntis")
    insights = cfg.get("insights") or {}
    return NtisInsightSource(
        _guarded(settings, cfg, transport=transport, resolver=resolver),
        apprv_key=settings.ntis_key,
        base_url=str(cfg.get("base_url", "https://www.ntis.go.kr")),
        outcome_path=str(cfg.get("outcome_path", "/rndopen/openApi/public_result")),
        related_path=str(cfg.get("related_path", "/rndopen/openApi/ConnectionContent")),
        record_tag=str(cfg.get("record_tag") or "HIT"),
        display_count=int(insights.get("max_items", 10)),
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
        source = build_ntis_insight_source(settings, transport=transport, resolver=resolver)
    cache_dir = data_location(settings, "ntis_cache", cfg=insights)
    cache = FileCache(cache_dir, ttl_sec=float(insights.get("cache_ttl_days", 7)) * 86400)
    return NtisProjectInsights(
        source,
        source,
        cache=cache,
        repo=repo,
        max_projects=int(insights.get("max_projects", 3)),
        public_ip=build_public_ip_probe(settings, transport=transport, resolver=resolver),
        availability=build_source_availability(settings),
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
        data_location(settings, "own_projects_inbox", cfg=cfg), limits=sandbox_limits(settings)
    )


def build_own_docs_source(settings: Settings | None = None):
    """OwnDocsSource — 공시완료 폴더의 공시용 요약문 (data/inbox/own_docs). 라벨은 alio 공용."""
    from rra.adapters.sources.own import OwnDocsSource

    settings = settings or load_settings()
    cfg = source_config(settings, "own")
    summary_cfg = source_config(settings, "alio").get("summary") or {}
    return OwnDocsSource(
        data_location(settings, "own_docs_inbox", cfg=cfg),
        limits=sandbox_limits(settings),
        institutions=institutions(settings),
        labels=summary_cfg.get("labels") or None,
        default_org=cfg.get("default_org") or "korail",
    )


def _korail_web_root(settings: Settings, cfg: dict[str, Any]) -> Path:
    return data_location(settings, "korail_web", cfg=cfg)


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
        store_dir=data_location(settings, "molit", cfg=cfg),
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


def _rnd_notice_root(settings: Settings, cfg: dict[str, Any]) -> Path:
    return data_location(settings, "rnd_notice", cfg=cfg)


def build_rnd_notice_crawler(settings: Settings | None = None, *, transport=None, resolver=None):
    """RndNoticeCrawler — config/rnd_notice.yaml (KAIA GET·IRIS 공개 POST 폼).

    2초 간격·동시 1·robots 준수 (P2-7)."""
    from rra.adapters.sources.rnd_notice import NoticeConfig, RndNoticeCrawler

    settings = settings or load_settings()
    raw = rnd_notice_config(settings)
    cfg = NoticeConfig.from_config(raw)
    client = _guarded(settings, raw, transport=transport, resolver=resolver)
    client._client.headers["Accept"] = "text/html,application/xhtml+xml,application/json,*/*;q=0.8"
    client._client.headers["User-Agent"] = cfg.user_agent
    return RndNoticeCrawler(client, cfg, root=_rnd_notice_root(settings, raw))


def build_rnd_notice_source(settings: Settings | None = None):
    """RndNoticeSource — 최신 스냅샷(data/rnd_notice/snapshots/<날짜>/) → Document(rnd_notice).

    첨부는 샌드박스 파싱."""
    from rra.adapters.sources.rnd_notice import RndNoticeSource

    settings = settings or load_settings()
    raw = rnd_notice_config(settings)
    return RndNoticeSource(_rnd_notice_root(settings, raw), limits=sandbox_limits(settings))


# ── [P2] 레인 E (2026-10-27): 발주 용역·감사·경영평가·통계 ─────────────
def build_g2b_source(settings: Settings | None = None, *, transport=None, resolver=None):
    """G2bProcurementSource — 나라장터 입찰공고(용역) API. RRA_DATA_GO_KR_KEY 없으면
    MissingCredential."""
    from rra.adapters.sources.procurement import G2bProcurementSource

    settings = settings or load_settings()
    require_credentials(settings, "g2b")
    cfg = source_config(settings, "g2b")
    return G2bProcurementSource(
        _guarded(settings, cfg, transport=transport, resolver=resolver),
        service_key=settings.data_go_kr_key,
        base_url=str(cfg.get("base_url") or "https://apis.data.go.kr"),
        path=str(
            cfg.get("path") or "/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch"
        ),
        queries=[str(q) for q in cfg.get("queries") or ["철도"]],
        institutions=institutions(settings),
        org_filter=[str(o) for o in cfg.get("org_filter") or []],
        lookback_days=int(cfg.get("lookback_days", 365)),
        rows=int(cfg.get("rows", 100)),
        max_pages=int(cfg.get("max_pages", 5)),
        active_days=int(cfg.get("active_days", 540)),
    )


def _bai_root(settings: Settings, cfg: dict[str, Any]) -> Path:
    return data_location(settings, "bai", cfg=cfg)


def build_bai_crawler(settings: Settings | None = None, *, transport=None, resolver=None):
    """BaiCrawler — config/bai.yaml. Playwright 로 공개 화면만 조작, robots 는 GuardedClient 로
    읽는다."""
    from rra.adapters.sources import GuardedClient
    from rra.adapters.sources.audit.bai_crawler import BaiConfig, BaiCrawler

    settings = settings or load_settings()
    raw = read_config("bai.yaml", settings)
    cfg = BaiConfig.from_config(raw)

    async def robots_text() -> str:
        client = GuardedClient(
            allowed_domains(settings),
            retries=0,
            transport=transport,
            user_agent=cfg.user_agent,
            accept="text/plain,*/*;q=0.8",
            **({"resolver": resolver} if resolver else {}),
        )
        try:
            _h, body, _s = await client.get_raw(f"{cfg.base_url}/robots.txt")
            return body.decode("utf-8", "replace")
        finally:
            await client.aclose()

    return BaiCrawler(cfg, _bai_root(settings, raw), robots_text=robots_text)


def build_bai_source(settings: Settings | None = None):
    """BaiAuditSource — 최신 스냅샷(data/bai/snapshots/<날짜>/) → Document(audit). 전문 PDF 는
    샌드박스
    파싱."""
    from rra.adapters.sources.audit import BaiAuditSource

    settings = settings or load_settings()
    raw = read_config("bai.yaml", settings)
    return BaiAuditSource(
        _bai_root(settings, raw),
        limits=sandbox_limits(settings),
        institutions=institutions(settings),
        max_file_bytes=int(float(raw.get("max_file_mb", 50)) * 1024 * 1024),
    )


def build_mofe_source(settings: Settings | None = None, *, transport=None, resolver=None):
    """MofeEvaluationSource — config/mofe.yaml (기획재정부 공공기관 경영평가 결과 보도자료)."""
    from rra.adapters.sources.audit import MofeEvaluationSource

    settings = settings or load_settings()
    cfg = read_config("mofe.yaml", settings)
    client = _guarded(settings, cfg, transport=transport, resolver=resolver)
    client._client.headers["Accept"] = "text/html,application/xhtml+xml,*/*;q=0.8"
    return MofeEvaluationSource(
        client,
        base_url=str(cfg.get("base_url") or "https://mofe.go.kr"),
        list_path=str(cfg.get("list_path") or "/nw/nes/nesdta.do"),
        detail_path=str(cfg.get("detail_path") or "/nw/nes/detailNesDtaView.do"),
        bbs_id=str(cfg.get("bbs_id") or "MOSFBBS_000000000028"),
        menu_no=str(cfg.get("menu_no") or "4010100"),
        queries=[str(q) for q in cfg.get("queries") or ["경영실적 평가 결과"]],
        title_filter=[str(t) for t in cfg.get("title_filter") or ["경영실적 평가"]],
        store_dir=data_location(settings, "mofe", cfg=cfg),
        limits=sandbox_limits(settings),
        max_file_bytes=int(float(cfg.get("max_file_mb", 50)) * 1024 * 1024),
    )


def build_datago_source(settings: Settings | None = None, *, transport=None, resolver=None):
    """DataGoKrFileSource — config/datago.yaml 데이터셋 목록(철도 안전·수송 통계 파일, 키 없음)."""
    from rra.adapters.sources.datago import DataGoKrFileSource

    settings = settings or load_settings()
    cfg = read_config("datago.yaml", settings)
    client = _guarded(settings, cfg, transport=transport, resolver=resolver)
    client._client.headers["Accept"] = "text/html,application/json,*/*;q=0.8"
    return DataGoKrFileSource(
        client,
        datasets=[d for d in cfg.get("datasets") or [] if isinstance(d, dict)],
        base_url=str(cfg.get("base_url") or "https://www.data.go.kr"),
        store_dir=data_location(settings, "datago", cfg=cfg),
        limits=sandbox_limits(settings),
        institutions=institutions(settings),
        max_file_bytes=int(float(cfg.get("max_file_mb", 50)) * 1024 * 1024),
        max_rows=int(cfg.get("max_rows", 400)),
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
    "rnd_notice": build_rnd_notice_source,
    "g2b": build_g2b_source,
    "bai": build_bai_source,
    "mofe": build_mofe_source,
    "datago": build_datago_source,
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
    from rra.domain.rules.overlap import SOURCE_LABELS

    settings = settings or load_settings()
    allowed = set(allowed_domains(settings))
    builders = {
        "scienceon": build_scienceon_source,
        "ntis": build_ntis_source,
        "ntis_reports": build_ntis_report_source,
        "ntis_insights": build_ntis_insight_source,
        "kipris": build_kipris_source,
        "g2b": build_g2b_source,
    }
    targets = []
    for name in names:
        if name not in builders:
            raise KeyError(f"연결 확인을 지원하지 않는 소스: {name} (가능: {list(builders)})")
        # 연구보고서·성과/연관콘텐츠는 과제검색 설정·키를 같이 쓴다
        cfg_name = "ntis" if name in ("ntis_reports", "ntis_insights") else name
        host = urlsplit(str(source_config(settings, cfg_name).get("base_url", ""))).hostname or ""
        creds = credential_status(settings, cfg_name)
        ready = host in allowed and all(creds.values())

        def connect(_build=builders[name]):
            return _build(settings, transport=transport, resolver=resolver)

        policy = source_ip_policy(settings, cfg_name, label=SOURCE_LABELS.get(cfg_name, cfg_name))
        targets.append(
            SourceTarget(
                name, host, host in allowed, creds, connect if ready else None, ip_policy=policy
            )
        )
    return CheckSources(
        targets,
        public_ip=build_public_ip_probe(settings, transport=transport, resolver=resolver),
        availability=build_source_availability(settings),
    )


# ── 렌더러 (Step 8) ───────────────────────────────────────
def build_renderer(settings: Settings | None = None):
    """RendererPort 구현체 — HWPX. config/templates/proposal_korail.hwpx 가 있으면 템플릿 모드."""
    from rra.adapters.rendering import HwpxRenderer, SlotMap

    settings = settings or load_settings()
    rules = lint_rules(settings)
    fig = figures_config(settings)["hwpx"]
    return HwpxRenderer(
        SlotMap.from_config(render_slots(settings)),
        titles=rules.titles,
        strategy=strategy_catalog(settings),
        template_path=render_template_path(settings),
        figure_placement=fig["placement"],
        figure_max_width=fig["max_width_hwp"],
        figure_caption_prefix=fig["caption_prefix"],
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
    return IngestSources(
        sources,
        repo,
        limit=limit,
        own=own_unit(settings),
        public_ip=build_public_ip_probe(settings),
        availability=build_source_availability(settings),
    )


def build_precheck(
    settings: Settings | None = None,
    repo=None,
    *,
    reranker=None,
    pipeline=None,
    judge: bool = False,
    llm=None,
    local_llm=None,
    local_slot=None,
    keyword_source=None,
):
    """PrecheckOverlap 유스케이스. repo 를 주면 그대로 쓴다(테스트·MCP 조립용).
    pipeline.reranker 가 켜져 있으면 Q8 reranker 로 k×4 를 다시 순위 매긴다 — 점수는 차단 판단의 주
    점수(overlap.yaml rerank, 레인 A).

    judge=True(REST ②) 면 AI 같음 판정(SameJudge: Argon → 로컬 → 규칙)과 핵심 키워드 출처(실시간
    검색과 같은 LiveKeywordMaker)를 붙인다. llm 을 주면(가짜 모드·테스트) 그것을 Argon 자리로
    쓴다."""
    from rra.application.usecases.precheck_overlap import PrecheckOverlap

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    if reranker is None and (pipeline or pipeline_config(settings)).reranker:
        reranker = build_reranker(settings)
    same_judge = None
    if judge:
        same_judge = build_same_judge(
            settings, repo=repo, llm=llm, local_llm=local_llm, local_slot=local_slot
        )
        if keyword_source is None:
            keyword_source = build_live_keywords(settings, llm=llm)
    return PrecheckOverlap(
        repo,
        own=own_unit(settings),
        keywords=keyword_rule(settings),
        reranker=reranker,
        mix=retrieval_mix(settings),
        candidates=overlap_candidates(settings),
        rerank=rerank_rule(settings),
        same_judge=same_judge,
        keyword_source=keyword_source if judge else None,
    )


def build_same_judge(
    settings: Settings | None = None, *, repo, llm=None, local_llm=None, local_slot=None
):
    """② AI 같음 판정(SameJudge, 레인 A) — overlap.yaml judgment. Argon = judgment.stage(기본
    review:
    gemini 면 일일 예산·공유 호출 제한기), 로컬 = judgment.local_stage. 키·설정이 없는 단계는
    건너뛴다.
    꺼져 있으면 None(규칙 판정만). llm 을 주면 그것만 Argon 자리로 쓴다(가짜 모드·테스트)."""
    from rra.application.usecases.judge_sameness import SameJudge

    settings = settings or load_settings()
    cfg = same_judgment_config(settings)
    if not cfg["enabled"]:
        return None
    primary, local = llm, local_llm
    provider = model = local_model = None
    if llm is None and llm_available(settings, stage=cfg["stage"]):
        try:
            primary = build_llm(settings, stage=cfg["stage"])
        except (LLMUnavailable, KeyError, ValueError):
            primary = None
    if primary is not None:
        try:
            scfg = llm_config(settings, cfg["stage"])
            provider, model = scfg["provider"], scfg["served_model"] or scfg["model"]
        except (KeyError, ValueError):
            pass
    if local is None and llm is None and cfg["local_stage"]:
        try:
            local = build_llm(settings, stage=cfg["local_stage"])
            lcfg = llm_config(settings, cfg["local_stage"])
            local_model = lcfg["served_model"] or lcfg["model"]
        except (LLMUnavailable, KeyError, ValueError):
            local = None
    return SameJudge(
        primary=primary,
        local=local,
        repo=repo,
        include_internal=review_policy(settings)["include_internal"],
        provider=provider,
        model=model,
        local_model=local_model,
        timeout=cfg["timeout"],
        local_timeout=cfg["local_timeout"],
        max_candidates=cfg["max_candidates"],
        local_slot=local_slot,
    )


def build_notice_match(settings: Settings | None = None, repo=None):
    """NoticeMatcher — rnd_notice 자료원만, 접수 중인 공고 상위 3건 (LLM 없음, #13 선행)."""
    from rra.application.usecases.notice_match import NoticeMatcher

    settings = settings or load_settings()
    repo = repo or build_repository(build_embedding(settings), settings)
    return NoticeMatcher(repo)


def build_policy_suggest(settings: Settings | None = None, repo=None):
    """PolicySuggest 유스케이스 — korail_web policy 문서에서 정책 문구 3~5개 (LLM 없음)."""
    from rra.application.usecases.policy_suggest import PolicySuggest

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    return PolicySuggest(repo, keywords=keyword_rule(settings))


def build_generate(
    settings: Settings | None = None,
    *,
    repo=None,
    llm=None,
    reranker=None,
    pipeline=None,
    local_slot=None,
    public: bool = False,
):
    """GenerateProposal 유스케이스. repo·llm 을 주면 그대로 쓴다(테스트용).
    [Q] 품질 단계(section_search·exemplars·rule_check·reranker)는 config/pipeline.yaml 을 따른다.
    [3] 작성자(llm.yaml compose.writer, ADR 0032): gemini 면 Argon 이 먼저 쓰고 실패 섹션만
    로컬(llm)이 local_slot 을 잡고 쓴다. public=True(공용 계정 run)면 원격 작성에 internal 을
    보내지 않는다."""
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
    policy = compose_policy(settings)
    writer = build_compose_writer(settings, fake_llm=llm if settings.fake_llm else None)
    # Argon 이 먼저 쓰면 ADR 0027 대체 작성(로컬 실패 → Gemini)은 쓰지 않는다 — 역할이 뒤집힌다
    fallback = build_compose_fallback(settings) if writer is None else None
    include_internal = review_policy(settings)["include_internal"]
    local_cfg = llm_config(settings, "compose")
    # U3 AI 다시 쓰기(2026-10-28 레인 B): 작성자가 로컬이면 다시 쓰기만 Argon(review 단계) 먼저
    rewrite = build_rewrite_writer(settings, fake_llm=llm if settings.fake_llm else None)
    if writer is not None:
        rewrite = None  # Argon 작성이면 다시 쓰기도 같은 작성자(writer_llm)를 쓴다
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
        chunk_max_chars=pipeline.chunk_max_chars,
        base_chunk_limit=pipeline.base_chunk_limit,
        fallback_llm=fallback["llm"] if fallback else None,
        fallback_provider=fallback["provider"] if fallback else "",
        fallback_model=fallback["model"] if fallback else "",
        fallback_include_internal=include_internal,
        writer_llm=writer["llm"] if writer else None,
        writer_provider=writer["provider"] if writer else "",
        writer_model=writer["model"] if writer else "",
        writer_include_internal=include_internal and not public,
        local_provider=local_cfg["provider"],
        local_model=local_cfg["served_model"] or local_cfg["model"],
        local_slot=local_slot,
        compose_concurrency=policy["concurrency"],
        local_check=policy["local_check"],
        local_check_timeout=policy["local_check_timeout_sec"],
        rewrite_llm=rewrite["llm"] if rewrite else None,
        rewrite_provider=rewrite["provider"] if rewrite else "",
        rewrite_model=rewrite["model"] if rewrite else "",
    )


def build_rewrite_writer(
    settings: Settings | None = None, *, fake_llm=None
) -> dict[str, Any] | None:
    """U3 AI 다시 쓰기의 원격 작성자 — review 단계 provider(Gemini 4 Argon, 예산 래퍼·공유 제한기).
    키가 없으면 None(로컬만). 가짜 모드는 fake_llm."""
    settings = settings or load_settings()
    if fake_llm is not None:
        return {"llm": fake_llm, "provider": "gemini", "model": "fake/argon"}
    if not llm_available(settings, stage="review"):
        return None
    cfg = llm_config(settings, "review")
    return {
        "llm": build_llm(settings, stage="review"),
        "provider": cfg["provider"],
        "model": cfg["served_model"] or cfg["model"],
    }


def build_argon_first(settings: Settings | None = None, *, llm=None, local_slot=None):
    """작성·편집 AI 버튼(보강 질문·정책 작성안·보완 질문)의 호출 순서 — Argon(review 단계 provider,
    BudgetedLLM·공유 제한기) 먼저, 실패하면 로컬(clarify 단계 = 로컬 모델, local_slot 안에서).
    review 키가 없으면 로컬만. 가짜 모드는 llm 하나가 Argon 자리를 맡는다(외부 호출 없음).
    llm 을 주면 로컬 자리에 그대로 쓴다(테스트·가짜 모드)."""
    from rra.application.usecases.argon_first import ArgonFirst

    settings = settings or load_settings()
    argon = None
    if settings.fake_llm:
        argon = llm
    elif llm_available(settings, stage="review"):
        argon = build_llm(settings, stage="review")
    local = llm if llm is not None else build_llm(settings, stage="clarify")
    if settings.fake_llm:
        local = None if argon is local else local
    review_cfg = llm_config(settings, "review") if argon is not None else None
    local_cfg = llm_config(settings, "clarify")
    return ArgonFirst(
        local,
        argon,
        local_gate=local_slot.acquire if local_slot is not None else None,
        argon_model=str(
            (review_cfg["served_model"] or review_cfg["model"]) if review_cfg else "argon"
        ),
        local_model=str(local_cfg["served_model"] or local_cfg["model"]),
    )


def build_policy_cards(settings: Settings | None = None, *, repo=None, llm=None, local_slot=None):
    """정책적 중요도 작성안 4개(PolicyCards) — 정책 자료원 검색 + Argon 작성(로컬 대체)."""
    from rra.application.usecases.policy_cards import PolicyCards

    settings = settings or load_settings()
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    return PolicyCards(
        repo,
        build_argon_first(settings, llm=llm, local_slot=local_slot),
        keywords=keyword_rule(settings),
    )


def build_section_questioner(settings: Settings | None = None, *, llm=None, local_slot=None):
    """U3 보완 질문(SectionQuestions) — Argon 이 본문·근거·작성 지침을 읽고 묻는다
    (실패하면 로컬 → 체크리스트)."""
    from rra.application.usecases.section_questions import SectionQuestions

    settings = settings or load_settings()
    return SectionQuestions(
        build_argon_first(settings, llm=llm, local_slot=local_slot),
        build_prompt_library(settings),
        checklists=section_checklists(settings),
        titles=lint_rules(settings).titles,
    )


def build_compose_writer(
    settings: Settings | None = None, *, fake_llm=None
) -> dict[str, Any] | None:
    """[3] 원격 작성 LLM(ADR 0032) — llm.yaml compose.writer=gemini 면 gemini provider 의
    compose 단계. 키가 없으면 None(자동으로 로컬 작성). 일일 예산 카운터(BudgetedLLM)·공유 호출
    제한기는 build_llm 이 씌운다. 가짜 모드는 fake_llm 을 Argon 자리에 그대로 쓴다
    (외부 호출 없음)."""
    settings = settings or load_settings()
    if compose_policy(settings)["writer"] != "gemini":
        return None
    if fake_llm is not None:
        return {"llm": fake_llm, "provider": "gemini", "model": "fake/argon"}
    cfg = llm_config(settings, "compose", provider="gemini")
    if not llm_key_present(settings, cfg):
        logger.warning("compose.writer=gemini 의 키가 없어 로컬 작성으로 진행합니다.")
        return None
    return {
        "llm": build_llm(settings, stage="compose", provider="gemini"),
        "provider": "gemini",
        "model": cfg["served_model"] or cfg["model"],
    }


def build_compose_fallback(settings: Settings | None = None) -> dict[str, Any] | None:
    """대체 작성 LLM(ADR 0027) — llm.yaml stages.compose.fallback 의 provider. 키가 없으면 None(자동
    끔).
    gemini 는 build_llm 이 일일 예산 카운터(BudgetedLLM)로 감싼다. 전송 범위는 검토 정책과 같다."""
    settings = settings or load_settings()
    provider = llm_fallback(settings, "compose")
    if provider is None:
        return None
    cfg = llm_config(settings, "compose", provider=provider)
    if not llm_key_present(settings, cfg):
        logger.warning("compose.fallback=%s 의 키가 없어 대체 작성을 끕니다.", provider)
        return None
    return {
        "llm": build_llm(settings, stage="compose", provider=provider),
        "provider": provider,
        "model": cfg["served_model"] or cfg["model"],
    }


def build_figure_renderer(settings: Settings | None = None):
    """[G] 밑그림 렌더러(SVG → PNG, 번들 Pretendard). config/figures.yaml 팔레트·비율·폭."""
    from rra.adapters.figures import SvgFigureRenderer

    settings = settings or load_settings()
    cfg = figures_config(settings)
    fonts = sorted(Path(cfg["fonts_dir"]).glob("*.otf"))
    return SvgFigureRenderer(
        cfg["palette"],
        cfg["aspects"],
        width_px=cfg["width_px"],
        font_files=fonts,
        dpi=cfg["dpi"],
        max_bytes=cfg["max_png_bytes"],
    )


_FIGURE_BUDGETS: dict[tuple[str, int], Any] = {}


def build_image_generator(settings: Settings | None = None):
    """[G] Nano Banana Pro(ImageGeneratorPort). gemini 키가 없으면 None → 기본 그림만.
    일일 상한(figures.daily_image_cap)은 FileDailyBudget 하나를 프로세스 안에서 공유한다."""
    from rra.adapters.llm.daily_budget import FileDailyBudget
    from rra.adapters.llm.image_gen import GeminiImageGenerator
    from rra.adapters.llm.rate_limiter import limiter_for

    settings = settings or load_settings()
    cfg = figures_config(settings)
    llm_cfg = llm_config(settings, "review", provider="gemini")
    if not llm_key_present(settings, llm_cfg):
        return None
    key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else ""
    providers = read_config("llm.yaml", settings).get("providers") or {}
    gemini = providers.get("gemini") or {}
    budget = None
    if cfg["daily_image_cap"] > 0:
        bkey = (str(cfg["budget_counter"]), cfg["daily_image_cap"])
        if bkey not in _FIGURE_BUDGETS:
            _FIGURE_BUDGETS[bkey] = FileDailyBudget(cfg["budget_counter"], cfg["daily_image_cap"])
        budget = _FIGURE_BUDGETS[bkey]
    rate = llm_cfg.get("rate") or {}
    return GeminiImageGenerator(
        base_url=llm_cfg["base_url"],
        api_key=key,
        model=str(gemini.get("image_model") or "gemini-3-pro-image"),
        allowed_hosts=allowed_domains(settings),
        timeout_sec=float(llm_cfg["timeout"]["read"]),
        attempts=int(llm_cfg["retry"]["attempts"]),
        limiter=limiter_for(
            "gemini",
            concurrency=int(rate.get("concurrency", 4)),
            per_minute=int(rate.get("per_minute", 60)),
        ),
        budget=budget,
        cache_dir=cfg["cache_dir"],
    )


def build_figures(
    settings: Settings | None = None,
    *,
    llm=None,
    images=None,
    renderer=None,
    fallback_llm=None,
    argon=None,
):
    """[G] 그림 유스케이스(MakeFigures). figures.yaml enabled=false 면 None.
    명세·[말로 고치기] 명세 변경은 Argon(review 단계 provider, 예산 래퍼) 먼저, 실패면 로컬 모델
    (stage figures). review 키가 없으면 로컬 → compose.fallback(예전 순서). 그림은 Nano Banana."""
    import json

    from rra.adapters.figures import shrink_image
    from rra.application.usecases.figures import FigureConfig, MakeFigures

    settings = settings or load_settings()
    cfg = figures_config(settings)
    if not cfg["enabled"]:
        return None
    if llm is None:
        llm = build_llm(settings, stage=cfg["spec_stage"])
    if images is None and not settings.fake_llm:
        images = build_image_generator(settings)
    if argon is None and not settings.fake_llm and llm_available(settings, stage="review"):
        argon = build_llm(settings, stage="review")  # gemini 면 BudgetedLLM (일일 상한 공유)
    if fallback_llm is None and argon is None and not settings.fake_llm:
        fb = build_compose_fallback(settings)
        fallback_llm = fb["llm"] if fb else None
    review_cfg = llm_config(settings, "review")
    local_cfg = llm_config(settings, cfg["spec_stage"])
    schemas = {}
    for kind in cfg["kinds"]:
        path = Path(cfg["template_dir"]) / f"{kind}.schema.json"
        if path.is_file():
            schemas[kind] = json.loads(path.read_text(encoding="utf-8"))
    rules = lint_rules(settings)
    return MakeFigures(
        llm,
        build_prompt_library(settings),
        renderer or build_figure_renderer(settings),
        images=images,
        fallback_llm=fallback_llm,
        config=FigureConfig(
            enabled=True,
            max_default=cfg["max_default"],
            concurrency=cfg["concurrency"],
            image_size=cfg["image_size"],
            aspects=cfg["aspects"],
            kinds=tuple(cfg["kinds"]),
            max_bytes=cfg["max_png_bytes"],
            schemas=schemas,
            auto_aspect=cfg["auto_aspect"],
            max_techniques=cfg["max_techniques"],
            auto_kinds=tuple(cfg["auto_kinds"]),
        ),
        catalog=technique_catalog(settings),
        include_internal=review_policy(settings)["include_internal"],
        titles=rules.titles,
        shrink=lambda data, mime: shrink_image(data, mime, max_bytes=cfg["max_png_bytes"]),
        clock=lambda: datetime.now(UTC).isoformat(timespec="seconds"),
        argon=argon,
        argon_model=str(review_cfg["served_model"] or review_cfg["model"]),
        local_model=str(local_cfg["served_model"] or local_cfg["model"]),
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
    figures=None,
    first_pass: bool | None = None,
    live_search=None,
):
    """RunManager — 파일 저장소(runs/), 프로세스 간 슬롯, manifest 로그, 실행기, HWPX 렌더러,
    검토 유스케이스(review 단계 키가 있을 때만; 없으면 None → review_skipped).
    pipeline·runs_dir 는 측정(`rra eval`)이 설정과 다른 구성·별도 폴더로 돌릴 때 준다.

    repo·llm 은 바로 만든다. 임베딩 모델은 어댑터가 첫 호출 때 올리므로 상태 조회만 할 때는
    로드되지 않는다 (SentenceTransformerEmbedding.loaded).
    """
    from rra.adapters.logging import FileRunLog
    from rra.adapters.runs import AsyncioTaskRunner, FileRunStore, FlockPool, FlockSlot
    from rra.application.services import RunManager

    settings = settings or load_settings()
    # runs/ 는 그대로(상대면 cwd). data/ 아래를 지정했을 때만 데이터 폴더로 옮긴다.
    root = data_path(settings, runs_dir or settings.runs_dir, only_prefixed=True)
    compose_cfg = llm_config(settings, "compose")
    pipeline = pipeline or pipeline_config(settings)
    # manifest 에는 선언된 실제 모델명(served_model)을, 없으면 요청용 이름을 남긴다
    model = compose_cfg["served_model"] or compose_cfg["model"]
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    if llm is None:
        llm = build_llm(settings, stage="compose")
    slot = FlockSlot(root / ".generate.lock")  # 로컬 모델 — 프로세스 간 한 번에 하나
    generate = build_generate(settings, repo=repo, llm=llm, pipeline=pipeline, local_slot=slot)
    generate_public = None
    if not auth_config(settings)["include_internal"]:  # 공용 계정 run 은 internal 제외 (레인 A)
        generate_public = build_generate(
            settings,
            repo=public_repository(repo),
            llm=llm,
            reranker=generate.reranker,
            pipeline=pipeline,
            local_slot=slot,
            public=True,
        )
    # [3] Argon 작성이면 run 은 N칸 슬롯(runs.max_concurrent)만, 로컬 단계만 slot 을 잡는다
    # (ADR 0032)
    run_slot = (
        FlockPool(root, runs_config(settings)["max_concurrent"])
        if generate.writes_remotely
        else None
    )
    manager = RunManager(
        generate,
        store or FileRunStore(root),
        slot,
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
        generate_public=generate_public,
        review_budget=build_review_budget(settings),
        figures=_with_local_slot(
            figures if figures is not None else build_figures(settings, llm=llm), slot
        ),
        run_slot=run_slot,
        first_pass=review_policy(settings)["first_pass"] if first_pass is None else first_pass,
        live_search=live_search,  # [4] build_api 가 REST 와 같은 인스턴스(세션 공유)를 준다
    )
    # 2026-10-28 레인 B — ④ 편집의 AI 버튼(보완 질문·빈 2-가-(1) 작성안). Argon 먼저, 로컬은 slot
    # 안에서
    manager.section_questioner = build_section_questioner(settings, llm=llm, local_slot=slot)
    manager.section_questioner_public = manager.section_questioner  # 청크 범위는 run 이 정한다
    manager.policy_cards = build_policy_cards(settings, repo=repo, llm=llm, local_slot=slot)
    if generate_public is not None:
        manager.policy_cards_public = build_policy_cards(
            settings, repo=public_repository(repo), llm=llm, local_slot=slot
        )
    return manager


def _with_local_slot(figures, slot):
    """그림 유스케이스의 로컬 모델 호출이 RunManager 와 같은 슬롯(.generate.lock)을 잡게 한다."""
    if figures is not None and figures.local_slot is None:
        figures.local_slot = slot
    return figures


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
    """등록 순서(안쪽부터): 인증 → 본문 상한 → 헤더 → 접근 로그(4xx·5xx 만).

    FastAPI.add_middleware 는 마지막에 넣은 것이 바깥이 된다.
    → 접근 로그가 가장 바깥에서 모든 응답 상태를 본다.
    """
    from rra.adapters.security import (
        AccessLogMiddleware,
        BodyLimitMiddleware,
        SecurityHeadersMiddleware,
        TokenAuthMiddleware,
    )

    limits = input_limits(settings)
    api = api_config(settings)
    outer_to_inner = [
        (
            AccessLogMiddleware,
            {
                "trust_cf": api["trust_cf_connecting_ip"],
                "trust_forwarded": api["trust_forwarded_from_loopback"],
            },
        ),
        (SecurityHeadersMiddleware, {}),
        (BodyLimitMiddleware, {"max_bytes": int(limits.get("api_max_body_bytes", 64 * 1024))}),
        (
            TokenAuthMiddleware,
            {
                "token": token,
                "sessions": sessions,
                "public_origin": api["public_origin"],
                "trust_cf": api["trust_cf_connecting_ip"],
                "trust_forwarded": api["trust_forwarded_from_loopback"],
            },
        ),
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


def _fake_policy() -> tuple[list[Any], list[Any]]:
    """가짜 모드 정책 자료 3건(국토부·공사 전략·감사원) — 정책적 중요도 작성안 e2e 경로."""
    from datetime import date

    from rra.domain.models import Chunk, Document

    rows = [
        (
            "molit:fake-plan",
            "molit",
            "policy",
            "철도 안전 강화 계획 (가짜)",
            "정부는 노후 궤도의 검측 고도화와 보수 체계 개선으로 철도 안전을 높이려 함.",
            "https://www.molit.go.kr/fake-plan",
        ),
        (
            "korail_web:fake-strategy",
            "korail_web",
            "policy",
            "공사 중장기 경영목표 (가짜)",
            "공사는 데이터 기반 궤도 유지보수로 안전 수준과 보수 효율을 함께 높이려 함.",
            "https://info.korail.com/fake-strategy",
        ),
        (
            "bai:fake-audit",
            "bai",
            "audit",
            "철도 시설 유지관리 실태 감사 (가짜)",
            "감사원은 궤도 틀림 보수가 주기 위주라 위험 구간 대응이 늦다고 지적함.",
            "https://www.bai.go.kr/fake-audit",
        ),
    ]
    docs = [
        Document(
            doc_id=d,
            source=src,
            doc_type=dt,
            title=title,
            body=body,
            pub_date=date(2025, 3, 1),
            url=url,
            orgs=["external"],
        )
        for d, src, dt, title, body, url in rows
    ]
    chunks = [
        Chunk(chunk_id=f"{d}#0", doc_id=d, ordinal=0, text=body, basis="full_text")
        for d, _, _, _, body, _ in rows
    ]
    return docs, chunks


_FAKE_POLICY_DOCS, _FAKE_POLICY_CHUNKS = _fake_policy()


def build_fake_parts(settings: Settings):
    """가짜 모드(RRA_FAKE_LLM=1) 부품 — 가짜 LLM·메모리 저장소·시드 문서. adapters/fake."""
    from datetime import date

    from rra.adapters.fake import (
        FakeImageGenerator,
        InMemoryDocumentRepository,
        InMemoryRunStore,
        NoopRunLog,
        ScriptedAuthStore,
        ScriptedComposeLLM,
        ScriptedNtisInsights,
        ScriptedReviewLLM,
    )
    from rra.application.usecases.ntis_insights import NtisProjectInsights
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
            # NTIS 과제검색 문서 → 유사과제 티어 national_rnd (② "주요 성과"·"NTIS 추천" e2e 경로).
            # 청크 없이 문서만 — precheck(find_similar) 에는 잡히고 생성 근거(hybrid_search) 에는
            # 안 들어간다
            Document(
                doc_id="ntis:fake-1",
                source="ntis",
                doc_type="rnd_project",
                title="궤도 틀림 진행 예측 국가R&D 과제 (가짜)",
                abstract="궤도 틀림 진행 속도를 예측해 보수 우선순위를 정하는 국가R&D 과제 요약",
                orgs=["external"],
                text_basis="abstract",
                raw={"kind": "national_rnd", "project_no": "fake-1"},
            ),
            # ScienceON 논문 → 유사과제 판정이 아니라 ② "관련 연구"(참고) 목록 (ADR 0028). 청크 없이
            # 문서만.
            Document(
                doc_id="scienceon:fake-1",
                source="scienceon",
                doc_type="paper",
                title="궤도 틀림 진행 속도 추정 논문 (가짜)",
                abstract="검측 이력으로 궤도 틀림 진행 속도를 추정하는 국내 논문 초록",
                orgs=["external"],
                pub_date=date(2024, 5, 1),
                url="https://scienceon.kisti.re.kr/fake-1",
                text_basis="abstract",
            ),
            *_FAKE_POLICY_DOCS,
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
            *_FAKE_POLICY_CHUNKS,
        ],
        when="2026-10-26",
    )
    ntis = ScriptedNtisInsights()
    return {
        "repo": repo,
        "llm": ScriptedComposeLLM(),
        "review_llm": ScriptedReviewLLM(),
        "store": InMemoryRunStore(),
        "run_log": NoopRunLog(),
        "ntis_insights": NtisProjectInsights(ntis, ntis, repo=repo),
        "auth": ScriptedAuthStore(),  # e2e 고정 계정 — 실제 data/auth 를 쓰지 않는다
        "images": FakeImageGenerator(),  # [G] 그림: 밑그림을 그대로 돌려준다 (외부 호출 없음)
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
    from rra.adapters.security import client_ip
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
        live = build_live_search(settings, repo=repo)  # [4] 가짜 자료원·규칙 키워드
        manager = build_run_manager(
            settings,
            repo=repo,
            llm=llm,
            runner=runner,
            review_llm=fake["review_llm"],
            store=fake["store"],
            run_log=fake["run_log"],
            figures=build_figures(settings, llm=llm, images=fake["images"]),
            # 가짜 모드는 e2e 화면(③ Argon 1차 검토·v2)을 계속 보여 주려고 1차 검토를 켠다.
            # 배포 기본(review.first_pass: off, ADR 0032)과 다르다
            first_pass=True,
            live_search=live,
        )
    else:
        if repo is None:
            repo = build_repository(build_embedding(settings), settings)
        live = build_live_search(settings, repo=repo)  # [4] REST·run 이 세션을 공유한다
        manager = build_run_manager(settings, repo=repo, llm=llm, runner=runner, live_search=live)
    sessions = build_sessions(settings)
    static = static_dir if static_dir is not None else Path(settings.static_dir)
    slot = getattr(manager.generate, "local_slot", None)  # 로컬 모델 — 생성과 같은 슬롯
    # ② 판정(레인 A): AI 같음 판정 + 핵심 키워드(실시간 검색과 같은 LiveKeywordMaker)
    precheck = build_precheck(
        settings, repo=repo, judge=True, llm=llm, local_slot=slot, keyword_source=live.keywords
    )
    pipeline = pipeline_config(settings)
    auth = auth_config(settings)
    guest_services = None
    if not auth["include_internal"]:  # 공용 계정용 — internal 을 뺀 저장소로 같은 유스케이스
        guest_services = build_scoped_services(
            settings,
            public_repository(repo),
            llm=llm,
            ntis_insights=fake["ntis_insights"] if fake else None,
            local_slot=slot,
            keyword_source=live.keywords,
        )
    return create_app(
        manager=manager,
        precheck=precheck,
        policy_suggest=build_policy_suggest(settings, repo=repo),
        notice_match=build_notice_match(settings, repo=repo),
        differentiate=build_differentiator(settings, repo=repo, llm=llm, local_slot=slot),
        recommend=build_recommender(
            settings, repo=repo, llm=llm, precheck=precheck, local_slot=slot
        ),
        recommend_auto=recommend_policy(settings)["auto"],
        clarify=build_clarifier(settings, llm=llm, local_slot=manager.slot)
        if pipeline.clarify
        else None,
        policy_cards=build_policy_cards(settings, repo=repo, llm=llm, local_slot=manager.slot),
        structure=build_structurer(settings, llm=llm),
        compare=build_comparer(settings, repo=repo, precheck=precheck, llm=llm, local_slot=slot),
        polish=build_polisher(settings, llm=llm, local_slot=slot),
        choice_log=build_choice_log(settings),
        brief=build_briefer(settings, repo=repo, llm=llm),
        ntis_insights=fake["ntis_insights"] if fake else build_ntis_insights(settings, repo=repo),
        repo=repo,
        login=build_login(settings, store=fake["auth"] if fake else None),
        auth_limits=auth["limits"],
        trust_cf=auth["trust_cf_connecting_ip"],
        trust_forwarded=auth["trust_forwarded_from_loopback"],
        client_ip=client_ip,
        guest_services=guest_services,
        user=LOCAL_USER,
        middlewares=api_middlewares(settings, token, sessions=sessions),
        query_max_chars=int(input_limits(settings).get("query_max_chars", 500)),
        on_shutdown=manager.generate.llm.aclose,
        session_auth=SessionAuth(token, sessions),
        public_origin=api_config(settings)["public_origin"],
        static_dir=static,
        sse_poll_sec=sse_poll_sec,
        fake_mode=fake is not None,
        snapshot_status=build_korail_web_source(settings).status,
        notice_snapshot_status=build_rnd_notice_source(settings).status,
        availability_notices=build_source_availability(settings).notices,
        version=build_version_info(settings),
        live_search=live if live.enabled else None,
    )


def build_version_info(settings: Settings | None = None) -> dict[str, Any]:
    """배포 버전 — data/deploy/version.json(tools/deploy.sh), 없으면 git HEAD + 시작 시각."""
    from rra.adapters.deploy import read_version

    settings = settings or load_settings()
    return read_version(
        data_location(settings, "deploy_version"), repo_root=Path(__file__).parents[2]
    )


def build_scoped_services(
    settings: Settings,
    repo,
    *,
    llm=None,
    ntis_insights=None,
    local_slot=None,
    keyword_source=None,
) -> dict[str, Any]:
    """공용 계정(guest)용 서비스 묶음 — 같은 유스케이스를 internal 제외 저장소로 조립 (레인 A).
    키는 create_app 의 인자 이름과 같다."""
    precheck = build_precheck(
        settings,
        repo=repo,
        judge=True,
        llm=llm,
        local_slot=local_slot,
        keyword_source=keyword_source,
    )
    return {
        "repo": repo,
        "precheck": precheck,
        "policy_suggest": build_policy_suggest(settings, repo=repo),
        "policy_cards": build_policy_cards(settings, repo=repo, llm=llm),
        "notice_match": build_notice_match(settings, repo=repo),
        "differentiate": build_differentiator(settings, repo=repo, llm=llm, local_slot=local_slot),
        "recommend": build_recommender(
            settings, repo=repo, llm=llm, precheck=precheck, local_slot=local_slot
        ),
        "compare": build_comparer(
            settings, repo=repo, precheck=precheck, llm=llm, local_slot=local_slot
        ),
        "brief": build_briefer(settings, repo=repo, llm=llm),
        "ntis_insights": ntis_insights
        if ntis_insights is not None
        else build_ntis_insights(settings, repo=repo),
    }


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


def _local_fallback(settings: Settings, *, remote: bool, llm=None):
    """Argon 단계의 로컬 대체(compose 단계, 레인 A). 이미 로컬이거나 llm 을 주었으면 None."""
    if not remote or llm is not None:
        return None
    try:
        return build_llm(settings, stage="compose")
    except (LLMUnavailable, KeyError, ValueError):
        return None


def build_differentiator(settings: Settings | None = None, *, repo=None, llm=None, local_slot=None):
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
    local = _local_fallback(settings, remote=not fallback, llm=llm)
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
        local=local,
        local_slot=local_slot,
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


def build_comparer(
    settings: Settings | None = None, *, repo=None, precheck=None, llm=None, local_slot=None
):
    """U4 차별성 비교표(CompareProjects). usability.comparison 이 꺼지면 None. 기존 과제 칸은
    CellExtractor(Argon → 로컬 → 규칙, 레인 A)가 원문에서 뽑는다. llm 을 주면 그것만 Argon
    자리로."""
    from rra.application.usecases.compare_projects import CompareProjects
    from rra.application.usecases.extract_cells import CellExtractor

    settings = settings or load_settings()
    if not usability_config(settings).comparison:
        return None
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    primary, local = _argon_and_local(settings, llm=llm)
    extractor = CellExtractor(
        primary=primary,
        local=local,
        include_internal=review_policy(settings)["include_internal"],
        local_slot=local_slot,
    )
    return CompareProjects(
        repo, precheck=precheck or build_precheck(settings, repo=repo), extractor=extractor
    )


def _argon_and_local(settings: Settings, *, llm=None):
    """② AI 기능 공용 — (Argon, 로컬). Argon = overlap.yaml judgment.stage(기본 review: gemini 면
    일일 예산·공유 호출 제한기), 로컬 = judgment.local_stage. llm 을 주면(가짜 모드·테스트) (llm,
    None)."""
    if llm is not None:
        return llm, None
    cfg = same_judgment_config(settings)
    primary = local = None
    if llm_available(settings, stage=cfg["stage"]):
        try:
            primary = build_llm(settings, stage=cfg["stage"])
        except (LLMUnavailable, KeyError, ValueError):
            primary = None
    if cfg["local_stage"]:
        try:
            local = build_llm(settings, stage=cfg["local_stage"])
        except (LLMUnavailable, KeyError, ValueError):
            local = None
    return primary, local


def build_polisher(settings: Settings | None = None, *, llm=None, local_slot=None):
    """② 과제안 [AI로 다듬기](PolishField, 레인 A) — Argon → 로컬. 둘 다 없으면 None."""
    from rra.application.usecases.polish_field import PolishField

    settings = settings or load_settings()
    primary, local = _argon_and_local(settings, llm=llm)
    if primary is None and local is None:
        return None
    return PolishField(primary=primary, local=local, local_slot=local_slot)


def build_choice_log(settings: Settings | None = None):
    """② 유사과제 선택 기록(JSONL, 레인 A). 가짜 모드는 메모리(데이터 폴더를 건드리지 않는다)."""
    from rra.adapters.logging.choice_log import JsonlChoiceLog, MemoryChoiceLog

    settings = settings or load_settings()
    if settings.fake_llm:
        return MemoryChoiceLog()
    return JsonlChoiceLog(data_location(settings, "similar_choices"))


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


def build_clarifier(settings: Settings | None = None, *, llm=None, local_slot=None):
    """③ 입력 보강 질문 유스케이스(Q1, ClarifyInput) — Argon(review 단계) 먼저, 실패하면 로컬
    (clarify 단계), 둘 다 실패하면 앱 점검 질문 + 사유(2026-10-28 레인 B). 호출자는
    pipeline.clarify 가 켜져 있을 때만 부른다(꺼져 있으면 상태 off)."""
    from rra.application.usecases.clarify_input import ClarifyInput

    settings = settings or load_settings()
    ask = build_argon_first(settings, llm=llm, local_slot=local_slot)
    return ClarifyInput(
        ask.local,
        build_prompt_library(settings),
        argon=ask.argon,
        checklists=section_checklists(settings),
        local_gate=ask.local_gate,
        argon_model=ask.argon_model,
        local_model=ask.local_model,
    )


def build_recommender(
    settings: Settings | None = None, *, repo=None, llm=None, precheck=None, local_slot=None
):
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
    local = _local_fallback(settings, remote=not fallback, llm=llm)
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
        local=local,
        local_slot=local_slot,
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


# ── [4] 실시간 자료 검색 (ADR 0031) ───────────────────────────
def build_live_sources(settings: Settings | None = None, *, transport=None, resolver=None):
    """실시간 검색 전용 자료원 어댑터 {scienceon, ntis, openalex}. 야간 적재와 다른 인스턴스라 요청
    예산이 섞이지 않는다. 키가 없는 자료원(MissingCredential)은 빠진다 — 세션 상태에 error 로
    보인다."""
    from rra.adapters.sources.live import LiveNtis, LiveOpenAlex, LiveScienceOn
    from rra.config_loader import live_search_config

    settings = settings or load_settings()
    cfg = live_search_config(settings)
    out: dict[str, Any] = {}
    kw = {"transport": transport, "resolver": resolver}
    if cfg.source("scienceon").enabled:
        try:
            out["scienceon"] = LiveScienceOn(
                build_scienceon_source(settings, **kw),
                max_requests=cfg.source("scienceon").max_requests,
            )
        except MissingCredential:
            logger.info("live.source_missing_key source=scienceon")
    if cfg.source("ntis").enabled:
        try:
            out["ntis"] = LiveNtis(
                build_ntis_source(settings, **kw),
                build_ntis_report_source(settings, **kw),
                max_requests=cfg.source("ntis").max_requests,
            )
        except MissingCredential:
            logger.info("live.source_missing_key source=ntis")
    if cfg.source("openalex").enabled:
        out["openalex"] = LiveOpenAlex(
            build_openalex_source(settings, transport=transport),
            max_requests=cfg.source("openalex").max_requests,
        )
    return out


def build_live_keywords(settings: Settings | None = None, *, llm=None, local_llm=None):
    """키워드 만들기 — Argon(keywords.stage, 기본 review=gemini: 일일 예산·공유 호출 제한기) →
    로컬(keywords.local_stage) → 규칙. 키가 없는 단계는 건너뛴다. llm 을 주면 그것만 쓴다(가짜
    모드)."""
    from rra.application.usecases.live_search import LiveKeywordMaker
    from rra.config_loader import live_search_config

    settings = settings or load_settings()
    kcfg = live_search_config(settings).keywords
    primary, local = llm, local_llm
    if llm is None:
        if kcfg.stage and llm_available(settings, stage=kcfg.stage):
            try:
                primary = build_llm(settings, stage=kcfg.stage)
            except (LLMUnavailable, KeyError, ValueError):
                primary = None
        if kcfg.local_stage and local_llm is None:
            try:
                local = build_llm(settings, stage=kcfg.local_stage)
            except (LLMUnavailable, KeyError, ValueError):
                local = None
    return LiveKeywordMaker(
        primary=primary,
        local=local,
        timeout=kcfg.timeout_seconds,
        local_timeout=kcfg.local_timeout_seconds,
        rule=keyword_rule(settings),
    )


def build_live_search(
    settings: Settings | None = None, *, repo=None, llm=None, sources=None, runner=None
):
    """LiveSearch 유스케이스. 가짜 모드(settings.fake_llm)면 가짜 자료원. 설정이 꺼져 있으면
    enabled=False 인 인스턴스(호출자는 그대로 써도 off 요약만 받는다 — 종전 동작)."""
    from rra.adapters.persistence.file_cache import FileCache
    from rra.adapters.runs import AsyncioTaskRunner
    from rra.application.usecases.live_search import LiveSearch
    from rra.config_loader import live_search_config

    settings = settings or load_settings()
    cfg = live_search_config(settings)
    if settings.fake_llm and not cfg.fake_mode:
        # 가짜 모드는 기본 끔 (live_search.yaml fake_mode: true 로 켬)
        cfg = cfg.model_copy(update={"enabled": False})
    if repo is None:
        repo = build_repository(build_embedding(settings), settings)
    if sources is None:
        if settings.fake_llm:
            from rra.adapters.fake import fake_live_sources

            sources = fake_live_sources()
        else:

            def sources() -> dict[str, Any]:  # 처음 쓸 때 만든다 (꺼져 있으면 만들지 않는다)
                return build_live_sources(settings)

    # 가짜 모드는 데이터 폴더(캐시·자료원 가용 상태)를 건드리지 않는다
    cache = (
        FileCache(data_location(settings, "live_search_cache"), ttl_sec=cfg.cache_hours * 3600)
        if cfg.cache_hours > 0 and not settings.fake_llm
        else None
    )
    if settings.fake_llm and llm is None:
        from rra.adapters.fake import FakeKeywordLLM
        from rra.application.usecases.live_search import LiveKeywordMaker

        keywords = LiveKeywordMaker(primary=FakeKeywordLLM(), rule=keyword_rule(settings))
    else:
        keywords = build_live_keywords(settings, llm=llm)
    return LiveSearch(
        cfg,
        repo,
        runner or AsyncioTaskRunner(),
        sources=sources,
        keywords=keywords,
        cache=cache,
        availability=None if settings.fake_llm else build_source_availability(settings),
        public_ip=None if settings.fake_llm else build_public_ip_probe(settings),
    )
