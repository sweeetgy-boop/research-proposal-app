"""② 유사과제 행 정리·제안자 선택 규칙 — 순수 함수 (2026-10-28 레인 A).

- merge_same_titles: 제목이 같은 행(NTIS 과제번호만 다른 중복 등)을 한 행으로. 앞(상위) 행을 남기고
  나머지 doc_id 는 merged_ids 에. 차단은 어느 하나라도 차단이면 차단.
- apply_choices: 제안자 선택([유사함]/[관련 없음])을 행에 붙인다. [관련 없음] 행은 차단에서 빠진다.
  차단 행을 모두 [관련 없음] 으로 고르면 차단이 풀린다(released).
- similar_alerts: [유사함] 으로 고른 행만 — 비교표·활용 제안·차별화 과제안·본문 차별성 문장의 입력.
- rows_for_writing: ③ 5. 특이사항 판정표 — [관련 없음] 행은 빼고, [유사함] 행은 "중복 검토 대상"
  (blocking) 으로 쓴다. 선택이 없으면 종전과 같다.
- choice_records: 임계치 조정용 선택 기록(JSONL 한 줄씩) — doc_id·선택·점수·시각·아이디어 해시만.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from rra.domain.models import OverlapAlert

_TITLE_NOISE = re.compile(r"[^0-9a-z가-힣]+")
IDEA_HASH_CHARS = 16
SIMILAR = "similar"
UNRELATED = "unrelated"


def title_key(title: str) -> str:
    """제목 비교 키 — 소문자, 한글·영숫자만 (dedup 의 제목 정규화와 같다)."""
    return _TITLE_NOISE.sub("", (title or "").lower())


def merge_same_titles(alerts: Sequence[OverlapAlert]) -> list[OverlapAlert]:
    """같은 제목 행을 한 행으로 (순서 유지). 제목 키가 4자 미만이면 합치지 않는다."""
    out: list[OverlapAlert] = []
    index: dict[str, int] = {}
    for a in alerts:
        key = title_key(a.title)
        if len(key) < 4 or key not in index:
            if len(key) >= 4:
                index[key] = len(out)
            out.append(a)
            continue
        i = index[key]
        kept = out[i]
        merged = list(dict.fromkeys([*kept.merged_ids, a.doc_id, *a.merged_ids]))
        keywords = list(dict.fromkeys([*kept.keywords, *a.keywords]))
        update: dict[str, Any] = {
            "merged_ids": [m for m in merged if m != kept.doc_id],
            "keywords": keywords,
            "blocking": kept.blocking or a.blocking,
            "rule_blocking": bool(kept.rule_blocking) or bool(a.rule_blocking),
        }
        if (a.rerank_score or 0) > (kept.rerank_score or 0):
            update["rerank_score"] = a.rerank_score
        if a.similarity > kept.similarity:
            update["similarity"] = a.similarity
        out[i] = kept.model_copy(update=update)
    return out


def _ids(alert: OverlapAlert) -> list[str]:
    return [alert.doc_id, *alert.merged_ids]


def choice_for(alert: OverlapAlert, choices: Mapping[str, str]) -> str | None:
    """행의 선택 — 대표 doc_id 또는 합쳐진 doc_id 중 하나에 대한 선택."""
    for i in _ids(alert):
        if i in choices:
            return choices[i]
    return None


def apply_choices(
    alerts: Sequence[OverlapAlert], choices: Mapping[str, str]
) -> tuple[list[OverlapAlert], bool]:
    """선택을 붙인 행 + 차단 해제 여부(released).

    released = 선택 전 차단 행이 있었고, 그 차단 행이 모두 [관련 없음] 이라 이제 차단이 없다."""
    had_block = any(a.blocking for a in alerts)
    out: list[OverlapAlert] = []
    for a in alerts:
        c = choice_for(a, choices)
        update: dict[str, Any] = {"choice": c}
        if c == UNRELATED:
            update["blocking"] = False
        out.append(a.model_copy(update=update))
    released = had_block and not any(a.blocking for a in out)
    return out, released


def effective_blocking(alerts: Sequence[OverlapAlert], choices: Mapping[str, str]) -> bool:
    """선택을 반영한 차단 여부 — 차단 행 중 [관련 없음] 이 아닌 것이 있으면 True."""
    return any(a.blocking and choice_for(a, choices) != UNRELATED for a in alerts)


def similar_alerts(
    alerts: Sequence[OverlapAlert], choices: Mapping[str, str]
) -> list[OverlapAlert]:
    """[유사함] 으로 고른 행만 (순서 유지)."""
    return [a for a in alerts if choice_for(a, choices) == SIMILAR]


def rows_for_writing(
    alerts: Sequence[OverlapAlert], choices: Mapping[str, str]
) -> list[OverlapAlert]:
    """③ 5. 특이사항 판정표 — 선택이 없으면 그대로. 있으면 [관련 없음] 행을 빼고 [유사함] 행만
    중복 검토 대상(blocking=True)으로, 고르지 않은 행은 참고(blocking=False)로 — 본문 차별성 문장은
    [유사함] 행에 대해서만 쓴다."""
    if not choices:
        return list(alerts)
    out: list[OverlapAlert] = []
    for a in alerts:
        c = choice_for(a, choices)
        if c == UNRELATED:
            continue
        out.append(a.model_copy(update={"blocking": c == SIMILAR, "choice": c}))
    return out


def missing_similar_ids(
    alerts: Iterable[OverlapAlert], choices: Mapping[str, str]
) -> list[str]:
    """[유사함] 으로 골랐지만 이번 판정 목록에 없는 doc_id (③ 이 문서를 따로 읽어 넣는다)."""
    have = {i for a in alerts for i in _ids(a)}
    return [d for d, c in choices.items() if c == SIMILAR and d not in have]


def idea_hash(search_text: str) -> str:
    """아이디어 글의 해시 앞 16자 — 선택 기록에 원문 대신 남긴다."""
    norm = " ".join((search_text or "").split()).casefold()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:IDEA_HASH_CHARS]


def choice_records(
    alerts: Sequence[OverlapAlert],
    choices: Mapping[str, str],
    *,
    idea: str,
    at: str,
    released: bool = False,
) -> list[dict[str, Any]]:
    """선택한 행마다 한 줄 — 임계치 조정용. 개인정보·본문 없음(doc_id·점수·판정·해시·시각)."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for a in alerts:
        c = choice_for(a, choices)
        if c is None or a.doc_id in seen:
            continue
        seen.add(a.doc_id)
        out.append(
            {
                "at": at,
                "idea": idea,
                "doc_id": a.doc_id,
                "merged_ids": list(a.merged_ids),
                "choice": c,
                "tier": a.tier,
                "similarity": round(a.similarity, 4),
                "rerank_score": a.rerank_score,
                "keywords": len(a.keywords),
                "rule_blocking": a.rule_blocking,
                "judgment": a.judgment,
                "judged_by": a.judged_by,
                "blocking": a.blocking,
                "released": released,
            }
        )
    return out
