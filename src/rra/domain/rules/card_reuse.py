"""문제 정의 카드 재사용·고정 규칙 (ADR 0065, 계약 problem-card.md 4.4절). 순수 함수.

- 공용 캐시 키 = 입력 글(가제·현황·원인·한계·목표를 정규화) + 진단 지시문 지문 + 모델 이름.
  지시문이나 모델이 바뀌면 키가 달라져 옛 카드를 다시 쓰지 않는다.
- 고정 키 = 사용자 가명 ID + 입력 글 해시. 다른 사용자의 키와 같아질 수 없다(사용자별 격리).
- 공용 계정(guest)은 여러 사람이 함께 쓰므로 고정하지 않는다.

이 키들은 **입력 글 기준**이다 — 유추 검색의 세션·메모 키(실제로 보낸 질의 지문, 계약 4.1절)와
별개이며 서로 영향을 주지 않는다. 키에는 원문이 남지 않는다(sha256).
"""

from __future__ import annotations

import hashlib
from typing import Literal

from rra.domain.models import Principal, ProposalRequest
from rra.domain.models.problem_card import ProblemCard
from rra.domain.rules.live_search import normalize_query

KEY_VERSION = "card-reuse-v1"
INPUT_FIELDS = ("title_hint", "current_state", "root_cause", "limitation", "goal")
ReuseKind = Literal["pinned", "cached"]
REUSE_PINNED: ReuseKind = "pinned"
REUSE_CACHED: ReuseKind = "cached"


def _sha(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def text_hash(req: ProposalRequest) -> str:
    """입력 글의 해시 — 칸 순서 고정, 칸마다 정규화(NFKC·소문자·공백 하나로)."""
    return _sha(KEY_VERSION, *(normalize_query(getattr(req, k) or "") for k in INPUT_FIELDS))


def prompt_version(prompt_text: str, model: str) -> str:
    """진단 지시문 지문 + 모델 이름 — 둘 중 하나가 바뀌면 공용 캐시 키가 바뀐다."""
    return f"{_sha(prompt_text)[:16]}:{model}"


def cache_key(req: ProposalRequest, version: str) -> str:
    return _sha("cache", text_hash(req), version)


def pin_key(user: str, req: ProposalRequest) -> str:
    return _sha("pin", user, text_hash(req))


def can_pin(principal: Principal | None) -> bool:
    """고정할 수 있는 사용자인가 — 로그인 없음·공용 계정은 고정하지 않는다."""
    return principal is not None and principal.kind != "guest"


def load_card(value: object) -> ProblemCard | None:
    """저장한 값 → 카드. 모양이 맞지 않으면(옛 판·손상) 없는 것으로 본다."""
    if not isinstance(value, dict):
        return None
    try:
        return ProblemCard.model_validate(value)
    except ValueError:
        return None
