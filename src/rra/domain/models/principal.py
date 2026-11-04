"""로그인 주체(Principal) — 누가 요청했는지. 사번·비밀번호 원문은 어디에도 들어오지 않는다.

- kind: admin(관리 토큰 X-RRA-Token) | staff(철도연구원 직원, 사번) | guest(공용 계정)
- id: 가명 ID. staff 는 `staff:<HMAC-SHA256(비밀 키, 사번) 앞 12자>`, guest 는 `guest:<아이디>`,
  admin 은 `admin:local`. run 저장소 키(디렉터리 이름)는 rules/auth_policy.run_user 가 만든다.
- test: 시험 계정(배포 확인용 임시 사번, `rra auth staff add --test`)으로 로그인한 세션. 직원만
  True 가 될 수 있다(공용 계정·관리 토큰은 늘 False). 선택 기록·과제안 측정 줄에 `test: true` 를
  붙여 평가 집계에서 뺀다(ADR 0056 2026-11-04 덧붙임). 화면·응답에는 내보내지 않는다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PrincipalKind = Literal["admin", "staff", "guest"]


class Principal(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: PrincipalKind
    id: str = Field(min_length=1, max_length=64)
    test: bool = False

    @property
    def is_admin(self) -> bool:
        return self.kind == "admin"
