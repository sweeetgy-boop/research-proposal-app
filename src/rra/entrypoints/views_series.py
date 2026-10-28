"""② 같은 연작 묶음 직렬화 (2026-10-29 레인 A, ADR 0043). 규칙은 domain/rules/series.

프런트엔드 영향: ② 유사과제 표의 행 ``series`` —
``{label, count, display: "광역철도 수송수요 예측(연작 7건)", members: [{title, year, doc_id,
source, source_label, url, summary, refs: [{doc_id, title, source, source_label, url}]}]}`` 또는
null.
화면은 doc_id 를 보이지 않는다(근거 패널을 여는 데만 쓴다). 제목·요약은 비신뢰 텍스트.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rra.domain.rules.doc_refs import doc_ref
from rra.domain.rules.series import series_display


def _same(text: str) -> str:
    return text


def series_payload(series: Any, *, clean: Callable[[str], str] = _same) -> dict[str, Any] | None:
    if series is None:
        return None
    label = clean(series.label)
    members = []
    for m in series.members:
        title = clean(m.title)
        refs = [
            doc_ref(d.doc_id, title, source=d.source, url=d.url, visibility=d.visibility)
            for d in m.docs
        ]
        if not refs:
            continue
        names = list(dict.fromkeys(r["source_label"] for r in refs))
        url = next((r["url"] for r in refs if r["url"]), None)
        members.append(
            {
                "title": title,
                "year": m.year,
                "doc_id": refs[0]["doc_id"],
                "source": refs[0]["source"],
                "source_label": " · ".join(names),
                "url": url,
                "summary": clean(m.summary) if m.summary else None,
                "refs": refs,
            }
        )
    return {
        "label": label,
        "count": series.count,
        "display": series_display(label, series.count),
        "members": members,
    }
