"""MCP 도구 본체. 유스케이스 호출과 결과 직렬화만 한다.

mcp SDK 를 import 하지 않는다 — SDK 없이도 도구 동작을 테스트할 수 있어야 하고,
전송 방식이 바뀌어도 이 파일은 그대로다.

보안 G-MCP:
- 입력 길이·개수 상한을 여기서 강제한다 (5슬롯은 ProposalRequest 가 이미 2,000자 제한).
- 두 도구 모두 결과가 비신뢰 텍스트이므로 경고 문구를 함께 돌려준다.
- 쓰기 동작 없음.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rra.application.ports import DocumentRepository
from rra.application.usecases.precheck_overlap import PrecheckOverlap
from rra.domain.models import ProposalRequest
from rra.domain.rules.trust import UNTRUSTED_NOTICE, escape_untrusted, untrusted_block

DEFAULT_K = 10
MAX_ORG_CHARS = 64


class ToolInputError(ValueError):
    """호출자에게 그대로 돌려줘도 되는 입력 오류. 내부 상태를 담지 않는다."""


@dataclass(frozen=True)
class ToolLimits:
    query_max_chars: int = 500
    max_k: int = 50
    max_orgs: int = 10

    @classmethod
    def from_security_config(cls, cfg: dict[str, Any]) -> ToolLimits:
        limits = (cfg or {}).get("input_limits") or {}
        return cls(
            query_max_chars=int(limits.get("query_max_chars", 500)),
            max_k=int(limits.get("mcp_max_k", 50)),
            max_orgs=int(limits.get("mcp_max_orgs", 10)),
        )


class RraTools:
    def __init__(
        self,
        precheck: PrecheckOverlap,
        repo: DocumentRepository,
        limits: ToolLimits | None = None,
    ):
        self._precheck = precheck
        self._repo = repo
        self.limits = limits or ToolLimits()

    def precheck(
        self,
        current_state: str,
        root_cause: str,
        limitation: str,
        goal: str,
        constraints: str = "",
    ) -> dict[str, Any]:
        """제안 5슬롯 → 기수행 과제 중복 경보."""
        req = ProposalRequest(  # 길이 상한은 도메인 모델이 강제한다
            current_state=current_state,
            root_cause=root_cause,
            limitation=limitation,
            goal=goal,
            constraints=constraints,
        )
        alerts = self._precheck(req)
        return {
            "notice": UNTRUSTED_NOTICE,  # 과제명은 수집 문서에서 온 비신뢰 텍스트
            "blocking": any(a.blocking for a in alerts),
            "alerts": [
                {
                    "doc_id": a.doc_id,
                    "title": escape_untrusted(a.title),
                    "tier": a.tier,
                    "similarity": round(a.similarity, 4),
                    "blocking": a.blocking,
                    "basis": a.basis,  # summary: 원문 비공개, 공개 요약만으로 판정
                }
                for a in alerts
            ],
        }

    def search(self, query: str, orgs: list[str] | None = None, k: int = DEFAULT_K) -> str:
        """하이브리드 검색 결과를 <doc> 구획 텍스트로 돌려준다."""
        q = (query or "").strip()
        if not q:
            raise ToolInputError("query 가 비어 있습니다.")
        if len(q) > self.limits.query_max_chars:
            raise ToolInputError(f"query 길이 {len(q)} > 상한 {self.limits.query_max_chars}")
        chunks = self._repo.hybrid_search(
            [q], k=self._clamp_k(k), orgs=self._clean_orgs(orgs) or None
        )
        return untrusted_block(list(chunks))

    def _clamp_k(self, k: int | None) -> int:
        try:
            value = int(k if k is not None else DEFAULT_K)
        except (TypeError, ValueError) as exc:
            raise ToolInputError("k 는 정수여야 합니다.") from exc
        return max(1, min(value, self.limits.max_k))

    def _clean_orgs(self, orgs: list[str] | None) -> list[str]:
        if not orgs:
            return []
        cleaned: list[str] = []
        for org in orgs:
            name = str(org).strip()
            if not name:
                continue
            if len(name) > MAX_ORG_CHARS:
                raise ToolInputError(f"orgs 항목이 {MAX_ORG_CHARS}자를 넘습니다.")
            if name not in cleaned:
                cleaned.append(name)
        if len(cleaned) > self.limits.max_orgs:
            raise ToolInputError(f"orgs 는 최대 {self.limits.max_orgs}개입니다.")
        return cleaned
