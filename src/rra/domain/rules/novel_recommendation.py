"""새 과제 추천(novel 갈래, ADR 0057)의 순수 규칙 — LLM 출력 검증·중복 제거·정렬·상한.

계약 docs/contracts/novel-recommend.md 3.3. LLM 출력은 비신뢰(보안 A) — 구획 태그를 무력화하고
길이를 자른 뒤, 아래를 지키는 안만 남긴다.

- 모든 과제명(title)은 장벽(barrier) 하나 이상을 가리킨다. 범위 밖 인덱스를 가리키면 그 과제명을
  버리고, 과제명이 0개가 되면 안을 버린다(`novel_no_title`).
- '근거 있음' 장벽의 doc_ids 는 이번 입력 구획([참고 논문]·[다른 분야 사례]·[근거]) 안에 있어야
  한다. 범위 밖 id 가 하나라도 있으면 지어낸 근거로 보고 안을 버린다(`novel_basis_out_of_range`).
  '근거 있음' 인데 id 가 하나도 없으면 '추정' 으로 낮춘다(확인 방법이 없으면 그 장벽을 버린다).
- '추정' 장벽은 확인 방법(check)이 있어야 한다. 없으면 그 장벽을 버리고 과제명의 인덱스를
  다시 매긴다(그 장벽만 가리키던 과제명은 버려진다).
- 글 칸(접근 방식·요약·첫 단계·단계·장벽·확인 방법·과제명·이유)에 입력에 없는 수치·정책·계획명
  (기존 `recommendation` 규칙)·법령명·조항·기관명(`unsupported_names`)·한자·가나가 있으면 안을
  버린다.
- 장벽 유형은 5갈래(수요·규제·비용·기술·운영)에 하나씩, 최대 5. 단계는 기획 → 시범 → 확대 순.
- 거의 같은 접근 방식의 안은 앞의 것만(`duplicate`), 최대 3(`novel_over_limit`).
- 정렬: 과제명은 해소 장벽 수가 많은 순, 안은 성숙도(즉시 적용 → 실증 필요 → 연구 필요)·근거 수가
  많은 순.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from rra.domain.models.novel import (
    BARRIER_TYPES,
    BASIS_ESTIMATED,
    BASIS_EVIDENCED,
    MATURITIES,
    MAX_BARRIERS,
    MAX_NOVEL,
    MAX_NOVEL_CHARS,
    MAX_NOVEL_TITLE_CHARS,
    MAX_TITLES,
    STAGE_NAMES,
    Barrier,
    BarrierBasis,
    NovelRecommendation,
    NovelStage,
    NovelTitle,
)
from rra.domain.rules.foreign_script import has_foreign_script
from rra.domain.rules.grounding import ungrounded
from rra.domain.rules.keywords import tokens
from rra.domain.rules.llm_output import clean_sentence
from rra.domain.rules.numbers import unsupported_numbers
from rra.domain.rules.recommendation import (
    DISCARD_DUPLICATE,
    DISCARD_FOREIGN,
    DISCARD_NUMBER,
    DISCARD_UNGROUNDED,
    DUPLICATE_RATIO,
    discard_label,
)
from rra.domain.rules.trust import escape_untrusted, normalize_evidence_id

DISCARD_NOVEL_EMPTY = "novel_empty_fields"
DISCARD_NOVEL_NO_TITLE = "novel_no_title"
DISCARD_NOVEL_BASIS = "novel_basis_out_of_range"
DISCARD_NOVEL_NAME = "novel_unsupported_name"
DISCARD_NOVEL_OVER_LIMIT = "novel_over_limit"

NOVEL_DISCARD_LABELS: dict[str, str] = {
    DISCARD_NOVEL_EMPTY: "필수 칸(접근 방식·요약)이 비어 있음",
    DISCARD_NOVEL_NO_TITLE: "장벽을 가리키는 과제명이 없음",
    DISCARD_NOVEL_BASIS: "장벽 근거 자료가 이번 확인 범위 밖임",
    DISCARD_NOVEL_NAME: "자료·입력에 없는 법령·기관 이름을 씀",
    DISCARD_NOVEL_OVER_LIMIT: "3건을 넘음",
}

# 새로움 확인(coverage)에서 확인 못 한 자료원 사유 (계약 3.1 열거값) — 화면 한 줄
COVERAGE_STATUS_LABELS: dict[str, str] = {
    "ip_blocked": "서버 IP 등록 필요로 확인 못 함",
    "timeout": "응답 시간 초과로 확인 못 함",
    "error": "오류로 확인 못 함",
    "off": "실시간 검색이 꺼져 있어 확인 못 함",
    "no_key": "이용 키가 없어 확인 못 함",
    "rate_limited": "일일 호출 한도 초과로 확인 못 함",
}
UNKNOWN_COVERAGE_STATUS = "확인 못 함"
# 계약 3.1 — 실시간 검색을 하지 않았을 때(live=false)의 확인 범위 문구
COVERAGE_NOTE_STORED = "저장 자료 범위 안에서 기존 과제 없음"

MAX_TITLE_PRINCIPLES = 3  # NovelTitle.principles 상한
NO_NOVEL_REASON = "만들 만한 새 과제안이 없음"
EXCLUDED_SUFFIX = "검증에서 제외됨 {n}건"

# 0건 다시 받기 지시 (계약 3.3 — 1회)
NOVEL_RETRY_HINT = (
    "[새 과제안 다시] 앞 응답에서 남은 새 과제안이 없다. 접근 방식이 서로 다른 안 2~3건을 다시 "
    "낸다. 과제명마다 해소하는 장벽 인덱스(resolves)를 반드시 쓰고, '추정' 장벽에는 확인 방법"
    "(check)을 쓴다. '근거 있음' 장벽의 doc_ids 는 입력 구획에 있는 id 만 쓴다. 입력에 없는 수치·"
    "법령명·조항·기관명을 쓰지 않는다."
)

_MATURITY_ORDER = {m: i for i, m in enumerate(MATURITIES)}
_STAGE_ORDER = {s: i for i, s in enumerate(STAGE_NAMES)}
_SQUASH = re.compile(r"\s+")

# 법령명·조항 — 보수적으로(놓치는 것보다 과하게 버리는 쪽).
# "…법률·시행령·규정" 은 grounding 이 잡는다.
_ARTICLE = re.compile(r"제\s?\d+\s?조(?:\s?제\s?\d+\s?항)?")
_LAW = re.compile(
    r"[가-힣A-Za-z0-9·]*(?:안전법|보호법|관리법|사업법|진흥법|기본법|촉진법|특별법|처벌법|보건법|"
    r"위생법|건축법|철도법|도로법|운송법|정비법|규제법|육성법|방지법|조례)"
)
# 기관명 — 정부 부처·청·공공기관 꼬리. "공사"(공사 작업)·"…부"(상부·접합부) 처럼 일반어와 겹치는
# 꼬리는 부처 어간이 붙은 것만 본다.
_AGENCY = re.compile(
    r"[가-힣A-Za-z0-9·]{2,}(?:위원회|공단|진흥원|진흥회|협회|재단)"
    r"|[가-힣]*(?:교통|환경|자원|안전|복지|가족|통상|외교|국방|통일|법무|교육|체육|관광|노동|재정|"
    r"정보통신|벤처|수산|식품|과학기술)부"
    r"|[가-힣]*(?:경찰|소방|조달|통계|산림|기상|문화재|국가유산|특허|관세|국세|질병관리|"
    r"식품의약품안전)청"
)


def novel_discard_label(reason: str) -> str:
    """새 과제안 폐기 사유 → 한국어 (공통 사유는 `recommendation.discard_label`)."""
    return NOVEL_DISCARD_LABELS.get(reason) or discard_label(reason)


def coverage_status_label(status: str) -> str:
    return COVERAGE_STATUS_LABELS.get(status, UNKNOWN_COVERAGE_STATUS)


def _squash(text: str) -> str:
    return _SQUASH.sub("", text or "")


def unsupported_names(text: str, allowed_texts: Iterable[str]) -> list[str]:
    """글에 나온 법령명·조항·기관명 중 허용 텍스트(입력·자료)에 없는 것. 비어 있으면 통과.
    대조는 공백을 없앤 부분 문자열 비교(grounding 과 같다)."""
    haystack = _squash(" ".join(allowed_texts))
    found: list[str] = []
    for pattern in (_ARTICLE, _LAW, _AGENCY):
        for m in pattern.finditer(text or ""):
            name = _squash(m.group(0))
            if name and name not in haystack and name not in found:
                found.append(name)
    return found


def _text(value: Any, limit: int = MAX_NOVEL_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    return clean_sentence(escape_untrusted(value)).strip()[:limit]


def _bad(text: str, allowed: list[str]) -> str | None:
    """글 하나의 검사 — 어긋나면 사유 코드."""
    if not text:
        return None
    if has_foreign_script(text):
        return DISCARD_FOREIGN
    if unsupported_numbers(text, allowed):
        return DISCARD_NUMBER
    if ungrounded(text, allowed):
        return DISCARD_UNGROUNDED
    if unsupported_names(text, allowed):
        return DISCARD_NOVEL_NAME
    return None


def _enum(value: Any, choices: Iterable[str]) -> str | None:
    """'즉시적용'·' 규제 ' 처럼 공백만 다른 값도 받는다."""
    if not isinstance(value, str):
        return None
    key = _squash(value)
    for c in choices:
        if _squash(c) == key:
            return c
    return None


def _ids(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out = [normalize_evidence_id(v.strip()) for v in value if isinstance(v, str)]
    return list(dict.fromkeys(i for i in out if i))


def _index(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _barriers(
    raw: Any, allowed_ids: set[str], allowed: list[str]
) -> tuple[list[Barrier], dict[int, int], str | None]:
    """장벽 목록 → (남은 장벽, 원래 인덱스 → 새 인덱스, 안 폐기 사유)."""
    items = raw if isinstance(raw, list) else []
    kept: list[Barrier] = []
    remap: dict[int, int] = {}
    seen_types: set[str] = set()
    for i, b in enumerate(items):
        if not isinstance(b, Mapping):
            continue
        btype = _enum(b.get("type"), BARRIER_TYPES)
        statement = _text(b.get("statement"))
        if btype is None or not statement or btype in seen_types or len(kept) >= MAX_BARRIERS:
            continue
        basis = b.get("basis") if isinstance(b.get("basis"), Mapping) else {}
        level = _enum(basis.get("level"), (BASIS_EVIDENCED, BASIS_ESTIMATED)) or BASIS_ESTIMATED
        doc_ids = _ids(basis.get("doc_ids"))
        check = _text(b.get("check"))
        for text in (statement, check):
            bad = _bad(text, allowed)
            if bad:
                return [], {}, bad
        if level == BASIS_EVIDENCED:
            if any(d not in allowed_ids for d in doc_ids):
                return [], {}, DISCARD_NOVEL_BASIS  # 지어낸 근거
            if not doc_ids:
                level = BASIS_ESTIMATED  # 근거 id 없이 '근거 있음' → 추정으로 낮춘다
        if level == BASIS_ESTIMATED:
            doc_ids = [d for d in doc_ids if d in allowed_ids]
            if not check:
                continue  # 확인 방법 없는 추정 → 그 장벽만 버린다
        seen_types.add(btype)
        remap[i] = len(kept)
        kept.append(
            Barrier(
                type=btype,  # type: ignore[arg-type]
                statement=statement,
                basis=BarrierBasis(level=level, doc_ids=doc_ids),  # type: ignore[arg-type]
                check=check,
            )
        )
    return kept, remap, None


def _principles(value: Any, allowed_numbers: Sequence[int]) -> list[int]:
    """과제명이 기댄 발명 원리 번호 — 카드 모순에 붙은 번호 안에서만(밖의 번호만 뺀다, 안은 살린다).
    카드가 없으면(allowed_numbers 빔) 늘 빈 목록."""
    if not allowed_numbers:
        return []
    items = value if isinstance(value, list) else [value]
    out: list[int] = []
    for v in items:
        n = _index(v.get("number") if isinstance(v, Mapping) else v)
        if n is not None and n in allowed_numbers and n not in out:
            out.append(n)
    return out[:MAX_TITLE_PRINCIPLES]


def _titles(
    raw: Any,
    raw_barrier_count: int,
    remap: dict[int, int],
    allowed: list[str],
    principle_numbers: Sequence[int] = (),
) -> tuple[list[NovelTitle], str | None]:
    """과제명 → (남은 과제명 — 해소 장벽 수 많은 순, 안 폐기 사유)."""
    items = raw if isinstance(raw, list) else []
    out: list[NovelTitle] = []
    for t in items:
        if not isinstance(t, Mapping):
            continue
        title = _text(t.get("title"), MAX_NOVEL_TITLE_CHARS)
        reason = _text(t.get("reason"))
        if not title or not reason:
            continue
        resolves_raw = t.get("resolves")
        if not isinstance(resolves_raw, list):
            resolves_raw = [resolves_raw]
        indexes = [_index(v) for v in resolves_raw]
        if not indexes or any(i is None or i < 0 or i >= raw_barrier_count for i in indexes):
            continue  # 범위 밖 인덱스 → 그 과제명 버림
        resolves = list(dict.fromkeys(remap[i] for i in indexes if i in remap))  # type: ignore[index]
        if not resolves:
            continue  # 가리키던 장벽이 모두 버려짐
        for text in (title, reason):
            bad = _bad(text, allowed)
            if bad:
                return [], bad
        if any(near_same(title, o.title) for o in out):
            continue
        out.append(
            NovelTitle(
                title=title,
                resolves=sorted(resolves),
                reason=reason,
                principles=_principles(t.get("principles"), principle_numbers),
            )
        )
    out.sort(key=lambda x: -len(x.resolves))  # 안정 정렬 — 같은 수면 모델 순서
    return out[:MAX_TITLES], None


def _stages(raw: Any, allowed: list[str]) -> tuple[list[NovelStage], str | None]:
    items = raw if isinstance(raw, list) else []
    by_stage: dict[str, str] = {}
    for s in items:
        if not isinstance(s, Mapping):
            continue
        name = _enum(s.get("stage"), STAGE_NAMES)
        text = _text(s.get("text"))
        if name is None or not text or name in by_stage:
            continue
        bad = _bad(text, allowed)
        if bad:
            return [], bad
        by_stage[name] = text
    ordered = sorted(by_stage.items(), key=lambda kv: _STAGE_ORDER[kv[0]])
    return [NovelStage(stage=k, text=v) for k, v in ordered], None  # type: ignore[arg-type]


def validate_novel(
    raw: Mapping[str, Any],
    *,
    allowed_doc_ids: Iterable[str],
    allowed_texts: Iterable[str],
    reference_doc_ids: Iterable[str] = (),
    principle_numbers: Iterable[int] = (),
) -> tuple[NovelRecommendation | None, str | None]:
    """LLM 새 과제안 하나 → (검증된 안, None) 또는 (None, 폐기 사유).

    principle_numbers: 문제 정의 카드의 모순에 붙은 발명 원리 번호(ADR 0065). 과제명의
    `principles` 는 이 안의 번호만 남긴다. 비면(카드 없음) 과제명의 principles 는 늘 빈 목록.

    allowed_doc_ids 는 이번 입력 구획([참고 논문]·[다른 분야 사례]·[근거])에 실제로 넣은 doc_id.
    evidence 의 범위 밖 id 는 목록에서만 뺀다(안은 남김). 참고 논문(제안자 선택)을 앞에 둔다.
    refs 는 유스케이스가 제목·자료원으로 채운다."""
    ids = list(dict.fromkeys(allowed_doc_ids))
    id_set = set(ids)
    allowed = [*allowed_texts, *ids]  # id 표기(W1·own:1)는 수치가 아니다
    approach = _text(raw.get("approach"))
    summary = _text(raw.get("summary"))
    if not approach or not summary:
        return None, DISCARD_NOVEL_EMPTY
    first_step = _text(raw.get("first_step"))
    for text in (approach, summary, first_step):
        bad = _bad(text, allowed)
        if bad:
            return None, bad
    stages, bad = _stages(raw.get("stages"), allowed)
    if bad:
        return None, bad
    raw_barriers = raw.get("barriers") if isinstance(raw.get("barriers"), list) else []
    barriers, remap, bad = _barriers(raw_barriers, id_set, allowed)
    if bad:
        return None, bad
    titles, bad = _titles(
        raw.get("titles"), len(raw_barriers), remap, allowed, list(principle_numbers)
    )
    if bad:
        return None, bad
    if not titles:
        return None, DISCARD_NOVEL_NO_TITLE
    maturity = _enum(raw.get("maturity"), MATURITIES) or MATURITIES[-1]  # 모르면 '연구 필요'
    references = [r for r in reference_doc_ids if r in id_set]
    evidence = [i for i in _ids(raw.get("evidence")) if i in id_set]
    evidence = sorted(evidence, key=lambda i: (i not in references,))  # 참고 논문 먼저
    return (
        NovelRecommendation(
            approach=approach,
            summary=summary,
            first_step=first_step,
            stages=stages,
            maturity=maturity,  # type: ignore[arg-type]
            evidence=evidence,
            barriers=barriers,
            titles=titles,
        ),
        None,
    )


def ref_ids(rec: NovelRecommendation) -> list[str]:
    """화면 근거 목록에 보일 doc_id — evidence ∪ 장벽 근거 (순서 유지)."""
    out = list(rec.evidence)
    for b in rec.barriers:
        out.extend(b.basis.doc_ids)
    return list(dict.fromkeys(out))


def near_same(a: str, b: str, ratio: float = DUPLICATE_RATIO) -> bool:
    """토큰 자카드 ≥ ratio 면 거의 같은 글."""
    x, y = set(tokens(a.lower())), set(tokens(b.lower()))
    if not x or not y:
        return _squash(a) == _squash(b)
    return len(x & y) / len(x | y) >= ratio


def select_novel(
    items: Iterable[NovelRecommendation], limit: int = MAX_NOVEL
) -> tuple[list[NovelRecommendation], list[dict[str, str]]]:
    """거의 같은 접근 방식은 앞의 것만 → 성숙도·근거 수 순 정렬 → 상한(3). 폐기 사유 기록."""
    unique: list[NovelRecommendation] = []
    discarded: list[dict[str, str]] = []
    for rec in items:
        if any(near_same(rec.approach, k.approach) for k in unique):
            discarded.append({"title": rec.approach[:80], "reason": DISCARD_DUPLICATE})
        else:
            unique.append(rec)
    unique.sort(key=lambda r: (_MATURITY_ORDER.get(r.maturity, len(MATURITIES)), -len(ref_ids(r))))
    for rec in unique[limit:]:
        discarded.append({"title": rec.approach[:80], "reason": DISCARD_NOVEL_OVER_LIMIT})
    return unique[:limit], discarded


def novel_retry_hint(discarded: Iterable[Mapping[str, str]]) -> str:
    """0건 다시 받기 지시 — 제외 사유 이름만(본문 없음) + 다시 쓰는 규칙."""
    reasons = list(dict.fromkeys(d.get("reason", "") for d in discarded if d.get("reason")))
    head = ""
    if reasons:
        head = "[앞 응답에서 제외된 이유] " + ", ".join(novel_discard_label(r) for r in reasons)
        head += ".\n"
    return head + NOVEL_RETRY_HINT


def no_novel_text(model_reason: Any, excluded: int) -> str:
    """새 과제안 0건일 때 사유 — 모델 사유(정리) + 검증 제외 건수."""
    reason = _text(model_reason) or NO_NOVEL_REASON
    if excluded:
        return f"{reason} · {EXCLUDED_SUFFIX.format(n=excluded)}"
    return reason
