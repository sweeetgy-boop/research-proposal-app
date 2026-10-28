"""근거 구성 규칙(config/retrieval_mix.yaml) — 섹션별 허용 doc_type, 논문·보고서·특허 최소 보장,
유사과제 판정 제외.

순수 규칙. 청크에는 doc_type 이 없으므로 호출자가 {doc_id: doc_type} 을 함께 준다(스냅샷
`doc_types`). doc_type 을 모르는 청크는 거르지 않는다(옛 스냅샷·가짜 저장소). 걸러서 0건이면
전부로 되돌린다 — 근거를 비우는 쪽보다 넓게 주는 쪽이 되돌리기 쉽다.

예외 둘(2026-10-29 레인 D, ADR 0046):
- ``only_in``: 이 doc_type 은 적힌 섹션에서만 근거가 된다 — 0건 되돌리기(전부)에서도 빠진다.
  행정 공시·사업 현황·통계는 필요성·현황 섹션에서만.
- ``strict`` 섹션: 0건이어도 전부로 되돌리지 않는다 — 2-가-(3) 경영전략 정합성은 정책·전략 문서만.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field

from rra.domain.models import Chunk
from rra.domain.rules.overlap_candidates import OverlapCandidateRule

DEFAULT_SCHOLARLY = ("paper", "report", "patent")


class SectionMix(BaseModel):
    model_config = ConfigDict(frozen=True)

    allow: tuple[str, ...] = ()  # 비면 전부
    min_scholarly: int = Field(default=0, ge=0)
    strict: bool = False  # 참이면 걸러서 0건이어도 전부로 되돌리지 않는다(빈 근거)


class RetrievalMix(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_per_source: int = Field(default=6, ge=0)
    section_min_per_source: int = Field(default=2, ge=0)
    scholarly: tuple[str, ...] = DEFAULT_SCHOLARLY
    sections: dict[str, SectionMix] = Field(default_factory=dict)
    overlap_exclude: tuple[str, ...] = ()
    # doc_type → 그 doc_type 을 근거로 쓸 수 있는 섹션.
    # 여기 없는 섹션에는 되돌리기에서도 주지 않는다.
    only_in: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    # 유사과제 판정 후보 자료원(config/overlap.yaml candidates, ADR 0028). None 이면 doc_type
    # 제외만.
    candidates: OverlapCandidateRule | None = None

    def scoped_out(self, section: str, doc_type: str | None) -> bool:
        """only_in 규칙으로 이 섹션에서는 쓸 수 없는 doc_type 인가."""
        if doc_type is None or doc_type not in self.only_in:
            return False
        return section not in self.only_in[doc_type]

    def allowed(self, section: str, doc_type: str | None) -> bool:
        if self.scoped_out(section, doc_type):
            return False
        mix = self.sections.get(section)
        if mix is None or not mix.allow or doc_type is None:
            return True
        return doc_type in mix.allow

    def filter(
        self, section: str, chunks: Iterable[Chunk], doc_types: Mapping[str, str]
    ) -> list[Chunk]:
        """섹션에 허용된 doc_type 의 청크만. 유사과제 보탬 청크(#overlap)는 항상 남긴다. 0건이면
        전부 — 단 only_in 으로 이 섹션에서 못 쓰는 doc_type 은 빼고, strict 섹션은 되돌리지
        않는다. strict 섹션은 유사과제 보탬 청크도 허용 doc_type 일 때만 남긴다(2-가-(3) 에
        연구용역·과제 요약이 섞이지 않게)."""
        items = list(chunks)
        mix = self.sections.get(section)
        strict = mix is not None and mix.strict
        kept = [
            c
            for c in items
            if (c.chunk_id.endswith("#overlap") and not strict)
            or self.allowed(section, doc_types.get(c.doc_id))
        ]
        if kept or strict:
            return kept
        return [c for c in items if not self.scoped_out(section, doc_types.get(c.doc_id))]

    def is_scholarly(self, doc_type: str | None) -> bool:
        return doc_type in self.scholarly

    def scholarly_shortfall(
        self, section: str, chunks: Iterable[Chunk], doc_types: Mapping[str, str]
    ) -> int:
        """섹션의 min_scholarly 에 모자라는 논문·보고서·특허 청크 수(0 이면 충족)."""
        mix = self.sections.get(section)
        if mix is None or mix.min_scholarly <= 0:
            return 0
        have = sum(1 for c in chunks if self.is_scholarly(doc_types.get(c.doc_id)))
        return max(0, mix.min_scholarly - have)

    def top_up_scholarly(
        self,
        section: str,
        picked: list[Chunk],
        pool: Iterable[Chunk],
        doc_types: Mapping[str, str],
    ) -> list[Chunk]:
        """모자라는 만큼 pool(순위 순)에서 논문·보고서·특허 청크를 뒤에 보탠다."""
        need = self.scholarly_shortfall(section, picked, doc_types)
        if need <= 0:
            return picked
        have = {c.chunk_id for c in picked}
        extra: list[Chunk] = []
        for c in pool:
            if c.chunk_id in have or not self.is_scholarly(doc_types.get(c.doc_id)):
                continue
            extra.append(c)
            if len(extra) >= need:
                break
        return [*picked, *extra]

    def overlap_candidates(self, hits, doc_type_of) -> list:
        """유사과제 판정에서 뺄 doc_type 의 문서를 거르고, candidates 규칙이 있으면 과제형 자료원만
        남긴 (문서, 유사도) 목록."""
        kept = list(hits)
        if self.overlap_exclude:
            kept = [(d, s) for d, s in kept if doc_type_of(d) not in self.overlap_exclude]
        if self.candidates is not None:
            kept = self.candidates.project_hits(kept)
        return kept
