"""xlsx·xls 워커 결과({"sheets": [{"name", "rows"}]})를 본문 텍스트로 — 순수 함수.

korail_web 첨부 스프레드시트(광역수송 통계·사전정보 표 등)는 워커가 시트 구조만 돌려줘
`ExtractResult.text` 가 없어 적재되지 않았다(2026-10-27 레인 F 발견). 시트마다 `[시트 이름]` 줄,
행은 셀을 " | " 로 잇는다(datago 와 같은 꼴 — table_facts 의 줄 표 규칙이 읽는다). 빈 행은 건너뛰고
시트당 행 수·전체 글자 수에 상한을 둔다.
"""

from __future__ import annotations

from typing import Any

MAX_ROWS_PER_SHEET = 400
MAX_CHARS = 200_000


def sheets_to_text(
    raw: Any, *, max_rows: int = MAX_ROWS_PER_SHEET, max_chars: int = MAX_CHARS
) -> str | None:
    """워커 결과에 `sheets` 가 있으면 텍스트, 아니면 None (호출자는 그대로 둔다)."""
    if not isinstance(raw, dict) or not isinstance(raw.get("sheets"), list):
        return None
    out: list[str] = []
    size = 0
    for sheet in raw["sheets"]:
        if not isinstance(sheet, dict):
            continue
        name = str(sheet.get("name") or "").strip()
        rows = sheet.get("rows") or []
        lines = [f"[{name}]"] if name else []
        for row in rows[:max_rows]:
            if not isinstance(row, list):
                continue
            cells = ["" if c is None else str(c).strip() for c in row]
            if not any(cells):
                continue
            lines.append(" | ".join(cells).rstrip(" |"))
        if len(lines) <= (1 if name else 0):
            continue
        block = "\n".join(lines)
        if size + len(block) > max_chars:
            out.append(block[: max(0, max_chars - size)])
            break
        out.append(block)
        size += len(block) + 2
    text = "\n\n".join(out).strip()
    return text or None
