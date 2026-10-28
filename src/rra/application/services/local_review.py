"""L2 로컬 2차 검토의 제안 처리 — RunManager 에 섞어 쓰는 메서드 묶음 (2026-10-28 레인 B, ADR 0040).

- local_review: 현재 버전 문장별 판정(지지·부분·불일치)과 불일치 문장의 Argon 제안.
- apply_local_suggestion: [반영] — 보통 편집 경로(apply_edits)로 새 버전. 다시 쓰기 = 직접 수정(원래
  근거 유지, proposer_edit), 빼기 = 삭제. 제안 상태 applied + 버전 번호.
- dismiss_local_suggestion: [무시] — 결정 기록만(새 버전 없음). 제안 상태 dismissed + 시각, 같은
  기록을 proposer_notes.json "local_review_decisions" 에도 남긴다. 그 문장의 불일치 알림은 사라진다.
- retry_local_suggestion: 제안 받기 실패(또는 다시 받기) — 그 문장만 Argon 에 다시 묻는다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rra.application.usecases.local_review_suggest import LocalReviewSuggester
from rra.domain.models import DraftVersion
from rra.domain.models.review import EditRequest, SentenceEdit, parse_sentence_id
from rra.domain.rules.local_review import review_view
from rra.domain.rules.writer import text_hash

if TYPE_CHECKING:  # pragma: no cover
    from rra.domain.models import RunState

APPLY_NOTE = "로컬 검토 제안 반영"


def _rm():
    from rra.application.services import run_manager as rm

    return rm


class LocalReviewMixin:
    """RunManager 전용 — self.store·status·_save·_current_version·apply_edits·_generate_for 를
    쓴다."""

    local_reviewer: LocalReviewSuggester | None = None  # 조립(composition)이 넣는다

    async def local_review(self, user: str, run_id: str) -> dict[str, Any]:
        state = await self.status(user, run_id)  # type: ignore[attr-defined]
        version = self._current_version(user, run_id, state)  # type: ignore[attr-defined]
        return local_review_view(state, version)

    def _find_suggestion(self, state: RunState, suggestion_id: str) -> dict[str, Any]:
        lc = state.local_check or {}
        for s in lc.get("suggestions") or []:
            if s.get("id") == suggestion_id:
                return s
        raise _rm().EditRejected("그런 로컬 검토 제안이 없습니다.")

    def _locate(self, version: DraftVersion, sugg: dict[str, Any]) -> str | None:
        """제안의 문장이 지금 버전 어디에 있는지 (글자 해시로) — 없으면 None(이미 바뀜)."""
        for sec in version.sections:
            if sec.key != sugg.get("section"):
                continue
            for i, s in enumerate(sec.sentences):
                if text_hash(s.text) == sugg.get("text_hash"):
                    return f"s:{sec.key}:{i}"
        return None

    def _set_status(self, user: str, run_id: str, state: RunState, sid: str, **update: Any) -> None:
        lc = dict(state.local_check or {})
        lc["suggestions"] = [
            {**s, **update} if s.get("id") == sid else s for s in lc.get("suggestions") or []
        ]
        state.local_check = lc
        notes = self.store.load_notes(user, run_id) or {}  # type: ignore[attr-defined]
        decisions = list(notes.get("local_review_decisions") or [])
        decisions.append({"id": sid, **{k: v for k, v in update.items() if k != "text"}})
        self.store.save_notes(user, run_id, {**notes, "local_review_decisions": decisions[-500:]})  # type: ignore[attr-defined]
        self._refresh_problems(user, run_id, state)  # type: ignore[attr-defined]
        self._save(state)  # type: ignore[attr-defined]

    async def apply_local_suggestion(
        self, user: str, run_id: str, suggestion_id: str, *, base_version: int | None = None
    ) -> DraftVersion:
        """[반영] — 보통 편집 경로로 새 버전 (같은 내용이면 새 버전 없음)."""
        rm = _rm()
        state = await self.status(user, run_id)  # type: ignore[attr-defined]
        sugg = self._find_suggestion(state, suggestion_id)
        if sugg.get("status") != "open" or sugg.get("action") not in ("rewrite", "remove"):
            raise rm.EditRejected(
                "반영할 수 있는 제안이 아닙니다 (이미 결정했거나 제안 받기 실패)."
            )
        if self.store.load_working(user, run_id) is not None:  # type: ignore[attr-defined]
            raise rm.EditRejected(
                "저장하지 않은 편집이 있습니다 — 먼저 저장하거나 버린 뒤 반영하십시오."
            )
        version = self._current_version(user, run_id, state)  # type: ignore[attr-defined]
        sid = self._locate(version, sugg)
        if sid is None:
            raise rm.EditRejected("그 문장이 이미 바뀌었습니다 — 최신 버전을 불러오십시오.")
        edit = (
            SentenceEdit(sentence_id=sid, action="manual", text=str(sugg.get("text") or ""))
            if sugg["action"] == "rewrite"
            else SentenceEdit(sentence_id=sid, action="delete")
        )
        new = await self.apply_edits(  # type: ignore[attr-defined]
            user,
            run_id,
            EditRequest(sentences=[edit], note=APPLY_NOTE, base_version=base_version),
        )
        state = await self.status(user, run_id)  # type: ignore[attr-defined]
        self._set_status(
            user,
            run_id,
            state,
            suggestion_id,
            status="applied",
            version=new.version,
            decided_at=self._clock(),  # type: ignore[attr-defined]
        )
        return new

    async def dismiss_local_suggestion(
        self, user: str, run_id: str, suggestion_id: str
    ) -> dict[str, Any]:
        """[무시] — 결정 기록만. 새 버전을 만들지 않는다."""
        state = await self.status(user, run_id)  # type: ignore[attr-defined]
        sugg = self._find_suggestion(state, suggestion_id)
        if sugg.get("status") in ("applied",):
            raise _rm().EditRejected("이미 반영한 제안입니다.")
        self._set_status(
            user,
            run_id,
            state,
            suggestion_id,
            status="dismissed",
            decided_at=self._clock(),  # type: ignore[attr-defined]
        )
        version = self._current_version(user, run_id, state)  # type: ignore[attr-defined]
        # 레인 D 확인 기록(versions/marks_vN.json)에도 한 줄 — 상태 표시는 새 버전을 만들지 않는다
        record = getattr(self, "record_mark", None)
        if record is not None:
            where = self._locate(version, sugg) or ""
            await record(
                user, run_id, "suggestion_ignore", target=where, label="로컬 검토 제안 무시"
            )
        return local_review_view(state, version)

    async def retry_local_suggestion(
        self, user: str, run_id: str, suggestion_id: str
    ) -> dict[str, Any]:
        """제안 다시 받기 — 그 문장만 Argon 에 다시 묻는다(실패 사유가 보였던 것)."""
        rm = _rm()
        if self.local_reviewer is None:
            raise rm.FeatureDisabled("로컬 검토 제안 모델이 없습니다.")
        state = await self.status(user, run_id)  # type: ignore[attr-defined]
        sugg = self._find_suggestion(state, suggestion_id)
        if sugg.get("status") in ("applied", "dismissed"):
            raise rm.EditRejected("이미 결정한 제안입니다.")
        version = self._current_version(user, run_id, state)  # type: ignore[attr-defined]
        sid = self._locate(version, sugg)
        if sid is None:
            raise rm.EditRejected("그 문장이 이미 바뀌었습니다 — 최신 버전을 불러오십시오.")
        parsed = parse_sentence_id(sid)
        if parsed is None:  # _locate 가 만든 id 라 오지 않는다
            raise rm.EditRejected("문장 위치를 찾지 못했습니다.")
        key, idx = parsed
        snapshot = self.store.load_snapshot(user, run_id)  # type: ignore[attr-defined]
        by_id: dict[str, Any] = {}
        for c in snapshot.chunks if snapshot is not None else []:
            by_id[c.chunk_id] = c
            by_id.setdefault(c.doc_id, c)
        gen = self._generate_for(state)  # type: ignore[attr-defined]
        fresh = await self.local_reviewer.suggest_one(
            version.section(key), idx, by_id, include_internal=gen.writer_include_internal
        )
        state = await self.status(user, run_id)  # type: ignore[attr-defined]
        lc = dict(state.local_check or {})
        lc["suggestions"] = [
            fresh if s.get("id") == suggestion_id else s for s in lc.get("suggestions") or []
        ]
        state.local_check = lc
        self._save(state)  # type: ignore[attr-defined]
        return local_review_view(state, version)


def local_review_view(state: Any, version: DraftVersion) -> dict[str, Any]:
    """화면용 — 문장 id 별 판정·제안 (현재 버전 기준). 규칙은
    domain/rules/local_review.review_view."""
    return review_view(state.local_check, version.sections)
