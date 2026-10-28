"""④ 편집 단계의 AI 버튼·변경 세기 — RunManager 에 섞어 쓰는 메서드 묶음 (2026-10-28 레인 B).

- section_questions: Argon 보완 질문(본문·근거·작성 지침) → 실패면 로컬 → 체크리스트. 결과는
버전별로
  proposer_notes.json 에 보관해 같은 버전이면 다시 부르지 않는다(refresh=True 면 새로).
- save_section_answers: 보완 질문의 답(제안자 입력) + 섹션별 저장 시각(변경 세기의 "보완 메모").
- changes: 마지막 검토 이후 변경 종류별 건수(domain/rules/change_count).
- run_policy_cards·run_policy_polish·choose_policy: 빈 2-가-(1) 을 정책적 중요도 작성안으로 채운다.
  고른 안의 인용 구간은 저장소 원문과 대조해(보안 A) 통과한 것만 스냅샷에 고정하고 근거로 쓴다.

RunManager 의 저장소·상태·버전 저장(_store_version)을 그대로 쓴다. 예외 클래스는 run_manager 에 있다
(순환 import 를 피해 호출 때 가져온다).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from rra.application.usecases.policy_cards import PolicyCards, PolicyCardsResult, PolishResult
from rra.application.usecases.section_questions import SectionQuestions
from rra.domain.models import DraftVersion, PolicyChoice, Section
from rra.domain.rules import review_flow
from rra.domain.rules.change_count import (
    ChangeSummary,
    after,
    base_version,
    count_changes,
    memo_sections_after,
)
from rra.domain.rules.checklist import clean_answers
from rra.domain.rules.evidence import decisions_for_sections
from rra.domain.rules.policy_cards import POLICY_SECTION, choice_section
from rra.domain.rules.review_flow import InvalidTransition
from rra.domain.rules.versions import changed_sections, same_content

if TYPE_CHECKING:  # pragma: no cover
    from rra.domain.models import RunState

POLICY_NOTE = "정책 근거 선택"


def _errors():
    from rra.application.services import run_manager as rm

    return rm


class EditAIMixin:
    """RunManager 전용 믹스인 — self.store·status·_current_version·_store_version 을 쓴다."""

    # 조립(composition)이 넣는다. None 이면 체크리스트만(보완 질문)·작성안 없음(503)
    section_questioner: SectionQuestions | None = None
    section_questioner_public: SectionQuestions | None = None  # 공용 계정 run (internal 제외)
    policy_cards: PolicyCards | None = None
    policy_cards_public: PolicyCards | None = None

    # ── U3 보완 질문 ────────────────────────────────────
    def _questioner(self, state: RunState) -> SectionQuestions | None:
        if state.scope == "public" and self.section_questioner_public is not None:
            return self.section_questioner_public
        return self.section_questioner

    async def section_questions(
        self, user: str, run_id: str, key: str, *, refresh: bool = False
    ) -> dict[str, Any]:
        """Argon 이 섹션 본문을 읽고 빠진·약한 부분을 묻는다(실패면 로컬 → 체크리스트). 저장된 답이
        있으면 함께. 같은 버전의 결과는 다시 부르지 않는다."""
        rm = _errors()
        if not self.usability.section_questions:  # type: ignore[attr-defined]
            raise rm.FeatureDisabled(
                "보완 질문이 꺼져 있습니다 (usability.yaml section_questions)."
            )
        state = await self.status(user, run_id)  # type: ignore[attr-defined]
        if key not in state.section_keys:
            raise rm.EditRejected(f"그런 섹션이 없습니다: {key}")
        version = self._current_version(user, run_id, state)  # type: ignore[attr-defined]
        notes = self.store.load_notes(user, run_id) or {}  # type: ignore[attr-defined]
        answers = (notes.get("answers") or {}).get(key) or {}
        cached = (notes.get("questions") or {}).get(key)
        if not refresh and isinstance(cached, dict) and cached.get("version") == version.version:
            return {"section": key, **cached["result"], "answers": dict(answers), "cached": True}
        section = version.section(key)
        checklist = self.checklists.get(key, [])  # type: ignore[attr-defined]
        questioner = self._questioner(state)
        if questioner is None:  # 모델 없음 — 체크리스트만 (예전 동작)
            from rra.application.usecases.section_questions import SectionQuestionsResult
            from rra.domain.rules.checklist import coverage, missing_elements

            found = missing_elements(section, checklist)
            result = SectionQuestionsResult(
                found[:4], "checklist" if found else "none", None, coverage(section, checklist)
            ).dump()
        else:
            gen = self._generate_for(state)  # type: ignore[attr-defined]
            snapshot = self.store.load_snapshot(user, run_id)  # type: ignore[attr-defined]
            chunks = gen._writer_chunks(key, snapshot) if snapshot is not None else []
            req = self.store.load_request(user, run_id)  # type: ignore[attr-defined]
            result = (await questioner(key, section, chunks, req, answers)).dump()
        store_q = dict(notes.get("questions") or {})
        store_q[key] = {"version": version.version, "result": result, "at": self._clock()}  # type: ignore[attr-defined]
        self.store.save_notes(user, run_id, {**notes, "questions": store_q})  # type: ignore[attr-defined]
        return {"section": key, **result, "answers": dict(answers), "cached": False}

    async def save_section_answers(
        self, user: str, run_id: str, key: str, answers: Mapping[str, Any]
    ) -> dict[str, str]:
        """보완 질문의 답을 제안자 입력으로 저장 (proposer_notes.json) — 다음 다시 쓰기에."""
        rm = _errors()
        state = await self.status(user, run_id)  # type: ignore[attr-defined]
        if key not in state.section_keys:
            raise rm.EditRejected(f"그런 섹션이 없습니다: {key}")
        cleaned = clean_answers(answers)
        notes = self.store.load_notes(user, run_id) or {}  # type: ignore[attr-defined]
        all_answers = dict(notes.get("answers") or {})
        merged = {**(all_answers.get(key) or {}), **cleaned}
        all_answers[key] = merged
        now = self._clock()  # type: ignore[attr-defined]
        answers_at = dict(notes.get("answers_at") or {})
        if cleaned:
            answers_at[key] = now
        self.store.save_notes(  # type: ignore[attr-defined]
            user,
            run_id,
            {**notes, "answers": all_answers, "answers_at": answers_at, "saved_at": now},
        )
        return merged

    # ── 변경 세기 ────────────────────────────────────────
    async def changes(self, user: str, run_id: str) -> ChangeSummary:
        state = await self.status(user, run_id)  # type: ignore[attr-defined]
        current = self._current_version(user, run_id, state)  # type: ignore[attr-defined]
        numbers = self.store.list_versions(user, run_id) or [current.version]  # type: ignore[attr-defined]
        versions: list[DraftVersion] = [
            v
            for n in numbers
            if (v := self.store.load_version(user, run_id, n)) is not None  # type: ignore[attr-defined]
        ] or [current]
        base = base_version(versions, state.final_reviewed_version)
        notes = self.store.load_notes(user, run_id) or {}  # type: ignore[attr-defined]
        confirmation = self.store.load_confirmation(user, run_id)  # type: ignore[attr-defined]
        policy = notes.get("policy_choice") if isinstance(notes.get("policy_choice"), dict) else {}
        return count_changes(
            base,
            current,
            confirmed_after_base=after(confirmation.updated_at if confirmation else None, base),
            policy_after_base=after(policy.get("at"), base),
            memo_sections=memo_sections_after(notes.get("answers_at"), base),
        )

    # ── 2-가-(1) 정책적 중요도 작성안 ─────────────────────
    def _cards(self, state: RunState) -> PolicyCards:
        rm = _errors()
        uc = (
            self.policy_cards_public
            if state.scope == "public" and self.policy_cards_public is not None
            else self.policy_cards
        )
        if uc is None:
            raise rm.FeatureDisabled("정책적 중요도 작성안을 쓸 수 없습니다 (정책 자료·모델 없음).")
        return uc

    async def run_policy_cards(
        self, user: str, run_id: str, *, exclude_docs: Sequence[str] = ()
    ) -> PolicyCardsResult:
        state = await self.status(user, run_id)  # type: ignore[attr-defined]
        req = self.store.load_request(user, run_id)  # type: ignore[attr-defined]
        return await self._cards(state)(req, exclude_docs=list(exclude_docs))

    async def run_policy_polish(
        self, user: str, run_id: str, choice: PolicyChoice, text: str
    ) -> PolishResult:
        state = await self.status(user, run_id)  # type: ignore[attr-defined]
        req = self.store.load_request(user, run_id)  # type: ignore[attr-defined]
        return await self._cards(state).polish(req, choice, text)

    async def choose_policy(
        self,
        user: str,
        run_id: str,
        choice: PolicyChoice,
        *,
        base_version: int | None = None,
    ) -> DraftVersion:
        """고른 작성안(또는 "정책 근거 없음")으로 2-가-(1) 을 바꾼 새 버전(origin edit, note "정책
        근거
        선택"). 인용 구간은 저장소 원문과 대조해 통과한 것만 근거로(스냅샷 policy_ids)."""
        rm = _errors()
        state = await self.status(user, run_id)  # type: ignore[attr-defined]
        if self.is_legacy(state):  # type: ignore[attr-defined]
            raise rm.EditRejected(rm.LEGACY_HINT.format(run_id=run_id))
        try:
            nxt = review_flow.transition(state.status, "edit")
        except InvalidTransition as exc:
            raise rm.EditRejected(str(exc)) from exc
        if POLICY_SECTION not in state.section_keys:
            raise rm.EditRejected("이 양식에는 정책적 중요도 칸이 없습니다.")
        current = self._current_version(user, run_id, state)  # type: ignore[attr-defined]
        if base_version is not None and base_version != current.version:
            raise rm.VersionConflict(
                f"기준 버전 v{base_version} 과 현재 버전 v{current.version} 이 다릅니다 — "
                "최신 버전을 불러와 다시 고르십시오."
            )
        snapshot = self.store.load_snapshot(user, run_id)  # type: ignore[attr-defined]
        if snapshot is None:
            raise rm.EditRejected("검색 스냅샷이 없어 근거를 대조할 수 없습니다.")
        gen = self._generate_for(state)  # type: ignore[attr-defined]
        await gen.pin_policy_choice(choice, snapshot)
        self.store.save_snapshot(user, run_id, snapshot)  # type: ignore[attr-defined]
        old = current.section(POLICY_SECTION)
        if choice.mode == "none":
            section = Section(
                key=POLICY_SECTION, sentences=[], choices=list(old.choices) if old else []
            )
        else:
            section = choice_section(choice, set(snapshot.policy_ids))
        notes = self.store.load_notes(user, run_id) or {}  # type: ignore[attr-defined]
        now = self._clock()  # type: ignore[attr-defined]
        self.store.save_notes(  # type: ignore[attr-defined]
            user,
            run_id,
            {**notes, "policy_choice": {"choice": choice.model_dump(mode="json"), "at": now}},
        )
        sections = [section if s.key == POLICY_SECTION else s for s in current.sections]
        if not any(s.key == POLICY_SECTION for s in sections):
            sections.append(section)
        if same_content(current.sections, sections):
            self._refresh_problems(user, run_id, state)  # type: ignore[attr-defined]
            self._save(state)  # type: ignore[attr-defined]
            return current
        new_version = DraftVersion(
            version=current.version + 1,
            origin="edit",
            sections=sections,
            created_at=now,
            note=POLICY_NOTE,
            changed_sections=changed_sections(current.sections, sections),
            annotations=current.annotations,
            evidence_decisions=decisions_for_sections(sections, current.evidence_decisions),
            figures=list(current.figures),
        )
        self._store_version(user, run_id, state, new_version, nxt)  # type: ignore[attr-defined]
        return self.store.load_version(user, run_id, new_version.version) or new_version  # type: ignore[attr-defined]
