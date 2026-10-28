"""L2 로컬 검토 불일치 → Argon "근거 안에서 다시 쓰기 또는 빼기" 제안 (2026-10-28 레인 B, ADR 0040).

로컬 모델이 "불일치" 로 판정한 문장만 그 근거와 함께 Argon(review 단계, 예산·공유 제한기)에 보낸다.
Argon 이 오류로 답하지 못할 때만 로컬(argon_first). 응답은
domain/rules/local_review.validate_suggestion
을 지나야 한다 — 다시 쓴 문장이 근거 밖 이름·수치를 담으면 "빼기" 제안으로 바뀐다. 제안은 run 의
state.local_check["suggestions"] 에 남고 자동으로 반영되지 않는다.
공용 계정 run(include_internal=False)은 사내 전용(internal) 근거를 원격 프롬프트에 넣지 않는다 —
근거가
전부 사내 전용이면 그 문장은 보내지 않고 사유를 남긴다.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from rra.application.usecases.argon_first import ArgonFirst
from rra.domain.models import Chunk, Section
from rra.domain.models.review import sentence_id
from rra.domain.rules.local_review import (
    LOCAL_SUGGEST_SYSTEM,
    suggest_prompt,
    suggestion_id,
    validate_suggestion,
)
from rra.domain.rules.writer import text_hash

INTERNAL_ONLY = "internal_only"
REASON_LABELS: dict[str, str] = {
    INTERNAL_ONLY: "근거가 사내 전용 자료라 Argon 에 보내지 않음",
}


def _utcnow() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class LocalReviewSuggester:
    ask: ArgonFirst
    clock: Callable[[], str] = field(default=_utcnow)

    async def suggest_one(
        self,
        section: Section,
        index: int,
        chunks: Mapping[str, Chunk],
        *,
        include_internal: bool = True,
    ) -> dict[str, Any]:
        """문장 하나 → 제안 기록 {id, section, sentence, text_hash, original, action, text, reason,
        filtered, status, evidence, model, fallback, calls, at}. 실패면 status=failed + reason."""
        sent = section.sentences[index]
        evidence = [chunks[e] for e in sent.evidence if e in chunks]
        sendable = [c for c in evidence if include_internal or c.visibility != "internal"]
        base: dict[str, Any] = {
            "id": suggestion_id(section.key, sent.text),
            "section": section.key,
            "sentence": index,
            "sentence_id": sentence_id(section.key, index),
            "text_hash": text_hash(sent.text),
            "original": sent.text,
            "evidence": list(sent.evidence),
            "at": self.clock(),
        }
        if not sendable:
            return {
                **base,
                "status": "failed",
                "reason": INTERNAL_ONLY if evidence else "empty",
                "reason_label": REASON_LABELS.get(INTERNAL_ONLY) if evidence else "근거 없음",
                "action": None,
                "text": "",
            }

        def check(raw: str) -> tuple[dict[str, Any] | None, str | None]:
            return validate_suggestion(raw, sent.text, sendable)

        result = await self.ask.ask(
            suggest_prompt(section.key, sent.text, sendable),
            system=LOCAL_SUGGEST_SYSTEM,
            check=check,
        )
        record = result.record()
        if result.value is None:
            return {
                **base,
                "status": "failed",
                "reason": result.reason,
                "reason_label": result.reason_label,
                "action": None,
                "text": "",
                "model": record["model"],
                "fallback": record["fallback"],
                "calls": record["calls"],
            }
        return {
            **base,
            **result.value,
            "status": "open",
            "model": record["model"],
            "fallback": record["fallback"],
            "calls": record["calls"],
        }

    async def attach(
        self,
        sections: Sequence[Section],
        chunks: Sequence[Chunk],
        local_check: Mapping[str, Any],
        *,
        include_internal: bool = True,
    ) -> dict[str, Any]:
        """local_check 결과에 불일치 문장마다 제안을 붙인다 (이미 결정한 제안은 그대로 둔다)."""
        by_id: dict[str, Chunk] = {}
        for c in chunks:
            by_id[c.chunk_id] = c
            by_id.setdefault(c.doc_id, c)
        wanted = set(local_check.get("mismatch_hashes") or [])
        prior = {s.get("id"): s for s in local_check.get("suggestions") or []}
        out: list[dict[str, Any]] = []
        started = time.monotonic()
        for sec in sections:
            for i, s in enumerate(sec.sentences):
                if not s.evidence or text_hash(s.text) not in wanted:
                    continue
                sid = suggestion_id(sec.key, s.text)
                old = prior.get(sid)
                if old is not None and old.get("status") != "failed":
                    out.append({**old, "sentence": i, "sentence_id": sentence_id(sec.key, i)})
                    continue
                out.append(await self.suggest_one(sec, i, by_id, include_internal=include_internal))
        return {
            **local_check,
            "suggestions": out,
            "suggest_seconds": round(time.monotonic() - started, 1),
        }
