"""유추 검색 보고 → 화면용 문장 (ADR 0065, 계약 problem-card.md 4.3절)."""

from rra.domain.models.novel import AnalogyReport
from rra.entrypoints.views import analogy_report_payload, novel_progress_payload


def test_no_report_means_no_key_and_old_payload():
    assert analogy_report_payload(None) is None
    assert "analogy_report" not in novel_progress_payload(None, [])


def test_partial_scope_names_checked_and_unchecked_sources_in_korean():
    report = AnalogyReport(
        count=2,
        searched=["scienceon", "openalex", "kipris_kr"],
        unavailable=[{"source": "ntis", "status": "ip_blocked"}],
        sources_total=4,
    )
    out = analogy_report_payload(report)
    assert out["heading"] == "다른 분야 사례" and out["partial"] is True
    assert out["sources_total"] == 4 and out["sources_checked"] == 3
    assert out["scope_text"].startswith("실시간 자료원 4곳 중 3곳 확인")
    assert "확인 못 함" in out["scope_text"] and "ip_blocked" not in out["scope_text"]
    assert out["empty_text"].startswith("찾지 못했습니다(검색 범위: 한국어·영어, 자료원 ")
    assert "일부만 확인" in out["empty_text"]
    assert novel_progress_payload(None, [], analogy_report=report)["analogy_report"] == out


def test_related_heading_and_full_scope_and_stored_only():
    full = analogy_report_payload(
        AnalogyReport(kind="related", count=5, searched=["scienceon"], sources_total=1)
    )
    assert full["heading"] == "관련 선행 자료" and full["partial"] is False
    assert "철도 시설" in full["description"] and "확인 못 함" not in full["scope_text"]
    assert "일부만" not in full["empty_text"]
    stored = analogy_report_payload(AnalogyReport())
    assert stored["scope_text"].startswith("저장 자료 범위에서만")
    assert "자료원 저장 자료" in stored["empty_text"]


def test_card_hint_only_when_card_path_is_empty_but_the_old_way_finds_some():
    """계약 4.4절 — 카드 방식만 0건이면 "카드를 확인해 주세요". 자료 자체는 싣지 않는다."""
    out = analogy_report_payload(AnalogyReport(count=0, legacy_count=3))
    assert out["card_hint"] == (
        "문제 정의 카드 기준으로는 찾지 못했지만, 카드 없이 찾으면 3건이 있습니다. "
        "핵심 문제 카드(기능 문장·대상)를 확인해 주세요."
    )
    assert "legacy" not in str(out) and "run" not in out["card_hint"]
    assert "legacy_count" not in out
    # 종전 방식도 0건이거나, 카드 방식에 자료가 있으면 안내가 없다
    assert analogy_report_payload(AnalogyReport(count=0))["card_hint"] is None
    assert analogy_report_payload(AnalogyReport(count=2, legacy_count=3))["card_hint"] is None
