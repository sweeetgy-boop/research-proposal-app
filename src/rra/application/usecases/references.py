"""참고 논문(reference) 읽기 — ProposalRequest.reference_ids → 문서 (ADR 0053).

차별화 활용 제안·과제안·비교표가 같은 규칙으로 읽는다. 저장소 포트의 get_document 만 쓴다.
- 없는 id·볼 수 없는 문서(공용 계정의 PublicOnlyRepository 가 internal 을 None 으로 돌려줌)는
  오류 없이 뺀다.
- include_internal=False(외부 전송 범위 정책)면 internal 문서는 보내지 않고 excluded 로 돌려준다.
- 실시간 검색(live) 문서는 precheck 때 public·raw.live 로 DB 에 저장되므로 같은 길로 읽힌다.
"""

from __future__ import annotations

from collections.abc import Iterable

from rra.application.ports import DocumentRepository
from rra.domain.models import Document
from rra.domain.rules.reference_papers import unique_references


async def load_references(
    repo: DocumentRepository,
    reference_ids: Iterable[str],
    *,
    exclude: Iterable[str] = (),
    include_internal: bool = True,
) -> tuple[list[Document], list[str]]:
    """(보낼 참고 문서 — 요청 순서, 전송 범위 정책으로 뺀 doc_id)."""
    docs: list[Document] = []
    excluded: list[str] = []
    for doc_id in unique_references(reference_ids, exclude):
        doc = await repo.get_document(doc_id)
        if doc is None:  # 없는 id·권한 밖 문서 — 조용히 뺀다
            continue
        if doc.visibility == "internal" and not include_internal:
            excluded.append(doc_id)
            continue
        docs.append(doc)
    return docs, excluded
