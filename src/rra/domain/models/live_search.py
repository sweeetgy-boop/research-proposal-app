"""[4] 실시간 자료 검색 — 설정·키워드·자료원별 결과·세션 요약 (ADR 0031).

입력 확인(②) 때 아이디어에서 국문·영문 키워드를 만들고 ScienceON·NTIS·OpenAlex 를 동시에 검색해
DB 에 public 으로 저장한다. 요약(`LiveSearchSummary`)은 REST·run 상태·manifest 에 나간다 — 본문
없음,
키워드는 화면용(manifest 에는 개수만).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

LIVE_SOURCES: tuple[str, ...] = ("scienceon", "ntis", "openalex")
LiveSourceName = Literal["scienceon", "ntis", "openalex"]
# ok=검색 완료(0건 포함), timeout=제한 시간 초과로 건너뜀, ip_blocked=호출 IP 거부(NTIS),
# error=그 밖의 실패(예외 클래스명만 로그), off=설정에서 끔
LiveSourceState = Literal["ok", "timeout", "ip_blocked", "error", "off"]
# done=모든 자료원 ok(또는 off), partial=끝났지만 일부 자료원 실패, pending=아직 도는 중, off=기능
# 꺼짐
LiveStatus = Literal["done", "partial", "pending", "off"]
KeywordOrigin = Literal["argon", "local", "rule", "none"]
MAX_KEYWORDS = 5
MIN_KEYWORDS = 3


class LiveSourceConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    top_n: int = Field(default=30, ge=1, le=100)
    max_requests: int = Field(default=8, ge=1, le=40)  # 세션 하나의 요청 상한 (토큰 요청 포함)


class LiveKeywordConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    stage: str = "review"  # Argon(gemini) — llm.yaml stages
    local_stage: str = "clarify"  # Argon 실패 시 로컬 모델. 빈 문자열이면 로컬 생략
    timeout_seconds: float = Field(default=6.0, gt=0, le=60)
    local_timeout_seconds: float = Field(default=6.0, gt=0, le=60)


class LiveSearchConfig(BaseModel):
    """config/live_search.yaml. 꺼져 있으면(enabled=false) 종전 동작(DB 만)."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    per_source_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    overall_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    wait_seconds: float = Field(default=15.0, ge=0, le=120)  # 결과가 필요한 곳에서 기다리는 상한
    cache_hours: float = Field(default=24.0, ge=0, le=24 * 30)
    ip_block_recheck_minutes: float = Field(default=60.0, ge=0)  # NTIS IP 거부 기록 뒤 재시도 간격
    session_ttl_minutes: float = Field(default=180.0, gt=0)
    max_sessions: int = Field(default=200, ge=1, le=5000)
    keywords: LiveKeywordConfig = Field(default_factory=LiveKeywordConfig)
    sources: dict[str, LiveSourceConfig] = Field(
        default_factory=lambda: {name: LiveSourceConfig() for name in LIVE_SOURCES}
    )

    def source(self, name: str) -> LiveSourceConfig:
        return self.sources.get(name) or LiveSourceConfig(enabled=False)

    def enabled_sources(self) -> list[str]:
        return [n for n in LIVE_SOURCES if self.source(n).enabled]


class LiveKeywords(BaseModel):
    """국문(ScienceON·NTIS)·영문(OpenAlex) 검색어. 정책명·고유명사는 원문 그대로."""

    ko: list[str] = Field(default_factory=list)
    en: list[str] = Field(default_factory=list)
    origin: KeywordOrigin = "none"


class LiveSourceResult(BaseModel):
    source: LiveSourceName
    status: LiveSourceState
    count: int = 0  # 이 자료원에서 받은 문서 수 (정규화 뒤)
    new: int = 0  # 그중 DB 에 새로 저장한 수 (중복·기존 문서 제외)
    seconds: float = 0.0
    notice: str | None = None  # IP 거부 안내 등 사람에게 보일 짧은 문구 (비밀 없음)
    cached: bool = False  # 24 시간 캐시에서 왔다


class LiveSearchSummary(BaseModel):
    status: LiveStatus
    keywords: LiveKeywords = Field(default_factory=LiveKeywords)
    sources: list[LiveSourceResult] = Field(default_factory=list)
    doc_ids: list[str] = Field(default_factory=list)  # 이 세션의 실시간 결과(중복 정리 뒤 doc_id)
    session: str | None = None  # 세션 해시 12자 (제안자 이름·입력 원문 없음)

    def payload(self) -> dict[str, Any]:
        """REST 응답 모양 (web 이 이 모양을 본다)."""
        return {
            "status": self.status,
            "keywords": {"ko": list(self.keywords.ko), "en": list(self.keywords.en)},
            "sources": [
                {
                    "source": s.source,
                    "status": s.status,
                    "count": s.count,
                    "new": s.new,
                    "seconds": round(s.seconds, 2),
                    "notice": s.notice,
                    "cached": s.cached,
                }
                for s in self.sources
            ],
        }

    def manifest(self) -> dict[str, Any]:
        """manifest 용 — 상태·건수만 (키워드·본문 없음)."""
        return {
            "status": self.status,
            "session": self.session,
            "keyword_origin": self.keywords.origin,
            "keywords": {"ko": len(self.keywords.ko), "en": len(self.keywords.en)},
            "sources": [
                {
                    "source": s.source,
                    "status": s.status,
                    "count": s.count,
                    "new": s.new,
                    "seconds": round(s.seconds, 2),
                    "cached": s.cached,
                }
                for s in self.sources
            ],
            "documents": len(self.doc_ids),
        }


def off_summary() -> LiveSearchSummary:
    return LiveSearchSummary(status="off")
