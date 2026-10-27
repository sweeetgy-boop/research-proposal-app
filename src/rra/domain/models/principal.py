"""로그인 주체(Principal) — 누가 요청했는지. 사번·비밀번호 원문은 어디에도 들어오지 않는다.

- kind: admin(관리 토큰 X-RRA-Token) | staff(철도연구원 직원, 사번) | guest(공용 계정)
- id: 가명 ID. staff 는 `staff:<HMAC-SHA256(비밀 키, 사번) 앞 12자>`, guest 는 `guest:<아이디>`,
  admin 은 `admin:local`. run 저장소 키(디렉터리 이름)는 rules/auth_policy.run_user 가 만든다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PrincipalKind = Literal["admin", "staff", "guest"]


class Principal(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: PrincipalKind
    id: str = Field(min_length=1, max_length=64)

    @property
    def is_admin(self) -> bool:
        return self.kind == "admin"
