from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from rra.domain.models import Confirmation, Draft, ProposerInfo
from rra.domain.models.figure import Figure, FigurePlacement

FigureFile = tuple[Figure, bytes, str]  # (그림 기록, 이미지 바이트, mime)


class RenderRejected(ValueError):
    """렌더할 수 없는 입력 — 확정값 없음, 선언되지 않은 슬롯, 템플릿 자리표시자 미치환 등.

    어댑터는 이 클래스의 하위 예외를 올린다. 메시지에 제안자 개인정보·초안 본문은 넣지 않는다.
    """


@runtime_checkable
class RendererPort(Protocol):
    """초안 → 양식 파일(bytes).

    confirmation: 선택형(과제유형·활용계획·전략) 확정값 — 체크 칸은 이 값으로만 채운다.
    proposer: 제안자·부서장 정보 — 렌더 시점에만 받고 어디에도 저장하지 않는다
    (domain/models/proposer.py).
    """

    def render(
        self,
        draft: Draft,
        *,
        confirmation: Confirmation | None = None,
        proposer: ProposerInfo | None = None,
    ) -> bytes: ...

    def render_with_figures(
        self,
        draft: Draft,
        *,
        confirmation: Confirmation | None = None,
        proposer: ProposerInfo | None = None,
        figures: Sequence[FigureFile] = (),
    ) -> tuple[bytes, list[FigurePlacement]]:
        """[G] 그림을 섹션 칸 안(inline) 또는 문서 끝 별첨(appendix)에 넣은 양식 + 배치 기록."""
        ...
