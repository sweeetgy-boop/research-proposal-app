"""유사과제 판정 후보 = 과제형 자료원만 (2026-10-28, ADR 0028).

ScienceON 논문·보고서·특허 2,045건과 NTIS 연구보고서 1,084건을 적재한 뒤 골든셋 precheck 적중이
9/10 → 6/10 으로 떨어졌다(유사도 0.88~0.90 의 논문이 사내 기록을 밀어냄). 논문·보고서·특허는 "기수행
과제" 가 아니므로 판정·차단·근접 알림에서 빼고, 대신 `related_research`(관련 연구, 참고) 목록으로
따로 돌려준다.

목록은 코드가 아니라 `config/overlap.yaml candidates` 가 정한다 — 여기에는 규칙만 있고 기본값은
"제한 없음"(목록이 비면 옛 동작). 자료원 하나가 과제와 보고서를 함께 담으면(NTIS: rnd_project 과제 ·
report 연구보고서) `doc_types` 로 가른다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field

from rra.domain.models import Document, RelatedResearch


class SourceMember(BaseModel):
    """자료원 하나 (+ 그 안에서 허용하는 doc_type; 비면 그 자료원 전부)."""

    model_config = ConfigDict(frozen=True)

    source: str
    doc_types: tuple[str, ...] = ()

    def matches(self, doc: Document) -> bool:
        return doc.source == self.source and (not self.doc_types or doc.doc_type in self.doc_types)


class OverlapCandidateRule(BaseModel):
    """project: 판정·알림 후보 자료원. research: 관련 연구 목록 자료원. 둘 다 비면 제한 없음."""

    model_config = ConfigDict(frozen=True)

    project: tuple[SourceMember, ...] = ()
    research: tuple[SourceMember, ...] = ()
    research_k: int = Field(default=5, ge=0)
    # 판정 후보 풀: 자료원마다 상위 per_source 건을 먼저 넣고(NTIS 2,000건이 사내 기록 1,119건을
    # 밀어내지 않게), 나머지는 전체 순위로 pool_size 까지. per_source 0 이면 전체 순위만.
    per_source: int = Field(default=0, ge=0)
    pool_size: int = Field(default=30, ge=1)

    @property
    def restricts(self) -> bool:
        return bool(self.project)

    def is_project(self, doc: Document) -> bool:
        return not self.project or any(m.matches(doc) for m in self.project)

    def is_research(self, doc: Document) -> bool:
        return bool(self.research) and any(m.matches(doc) for m in self.research)

    def project_sources(self) -> list[str]:
        """저장소 검색 필터용 자료원 목록 (순서 유지, 중복 제거). 제한 없으면 빈 목록."""
        return _unique(m.source for m in self.project)

    def research_sources(self) -> list[str]:
        return _unique(m.source for m in self.research)

    def project_hits(self, hits: Iterable[tuple[Document, float]]) -> list[tuple[Document, float]]:
        """판정 후보만 (순서 유지). 자료원 필터로 받은 결과에서 doc_type 까지 다시 거른다."""
        return [(d, s) for d, s in hits if self.is_project(d)]

    def pool(
        self,
        by_source: Mapping[str, Iterable[tuple[Document, float]]],
        overall: Iterable[tuple[Document, float]],
        *,
        group: Callable[[Document], str] | None = None,
    ) -> list[tuple[Document, float]]:
        """자료원별 상위 per_source + 전체 순위 채움, 중복 없이 pool_size 건. 자료원 순서는 project
        순.

        group(문서 → 묶음 키, ADR 0043)을 주면 건수 대신 서로 다른 묶음(연작) 수를 센다 — 이미
        들어온 묶음의 다른 판은 상한과 관계없이 구성원으로 붙는다(새 묶음은 상한까지만)."""
        seen: set[str] = set()
        groups: set[str] = set()
        out: list[tuple[Document, float]] = []

        def size() -> int:
            return len(groups) if group is not None else len(out)

        def take(items: Iterable[tuple[Document, float]], limit: int) -> None:
            n = 0
            for d, s in items:
                if d.doc_id in seen or not self.is_project(d):
                    continue
                key = (group(d) or f"d:{d.doc_id}") if group is not None else ""
                if group is not None and key in groups:
                    seen.add(d.doc_id)
                    out.append((d, s))  # 이미 든 묶음의 구성원 — 상한을 쓰지 않는다
                    continue
                if n >= limit or size() >= self.pool_size:
                    if group is None:
                        return
                    continue
                seen.add(d.doc_id)
                if group is not None:
                    groups.add(key)
                out.append((d, s))
                n += 1

        for source in self.project_sources():
            take(by_source.get(source, ()), self.per_source)
        take(overall, self.pool_size)
        return out

    def related_research(self, hits: Iterable[tuple[Document, float]]) -> list[RelatedResearch]:
        """관련 연구 상위 research_k 건 (유사도 내림차순, 판정 아님)."""
        rows = [(d, s) for d, s in hits if self.is_research(d)]
        rows.sort(key=lambda ds: (-ds[1], ds[0].doc_id))
        return [
            RelatedResearch(
                doc_id=d.doc_id,
                title=d.title,
                source=d.source,
                doc_type=d.doc_type,
                year=d.pub_date.year if d.pub_date else None,
                similarity=s,
                url=d.url,
            )
            for d, s in rows[: self.research_k]
        ]


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in items:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out
