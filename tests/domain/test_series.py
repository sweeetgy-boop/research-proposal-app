"""② 같은 연작 묶기 규칙 (2026-10-29 레인 A, ADR 0043) — 제목이 연도·차수만 다른 과제를 한 줄로."""

from __future__ import annotations

from datetime import date

import pytest

from rra.domain.models import Document, OverlapAlert
from rra.domain.rules.overlap_candidates import OverlapCandidateRule, SourceMember
from rra.domain.rules.series import (
    display_title,
    group_hits,
    group_key,
    member_titles,
    merge_series,
    pick_for_rerank,
    series_display,
    series_key,
    series_label,
    title_year,
)
from rra.domain.rules.similar_choice import apply_choices, effective_blocking

# 시범 측정(골든셋 08) ② 상위 10칸 제목 — docs/eval-2026-10-28-pilot2.md §08
PILOT_08 = [
    "요 약 문 1. 연구 제목 신규 개통 준고속노선 중장기 수송수요 예측 연구",
    "2026년도 일반철도 수송수요 예측 연구",
    "광역철도 수송수요 예측(2020~2029)",
    "2019년도 KTX 수송수요 예측",
    "2027년도 준고속철도 수송수요 예측 연구",
    "2027년도 고속철도 수송수요 예측 연구",
    "2016년 광역철도 중장기 수송수요 예측",
    "2018년도 광역철도 수송수요 예측",
    "2017년 광역철도 중장기 수송수요 예측",
    "2017년도 광역철도 수송수요 예측",
]
# 08 정답의 광역철도 연도별 판 (2023~2027) — 자료원마다 띄어쓰기·어순이 다르다
GWANGYEOK = [
    "2023년도 광역철도 수송수요 예측 연구",
    "2023년 광역철도 수송수요 예측 연구",
    "2024년도 광역철도 수송수요 예측 연구",
    "2025년도 광역철도 수송수요 예측 연구",
    "2026년 광역철도 수송수요 예측 연구",
    "광역철도 2026년도 수송수요 예측연구",
    "광역철도 2027년도 수송수요 예측 연구",
    "2027년 광역철도 수송수요 예측 연구",
]


def test_gwangyeok_annual_editions_are_one_series():
    keys = {series_key(t) for t in [*GWANGYEOK, PILOT_08[2], PILOT_08[7], PILOT_08[9]]}
    assert keys == {"광역철도수송수요예측"}
    assert series_label(GWANGYEOK[0]) == "광역철도 수송수요 예측"
    assert series_display("광역철도 수송수요 예측", 7) == "광역철도 수송수요 예측(연작 7건)"


def test_pilot_top10_falls_into_distinct_series_by_line_and_horizon():
    groups = {series_key(t) for t in PILOT_08}
    # 광역(연도별)·광역 중장기·일반철도·KTX·준고속철도·고속철도·신규 개통 준고속노선 중장기 = 7 줄
    assert groups == {
        "신규개통준고속노선중장기수송수요예측",
        "일반철도수송수요예측",
        "광역철도수송수요예측",
        "ktx수송수요예측",
        "준고속철도수송수요예측",
        "고속철도수송수요예측",
        "광역철도중장기수송수요예측",
    }


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("광역철도 중장기(2026~2055) 수송수요 예측", "2016년 광역철도 중장기 수송수요 예측"),
        (
            "고속 및 일반철도 중장기(2025~2045) 수송수요예측(2023)",
            "고속 및 일반철도 중장기(2025~2045) 수송수요 예측(2024)",
        ),
        ("2024년도 고속 및 준고속 철도 수송수요 예측", "2024년도 고속, 준고속철도 수송수요 예측"),
        ("KTX 수송수요 예측(2020∼2021)", "2019년도 KTX 수송수요 예측 연구"),
        ("제2차 철도안전 종합계획 연구", "제3차 철도안전 종합계획"),
        ("궤도 상태 진단 기술 개발(1단계)", "궤도 상태 진단 기술 개발(2단계)"),
        ("’23년 광역철도 수송수요 예측", "2024년 광역철도 수송수요 예측 연구용역"),
    ],
)
def test_same_series_when_only_years_or_editions_differ(a, b):
    assert series_key(a) == series_key(b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        # 다른 노선·예측 기간은 다른 과제 (판단: 연도·차수만 다른 것이 아니다)
        ("2024년도 광역철도 수송수요 예측 연구", "2024년도 고속철도 수송수요 예측 연구"),
        ("2024년도 광역철도 수송수요 예측 연구", "2024년도 일반철도 수송수요 예측 연구"),
        ("2018년도 광역철도 수송수요 예측", "2017년 광역철도 중장기 수송수요 예측"),
        ("2012년도 광역철도 단기 수송수요 예측 연구", "2013년도 광역철도 수송수요 예측"),
        ("2차전지 열차 연구", "3차전지 열차 연구"),
    ],
)
def test_different_lines_and_horizons_stay_apart(a, b):
    assert series_key(a) != series_key(b)


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        (
            "요 약 문 1. 연구 제목 신규 개통 준고속노선 중장기 수송수요 예측 연구",
            "신규 개통 준고속노선 중장기 수송수요 예측 연구",
        ),
        (
            "요 약 문 연구제목 우리나라 궤도교통의 효시에 관한 연구",
            "우리나라 궤도교통의 효시에 관한 연구",
        ),
        (
            "연구과제 요약서 1. 연구 제목 ◦ 8500호대 전기기관차 GDU 국산화개발",
            "8500호대 전기기관차 GDU 국산화개발",
        ),
        (
            "2026년도 준고속철도 수송수요 예측 연구 □ 개 요",
            "2026년도 준고속철도 수송수요 예측 연구",
        ),
        ("광역철도 수송수요 예측(2020~2029)", "광역철도 수송수요 예측(2020~2029)"),
        ("요 약 문", "요 약 문"),  # 남는 게 없으면 원래 제목
    ],
)
def test_display_title_strips_summary_form_head_and_tail(raw, shown):
    assert display_title(raw) == shown


def test_label_keeps_sentence_final_research_word():
    assert series_label("고속철도역 중장기 주차수요 예측에 관한 연구") == (
        "고속철도역 중장기 주차수요 예측에 관한 연구"
    )
    assert series_label("고속 및 일반철도 중장기(2025~2045) 수송수요예측(2023)") == (
        "고속 및 일반철도 중장기 수송수요예측"
    )


@pytest.mark.parametrize(
    ("title", "year"),
    [
        ("2026년도 광역철도 수송수요 예측 연구", 2026),
        ("광역철도 2027년 수송수요 예측 연구", 2027),
        ("고속 및 일반철도 중장기(2025~2045) 수송수요예측(2023)", 2023),
        ("광역철도 중장기(2026~2055) 수송수요 예측", 2026),
        ("광역철도 중장기 수송수요 예측", None),
    ],
)
def test_title_year(title, year):
    assert title_year(title) == year


def test_short_keys_do_not_form_series():
    # 연도를 빼면 남는 글자가 너무 짧다 — 연작으로 묶지 않고 같은 제목 키만
    assert group_key("2023년도 연구") == "t:2023년도연구"
    assert group_key("2024년도 연구") != group_key("2023년도 연구")
    assert group_key("궤도 틀림") == "t:궤도틀림"  # 같은 제목 묶음 키(종전 규칙)


def _doc(doc_id, title, source="own", year=None, **kw):
    return Document(
        doc_id=doc_id,
        source=source,
        doc_type="rnd_project" if source == "own" else "internal_report",
        title=title,
        body=f"{title} 본문",
        pub_date=date(year, 1, 1) if year else None,
        **kw,
    )


def _alert(doc_id, title, score, blocking=False, keywords=()):
    return OverlapAlert(
        doc_id=doc_id,
        title=title,
        tier="own",
        similarity=0.85,
        blocking=blocking,
        rule_blocking=blocking,
        rerank_score=score,
        keywords=list(keywords),
    )


def test_merge_series_one_row_best_member_pool_members_and_any_blocking():
    alerts = [
        _alert(
            "own:b",
            "2024년도 광역철도 수송수요 예측 연구",
            0.71,
            blocking=True,
            keywords=["광역철도"],
        ),
        _alert("alio:a", "2025년도 광역철도 수송수요 예측 연구", 0.83, keywords=["수송수요"]),
        _alert("own:x", "궤도 상태 진단", 0.60),
        _alert("korail_web:c", "2025년도 광역철도 수송수요 예측 연구", 0.40),
    ]
    pool = [
        (_doc("own:d", "광역철도 2027년도 수송수요 예측 연구"), 0.8),
        (_doc("own:e", "2017년 광역철도 중장기 수송수요 예측"), 0.8),  # 다른 연작 — 붙지 않는다
    ]
    rows = merge_series(alerts, pool=pool)
    assert [r.doc_id for r in rows] == ["alio:a", "own:x"]  # 대표 = 점수 최고, 차단 행 먼저
    row = rows[0]
    assert row.blocking and row.rule_blocking  # 하나라도 차단이면 차단
    assert set(row.merged_ids) == {"own:b", "korail_web:c", "own:d"}
    assert row.keywords == ["수송수요", "광역철도"]
    assert row.series is not None
    assert row.series.label == "광역철도 수송수요 예측" and row.series.count == 3  # 판 = 제목 수
    assert [m.year for m in row.series.members] == [2024, 2025, 2027]  # 연도 순
    by_year = {m.year: m for m in row.series.members}
    assert [d.doc_id for d in by_year[2025].docs] == ["alio:a", "korail_web:c"]
    assert rows[1].series is None


def test_same_title_only_group_has_no_series_but_merges():
    alerts = [
        _alert("own:1", "궤도 틀림 진행 예측 모형 개발", 0.9),
        _alert("alio:1", "궤도 틀림 진행 예측 모형 개발 연구", 0.7),
    ]
    rows = merge_series(alerts)
    assert len(rows) == 1 and rows[0].merged_ids == ["alio:1"]
    assert rows[0].series is not None  # 제목 글자가 다르면(끝 "연구") 판 둘 — 연작 표시
    same = merge_series([_alert("own:1", "같은 과제", 0.9), _alert("alio:1", "같은 과제", 0.7)])
    assert len(same) == 1 and same[0].series is None  # 판 하나 = 같은 제목 묶음


def test_choice_on_series_row_applies_to_all_members():
    alerts = [
        _alert("own:b", "2024년도 광역철도 수송수요 예측 연구", 0.71, blocking=True),
        _alert("alio:a", "2025년도 광역철도 수송수요 예측 연구", 0.83),
    ]
    rows = merge_series(alerts)
    assert effective_blocking(rows, {})
    # 구성원 doc_id 하나로 고른 선택도 행 전체에 적용된다
    shown, released = apply_choices(rows, {"own:b": "unrelated"})
    assert released and not shown[0].blocking and shown[0].choice == "unrelated"


def test_member_titles_for_judgment_prompt_respects_public_only():
    alerts = [
        _alert("own:b", "2024년도 광역철도 수송수요 예측 연구", 0.71),
        _alert("alio:a", "2025년도 광역철도 수송수요 예측 연구", 0.83),
    ]
    docs = {
        "own:b": _doc("own:b", "2024년도 광역철도 수송수요 예측 연구", visibility="internal"),
        "alio:a": _doc("alio:a", "2025년도 광역철도 수송수요 예측 연구", source="alio"),
    }
    row = merge_series(alerts, docs=docs)[0]
    assert member_titles(row) == [
        "2024년도 광역철도 수송수요 예측 연구",
        "2025년도 광역철도 수송수요 예측 연구",
    ]
    assert member_titles(row, public_only=True) == ["2025년도 광역철도 수송수요 예측 연구"]


def test_pick_for_rerank_takes_per_series_up_to_limit():
    hits = [(_doc(f"own:{i}", f"{2010 + i}년도 광역철도 수송수요 예측"), 0.9) for i in range(5)]
    hits += [(_doc("own:z", "궤도 상태 진단"), 0.8), (_doc("own:y", "전차선 아크 감지"), 0.7)]
    groups = group_hits(hits)
    assert len(groups) == 3
    picked = pick_for_rerank(groups, per_series=2, limit=10)
    assert [d.doc_id for d, _ in picked] == ["own:0", "own:1", "own:z", "own:y"]
    assert len(pick_for_rerank(groups, per_series=2, limit=3)) == 3


def test_candidate_pool_counts_distinct_series_not_documents():
    rule = OverlapCandidateRule(
        project=(SourceMember(source="own"), SourceMember(source="alio")), per_source=2, pool_size=3
    )
    series = [(_doc(f"own:{i}", f"{2010 + i}년도 광역철도 수송수요 예측"), 0.9) for i in range(6)]
    others = [(_doc(f"own:o{i}", f"다른 과제 주제 {chr(0xAC00 + i)}"), 0.8) for i in range(4)]
    alio = [(_doc("alio:1", "2026년도 광역철도 수송수요 예측 연구", source="alio"), 0.88)]
    overall = [*series, *others, *alio]
    flat = rule.pool({"own": series[:2], "alio": alio}, overall)
    assert len(flat) == 3  # 종전: 건수 상한
    grouped = rule.pool(
        {"own": series[:2], "alio": alio}, overall, group=lambda d: group_key(d.title)
    )
    ids = [d.doc_id for d, _ in grouped]
    # 연작 하나(구성원 7건) + 다른 과제 2건 = 묶음 3개
    assert len(group_hits(grouped)) == 3
    assert {"own:o0", "own:o1"} <= set(ids) and "own:o2" not in ids
    assert {f"own:{i}" for i in range(6)} | {"alio:1"} <= set(ids)
