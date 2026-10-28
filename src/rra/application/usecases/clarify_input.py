"""Q1 입력 보강 질문 — 초안 생성 전에 빠진 정보를 2~4개 질문으로 (2026-10-28 레인 B 개편).

순서: 앱 점검(정책 근거·소요예산·연구기간·적용 대상·정량 목표치가 입력에 있는지, 섹션 체크리스트의
요소) → Argon 이 그 점검표와 입력을 읽고 질문을 쓴다 → 실패하면 로컬 모델 → 둘 다 실패하면 앱 점검
질문만(사유와 [다시 시도] 를 함께 돌려준다).

출력(JSON 만 파싱): {"questions": [{"topic": "…", "question": "…"}]} — 이미 충분하면 빈 배열. 질문은
한국어 문장 200자 이내, 한자·가나 없음. 정책 근거 질문(topic policy)은 앱이 직접 낸다 — 화면은 그
자리에 "정책적 중요도 작성안" 4개를 보인다(usecases/policy_cards).

결과 상태(status): ok | enough(입력 충분) | failed(생성 실패 — 다시 시도) | off(꺼짐, 진입점이
정한다).
답은 ProposalRequest.supplement("보충 정보")에 "질문: 답" 줄로 저장되어 설계도·작성 프롬프트에
들어간다(제안자 입력 근거로 취급). 건너뛸 수 있다.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from rra.application.ports import LLMPort, PromptLibraryPort
from rra.application.usecases.argon_first import FAILURE_REASONS, ArgonFirst, reason_label
from rra.domain.models import ProposalRequest
from rra.domain.rules.foreign_script import has_foreign_script
from rra.domain.rules.llm_output import clean_sentence, parse_object
from rra.domain.rules.policy_cards import needs_policy_basis
from rra.domain.rules.trust import escape_untrusted

MAX_QUESTIONS = 4
MAX_QUESTION_CHARS = 200
TOPICS = ("policy", "budget_period", "target", "metric", "other")
TOPIC_LABELS = {
    "policy": "정책 근거",
    "budget_period": "소요예산·연구기간",
    "target": "적용 대상",
    "metric": "정량 목표치",
    "other": "기타",
}
POLICY_QUESTION = (
    "이 과제를 뒷받침하는 정책 근거(정부 계획·공사 전략·감사 지적 등)가 있습니까? "
    "아래 작성안에서 고르거나 직접 적어 주십시오."
)
_PERIOD = re.compile(r"\d+\s?(?:개월|년|개년)")
_METRIC = re.compile(r"\d+(?:\.\d+)?\s?(?:%|퍼센트|건|회|분|초|시간|원|천원|만원|억원|km|배)")
# 앱 점검 질문 (Argon·로컬이 모두 실패하면 이것만 낸다)
RULE_QUESTIONS = {
    "budget_period": "연구기간(개월)과 소요예산(천원)은 어느 정도로 예상합니까?",
    "target": "연구 결과를 적용할 대상(노선·구간·설비·차량·업무)과 활용 부서는 어디입니까?",
    "metric": "목표를 무엇으로 재고(지표) 어느 수준까지 달성하려 합니까? (예: 오류율 ○% 감소)",
}


def gaps(req: ProposalRequest) -> list[str]:
    """앱 점검 — 입력에 없어 보이는 항목(topic). 정책 근거는 고른 작성안도 근거로 본다."""
    out: list[str] = []
    if needs_policy_basis(req):
        out.append("policy")
    text = " ".join([req.constraints, req.goal, req.supplement, req.remarks])
    no_budget = req.budget is None or req.budget.amount_thousand_krw is None
    if no_budget and not _PERIOD.search(text):
        out.append("budget_period")
    if not req.beneficiaries.strip() and not re.search(
        r"노선|구간|역|설비|차량|부서|처|본부", text
    ):
        out.append("target")
    if not _METRIC.search(" ".join([req.goal, req.supplement])):
        out.append("metric")
    return out


@dataclass
class ClarifyQuestion:
    id: str
    question: str
    topic: str = "other"
    hint: str | None = None

    def dump(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "topic": self.topic,
            "topic_label": TOPIC_LABELS.get(self.topic, TOPIC_LABELS["other"]),
            "hint": self.hint,
        }


@dataclass
class ClarifyResult:
    questions: list[ClarifyQuestion] = field(default_factory=list)
    status: str = "ok"  # ok | enough | failed | off
    reason: str | None = None  # 모델 실패 사유 (앱 점검 질문만 남았을 때도 채운다)
    source: str = "argon"  # argon | local | rule | none
    policy_needed: bool = False
    record: dict[str, Any] = field(default_factory=dict)

    @property
    def reason_label(self) -> str | None:
        return reason_label(self.reason)

    def dump(self) -> dict[str, Any]:
        return {
            "questions": [q.dump() for q in self.questions],
            "status": self.status,
            "status_label": STATUS_LABELS.get(self.status, self.status),
            "reason": self.reason,
            "reason_label": self.reason_label,
            "source": self.source,
            "policy_needed": self.policy_needed,
            "transfer": self.record,
        }


STATUS_LABELS = {
    "ok": "질문 있음",
    "enough": "입력 충분 — 물을 것이 없습니다",
    "failed": "질문 생성 실패",
    "off": "보강 질문이 꺼져 있습니다",
}


def validate_questions(data: object, limit: int = MAX_QUESTIONS) -> list[tuple[str, str]]:
    """LLM 출력 → (topic, 질문) 목록(비신뢰 텍스트 정리, 중복·외국 문자·빈 문자열 제거, 상한).
    옛 형식 {"questions": ["…"]} 도 받는다."""
    if not isinstance(data, dict):
        return []
    raw = data.get("questions")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out: list[tuple[str, str]] = []
    for q in raw:
        topic = "other"
        if isinstance(q, dict):
            topic = q.get("topic") if q.get("topic") in TOPICS else "other"
            q = q.get("question")
        if not isinstance(q, str):
            continue
        text = clean_sentence(escape_untrusted(q))[:MAX_QUESTION_CHARS]
        if not text or has_foreign_script(text) or any(text == t for _, t in out):
            continue
        out.append((str(topic), text))
        if len(out) >= limit:
            break
    return out


@dataclass
class ClarifyInput:
    llm: LLMPort | None  # 로컬 모델 (Argon 실패 시)
    prompts: PromptLibraryPort
    max_questions: int = MAX_QUESTIONS
    argon: LLMPort | None = None  # review 단계 provider (예산 래퍼) — 먼저 묻는다
    checklists: Mapping[str, Sequence[Mapping[str, Any]]] = field(default_factory=dict)
    local_gate: Any = None  # 로컬 호출 슬롯 (callable → async cm)
    argon_model: str = "argon"
    local_model: str = "local"

    def _prompt(self, req: ProposalRequest, found: list[str]) -> str:
        checklist = [
            f"- {key}: {item.get('element')}"
            for key, items in self.checklists.items()
            for item in items
            if item.get("element")
        ][:40]
        return "\n\n".join(
            [
                "[보강 질문]",
                "[제안 입력]\n" + json.dumps(req.prompt_view(), ensure_ascii=False),
                "[앱 점검 — 입력에 없어 보이는 항목]\n"
                + (", ".join(TOPIC_LABELS[t] for t in found if t != "policy") or "(없음)"),
                "[섹션 체크리스트 — 초안 각 칸이 갖춰야 할 요소]\n" + "\n".join(checklist),
                '[출력] JSON 객체 하나: {"questions": [{"topic": '
                '"budget_period|target|metric|other", "question": "…"}]}'
                f" — 최대 {self.max_questions - int('policy' in found)}개."
                " 정책 근거는 묻지 않는다(앱이 따로 묻는다). 이미 충분하면 빈 배열.",
            ]
        )

    async def __call__(self, req: ProposalRequest) -> list[str]:
        """질문 문장만 (CLI·MCP·Streamlit). 상태·사유가 필요하면 inspect."""
        return [q.question for q in (await self.inspect(req)).questions]

    async def inspect(self, req: ProposalRequest) -> ClarifyResult:
        found = gaps(req)
        policy = "policy" in found
        head: list[ClarifyQuestion] = (
            [ClarifyQuestion("policy", POLICY_QUESTION, "policy")] if policy else []
        )
        room = self.max_questions - len(head)

        def check(raw: str) -> tuple[list[tuple[str, str]] | None, str | None]:
            data = parse_object(raw)
            if not isinstance(data, dict) or "questions" not in data:
                return None, "invalid"
            items = [x for x in validate_questions(data, room) if x[0] != "policy"]
            return (items, None) if items else (None, "empty")

        ask = ArgonFirst(
            self.llm,
            self.argon,
            local_gate=self.local_gate,
            argon_model=self.argon_model,
            local_model=self.local_model,
        )
        res = await ask.ask(self._prompt(req, found), system=self.prompts.clarify(), check=check)
        result = ClarifyResult(policy_needed=policy, record=res.record())
        if res.value:
            result.questions = head + [
                ClarifyQuestion(f"q{i}", text, topic) for i, (topic, text) in enumerate(res.value)
            ]
            result.source = "local" if res.fallback else "argon"
            return result
        if res.reason == "empty":  # 모델: 입력 충분
            result.questions = head
            result.source = "argon" if res.model == self.argon_model else "local"
            result.status = "ok" if head else "enough"
            return result
        # 호출 실패 — 앱 점검 질문만, 사유를 함께
        result.reason = res.reason if res.reason in FAILURE_REASONS else "error"
        rule = [
            ClarifyQuestion(f"r{i}", RULE_QUESTIONS[t], t)
            for i, t in enumerate(x for x in found if x in RULE_QUESTIONS)
        ][:room]
        result.questions = head + rule
        result.source = "rule" if result.questions else "none"
        result.status = "ok" if result.questions else "failed"
        return result


def apply_answers(
    req: ProposalRequest, answers: dict[str, str] | list[tuple[str, str]]
) -> ProposalRequest:
    """답을 보충 정보로 — "질문: 답" 줄을 supplement 에 덧붙인다 (비면 그대로)."""
    pairs = list(answers.items()) if isinstance(answers, dict) else list(answers)
    lines = [
        f"{clean_sentence(q)[:MAX_QUESTION_CHARS]}: {clean_sentence(a)}"
        for q, a in pairs
        if isinstance(a, str) and clean_sentence(a)
    ]
    if not lines:
        return req
    existing = req.supplement.strip()
    joined = "\n".join(([existing] if existing else []) + lines)
    return req.model_copy(update={"supplement": joined})
