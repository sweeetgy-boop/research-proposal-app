"""E. SQL 안전 — 사용자 문자열이 SQL 문법에 닿는 유일한 지점.

- FTS5 MATCH 입력은 여기서만 만든다 (`quote_fts_query`).
- k·질의 길이·질의 개수 상한도 여기서 강제한다.
- 문자열로 SQL 조각을 만드는 함수는 `placeholders()` 하나뿐이고 정수만 받는다.
"""

from __future__ import annotations

import re

MAX_K = 100
MAX_QUERIES = 8
MAX_QUERY_CHARS = 500  # config/security.yaml: input_limits.query_max_chars
MAX_FTS_TOKENS = 32

# \w 는 한글 음절·CJK·라틴·숫자를 포함하고, FTS5 연산자 문자(" * : ^ ( ) - + . , 등)는
# 전부 제외한다. 밑줄만 별도로 뺀다.
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def clamp_k(k: int, *, max_k: int = MAX_K) -> int:
    """벡터·FTS fetch 상한. DoS 방지."""
    if not isinstance(k, int) or isinstance(k, bool):
        raise TypeError("k must be an int")
    return max(1, min(k, max_k))


def clamp_query(text: str, *, max_chars: int = MAX_QUERY_CHARS) -> str:
    if not isinstance(text, str):
        raise TypeError("query must be a str")
    return text.strip()[:max_chars]


def clamp_queries(queries: list[str], *, max_queries: int = MAX_QUERIES, **kw: int) -> list[str]:
    out = [clamp_query(q, **kw) for q in queries[:max_queries]]
    return [q for q in out if q]


def fts_tokens(text: str, *, max_chars: int = MAX_QUERY_CHARS, max_tokens: int = MAX_FTS_TOKENS):
    """질의를 FTS5 토큰 후보로 분해. 연산자·구두점은 이 단계에서 사라진다."""
    seen: list[str] = []
    for tok in _TOKEN_RE.findall(clamp_query(text, max_chars=max_chars)):
        low = tok.lower()
        if low not in seen:
            seen.append(low)
        if len(seen) >= max_tokens:
            break
    return seen


def quote_fts_query(text: str, *, prefix: bool = True, **kw: int) -> str:
    """FTS5 MATCH 식을 만든다. 토큰이 없으면 빈 문자열(호출측이 SQL을 실행하지 않음).

    각 토큰은 큰따옴표로 감싸 문자열 리터럴이 되므로 AND/OR/NEAR/NOT 같은 바리워드도
    연산자가 아니라 검색어로 취급된다. 내부 `"` 는 `""` 로 이스케이프(방어적 — 토크나이저가
    이미 제거하지만 토크나이저를 바꿔도 안전하도록 남겨 둔다).
    """
    tokens = fts_tokens(text, **kw)
    if not tokens:
        return ""
    star = "*" if prefix else ""
    return " OR ".join(f'"{t.replace(chr(34), chr(34) * 2)}"{star}' for t in tokens)


def placeholders(n: int) -> str:
    """`IN (?,?,?)` 용. 정수 개수만 받으므로 인젝션 경로가 없다."""
    if not isinstance(n, int) or isinstance(n, bool) or n < 1 or n > MAX_K * 4:
        raise ValueError(f"invalid placeholder count: {n!r}")
    return ",".join("?" * n)
