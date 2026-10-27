"""표 → 사실 적재 (P2-8). 적재(ingest) 뒤에 돈다 — 문서 doc_id 는 자료원 어댑터와 같은 규칙으로
만든다.

- TableSourcePort 가 낸 표마다 `table_to_facts`(순수) → 문서별로 모아 `replace_facts`(통째 교체,
  멱등).
- 문서가 아직 저장소에 없으면(missing_doc) 사실은 그대로 넣고 건수·id 를 보고한다 — 수치 lint 는
  검색 집합에 든 문서의 사실만 쓰므로 해가 없고, 나중에 문서가 적재되면 바로 연결된다.
- dry_run 이면 저장하지 않고 건수만.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rra.application.ports import DocumentRepository
from rra.application.ports.table_facts import TableFactRepository, TableSourcePort
from rra.domain.models import TableFact
from rra.domain.rules.table_facts import table_to_facts

MAX_REPORTED_IDS = 20


@dataclass
class FactsReport:
    source: str
    tables: int = 0
    facts: int = 0
    documents: int = 0
    empty_tables: int = 0
    missing_docs: list[str] = field(default_factory=list)
    by_basis: dict[str, int] = field(default_factory=dict)
    dry_run: bool = False
    samples: list[TableFact] = field(default_factory=list)  # 화면·CLI 확인용 앞쪽 몇 건

    def summary(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "dry_run": self.dry_run,
            "tables": self.tables,
            "facts": self.facts,
            "documents": self.documents,
            "empty_tables": self.empty_tables,
            "missing_docs": len(self.missing_docs),
            "missing_doc_ids": self.missing_docs[:MAX_REPORTED_IDS],
            "by_basis": dict(self.by_basis),
        }


class ExtractTableFacts:
    def __init__(
        self,
        source: TableSourcePort,
        facts: TableFactRepository,
        docs: DocumentRepository,
        *,
        sample_size: int = 5,
    ):
        self.source, self.facts, self.docs, self.sample_size = source, facts, docs, sample_size

    async def __call__(self, *, dry_run: bool = False, limit: int | None = None) -> FactsReport:
        report = FactsReport(source=self.source.name, dry_run=dry_run)
        per_doc: dict[str, list[TableFact]] = {}
        for table in await self.source.tables(limit=limit):
            report.tables += 1
            found = table_to_facts(table)
            if not found:
                report.empty_tables += 1
                continue
            per_doc.setdefault(table.doc_id, []).extend(found)
        for doc_id, facts in per_doc.items():
            facts = _dedupe(facts)
            report.documents += 1
            report.facts += len(facts)
            for f in facts:
                report.by_basis[f.basis] = report.by_basis.get(f.basis, 0) + 1
            if len(report.samples) < self.sample_size:
                report.samples.extend(facts[: self.sample_size - len(report.samples)])
            if await self.docs.get_document(doc_id) is None:
                report.missing_docs.append(doc_id)
            if not dry_run:
                await self.facts.replace_facts(doc_id, facts)
        return report


def _dedupe(facts: list[TableFact]) -> list[TableFact]:
    seen: set[tuple[Any, ...]] = set()
    out: list[TableFact] = []
    for f in facts:
        key = (f.item, f.year, f.unit, f.value, f.page, f.sheet)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out
