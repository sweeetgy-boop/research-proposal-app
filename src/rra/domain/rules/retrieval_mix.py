"""근거 구성 규칙(config/retrieval_mix.yaml) — 섹션별 허용 doc_type, 논문·보고서·특허 최소 보장,
유사과제 판정 제외.

순수 규칙. 청크에는 doc_type 이 없으므로 호출자가 {doc_id: doc_type} 을 함께 준다(스냅샷
`doc_types`). doc_type 을 모르는 청크는 거르지 않는다(옛 스냅샷·가짜 저장소). 걸러서 0건이면
전부로 되돌린다 — 근거를 비우는 쪽보다 넓게 주는 쪽이 되돌리기 쉽다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field

from rra.domain.models import Chunk

DEFAULT_SCHOLARLY = ("paper", "report", "patent")


class SectionMix(BaseModel):
    model_config = ConfigDict(frozen=True)

    allow: tuple[str, ...] = ()  # 비면 전부
    min_scholarly: int = Field(default=0, ge=0)


class RetrievalMix(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_per_source: int = Field(default=6, ge=0)
    section_min_per_source: int = Field(default=2, ge=0)
    scholarly: tuple[str, ...] = DEFAULT_SCHOLARLY
    sections: dict[str, SectionMix] = Field(default_factory=dict)
    overlap_exclude: tuple[str, ...] = ()

    def allowed(self, section: str, doc_type: str | None) -> bool:
        mix = self.sections.get(section)
        if mix is None or not mix.allow or doc_type is None:
            return True
        return doc_type in mix.allow

    def filter(
        self, section: str, chunks: Iterable[Chunk], doc_types: Mapping[str, str]
    ) -> list[Chunk]:
        """섹션에 허용된 doc_type 의 청크만. 유사과제 보탬 청크(#overlap)는 항상 남긴다. 0건이면
        전부."""
        items = list(chunks)
        kept = [
            c
            for c in items
            if c.chunk_id.endswith("#overlap") or self.allowed(section, doc_types.get(c.doc_id))
        ]
        return kept or items

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
        """유사과제 판정에서 뺄 doc_type 의 문서를 거른 (문서, 유사도) 목록."""
        if not self.overlap_exclude:
            return list(hits)
        return [(d, s) for d, s in hits if doc_type_of(d) not in self.overlap_exclude]
