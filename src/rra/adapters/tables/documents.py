"""저장소 문서 본문 → 본문 줄 표 (molit 등 스냅샷이 없는 자료원).

문서 body 의 줄을 그대로 넘기고 규칙(`facts_from_lines`)이 정렬된 숫자 줄만 사실로 본다. 쪽 번호는
없다.
"""

from __future__ import annotations

import re

from rra.application.ports.table_facts import CorpusAccessPort
from rra.domain.models import ParsedTable

_DIGIT = re.compile(r"\d")
MAX_LINES = 20_000


class DocumentTables:
    def __init__(self, repo: CorpusAccessPort, *, source: str):
        self.repo, self.name = repo, source

    async def tables(self, *, limit: int | None = None) -> list[ParsedTable]:
        out: list[ParsedTable] = []
        for doc in await self.repo.documents_of(self.name, limit=limit):
            body = doc.body or ""
            if not _DIGIT.search(body):
                continue
            lines = [ln for ln in body.splitlines() if ln.strip()][:MAX_LINES]
            out.append(ParsedTable(doc_id=doc.doc_id, lines=lines, title=doc.title[:300]))
        return out
