"""MCP 쓰기 도구 본체 — rra_generate · rra_get_draft. mcp SDK 를 import 하지 않는다.

권한 경계 (G-MCP):
- RunManager 를 받는 유일한 MCP 객체다. 읽기 도구(tools.py)는 이 모듈·RunManager 를
  import 할 수 없다 (import-linter 계약).
- 서버가 `--enable-generate` 로 떴을 때만 등록된다. 기본 서버는 읽기 도구 2개뿐이다.
- 사용자는 stdio 프로세스 소유자 한 명(`local`). 다른 사용자의 run 은 보이지 않는다.
- 생성은 백그라운드로 돌고 run_id 만 즉시 돌려준다. 진행은 rra_get_draft 로 폴링한다.
- 초안은 비신뢰 자료에서 파생된 텍스트다 → 경고 문구 + 구획 태그 무력화.
"""

from __future__ import annotations

from typing import Any

from rra.application.ports import RunBusy, RunNotFound
from rra.application.services import QueueFull, RunManager, RunNotResumable
from rra.domain.models import ProposalRequest
from rra.domain.models.run import is_valid_run_id
from rra.domain.rules.trust import UNTRUSTED_NOTICE, escape_untrusted
from rra.entrypoints.mcp.tools import ToolInputError
from rra.entrypoints.views import draft_payload

POLL_HINT = "생성은 수 분 걸린다. rra_get_draft(run_id) 로 진행 상황과 부분 초안을 확인한다."


def _run_id(value: str) -> str:
    rid = (value or "").strip()
    if not is_valid_run_id(rid):
        raise ToolInputError("run_id 형식이 올바르지 않습니다.")
    return rid


class RraRunTools:
    def __init__(self, manager: RunManager, user: str = "local"):
        self._manager = manager
        self._user = user

    async def generate(
        self,
        current_state: str = "",
        root_cause: str = "",
        limitation: str = "",
        goal: str = "",
        constraints: str = "",
        resume_run_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            if resume_run_id:
                state = await self._manager.resume(self._user, _run_id(resume_run_id))
            else:
                req = ProposalRequest(  # 길이 상한은 도메인 모델이 강제한다
                    current_state=current_state,
                    root_cause=root_cause,
                    limitation=limitation,
                    goal=goal,
                    constraints=constraints,
                )
                missing = [
                    k
                    for k in ("current_state", "root_cause", "limitation", "goal")
                    if not getattr(req, k)
                ]
                if missing:
                    raise ToolInputError(f"필수 슬롯이 비었습니다: {', '.join(missing)}")
                state = await self._manager.submit(self._user, req)
        except (QueueFull, RunBusy, RunNotResumable, RunNotFound) as exc:
            raise ToolInputError(str(exc)) from exc
        done, total = state.progress
        return {
            "run_id": state.run_id,
            "status": state.status,
            "progress": [done, total],
            "hint": POLL_HINT,
        }

    async def get_draft(self, run_id: str) -> dict[str, Any]:
        try:
            view = await self._manager.get_draft(self._user, _run_id(run_id))
        except RunNotFound as exc:
            raise ToolInputError("해당 run 이 없습니다.") from exc
        return {"notice": UNTRUSTED_NOTICE, **draft_payload(view, clean=escape_untrusted)}
