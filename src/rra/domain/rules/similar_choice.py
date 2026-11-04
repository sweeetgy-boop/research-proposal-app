"""② 유사과제 행 정리·제안자 선택 규칙 — 순수 함수 (2026-10-28 레인 A).

- merge_same_titles: 제목이 같은 행(NTIS 과제번호만 다른 중복 등)을 한 행으로. 앞(상위) 행을 남기고
  나머지 doc_id 는 merged_ids 에. 차단은 어느 하나라도 차단이면 차단.
- apply_choices: 제안자 선택([유사함]/[관련 없음])을 행에 붙인다. [관련 없음] 행은 차단에서 빠진다.
  차단 행을 모두 [관련 없음] 으로 고르면 차단이 풀린다(released).
- effective_choice / effective_similar (ADR 0054): 행의 유효 선택 = 제안자 선택, 없으면 AI
  판정의 기본 선택(같다·일부 겹침 → [유사함], 다르다 → [관련 없음]). 규칙 판정·AI 실패·판정 전
  행은 기본 선택이 없다(유사함 아님). [유사함] 건수·'새 영역' 다시 받기·과제안 근거·비교표·활용
  제안은 모두 이 규칙을 application/usecases/similar_rows 로 거쳐 쓴다. 차단 게이트
  (effective_blocking)는 제안자 선택만 본다.
- rows_for_writing: ③ 5. 특이사항 판정표 — [관련 없음] 행은 빼고, [유사함] 행은 "중복 검토 대상"
  (blocking) 으로 쓴다. 선택이 없으면 종전과 같다.
- choice_records: 임계치 조정용 선택 기록(JSONL 한 줄씩) — doc_id·선택·출처·점수·시각·아이디어
  해시만. 출처(source, ADR 0056)는 user(제안자가 직접 바꾼 값)·ai_prefill(화면이 미리 고른 AI
  기본 선택이 그대로 남은 값). 출처는 기록용 메타데이터 — 위 규칙(차단·유효 선택·건수)은 출처를
  보지 않는다.
- 기록 시점·중복 한 줄 (ADR 0056 2026-11-04 후속): 줄마다 event — generate(생성 요청)·apply(②
  [선택 적용]). 같은 세션(로그인 주체 + 아이디어 해시)이 같은 서명(event + (doc_id, 선택, 출처)
  집합)을 잇따라 보내면 한 줄 묶음만 쓴다(choice_signature·is_repeat). 서명에 event 가 들어가므로
  [선택 적용] 뒤 같은 선택의 생성 요청은 다른 사건이라 둘 다 남는다. 마지막 서명은 진입점의 메모리.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from rra.domain.models import OverlapAlert

_TITLE_NOISE = re.compile(r"[^0-9a-z가-힣]+")
IDEA_HASH_CHARS = 16
SIMILAR = "similar"
UNRELATED = "unrelated"
_DEFAULT_BY_VERDICT: dict[str, str] = {"same": SIMILAR, "partial": SIMILAR, "different": UNRELATED}
# 선택 출처 (ADR 0056) — 보내지 않은 선택은 USER (domain/models/request.SimilarChoice.source 기본값)
SOURCE_USER = "user"
SOURCE_AI_PREFILL = "ai_prefill"
# 기록 시점 (ADR 0056 후속, 2026-11-04) — event 가 없는 옛 줄은 2026-11-04 이전의 생성 요청 기록
EVENT_GENERATE = "generate"
EVENT_APPLY = "apply"
EVENTS = (EVENT_APPLY, EVENT_GENERATE)
SESSION_KEY_CHARS = 16


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


def _chosen_id(alert: OverlapAlert, choices: Mapping[str, str]) -> str | None:
    """선택이 걸린 doc_id — 대표 doc_id 먼저, 다음 합쳐진 doc_id."""
    for i in _ids(alert):
        if i in choices:
            return i
    return None


def choice_for(alert: OverlapAlert, choices: Mapping[str, str]) -> str | None:
    """행의 선택 — 대표 doc_id 또는 합쳐진 doc_id 중 하나에 대한 선택."""
    i = _chosen_id(alert, choices)
    return choices[i] if i is not None else None


def default_choice(alert: OverlapAlert) -> str | None:
    """AI 판정의 기본 선택 (ADR 0054) — 같다·일부 겹침 → similar, 다르다 → unrelated.
    AI 판정이 없으면(규칙 판정·AI 실패·판정 전) None."""
    if getattr(alert, "judged_by", None) == "rule":
        return None
    return _DEFAULT_BY_VERDICT.get(getattr(alert, "judgment", None) or "")


def effective_choice(alert: OverlapAlert, choices: Mapping[str, str]) -> str | None:
    """행의 유효 선택 — 제안자 선택이 이기고, 없으면 AI 판정의 기본 선택 (ADR 0054)."""
    chosen = choice_for(alert, choices)
    return chosen if chosen is not None else default_choice(alert)


def effective_similar(
    alerts: Sequence[OverlapAlert], choices: Mapping[str, str]
) -> list[OverlapAlert]:
    """유효 선택이 [유사함] 인 행 (순서 유지) — 비교표·활용 제안·과제안·건수의 입력."""
    return [a for a in alerts if effective_choice(a, choices) == SIMILAR]


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


def missing_similar_ids(alerts: Iterable[OverlapAlert], choices: Mapping[str, str]) -> list[str]:
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
    sources: Mapping[str, str] | None = None,
    event: str = EVENT_GENERATE,
) -> list[dict[str, Any]]:
    """선택한 행마다 한 줄 — 임계치 조정용. 개인정보·본문 없음(doc_id·점수·판정·해시·시각).
    제안자가 보낸 선택만 남긴다 — 서버의 AI 기본 선택(effective_choice)은 선택 기록이 아니다
    (ADR 0054). 줄마다 source — 그 선택의 출처(sources: doc_id → user | ai_prefill, 선택이 걸린
    doc_id 기준). sources 에 없으면 user (ADR 0056). 줄마다 event — generate(생성 요청, 기본)·
    apply([선택 적용]) (ADR 0056 후속)."""
    if event not in EVENTS:
        raise ValueError(f"모르는 기록 시점: {event}")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for a in alerts:
        chosen = _chosen_id(a, choices)
        if chosen is None or a.doc_id in seen:
            continue
        c = choices[chosen]
        seen.add(a.doc_id)
        out.append(
            {
                "at": at,
                "event": event,
                "idea": idea,
                "doc_id": a.doc_id,
                "merged_ids": list(a.merged_ids),
                "choice": c,
                "source": (sources or {}).get(chosen, SOURCE_USER),
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


def choice_signature(records: Sequence[Mapping[str, Any]]) -> str | None:
    """같은 선택인지 가리는 서명 — event + (doc_id, 선택, 출처) 집합의 해시 (ADR 0056 후속).
    점수·판정·시각·차단 해제는 서명에 들지 않는다. 줄이 없으면 None(쓸 것이 없다)."""
    if not records:
        return None
    events = sorted({str(r.get("event") or EVENT_GENERATE) for r in records})
    items = sorted(
        {(str(r["doc_id"]), str(r["choice"]), str(r.get("source") or SOURCE_USER)) for r in records}
    )
    payload = json.dumps([events, items], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_repeat(last_signature: str | None, signature: str | None) -> bool:
    """마지막으로 기록한 서명과 같으면 True — 쓰지 않는다. 사이에 다른 서명이 기록되면 마지막
    서명이 바뀌므로 다시 쓴다. 서명이 없으면(줄 없음) 반복이 아니다."""
    return signature is not None and last_signature == signature


def session_key(owner: str, idea: str) -> str:
    """중복 판정의 세션 키 — 로그인 주체 키 + 아이디어 해시의 해시 앞 16자. 주체 키를 그대로
    들고 다니지 않는다. 메모리에만 두고 기록 줄에는 쓰지 않는다."""
    raw = "\x00".join((owner or "", idea or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:SESSION_KEY_CHARS]
