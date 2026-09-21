"""양식 하단 제안자 정보 — 렌더 시점에만 받는 개인정보.

run 폴더·manifest·로그에 저장하지 않는다. 렌더러에 곧바로 넘기고 버린다 (Step 8).
비어 있으면 양식 칸을 빈칸으로 둔다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_SHORT = 100


class Person(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(default="", max_length=_SHORT)
    rank: str = Field(default="", max_length=_SHORT, description="직급")
    phone: str = Field(default="", max_length=_SHORT, description="연락처")

    def __repr__(self) -> str:  # 로그·예외에 원문이 새지 않게
        return "Person(***)"

    __str__ = __repr__


class ProposerInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    proposed_on: str = Field(default="", max_length=20, description="제안일자")
    proposer: Person = Field(default_factory=Person, description="제안자")
    head: Person = Field(default_factory=Person, description="제안부서장")

    def __repr__(self) -> str:
        return "ProposerInfo(***)"

    __str__ = __repr__
