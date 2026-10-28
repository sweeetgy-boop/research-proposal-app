"""문서 표시 직렬화 — doc_id 를 내보내는 뷰마다 제목·자료원 이름(한국어)·원문 링크를 함께 싣는다
(2026-10-28 레인 B, ADR 0040). 규칙은 domain/rules/doc_refs.

프런트엔드 영향: web/src/lib/docRefs.ts 의 ``docRef``/``replaceDocIds`` 와 web/src/components/DocRef.tsx 가
이 모양({doc_id, title, source, source_label, url})을 쓴다. 화면은 doc_id 를 그대로 보이지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from rra.domain.rules.doc_refs import doc_ref, replace_internal_ids


def _same(text: str) -> str:
    return text


def citation_ref(c: Any, *, clean: Callable[[str], str] = _same, live: bool = False) -> dict:
    """RunManager.Citation → {id, doc_id, title, source, source_label, url, live}."""
    ref = doc_ref(
        c.doc_id,
        clean(c.title) if getattr(c, "title", None) else None,
        source=getattr(c, "source", None),
        url=getattr(c, "url", None),
        visibility=getattr(c, "visibility", None),
    )
    return {"id": c.id, **ref, "live": live}


def titles_from(citations: Iterable[Any]) -> dict[str, str]:
    """근거 id(chunk_id·doc_id) → 제목. 제목이 없는 것은 뺀다."""
    out: dict[str, str] = {}
    for c in citations:
        title = getattr(c, "title", None) or (c.get("title") if isinstance(c, Mapping) else None)
        if not title:
            continue
        cid = getattr(c, "id", None) or (c.get("id") if isinstance(c, Mapping) else None)
        did = getattr(c, "doc_id", None) or (c.get("doc_id") if isinstance(c, Mapping) else None)
        for k in (cid, did):
            if k:
                out.setdefault(str(k), str(title))
    return out


def no_ids(
    text: str | None,
    titles: Mapping[str, str] | None = None,
    section_titles: Mapping[str, str] | None = None,
) -> str:
    """화면 글에서 내부 번호를 「제목」 또는 일반 말로 바꾼다 (비신뢰 텍스트 정리 뒤)."""
    return replace_internal_ids(text or "", titles, section_titles=section_titles)


def refs_for(ids: Iterable[str], citations: Iterable[Any]) -> list[dict[str, Any]]:
    """근거 id 목록 → 표시 정보 목록 (모르는 id 는 자료원 이름만)."""
    by_id: dict[str, Any] = {}
    for c in citations:
        by_id.setdefault(c.id, c)
        by_id.setdefault(c.doc_id, c)
    out = []
    for i in ids:
        c = by_id.get(i) or by_id.get(i.split("#", 1)[0])
        if c is not None:
            out.append({"id": i, **citation_ref(c)})
        else:
            out.append({"id": i, **doc_ref(i.split("#", 1)[0], None)})
    return out
