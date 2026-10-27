"""P3 ③ 순서·예산 계획 — 그룹 판정, 캐시 제외, 상한 초과는 OCR 만."""

from rra.domain.models.vision import ImageItem
from rra.domain.rules.vision_plan import classify_group, group_keywords, plan


def it(n: int, **kw) -> ImageItem:
    base = {"sha256": f"{n:064x}", "path": f"img/{n}.png"}
    base.update(kw)
    return ImageItem(**base)


def test_group_from_page_url_title_or_alt_and_manifest_value_wins():
    assert classify_group(it(1, page_url="https://x/press/news")) == "press"
    assert classify_group(it(2, page_title="경영목표와 비전")) == "strategy"
    assert classify_group(it(3, alt="ESG 추진체계")) == "esg_policy"
    assert classify_group(it(4, caption="수송 통계")) == "statistics"
    assert classify_group(it(5)) == "other"
    assert classify_group(it(6, page_url="https://x/press", order_group="strategy")) == "strategy"


def test_strategy_before_esg_before_statistics_before_press_stable_within_group():
    items = [
        it(1, page_url="https://x/press"),
        it(2, page_title="통계"),
        it(3, page_title="비전"),
        it(4, page_title="ESG"),
        it(5, page_title="경영전략"),
    ]
    out = plan(items)
    assert [i.sha256[-1] for i in out.ordered] == ["3", "5", "4", "2", "1"]
    assert out.groups == {"strategy": 2, "esg_policy": 1, "statistics": 1, "press": 1}


def test_cached_hashes_do_not_consume_budget_and_cap_sends_rest_to_ocr_only():
    items = [it(n, page_title="비전") for n in range(1, 7)]
    out = plan(items, cached_hashes={items[0].sha256, items[2].sha256}, cap=2)
    assert [i.sha256 for i in out.cached] == [items[0].sha256, items[2].sha256]
    assert [i.sha256 for i in out.to_call] == [items[1].sha256, items[3].sha256]
    assert [i.sha256 for i in out.ocr_only] == [items[4].sha256, items[5].sha256]
    assert out.expected_calls == 2
    assert out.summary() == {
        "planned": 6,
        "cached": 2,
        "expected_calls": 2,
        "ocr_only": 2,
        "cap": 2,
        "groups": {"strategy": 6},
    }


def test_limit_truncates_after_ordering_and_zero_cap_means_ocr_only():
    items = [it(1, page_url="https://x/press"), it(2, page_title="비전"), it(3)]
    out = plan(items, cap=0, limit=2)
    assert [i.sha256[-1] for i in out.ordered] == ["2", "1"]
    assert out.to_call == [] and len(out.ocr_only) == 2


def test_group_keywords_from_config_replace_defaults_per_group_only():
    kw = group_keywords({"press": ["언론"], "bogus": ["x"], "strategy": "notalist"})
    assert kw["press"] == ("언론",)
    assert "비전" in kw["strategy"]
    assert classify_group(it(1, page_title="언론 보도"), kw) == "press"
