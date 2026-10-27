"""NTIS 부가 조회 규칙 — 대상 과제 선정·성과·추천 검증. 순수 함수."""

from rra.domain.models import OverlapAlert
from rra.domain.rules.ntis_insights import (
    merge_recommended,
    project_no_of,
    target_projects,
    validate_outcomes,
    validate_related,
)


def alert(doc_id, tier="national_rnd", sim=0.85, blocking=False):
    return OverlapAlert(
        doc_id=doc_id, title=f"t {doc_id}", tier=tier, similarity=sim, blocking=blocking
    )


def test_project_no_of():
    assert project_no_of("ntis:1415171234") == "1415171234"
    assert project_no_of("ntis:REP-2023-0115000001") == "REP-2023-0115000001"
    assert project_no_of("own:1415171234") is None and project_no_of("ntis:../x") is None


def test_target_projects_blocking_then_similarity_only_national_rnd():
    alerts = [
        alert("ntis:1415100003", sim=0.95),
        alert("own:1", tier="own", sim=0.99, blocking=True),
        alert("ntis:1415100001", sim=0.81, blocking=True),
        alert("ntis:1415100002", sim=0.90),
        alert(
            "ntis:REP-2023-0000001", tier="external", sim=0.97
        ),  # 보고서(external 티어)는 대상 아님
        alert("ntis:1415100003", sim=0.95),  # 중복
    ]
    assert [a.doc_id for a in target_projects(alerts, 2)] == ["ntis:1415100001", "ntis:1415100003"]
    assert [a.doc_id for a in target_projects(alerts)] == [
        "ntis:1415100001",
        "ntis:1415100003",
        "ntis:1415100002",
    ]


def test_validate_outcomes_filters_dedups_and_caps():
    items = [
        {"kind": "paper", "title": "A", "year": "2023", "venue": "J"},
        {"kind": "paper", "title": "A", "year": "2023"},  # 중복
        {"kind": "equipment", "title": "X"},  # 모르는 종류
        {"kind": "patent", "title": ""},  # 제목 없음
        {"kind": "patent", "title": " B  C ", "registration_no": "10-1", "year": 20230},
    ] + [{"kind": "paper", "title": f"P{i}"} for i in range(20)]
    out = validate_outcomes(items, limit=5)
    assert [o.title for o in out] == ["A", "B C", "P0", "P1", "P2"]
    assert out[1].registration_no == "10-1" and out[1].year == "2023"


def test_validate_related_excludes_known_and_bad_ids():
    items = [
        {"project_no": "1415199001", "title": "새 과제", "score": 0.91, "rank": 1},
        {"project_no": "1711185678", "title": "이미 알림에 있음", "score": 0.84, "rank": 2},
        {"project_no": "1415171234", "title": "자기 자신", "score": 0.8, "rank": 3},
        {"project_no": "../bad", "title": "형식 오류", "score": 0.7, "rank": 4},
        {"project_no": "1415199002", "title": "점수 범위 밖", "score": 7, "rank": -1},
    ]
    out = validate_related(items, source_project_no="1415171234", known={"1711185678"})
    assert [r.project_no for r in out] == ["1415199001", "1415199002"]
    assert out[0].score == 0.91 and out[0].rank == 1 and out[0].source_project_no == "1415171234"
    assert out[1].score is None and out[1].rank is None


def test_merge_recommended_dedups_by_best_score():
    a = validate_related(
        [{"project_no": "1415100001", "title": "x", "score": 0.5}], source_project_no="s1", known=()
    )
    b = validate_related(
        [
            {"project_no": "1415100001", "title": "x", "score": 0.9},
            {"project_no": "1415100002", "title": "y", "score": 0.7},
        ],
        source_project_no="s2",
        known=(),
    )
    merged = merge_recommended([a, b])
    assert [(r.project_no, r.score, r.source_project_no) for r in merged] == [
        ("1415100001", 0.9, "s2"),
        ("1415100002", 0.7, "s2"),
    ]
