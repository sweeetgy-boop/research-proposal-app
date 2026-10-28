"""Argon 먼저, 실패면 로컬 — 작성·편집 AI 버튼(보강 질문·정책 작성안·보완 질문)의 공용 호출 순서.

원칙(2026-10-28, 레인 B · ADR "작성·편집 AI 버튼"): 외부 모델(Gemini 4 Argon, review 단계 provider —
일일 예산 래퍼·공유 호출 제한기는 조립이 씌운다)이 먼저 답하고, 호출이 실패하거나(오류·429·예산)
교정 재요청 뒤에도 형식이 틀리면 로컬 모델이 같은 프롬프트로 답한다. 로컬 호출은 전역 슬롯
(local_gate) 안에서만. 끝내 값이 없으면 **사유 코드**를 돌려준다 — 화면은 빈 결과로 조용히 끝내지
않고 사유와 [다시 시도] 를 보인다.

사유 코드(REASON_LABELS): error·rate_limit·budget = 호출 실패, invalid = 형식 오류(교정 뒤에도),
filtered = 규칙에 걸러짐(근거·정책명·수치 검사로 전부 폐기), empty = 해당 없음(모델이 "없음" 이라고
답함), off = 꺼져 있음. 예외 메시지는 남기지 않는다(제안 내용이 섞일 수 있다).
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from rra.application.ports import LLMPort
from rra.application.ports.auth import BudgetExhausted
from rra.application.ports.llm import RateLimited

logger = logging.getLogger("rra.argon_first")

T = TypeVar("T")

# 화면 문구 (내부 코드를 그대로 보이지 않는다)
REASON_LABELS: dict[str, str] = {
    "error": "호출 실패",
    "rate_limit": "호출 실패 (호출 한도 — 잠시 뒤 다시 시도)",
    "budget": "호출 실패 (오늘 외부 호출 상한)",
    "invalid": "호출 실패 (응답 형식 오류)",
    "filtered": "규칙에 걸러짐 (근거·정책명·수치 검사)",
    "empty": "해당 없음",
    "off": "꺼져 있음",
    "no_llm": "호출 실패 (쓸 수 있는 모델 없음)",
}
FAILURE_REASONS = frozenset({"error", "rate_limit", "budget", "invalid", "no_llm"})


def reason_label(code: str | None) -> str | None:
    return None if code is None else REASON_LABELS.get(code, REASON_LABELS["error"])


def call_failure(exc: BaseException) -> str:
    if isinstance(exc, BudgetExhausted):
        return "budget"
    if isinstance(exc, RateLimited):
        return "rate_limit"
    return "error"


# check(raw) → (값, 사유). 값이 None 이면 사유: "invalid"(교정 재요청) | "filtered" | "empty"
Check = Callable[[str], tuple[Any, str | None]]


@dataclass
class AskResult(Generic[T]):  # noqa: UP046 — 다른 모듈과 같은 Generic 표기
    value: T | None = None
    model: str | None = None  # 답한 모델 라벨 (argon_model | local_model)
    fallback: bool = False  # 로컬이 대신 답했다
    reason: str | None = None  # 값이 없을 때 사유 코드
    calls: int = 0  # 실제 호출 수 (원격 + 로컬)
    remote_calls: int = 0

    @property
    def reason_label(self) -> str | None:
        return reason_label(self.reason)

    def record(self) -> dict[str, Any]:
        """전송·작성 기록(본문 없음) — 화면·manifest 용."""
        return {
            "model": self.model,
            "fallback": self.fallback,
            "reason": self.reason,
            "reason_label": self.reason_label,
            "calls": self.calls,
            "remote_calls": self.remote_calls,
        }


@dataclass
class ArgonFirst:
    """argon(원격) → local(로컬) 순서. 둘 다 없으면 no_llm."""

    local: LLMPort | None
    argon: LLMPort | None = None
    local_gate: Callable[[], AbstractAsyncContextManager[None]] | None = None
    argon_model: str = "argon"
    local_model: str = "local"
    correction: str = (
        "[형식 교정 — 직전 응답은 형식 오류였음] "
        "설명·코드블록 없이 지시한 JSON 객체 하나만 내십시오."
    )

    def _chain(self) -> list[tuple[str, LLMPort, bool]]:
        chain: list[tuple[str, LLMPort, bool]] = []
        if self.argon is not None:
            chain.append((self.argon_model, self.argon, True))
        if self.local is not None:
            chain.append((self.local_model, self.local, False))
        return chain

    def _gate(self, remote: bool) -> AbstractAsyncContextManager[None]:
        if not remote and self.local_gate is not None:
            return self.local_gate()
        return contextlib.nullcontext()

    async def ask(
        self,
        prompt: str,
        *,
        system: str,
        check: Check,
        local_prompt: str | None = None,
        max_tokens: int | None = None,
    ) -> AskResult[Any]:
        """모델마다 1회 + 형식 오류(invalid)면 교정 재요청 1회. filtered·empty 는 그 답을 존중해
        멈추지 않고 다음 모델에 한 번 더 묻지 않는다 — 단 filtered 는 로컬에 한 번 더 묻는다(원격이
        규칙을 어긴 답을 냈을 수 있다). local_prompt: 로컬용 짧은 프롬프트(없으면 같은 것)."""
        out: AskResult[Any] = AskResult()
        chain = self._chain()
        if not chain:
            out.reason = "no_llm"
            return out
        for i, (label, llm, remote) in enumerate(chain):
            text = prompt if remote or local_prompt is None else local_prompt
            reason: str | None = None
            try:
                async with self._gate(remote):
                    raw = await llm.complete(
                        text, system=system, max_tokens=max_tokens, json_mode=True
                    )
                    out.calls += 1
                    out.remote_calls += int(remote)
                    value, reason = check(raw)
                    if value is None and reason == "invalid":
                        raw = await llm.complete(
                            f"{text}\n\n{self.correction}",
                            system=system,
                            max_tokens=max_tokens,
                            json_mode=True,
                        )
                        out.calls += 1
                        out.remote_calls += int(remote)
                        value, reason = check(raw)
            except BudgetExhausted as exc:  # 보내지 않았다 — 호출 수에 넣지 않는다
                reason = call_failure(exc)
                logger.info("argon_first.failed model=%s reason=%s", label, reason)
                out.reason = out.reason if out.reason in ("empty", "filtered") else reason
                continue
            except Exception as exc:  # 네트워크·429·서버 오류 — 사유 코드만
                out.calls += 1
                out.remote_calls += int(remote)
                reason = call_failure(exc)
                logger.info(
                    "argon_first.failed model=%s reason=%s error=%s",
                    label,
                    reason,
                    type(exc).__name__,
                )
                out.reason = out.reason if out.reason in ("empty", "filtered") else reason
                continue
            if value is not None:
                out.value, out.model, out.fallback, out.reason = value, label, i > 0, None
                return out
            out.reason = reason or "invalid"
            if reason == "empty":  # 모델이 "해당 없음" 이라고 답했다 — 다른 모델에 다시 묻지 않는다
                out.model = label
                return out
        return out
