"""근거 구성 규칙(retrieval_mix) — 섹션별 허용 doc_type, 논문·보고서·특허 최소 보장, 유사과제 판정
제외."""

from rra.domain.models import Chunk, Document
from rra.domain.rules.retrieval_mix import RetrievalMix, SectionMix

MIX = RetrievalMix(
    section_min_per_source=2,
    sections={
        "tech_importance": SectionMix(
            allow=("paper", "report", "patent", "internal_report", "rnd_project"), min_scholarly=2
        ),
        "policy_importance": SectionMix(allow=("policy",)),
    },
    overlap_exclude=("policy", "korail_news"),
)
TYPES = {
    "openalex:W1": "paper",
    "openalex:W2": "paper",
    "own:1": "rnd_project",
    "alio:1": "internal_report",
    "korail_web:p1": "policy",
}


def chunk(doc_id, n=0):
    return Chunk(chunk_id=f"{doc_id}#{n}", doc_id=doc_id, ordinal=n, text="t")


def test_filter_keeps_allowed_types_unknown_types_and_overlap_chunks():
    chunks = [chunk("korail_web:p1"), chunk("own:1"), chunk("zzz:new"), chunk("openalex:W1")]
    overlap = Chunk(chunk_id="alio:9#overlap", doc_id="alio:9", ordinal=0, text="x")
    kept = MIX.filter("tech_importance", [*chunks, overlap], TYPES)
    assert [c.doc_id for c in kept] == ["own:1", "zzz:new", "openalex:W1", "alio:9"]
    assert MIX.filter("objective", chunks, TYPES) == chunks  # 규칙 없는 섹션은 전부
    assert MIX.filter("policy_importance", [chunk("own:1")], TYPES) == [
        chunk("own:1")
    ]  # 0건 → 전부
    assert MIX.filter("tech_importance", chunks, {}) == chunks  # doc_type 모르면 거르지 않는다


def test_top_up_scholarly_adds_papers_from_pool_until_minimum():
    picked = [chunk("own:1"), chunk("alio:1")]
    pool = [
        chunk("own:1"),
        chunk("alio:1"),
        chunk("openalex:W1"),
        chunk("korail_web:p1"),
        chunk("openalex:W2"),
    ]
    assert MIX.scholarly_shortfall("tech_importance", picked, TYPES) == 2
    out = MIX.top_up_scholarly("tech_importance", picked, pool, TYPES)
    assert [c.doc_id for c in out] == ["own:1", "alio:1", "openalex:W1", "openalex:W2"]
    assert MIX.scholarly_shortfall("tech_importance", out, TYPES) == 0
    assert MIX.top_up_scholarly("objective", picked, pool, TYPES) == picked  # 보장 없는 섹션


def test_overlap_candidates_drop_policy_and_news_documents():
    def doc(doc_id, doc_type, source="alio"):
        return Document(doc_id=doc_id, source=source, doc_type=doc_type, title="t")

    hits = [(doc("own:1", "rnd_project", "own"), 0.9), (doc("alio:p", "internal_report"), 0.95)]
    mix = RetrievalMix(overlap_exclude=("internal_report",))
    kept = mix.overlap_candidates(hits, lambda d: d.doc_type)
    assert [d.doc_id for d, _ in kept] == ["own:1"]
    assert RetrievalMix().overlap_candidates(hits, lambda d: d.doc_type) == hits


# ── 근거 범위 (2026-10-29 레인 D, ADR 0046) ──────────────────────
SCOPED = RetrievalMix(
    sections={
        "strategy_alignment": SectionMix(allow=("policy",), strict=True),
        "objective": SectionMix(allow=("paper", "status_report", "admin_notice", "statistics")),
        "method": SectionMix(allow=("paper",)),
    },
    only_in={
        "admin_notice": ("tech_importance", "objective"),
        "status_report": ("tech_importance", "objective"),
    },
)
SCOPED_TYPES = {
    "korail_web:a": "admin_notice",
    "korail_web:s": "status_report",
    "korail_web:p": "policy",
    "openalex:W1": "paper",
    "own:1": "rnd_project",
}


def test_strict_section_never_falls_back_to_everything():
    pool = [chunk("korail_web:a"), chunk("korail_web:s"), chunk("openalex:W1")]
    assert SCOPED.filter("strategy_alignment", pool, SCOPED_TYPES) == []  # 되돌리기 없음
    kept = SCOPED.filter("strategy_alignment", [*pool, chunk("korail_web:p")], SCOPED_TYPES)
    assert [c.doc_id for c in kept] == ["korail_web:p"]
    # 유사과제 보탬 청크(연구용역·과제 요약)도 2-가-(3) 에는 들어가지 않는다
    research = Chunk(chunk_id="korail_web:r#overlap", doc_id="korail_web:r", ordinal=0, text="x")
    types = {**SCOPED_TYPES, "korail_web:r": "procurement"}
    kept = SCOPED.filter("strategy_alignment", [research, chunk("korail_web:p")], types)
    assert [c.doc_id for c in kept] == ["korail_web:p"]
    assert SCOPED.filter("objective", [research], types) == [research]  # 다른 섹션은 종전대로


def test_only_in_types_stay_out_of_other_sections_even_on_fallback():
    pool = [chunk("korail_web:a"), chunk("korail_web:s"), chunk("own:1")]
    # method 는 paper 만 허용 — 0건 되돌리기에서도 행정 공시·사업 현황은 빠진다
    assert [c.doc_id for c in SCOPED.filter("method", pool, SCOPED_TYPES)] == ["own:1"]
    # 규칙 없는 섹션(전부)에서도 빠진다
    assert [c.doc_id for c in SCOPED.filter("utilization", pool, SCOPED_TYPES)] == ["own:1"]
    # 필요성·현황 섹션은 쓸 수 있다
    assert [c.doc_id for c in SCOPED.filter("objective", pool, SCOPED_TYPES)] == [
        "korail_web:a",
        "korail_web:s",
    ]
    assert SCOPED.allowed("tech_importance", "status_report")
    assert not SCOPED.allowed("strategy_alignment", "admin_notice")


def test_shipped_retrieval_mix_scopes_admin_status_statistics():
    """config/retrieval_mix.yaml — 2-가-(3) 은 정책만(되돌리기 없음), 세 종류는 필요성·현황
    섹션만."""
    from pathlib import Path

    from rra.config_loader import retrieval_mix
    from rra.settings import Settings

    mix = retrieval_mix(Settings(_env_file=None, config_dir=Path(__file__).parents[2] / "config"))
    assert mix is not None
    three = ("admin_notice", "status_report", "statistics")
    sections = (
        "title",
        "task_type",
        "policy_importance",
        "tech_importance",
        "strategy_alignment",
        "objective",
        "method",
        "expected_management",
        "expected_technology",
        "expected_standing",
        "utilization",
        "overlap_review",
    )
    for dt in three:
        assert not mix.allowed("strategy_alignment", dt)
        assert not mix.allowed("policy_importance", dt)
        assert mix.allowed("tech_importance", dt) and mix.allowed("objective", dt)
        assert dt in mix.overlap_exclude  # 과제가 아니다
        for key in sections:
            if key not in ("tech_importance", "objective", "expected_management"):
                assert not mix.allowed(key, dt), (key, dt)
    assert mix.allowed("expected_management", "statistics")  # 기대효과 현황 기준값(datago 와 같음)
    assert not mix.allowed("expected_management", "admin_notice")
    assert mix.sections["strategy_alignment"].strict
    assert mix.allowed("strategy_alignment", "policy")
    # 정책 근거만 있는 섹션 — 행정 공시만 있으면 빈 근거(되돌리기 없음)
    pool = [chunk("korail_web:a"), chunk("korail_web:s"), chunk("openalex:W1")]
    assert mix.filter("strategy_alignment", pool, SCOPED_TYPES) == []
    assert "procurement" not in mix.overlap_exclude  # 연구용역(사내 발주)은 유사과제 판정에 남는다
