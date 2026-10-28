"""자료 분류 이주 (`rra db reclassify`, 2026-10-28 레인 B, ADR 0040).

이미 적재된 행을 domain/rules/doc_category 규칙으로 다시 판정해 doc_type·raw.doc_class 를
바로잡는다.
- 공사 홈페이지 사전정보공표 연구용역 → doc_type procurement + doc_class research_service
  (유사과제 판정·선행연구에는 남고 정책 근거 추천에서는 빠진다).
- 행정 공시·사업 현황 → doc_type 그대로, category 만.
- 다른 자료원(국토부·감사원·기재부·R&D 공고·사내·알리오·실시간 검색 행)은 규칙대로 점검만 하고
바뀌는
  것이 있을 때만 쓴다.
본문·청크·벡터는 건드리지 않는다(재색인 없음). dry_run 이면 집계만.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from rra.application.ports.maintenance import DocumentReclassifyPort
from rra.domain.rules.doc_category import CLASS_KEY, classify, is_policy_basis

# 점검하는 자료원 — 정책 근거 자료원 + 사내·알리오 + 실시간 검색이 저장하는 자료원
AUDIT_SOURCES: tuple[str, ...] = (
    "korail_web",
    "molit",
    "bai",
    "mofe",
    "rnd_notice",
    "own",
    "alio",
    "datago",
    "scienceon",
    "ntis",
    "openalex",
)
READ_LIMIT = 1_000_000


def _key(doc_type: str, category: str | None) -> str:
    return f"{doc_type}/{category}" if category else doc_type


@dataclass
class SourceReport:
    source: str
    total: int = 0
    changed: int = 0
    live: int = 0  # 실시간 검색으로 저장된 행 (raw.live)
    before: Counter[str] = field(default_factory=Counter)
    after: Counter[str] = field(default_factory=Counter)
    policy_basis_before: int = 0
    policy_basis_after: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "total": self.total,
            "changed": self.changed,
            "live": self.live,
            "before": dict(sorted(self.before.items())),
            "after": dict(sorted(self.after.items())),
            "policy_basis_before": self.policy_basis_before,
            "policy_basis_after": self.policy_basis_after,
        }


@dataclass
class ReclassifyReport:
    dry_run: bool
    sources: list[SourceReport] = field(default_factory=list)
    written: int = 0

    @property
    def changed(self) -> int:
        return sum(s.changed for s in self.sources)

    def as_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "changed": self.changed,
            "written": self.written,
            "sources": [s.as_dict() for s in self.sources],
        }


class ReclassifyDocuments:
    def __init__(self, repo: DocumentReclassifyPort, *, sources: Sequence[str] = AUDIT_SOURCES):
        self.repo = repo
        self.sources = tuple(sources)

    async def __call__(self, *, dry_run: bool = True) -> ReclassifyReport:
        report = ReclassifyReport(dry_run=dry_run)
        changes: list[tuple[str, str, dict[str, Any]]] = []
        for source in self.sources:
            rep = SourceReport(source=source)
            for doc in await self.repo.documents_of(source, limit=READ_LIMIT):
                rep.total += 1
                rep.live += 1 if doc.raw.get("live") else 0
                stored_cat = doc.raw.get(CLASS_KEY)
                rep.before[_key(doc.doc_type, stored_cat)] += 1
                rep.policy_basis_before += int(
                    doc.doc_type in ("policy", "rnd_notice", "audit")
                    and source in ("korail_web", "molit", "rnd_notice", "bai", "mofe")
                )
                doc_type, category = classify(doc)
                raw = dict(doc.raw)
                if category and source == "korail_web":
                    raw[CLASS_KEY] = category
                rep.after[_key(doc_type, raw.get(CLASS_KEY))] += 1
                fixed = doc.model_copy(update={"doc_type": doc_type, "raw": raw})
                rep.policy_basis_after += int(is_policy_basis(fixed))
                if doc_type != doc.doc_type or raw != doc.raw:
                    rep.changed += 1
                    changes.append((doc.doc_id, doc_type, raw))
            report.sources.append(rep)
        if not dry_run and changes:
            report.written = await self.repo.reclassify(changes)
        return report
