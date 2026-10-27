"""판독 순서·예산 계획 — 순수 규칙 (P3 ③ 순서·상한).

순서: 경영목표·전략·비전(strategy) > ESG·정책(esg_policy) > 통계(statistics) > 보도자료(press) >
기타.
그룹은 manifest 가 주면 그대로, 없으면 페이지 URL·제목·alt 의 키워드로 판정한다 (config/vision.yaml
order).
예산: 캐시에 있는 해시는 호출이 없으므로 상한을 쓰지 않는다. 상한을 넘는 나머지는 OCR 만 한다.
dry-run 은 이 계획(판독 예정 수·예상 호출 수·OCR 만 할 목록)을 그대로 보여 준다.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from rra.domain.models.vision import ORDER_GROUPS, ImageItem, OrderGroup

DEFAULT_GROUP_KEYWORDS: dict[OrderGroup, tuple[str, ...]] = {
    "strategy": (
        "비전",
        "경영목표",
        "경영전략",
        "전략체계",
        "전략과제",
        "미션",
        "핵심가치",
        "vision",
        "strategy",
    ),
    "esg_policy": (
        "esg",
        "정책",
        "윤리",
        "안전경영",
        "환경",
        "사회공헌",
        "인권",
        "준법",
        "지속가능",
    ),
    "statistics": ("통계", "실적", "현황", "지표", "수송", "경영공시", "재무", "statistics"),
    "press": ("보도자료", "뉴스", "news", "press", "홍보"),
}
DEFAULT_CAP = 2000


def group_keywords(raw: dict | None) -> dict[OrderGroup, tuple[str, ...]]:
    """config order.keywords → 그룹별 소문자 키워드. 없는 그룹은 기본값."""
    out = dict(DEFAULT_GROUP_KEYWORDS)
    for group, words in (raw or {}).items():
        if group in ORDER_GROUPS and isinstance(words, list):
            out[group] = tuple(str(w).lower() for w in words if str(w).strip())  # type: ignore[index]
    return out


def classify_group(
    item: ImageItem, keywords: dict[OrderGroup, tuple[str, ...]] | None = None
) -> OrderGroup:
    if item.order_group:
        return item.order_group
    keywords = keywords or DEFAULT_GROUP_KEYWORDS
    hay = " ".join(
        v for v in (item.page_url, item.page_title, item.alt, item.caption, item.path) if v
    ).lower()
    for group in ORDER_GROUPS:
        if group == "other":
            continue
        if any(k in hay for k in keywords.get(group, ())):
            return group
    return "other"


@dataclass
class VisionPlan:
    ordered: list[ImageItem] = field(default_factory=list)  # 우선순위 순서 (캐시 포함)
    cached: list[ImageItem] = field(default_factory=list)  # 호출 없이 캐시로 끝나는 것
    to_call: list[ImageItem] = field(default_factory=list)  # Argon 호출 예정
    ocr_only: list[ImageItem] = field(default_factory=list)  # 상한 초과 → OCR 만
    cap: int = DEFAULT_CAP
    groups: dict[str, int] = field(default_factory=dict)

    @property
    def expected_calls(self) -> int:
        return len(self.to_call)

    def summary(self) -> dict[str, int | dict[str, int]]:
        return {
            "planned": len(self.ordered),
            "cached": len(self.cached),
            "expected_calls": self.expected_calls,
            "ocr_only": len(self.ocr_only),
            "cap": self.cap,
            "groups": dict(self.groups),
        }


def plan(
    items: Sequence[ImageItem],
    *,
    cached_hashes: Iterable[str] = (),
    cap: int = DEFAULT_CAP,
    keywords: dict[OrderGroup, tuple[str, ...]] | None = None,
    limit: int | None = None,
) -> VisionPlan:
    """거르기를 통과한 항목을 순서대로 세우고 예산을 배분한다. limit 는 처리 항목 수
    상한(테스트·시험용)."""
    cached = set(cached_hashes)
    rank = {g: i for i, g in enumerate(ORDER_GROUPS)}
    tagged = [(classify_group(it, keywords), it) for it in items]
    tagged.sort(key=lambda t: rank[t[0]])  # 안정 정렬 — 같은 그룹은 manifest 순서 유지
    if limit is not None:
        tagged = tagged[: max(0, limit)]
    out = VisionPlan(cap=max(0, cap))
    for group, it in tagged:
        it = it.model_copy(update={"order_group": group})
        out.ordered.append(it)
        out.groups[group] = out.groups.get(group, 0) + 1
        if it.sha256 in cached:
            out.cached.append(it)
        elif len(out.to_call) < out.cap:
            out.to_call.append(it)
        else:
            out.ocr_only.append(it)
    return out
