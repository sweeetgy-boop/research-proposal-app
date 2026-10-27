"""데이터셋 상세 페이지 해석 (순수, 정규식) — fn_fileDataDown 인자와 메타."""

from __future__ import annotations

import html as htmllib
import re
from dataclasses import dataclass

_DOWN = re.compile(
    r"fn_fileDataDown\(\s*'(\d+)'\s*,\s*'([^']+)'\s*,\s*'([^']*)'\s*,\s*'(\d+)'\s*,\s*'(\d+)'\s*\)"
)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class DatasetPage:
    public_data_pk: str
    detail_pk: str
    file_sn: str
    hist_sn: str
    title: str
    institution: str | None
    updated: str | None
    description: str | None
    ext: str | None
    cycle: str | None
    rows: int | None


def _text(html: str) -> str:
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
    return _WS.sub(" ", htmllib.unescape(_TAG.sub(" ", body))).strip()


def _after(text: str, label: str, limit: int = 200, start: int = 0) -> str | None:
    i = text.find(label, start)
    if i < 0:
        return None
    return text[i + len(label) : i + len(label) + limit].strip()


def _field(text: str, label: str, stops: tuple[str, ...], start: int = 0) -> str | None:
    """`start` 이후의 첫 label.

    안내문("제공기관의 관리부서 전화번호로…")이 메타 표보다 앞에 있어서 시작 위치를 받는다."""
    seg = _after(text, label, start=start)
    if seg is None:
        return None
    cut = len(seg)
    for s in stops:
        j = seg.find(s)
        if 0 <= j < cut:
            cut = j
    return seg[:cut].strip() or None


def parse_dataset_page(html: str) -> DatasetPage | None:
    m = _DOWN.search(html)
    if not m:
        return None
    t = _text(html)
    base = max(t.find("파일데이터명"), 0)  # 메타 표 시작 — 그 앞의 안내문은 무시
    title = _field(t, "파일데이터명", ("분류체계",), base) or ""
    updated = _field(t, "수정일", ("기타",), base)
    um = _DATE.search(updated or "")
    rows_s = _field(t, "전체 행", ("키워드",), base)
    rows = int(re.sub(r"[^\d]", "", rows_s)) if rows_s and re.search(r"\d", rows_s) else None
    return DatasetPage(
        public_data_pk=m.group(1),
        detail_pk=m.group(2),
        file_sn=m.group(4),
        hist_sn=m.group(5),
        title=title[:300],
        institution=_field(t, "제공기관", ("관리부서명", "관리부서"), base),
        updated=um.group(0) if um else None,
        description=(_field(t, "설명", ("데이터 항목(컬럼) 정보",), base) or None),
        ext=_field(t, "확장자", ("전체 행", "키워드"), base),
        cycle=_field(t, "업데이트 주기", ("차기",), base),
        rows=rows,
    )
