"""배치 수집: 소스별 search → normalize → (전체) dedup → chunking → repo.upsert.

- 레코드 하나가 깨져도 그 레코드만 건너뛴다.
- 소스 하나가 실패해도 다른 소스는 계속한다.
  실패는 예외 클래스명만 남긴다 (D: 메시지에 URL·키가 섞일 수 있음).
- API 가 호출 IP 를 거부하면(SourceIpBlocked, 레인 I) 그 소스만 건너뛰고 `unavailable` 에 안내 문구
  ("현재 IP … 등록 IP 에 없습니다. 활용신청에 추가하세요")를 남긴다 — 로그와 자료원 가용 상태
  (SourceAvailabilityPort → 웹 자료원 상태)에 같은 문구. 공인 IP 는 그때 한 번만 조회한다.
- 이미 저장된 문서보다 근거 수준이 낮은 문서(원문 위에 공개 요약)는 덮어쓰지 않는다.
  이런 raw 도 처리 완료로 통보한다 (더 나은 판본이 이미 있다).
- 저장될 문서에 대해 경고를 모은다 (적재는 막지 않는다):
  `unlisted_department` — own 기관 문서인데 부서가 own 부서 목록에 없음 (목록 보완 확인용),
  그 밖의 코드는 WarningSource 가 준다 (예: `assumed_org` — 카탈로그 매칭 없이 기본 기관 태그).
  로그에는 코드·doc_id·제어문자를 뺀 40자 이내 설명만 남긴다.
- upsert 는 마지막에 한 번만 호출한다 (저장소 쪽 단일 트랜잭션).
- upsert 가 성공한 뒤에만 AcknowledgingSource 에 정규화된 raw 를 통보한다
  (filedrop 은 이때 파일을 _done/ 으로 옮긴다. upsert 실패면 inbox 에 남아 재시도된다).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from rra.application.ports import (
    AcknowledgingSource,
    DocumentRepository,
    PublicIpPort,
    SourceAvailabilityPort,
    SourcePort,
    WarningSource,
)
from rra.domain.models import Chunk, Document
from rra.domain.rules.dedup import dedup, should_replace
from rra.domain.rules.overlap import SOURCE_LABELS, OwnUnit, unlisted_department
from rra.domain.rules.source_ip import SourceIpBlocked, unregistered_notice
from rra.domain.services.chunking import chunk_document

logger = logging.getLogger("rra.ingest")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
MAX_DETAIL_CHARS = 40


def _safe(text: str) -> str:
    return " ".join(_CONTROL.sub(" ", str(text)).split())[:MAX_DETAIL_CHARS]


@dataclass(frozen=True)
class IngestWarning:
    code: str  # unlisted_department | assumed_org | (소스가 정한 코드)
    doc_id: str
    detail: str  # 부서명·기관 태그 등 짧은 값 (제어문자 제거, 40자)


@dataclass(frozen=True)
class IngestReport:
    fetched: dict[str, int] = field(default_factory=dict)
    normalized: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)
    # IP 거부로 건너뛴 소스 → 안내 문구 (failed 에도 예외 클래스명이 남는다)
    unavailable: dict[str, str] = field(default_factory=dict)
    deduped: int = 0  # dedup 으로 빠진 문서 수 (전 소스 합계)
    kept_existing: int = 0  # 저장본이 더 나은 근거(원문)라 덮어쓰지 않은 문서 수
    warnings: list[IngestWarning] = field(default_factory=list)  # 저장된 문서에 대한 경고
    stored: int = 0
    chunks: int = 0


class IngestSources:
    def __init__(
        self,
        sources: list[SourcePort],
        repo: DocumentRepository,
        *,
        limit: int = 200,
        chunk_max_chars: int = 1500,
        own: OwnUnit | None = None,
        public_ip: PublicIpPort | None = None,
        availability: SourceAvailabilityPort | None = None,
    ):
        self.sources, self.repo = sources, repo
        self.limit, self.chunk_max_chars = limit, chunk_max_chars
        self.own = own
        self.public_ip, self.availability = public_ip, availability

    async def __call__(self, query: str | None = None) -> IngestReport:
        fetched: dict[str, int] = {}
        normalized: dict[str, int] = {}
        skipped: dict[str, int] = {}
        failed: dict[str, str] = {}
        unavailable: dict[str, str] = {}
        docs: list[Document] = []
        origin: dict[int, SourcePort] = {}  # id(doc) → 그 문서를 만든 소스 (경고용)
        accepted: list[tuple[SourcePort, list[dict[str, Any]]]] = []
        current_ip: str | None = None

        for source in self.sources:
            name = source.source
            try:
                raws = await source.search(query, self.limit)
            except SourceIpBlocked as exc:  # IP 거부 — 이 소스만 건너뛰고 안내를 남긴다 (레인 I)
                failed[name] = type(exc).__name__
                current_ip = current_ip or await self._current_ip()
                notice = unregistered_notice(current_ip, SOURCE_LABELS.get(name, name))
                unavailable[name] = notice
                logger.warning("ingest.ip_blocked source=%s %s", name, notice)
                self._record(name, notice)
                continue
            except Exception as exc:  # 소스 격리
                failed[name] = type(exc).__name__
                continue
            self._record(name, None)
            fetched[name] = len(raws)
            ok_raws: list[dict[str, Any]] = []
            for raw in raws:
                try:
                    doc = source.normalize(raw)
                except ValueError:  # pydantic ValidationError 포함
                    continue
                docs.append(doc)
                origin[id(doc)] = source
                ok_raws.append(raw)
            ok = len(ok_raws)
            accepted.append((source, ok_raws))
            normalized[name] = ok
            skipped[name] = len(raws) - ok

        deduped = dedup(docs)
        unique = [d for d in deduped if should_replace(await self.repo.get_document(d.doc_id), d)]
        warnings = self._warnings(unique, origin)
        chunks: list[Chunk] = [
            c for d in unique for c in chunk_document(d, max_chars=self.chunk_max_chars)
        ]
        if unique:
            await self.repo.upsert(unique, chunks)

        for source, ok_raws in accepted:
            if ok_raws and isinstance(source, AcknowledgingSource):
                try:
                    source.acknowledge(ok_raws)
                except Exception as exc:  # 통보 실패는 다음 실행에서 재처리될 뿐
                    failed.setdefault(source.source, type(exc).__name__)

        return IngestReport(
            fetched=fetched,
            normalized=normalized,
            skipped=skipped,
            failed=failed,
            unavailable=unavailable,
            deduped=len(docs) - len(deduped),
            kept_existing=len(deduped) - len(unique),
            warnings=warnings,
            stored=len(unique),
            chunks=len(chunks),
        )

    async def _current_ip(self) -> str | None:
        """안내 문구용 공인 IP — 조회 실패는 None (문구에 "(확인 실패)")."""
        if self.public_ip is None:
            return None
        try:
            return await self.public_ip.current_ip()
        except Exception as exc:
            logger.warning("ingest.public_ip_lookup_failed err=%s", type(exc).__name__)
            return None
        finally:
            await self.public_ip.aclose()

    def _record(self, source: str, notice: str | None) -> None:
        if self.availability is None:
            return
        try:
            self.availability.record(source, notice)
        except Exception as exc:  # 상태 기록 실패가 적재를 막지 않는다
            logger.warning("ingest.availability_failed err=%s", type(exc).__name__)

    def _warnings(self, docs: list[Document], origin: dict[int, SourcePort]) -> list[IngestWarning]:
        out: list[IngestWarning] = []
        for d in docs:
            found: list[tuple[str, str]] = []
            source = origin.get(id(d))
            if isinstance(source, WarningSource):
                try:
                    found.extend(source.ingest_warnings(d))
                except Exception as exc:  # 경고 수집 실패가 적재를 막지 않는다
                    logger.warning("ingest.warning_failed error=%s", type(exc).__name__)
            if self.own is not None and (dept := unlisted_department(d, self.own)):
                found.append(("unlisted_department", dept))
            for code, detail in found:
                w = IngestWarning(code=_safe(code), doc_id=d.doc_id, detail=_safe(detail))
                logger.warning("ingest.%s doc=%s detail=%s", w.code, w.doc_id, w.detail)
                out.append(w)
        return out
