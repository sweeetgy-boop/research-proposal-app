"""② NTIS 부가 조회 — 유사과제 알림의 NTIS 과제(상위 3건)별 주요 성과(참고용) + 연관 과제 추천(교차

확인).

- 호출 전 캐시(과제번호 기준, CachePort)를 본다. 없을 때만 API — 간격 제한은
  GuardedClient(sources.yaml ntis.rate_limit).
- 한 과제 조회가 실패해도 나머지는 계속한다. 실패는 예외 클래스명만 남긴다 (키·URL 없음).
- 추천에서 우리 검색에 이미 있는 과제(알림 목록·저장소에 있는 doc_id)는 뺀다.
- 결과는 전부 비신뢰(API 출력). 양식 본문 근거로 쓰지 않는다 — 화면 카드 표시용.
"""

from __future__ import annotations

import logging
from typing import Any

from rra.application.ports import (
    CachePort,
    DocumentRepository,
    ProjectOutcomePort,
    RelatedProjectPort,
)
from rra.domain.models import OverlapAlert
from rra.domain.rules.ntis_insights import (
    MAX_PROJECTS,
    NtisInsights,
    ProjectInsight,
    merge_recommended,
    project_no_of,
    target_projects,
    validate_outcomes,
    validate_related,
)

logger = logging.getLogger("rra.ntis_insights")


class NtisProjectInsights:
    def __init__(
        self,
        outcomes: ProjectOutcomePort | None,
        related: RelatedProjectPort | None,
        *,
        cache: CachePort | None = None,
        repo: DocumentRepository | None = None,
        max_projects: int = MAX_PROJECTS,
    ):
        self.outcomes, self.related, self.cache, self.repo = outcomes, related, cache, repo
        self.max_projects = max_projects

    @property
    def enabled(self) -> bool:
        return self.outcomes is not None or self.related is not None

    async def __call__(self, alerts: list[OverlapAlert]) -> NtisInsights:
        targets = target_projects(alerts, self.max_projects)
        known = {no for a in alerts if (no := project_no_of(a.doc_id))}
        projects: list[ProjectInsight] = []
        groups = []
        for a in targets:
            no = project_no_of(a.doc_id) or ""
            raw_out, cached, error = await self._cached(
                f"outcomes:{no}", self.outcomes, "outcomes", no
            )
            raw_rel, cached_rel, error_rel = await self._cached(
                f"related:{no}", self.related, "related", no
            )
            projects.append(
                ProjectInsight(
                    project_no=no,
                    doc_id=a.doc_id,
                    title=a.title,
                    tier=a.tier,
                    similarity=a.similarity,
                    blocking=a.blocking,
                    outcomes=validate_outcomes(raw_out),
                    cached=cached and cached_rel,
                    error=error or error_rel,
                )
            )
            groups.append(validate_related(raw_rel, source_project_no=no, known=known))
        recommended = merge_recommended(groups)
        if self.repo is not None and recommended:
            kept = []
            for r in recommended:
                if await self.repo.get_document(f"ntis:{r.project_no}") is None:
                    kept.append(r)
            recommended = kept
        return NtisInsights(projects=projects, recommended=recommended)

    async def _cached(
        self, key: str, port: Any, method: str, project_no: str
    ) -> tuple[list[dict[str, Any]], bool, str | None]:
        if port is None:
            return [], True, None
        if self.cache is not None:
            hit = self.cache.get(key)
            if isinstance(hit, list):
                return hit, True, None
        try:
            items = await getattr(port, method)(project_no)
        except Exception as exc:  # 한 과제 실패는 나머지를 막지 않는다
            logger.warning(
                "ntis_insights.%s_failed project=%s err=%s", method, project_no, type(exc).__name__
            )
            return [], False, type(exc).__name__
        items = [i for i in items if isinstance(i, dict)]
        if self.cache is not None:
            self.cache.set(key, items)
        return items, False, None
