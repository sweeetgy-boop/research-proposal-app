"""자료 분류 (ADR 0040·0046) — 사전정보공표 연구용역·행정 공시·사업 현황은 정책 근거가 아니다.

ADR 0046: 행정 공시 → doc_type admin_notice, 사업 현황 → status_report, 통계 → statistics."""

import pytest

from rra.adapters.sources.korail_web import normalize_korail_item
from rra.application.usecases.reclassify_documents import ReclassifyDocuments
from rra.domain.models import Document
from rra.domain.rules.doc_category import (
    CLASS_KEY,
    category_label,
    category_of,
    classify_korail,
    is_policy_basis,
)
from tests.fakes import InMemoryRepository

PREINFO = "정보공개 > 사전정보공표 > 사전정보공개목록"
URL = "https://info.korail.com/info/selectInfoRelWebDetail.do?infoRelNo={n}&infoRelDetailNo=1&infoRelCategory={c}"


def _raw(title, *, rel, cat, menu="preinfo", kind="attachment"):
    return {
        "kind": kind,
        "sha256": f"{rel:04d}" + "a" * 60,
        "text": "본문 " * 40,
        "title": title,
        "parent_title": title,
        "menu": menu,
        "menu_path": PREINFO,
        "doc_type": "policy",
        "native_id": f"preinfo:{rel}:1",
        "page_url": URL.format(n=rel, c=cat),
        "snapshot": "2026-10-27",
    }


@pytest.mark.parametrize(
    ("title", "rel", "cat", "want"),
    [
        ("레인보우 비경열차 관광수요 예측 연구", 55, "IRTYP2", ("procurement", "research_service")),
        ("2019년도 일반여객 수송수요 예측", 55, "IRTYP2", ("procurement", "research_service")),
        ("전차선 급전장애(아크) 감지 기술 개선", 55, "IRTYP2", ("procurement", "research_service")),
        ("2026년 부서별 주요계획", 39, "IRTYP2", ("policy", "policy")),
        ("(홈페이지)전략목표및과제종합", 53, "IRTYP2", ("policy", "policy")),
        (
            "26년 2분기 신규채용자 친인척 재직관련 현황",
            60,
            "IRTYP4",
            ("admin_notice", "admin_record"),
        ),
        ("2025년 소송 주요 판례", 56, "IRTYP3", ("admin_notice", "admin_record")),
        ("동해산타열차 소개", 137, "IRTYP6", ("status_report", "status")),
        ("2026년 전사 산업안전보건관리 계획", 232, "IRTYP6", ("policy", "policy")),
    ],
)
def test_normalizer_classifies_preinfo_items(title, rel, cat, want):
    doc = normalize_korail_item(_raw(title, rel=rel, cat=cat))
    assert (doc.doc_type, doc.raw[CLASS_KEY]) == want
    assert is_policy_basis(doc) is (want[1] == "policy")


def test_other_menus_and_statistics_board():
    assert classify_korail(doc_type="policy", title="통계", raw={"menu": "biz_stat_docs"}) == (
        "statistics",
        "statistics",
    )
    assert classify_korail(
        doc_type="policy", title="선로시설 현황", raw={"menu": "biz_maint_track"}
    ) == ("status_report", "status")
    assert classify_korail(
        doc_type="policy", title="계약업무처리 세부기준", raw={"menu": "contract_rules"}
    ) == ("admin_notice", "admin_record")
    study = classify_korail(
        doc_type="policy",
        title="(요약본) 구.원주역 유휴부지 활용방안 검토 자문용역",
        raw={"menu": "biz_newbiz"},
    )
    assert study == ("procurement", "research_service")
    assert classify_korail(
        doc_type="policy", title="중장기 경영목표", raw={"menu": "mgmt_goal"}
    ) == ("policy", "policy")
    assert classify_korail(doc_type="korail_news", title="보도", raw={"menu": "press"}) == (
        "korail_news",
        None,
    )
    assert category_label("procurement", "research_service") == "연구용역(사내 발주)"


def test_old_rows_are_judged_on_the_fly_and_other_sources_keep_their_category():
    old = Document(
        doc_id="korail_web:x",
        source="korail_web",
        doc_type="policy",
        title="2024년도 고속 및 준고속 철도 수송수요 예측",
        raw={"menu": "preinfo", "native_id": "preinfo:55:9"},
    )
    assert category_of(old) == "research_service" and not is_policy_basis(old)
    # 국토부 raw.category 는 다른 뜻(메뉴 이름) — 분류 키와 섞이지 않는다
    molit = Document(
        doc_id="molit:1",
        source="molit",
        doc_type="policy",
        title="국가철도망 구축계획",
        raw={"category": "도로철도 > 철도정책"},
    )
    assert is_policy_basis(molit)
    paper = Document(doc_id="openalex:W1", source="openalex", doc_type="paper", title="p")
    assert not is_policy_basis(paper)


async def test_reclassify_counts_and_writes_only_with_apply():
    research = normalize_korail_item(_raw("수송수요 예측 연구", rel=55, cat="IRTYP2"))
    # 옛 적재분: policy 로 들어가 있고 분류 키가 없다
    old = research.model_copy(
        update={
            "doc_type": "policy",
            "raw": {k: v for k, v in research.raw.items() if k != CLASS_KEY},
        }
    )
    goal = Document(
        doc_id="korail_web:g",
        source="korail_web",
        doc_type="policy",
        title="중장기 경영목표",
        raw={"menu": "mgmt_goal"},
    )
    molit = Document(
        doc_id="molit:1", source="molit", doc_type="policy", title="국가철도망", raw={}
    )
    repo = InMemoryRepository()
    repo.seed([old, goal, molit], [])
    use = ReclassifyDocuments(repo, sources=("korail_web", "molit"))
    dry = await use(dry_run=True)
    kw = dry.sources[0]
    assert (kw.total, kw.changed, kw.policy_basis_before, kw.policy_basis_after) == (2, 2, 2, 1)
    assert kw.after["procurement/research_service"] == 1 and dry.written == 0
    assert repo.docs[old.doc_id].doc_type == "policy"  # 점검만
    assert dry.sources[1].changed == 0
    done = await use(dry_run=False)
    assert done.written == 2
    assert repo.docs[old.doc_id].doc_type == "procurement"
    assert repo.docs[old.doc_id].raw[CLASS_KEY] == "research_service"
    assert repo.docs["korail_web:g"].raw[CLASS_KEY] == "policy"
    again = await use(dry_run=True)
    assert again.changed == 0  # 두 번 돌려도 같다


@pytest.mark.parametrize(
    ("doc_type", "title", "raw", "want"),
    [
        # 행정 공시 — 감사·법무·행정(사전정보공표 IRTYP1·3·4)·규정 메뉴·규정 제목의 신사업자료
        (
            "policy",
            "법인카드 사용 내역",
            {"menu": "preinfo", "native_id": "preinfo:60:1"},
            "admin_notice",
        ),
        ("policy", "인사 규정", {"menu": "human_docs"}, "admin_notice"),
        ("policy", "상생협력 안내", {"menu": "winwin_guide"}, "admin_notice"),
        ("policy", "신사업 추진 세칙", {"menu": "biz_newbiz"}, "admin_notice"),
        # 사업 현황·소개 — IRTYP6·현황 메뉴·브로슈어
        ("policy", "선로 현황", {"menu": "biz_maint_track"}, "status_report"),
        ("policy", "회사 소개 책자", {"menu": "brochure"}, "status_report"),
        ("policy", "역사", {"menu": "history"}, "status_report"),
        # 통계 — 통계자료 게시판·이미 statistics 인 행
        ("policy", "광역 수송 통계", {"menu": "biz_stat_docs"}, "statistics"),
        ("statistics", "수송 통계", {"menu": "biz_stat_docs"}, "statistics"),
        # 정책·연구용역은 그대로
        ("policy", "중장기 경영목표", {"menu": "mgmt_goal"}, "policy"),
        (
            "policy",
            "수송수요 예측",
            {"menu": "preinfo", "native_id": "preinfo:55:1"},
            "procurement",
        ),
    ],
)
def test_each_category_gets_its_doc_type(doc_type, title, raw, want):
    got, category = classify_korail(doc_type=doc_type, title=title, raw=raw)
    assert got == want
    doc = Document(
        doc_id="korail_web:t", source="korail_web", doc_type=got, title=title, raw=dict(raw)
    )
    assert is_policy_basis(doc) is (want == "policy")
    # 이미 바뀐 행을 다시 판정해도 같다(멱등)
    assert classify_korail(doc_type=got, title=title, raw=raw) == (got, category)


def test_new_doc_types_keep_their_category_without_stored_class():
    for doc_type, category in (("admin_notice", "admin_record"), ("status_report", "status")):
        doc = Document(doc_id="korail_web:z", source="korail_web", doc_type=doc_type, title="t")
        assert category_of(doc) == category and not is_policy_basis(doc)
        assert classify_korail(doc_type=doc_type, title="t", raw={}) == (doc_type, category)


async def test_reclassify_moves_admin_and_status_rows_out_of_policy_once():
    """ADR 0040 때 policy + doc_class 로 적재된 행 → admin_notice·status_report. 두 번째는 0건."""
    admin = Document(
        doc_id="korail_web:a",
        source="korail_web",
        doc_type="policy",
        title="2025년 소송 주요 판례",
        raw={"menu": "preinfo", "native_id": "preinfo:56:1", CLASS_KEY: "admin_record"},
    )
    status = Document(
        doc_id="korail_web:s",
        source="korail_web",
        doc_type="policy",
        title="선로 현황",
        raw={"menu": "biz_maint_track", CLASS_KEY: "status"},
    )
    stat = Document(
        doc_id="korail_web:t",
        source="korail_web",
        doc_type="statistics",
        title="통계",
        raw={"menu": "biz_stat_docs", CLASS_KEY: "statistics"},
    )
    goal = Document(
        doc_id="korail_web:g",
        source="korail_web",
        doc_type="policy",
        title="중장기 경영목표",
        raw={"menu": "mgmt_goal", CLASS_KEY: "policy"},
    )
    repo = InMemoryRepository()
    repo.seed([admin, status, stat, goal], [])
    use = ReclassifyDocuments(repo, sources=("korail_web",))
    dry = await use(dry_run=True)
    rep = dry.sources[0]
    assert rep.changed == 2 and dry.written == 0
    assert rep.transitions == {"policy→admin_notice": 1, "policy→status_report": 1}
    assert rep.as_dict()["transitions"] == {"policy→admin_notice": 1, "policy→status_report": 1}
    assert repo.docs["korail_web:a"].doc_type == "policy"  # 점검만
    done = await use(dry_run=False)
    assert done.written == 2
    assert repo.docs["korail_web:a"].doc_type == "admin_notice"
    assert repo.docs["korail_web:s"].doc_type == "status_report"
    assert repo.docs["korail_web:t"].doc_type == "statistics"
    assert repo.docs["korail_web:g"].doc_type == "policy"
    assert repo.docs["korail_web:a"].raw[CLASS_KEY] == "admin_record"
    again = await use(dry_run=True)
    assert again.changed == 0 and not again.sources[0].transitions  # 멱등
