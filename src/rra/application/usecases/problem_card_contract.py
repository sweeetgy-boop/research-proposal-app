"""문제 정의 카드의 협력자 계약 (ADR 0065, docs/contracts/problem-card.md).

0단계에서만 고친다. 레인 A 가 진단·수정·기록을, 레인 B 가 KIPRIS 분류 검색(건수)을 구현하고
조립(composition)이 잇는다 — 레인끼리 서로의 모듈을 import 하지 않는다.

카드는 `ProposalRequest.problem_card` 로 다니므로 유추 검색(`novel_contract.AnalogySearch`)·
새 과제안·보완 질문의 호출 모양은 바뀌지 않는다. 카드가 None 이거나 설정이 꺼져 있으면 소비자는
종전 방식 그대로 돈다(안전망).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from rra.domain.models import Principal, ProposalRequest
from rra.domain.models.problem_card import CardField, CodeKind, CodeVerified, ProblemCard, Rerun

# ok: 카드 있음 / off: 설정 꺼짐(카드 없음) /
# failed: 진단 실패·시간 초과(카드 없음 — 종전 방식으로 진행)
DiagnoseStatus = Literal["ok", "off", "failed"]


@dataclass(frozen=True)
class DiagnoseOutcome:
    """진단 결과. card 가 None 이면 화면은 카드를 보이지 않고 그대로 진행한다.

    reason: 실패 사유 열거값(argon_first.REASON_LABELS 의 키 또는 "timeout") — 화면에는 한국어
      설명으로만. provider·model·fallback 은 다른 Argon 먼저 호출과 같은 뜻.
    examples: 지시문에 넣은 본인 수정 예시 수(다른 사용자 것은 넣지 않는다).
    """

    status: DiagnoseStatus
    card: ProblemCard | None = None
    reason: str | None = None
    provider: str | None = None
    model: str | None = None
    fallback: bool = False
    seconds: float = 0.0
    examples: int = 0


@runtime_checkable
class ProblemDiagnosis(Protocol):
    """[1단계] AI 1회 + [3단계] 규칙 검증 → 카드 한 장.

    previous: 화면이 갖고 있던 카드. 사용자가 고친 항목(origin=user)은 그대로 두고 나머지만
      새로 채운다. principal: 본인 수정 예시를 고를 때만 쓴다(없으면 예시 없음).
    """

    async def __call__(
        self,
        req: ProposalRequest,
        *,
        previous: ProblemCard | None = None,
        principal: Principal | None = None,
    ) -> DiagnoseOutcome: ...


@dataclass(frozen=True)
class CardEdit:
    """사용자 수정 한 건 — 항목 이름만(값은 함께 보낸 카드에 이미 반영돼 있다)."""

    field: CardField


@dataclass(frozen=True)
class EditOutcome:
    """수정 반영 결과.

    card: 고친 항목은 origin=user 로, 그 항목에 기대는 것만 다시 계산한 카드.
    reruns: 다시 계산했거나 화면·다음 요청이 다시 해야 하는 것(CARD_DEPENDENTS 의 합집합,
      순서 유지).
      plans_stale 이 있으면 화면이 [과제안 다시 만들기] 를 보인다 — 서버가 과제안을 자동으로
      다시 만들지 않는다(모순 수정 포함).
    recorded: 수정 짝·card_edit 기록을 남겼는가(공용 계정·저장 꺼짐이면 False). 표현 다듬기도 줄은
      남기고 본인 예시에서만 뺀다.
    """

    card: ProblemCard
    reruns: list[Rerun] = field(default_factory=list)
    recorded: bool = False
    calls: int = 0  # 이 수정으로 쓴 AI 호출 수(derive 0~1)


@runtime_checkable
class CardEditor(Protocol):
    """사용자 수정 → 의존 항목만 다시 계산 + 기록. before 는 수정 전 카드(수정 짝의 '변경 전')."""

    async def __call__(
        self,
        req: ProposalRequest,
        before: ProblemCard,
        after: ProblemCard,
        edits: list[CardEdit],
        *,
        principal: Principal | None = None,
    ) -> EditOutcome: ...


@dataclass(frozen=True)
class CodeCheck:
    verified: CodeVerified
    count: int | None = None
    label: str = ""  # 코드표·메타데이터에 있는 이름(없으면 빈 값 — 지어내지 않는다)


@runtime_checkable
class ClassCodeCheck(Protocol):
    """[3단계] 분류 코드가 실제로 있는지 — 공식 코드표 → 저장 자료의 코드 → KIPRIS 건수 순.
    실패는 unverified(예외를 내지 않는다). 같은 코드는 캐시한다."""

    async def __call__(self, kind: CodeKind, code: str) -> CodeCheck: ...


@runtime_checkable
class PatentClassCount(Protocol):
    """KIPRIS 분류 검색의 총 건수(레인 B, KIPRIS 어댑터). 일일 상한을 넘었거나 실패면 None."""

    async def __call__(self, ipc: str) -> int | None: ...


@runtime_checkable
class CardEditLogPort(Protocol):
    """수정 짝 저장소(data/feedback/card_edits.jsonl). 허용 칸만(계약 6절). 이름·연락처 없음."""

    def append(self, record: dict[str, Any]) -> None: ...

    def by_user(self, user: str, *, limit: int = 200) -> list[dict[str, Any]]:
        """그 가명 ID 가 남긴 수정 짝(최근 것부터). 다른 사용자 줄은 돌려주지 않는다."""
        ...
