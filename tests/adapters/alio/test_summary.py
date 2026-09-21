"""알리오 공개 요약 경로 — 라벨 해석·정규화(순수), 격리·로그, 실제 샌드박스 end-to-end.

샘플은 합성이다. 실제 알리오 복사본 fixture 는 tests/fixtures/alio/summary/ (README 참고).
"""

import logging
from datetime import date
from pathlib import Path

import pytest

from rra.adapters.sources.alio._inbox import inbox_status
from rra.adapters.sources.alio.summary import (
    AlioSummarySource,
    MissingRequiredField,
    normalize_summary,
    parse_budget_krw,
    parse_labeled,
    parse_period,
    split_names,
)
from rra.application.usecases.ingest_sources import IngestSources
from rra.domain.models import CatalogEntry
from tests.fakes import InMemoryRepository

INSTITUTIONS = [{"code": "C0268", "name": "한국철도공사", "tag": "korail"}]
HIDDEN_NAME = "기밀_코레일_요약"

SAMPLE = """\
알리오 공공기관 경영정보 공개시스템
연구보고서 상세
제목\t궤도 틀림 자동 감지 기법 연구
기관명\t한국철도공사
발간일\t2022.03.15
저자\t홍길동, 김철수 · 이영희
과제유형·연구책임자\t자체연구 / 홍길동(철도연구원)
연구기간·소요예산\t2021.03 ~ 2021.12 / 120,000천원
연구목적
궤도 틀림을 영상으로 자동 감지하는 기법을 개발한다.
연구내용
1. 영상 데이터 수집
2. 딥러닝 기반 감지 모델
기대효과\t점검 인력 절감
활용계획\t2023년 시범 적용
원문공개 여부\t비공개
비공개사유\t정보공개법 제9조 제1항 제7호(영업상 비밀)
공개예정일\t2025.12.31
"""


def raw_of(text=SAMPLE, catalog=None):
    return {"sha256": "ab" * 32, "lines": text.splitlines(), "catalog": catalog}


# ── 라벨 해석 ────────────────────────────────────────────
def test_parse_labeled_tabs_pairs_and_multiline_sections():
    f = parse_labeled(SAMPLE.splitlines())
    assert f["title"] == "궤도 틀림 자동 감지 기법 연구"
    assert f["project_type"] == "자체연구" and f["pi"] == "홍길동(철도연구원)"
    assert f["period"] == "2021.03 ~ 2021.12" and f["budget"] == "120,000천원"
    assert f["content"] == "1. 영상 데이터 수집\n2. 딥러닝 기반 감지 모델"
    assert "알리오" not in " ".join(f.values())  # 첫 라벨 전 머리글은 버린다


def test_parse_labeled_colon_bullets_spaces_and_label_spacing():
    f = parse_labeled(["■ 제목: 전차선 마모 예측", "원문공개여부 :  공개", "□ 연구 목적", "본문"])
    assert f["title"] == "전차선 마모 예측" and f["disclosure_status"] == "공개"
    # "연구 목적"은 라벨 "연구목적"과 같다
    assert f["purpose"] == "본문"


def test_body_line_starting_with_label_word_is_not_a_label():
    # 라벨 뒤 구분자(콜론·탭·두 칸 이상·줄끝)가 없으면 본문 줄이다
    f = parse_labeled(["연구목적", "연구내용 중 일부를 먼저 수행한다."])
    assert f == {"purpose": "연구내용 중 일부를 먼저 수행한다."}


def test_repeated_label_keeps_first_and_does_not_absorb_following_lines():
    f = parse_labeled(["제목\tA", "연구목적\t첫째", "제목\tB", "딸린 줄"])
    assert f == {"title": "A", "purpose": "첫째"}


def test_custom_labels_override():
    f = parse_labeled(["과제명칭\t새 이름"], {"title": ["과제명칭"]})
    assert f == {"title": "새 이름"}


# ── 값 해석 ──────────────────────────────────────────────
@pytest.mark.parametrize(
    ("text", "krw"),
    [
        ("120,000천원", 120_000_000),
        ("1.2억원", 120_000_000),
        ("12억 3,000만원", 1_230_000_000),
        ("150백만원", 150_000_000),
        ("1억2천만원", 120_000_000),
        ("120,000천원 (국비 100,000천원)", 120_000_000),
        ("비공개", None),
        ("", None),
    ],
)
def test_parse_budget(text, krw):
    assert parse_budget_krw(text) == krw


def test_parse_period_month_only_end_is_month_end_and_reversed_is_none():
    assert parse_period("2021.03 ~ 2021.12") == (date(2021, 3, 1), date(2021, 12, 31))
    assert parse_period("2021-03-02~2022-02-28") == (date(2021, 3, 2), date(2022, 2, 28))
    assert parse_period("2022.01 ~ 2021.01") is None
    assert parse_period("12개월") is None


def test_split_names():
    assert split_names("홍길동, 김철수 · 이영희, 홍길동") == ["홍길동", "김철수", "이영희"]


# ── 정규화 ───────────────────────────────────────────────
def test_normalize_maps_fields():
    doc = normalize_summary(raw_of(), institutions=INSTITUTIONS)
    assert doc.text_basis == "summary" and doc.source == "alio"
    assert doc.doc_type == "internal_report"
    assert doc.doc_id.startswith("alio:sum-")
    assert doc.title == "궤도 틀림 자동 감지 기법 연구"
    assert doc.pub_date == date(2022, 3, 15)
    assert doc.authors == ["홍길동", "김철수", "이영희"]
    assert doc.department == "철도연구원"  # own 티어 판정에 쓰인다
    assert doc.orgs == ["korail"]
    assert doc.project_period == (date(2021, 3, 1), date(2021, 12, 31))
    assert doc.raw["budget_krw"] == 120_000_000
    assert doc.raw["disclosure"] == {
        "status": "비공개",
        "reason": "정보공개법 제9조 제1항 제7호(영업상 비밀)",
        "open_date": "2025-12-31",
    }
    assert doc.toc == ["■ 연구목적", "■ 연구내용", "■ 기대효과", "■ 활용계획"]


def test_body_has_preface_and_sections_but_not_disclosure():
    doc = normalize_summary(raw_of(), institutions=INSTITUTIONS)
    first = doc.body.splitlines()[0]
    assert first.startswith("[공개 요약] 자체연구")
    assert "연구기간 2021.03 ~ 2021.12" in first and "소요예산 120,000천원" in first
    assert "부서 철도연구원" in first
    assert "■ 연구내용\n1. 영상 데이터 수집" in doc.body
    assert "비공개사유" not in doc.body and "영업상 비밀" not in doc.body


def test_catalog_match_uses_catalog_id_title_and_org():
    entry = CatalogEntry(
        catalog_id="2022-031",
        institution_tag="korail",
        title="카탈로그 제목",
        published=date(2022, 4, 1),
    )
    doc = normalize_summary(raw_of(catalog=entry.model_dump(mode="json")))
    assert doc.doc_id == "alio:2022-031"  # 원문 filedrop 과 같은 id
    assert doc.title == "카탈로그 제목" and doc.pub_date == date(2022, 4, 1)
    assert doc.orgs == ["korail"] and doc.raw["catalog_matched"]


def test_doc_id_without_catalog_is_stable():
    a = normalize_summary(raw_of(), institutions=INSTITUTIONS)
    b = normalize_summary({**raw_of(), "sha256": "cd" * 32}, institutions=INSTITUTIONS)
    assert a.doc_id == b.doc_id  # 같은 요약을 다시 복사해도 같은 문서


@pytest.mark.parametrize(
    "text",
    ["제목\t제목만 있음\n기대효과\t효과", "연구목적\t목적만 있음"],
)
def test_missing_required_raises(text):
    with pytest.raises(MissingRequiredField):
        normalize_summary(raw_of(text))


# ── 소스 (격리·로그·end-to-end) ──────────────────────────
@pytest.fixture
def inbox(tmp_path):
    d = tmp_path / "alio_summary"
    d.mkdir()
    return d


@pytest.mark.parametrize(
    ("body", "error"),
    [
        (b"PK\x03\x04 zip", "MagicMismatch"),
        (b"\xef\xbb\xbf\xec\xa0\x9c\xeb\xaa\xa9\x00", "MagicMismatch"),  # NUL
        (b"x" * 300_000, "TooLarge"),
        (b"\xff\xfe\xfa\xfb" * 10, "UnknownEncoding"),
        ("제목\t목적 없는 요약\n".encode(), "MissingRequiredField"),
    ],
)
async def test_rejected_file_quarantined_log_has_only_class_name(
    inbox, limits, caplog, body, error
):
    (inbox / f"{HIDDEN_NAME}.txt").write_bytes(body)
    with caplog.at_level(logging.WARNING, logger="rra.sources.alio_summary"):
        assert await AlioSummarySource(inbox, limits=limits).search(None, 10) == []
    [record] = caplog.records
    message = record.getMessage()
    assert f"error={error}" in message
    assert HIDDEN_NAME not in message and str(inbox) not in message
    assert inbox_status(inbox) == {"pending": 0, "done": 0, "quarantine": 1}


async def test_ingest_end_to_end_real_sandbox_cp949(inbox, limits):
    (inbox / "a.txt").write_bytes(SAMPLE.encode("cp949"))
    (inbox / "b.txt").write_text(SAMPLE.replace("궤도 틀림", "전차선 마모"), encoding="utf-8")
    repo = InMemoryRepository()
    src = AlioSummarySource(inbox, limits=limits, institutions=INSTITUTIONS)
    report = await IngestSources([src], repo)()

    assert report.stored == 2 and report.failed == {}
    docs = list(repo.docs.values())
    assert {d.text_basis for d in docs} == {"summary"}
    assert {c.basis for c in repo.chunks} == {"summary"}
    assert inbox_status(inbox) == {"pending": 0, "done": 2, "quarantine": 0}


# ── 알리오 실물 형식 (korail_2026_asset.txt 에서 본 규칙) ─────
ALIO_FORMAT = """\
* 제목
자산개발 모델 연구
* 저자
홍길동
* 내용
1. 과제개요
  - 과제유형 / 연구책임자 : 수시연구과제 / 경영연구처 홍길동
  - 연구기간 / 소요예산 : 2025.11.24.∼2026.8.31.(9개월) / 90,000천원

2. 연구목적
  - 목적 문장

3. 연구내용
  - 법규·제도 개선 / 시사점
* 원문공개
비공개
* 공개예정일
"""


def test_star_labels_numbered_sections_and_group_headers():
    f = parse_labeled(ALIO_FORMAT.splitlines())
    assert f["title"] == "자산개발 모델 연구"
    assert f["authors"] == "홍길동"  # "* 내용"·"1. 과제개요" 가 끊는다
    assert f["project_type"] == "수시연구과제" and f["pi"] == "경영연구처 홍길동"
    assert f["period"] == "2025.11.24.∼2026.8.31.(9개월)" and f["budget"] == "90,000천원"
    assert f["purpose"] == "- 목적 문장"
    assert f["content"] == "- 법규·제도 개선 / 시사점"  # 본문 줄은 쌍 라벨로 쪼개지 않는다
    assert f["disclosure_status"] == "비공개"
    assert "open_date" not in f and "_group" not in f  # 빈 값·묶음 머리글은 저장 안 함


def test_spaced_slash_pairs_before_middle_dot():
    f = parse_labeled(["과제유형 / 연구책임자 : 정책·전략 과제 / 기술연구처 김철수"])
    assert f["project_type"] == "정책·전략 과제" and f["pi"] == "기술연구처 김철수"


def test_period_with_u223c_tilde_and_trailing_dots():
    assert parse_period("2025.11.24.∼2026.8.31.(9개월)") == (date(2025, 11, 24), date(2026, 8, 31))
    assert parse_period("2025.11.∼2026.8.") == (date(2025, 11, 1), date(2026, 8, 31))


def test_budget_thousand_won():
    assert parse_budget_krw("90,000천원") == 90_000_000


@pytest.mark.parametrize(
    ("pi", "department"),
    [
        ("경영연구처 홍길동", "경영연구처"),
        ("철도연구원 기술연구처 홍길동", "철도연구원 기술연구처"),
        ("경영연구처 책임연구원 홍길동", "경영연구처"),  # 직급은 뺀다
        ("홍길동(경영연구처)", "경영연구처"),
        ("홍길동", None),
        ("홍길동 외 2인", None),  # 조직 단위 접미사가 아니면 부서로 보지 않는다
    ],
)
def test_department_from_pi(pi, department):
    text = f"제목\tT\n연구목적\t목적\n연구책임자\t{pi}"
    assert normalize_summary(raw_of(text)).department == department


def test_default_org_applies_only_when_nothing_else_found():
    doc = normalize_summary(raw_of(ALIO_FORMAT), default_org="korail")
    assert doc.orgs == ["korail"] and doc.department == "경영연구처"
    assert normalize_summary(raw_of(ALIO_FORMAT)).orgs == []
    # 기관명 라벨이 있으면 그것이 우선한다
    text = ALIO_FORMAT.replace("* 저자", "* 기관명\n국가철도공단\n* 저자")
    kr = [{"code": "C0270", "name": "국가철도공단", "tag": "kr"}]
    assert normalize_summary(raw_of(text), institutions=kr, default_org="korail").orgs == ["kr"]


def test_preface_normalizes_tilde():
    doc = normalize_summary(raw_of(ALIO_FORMAT), default_org="korail")
    assert "연구기간 2025.11.24.~2026.8.31.(9개월)" in doc.body.splitlines()[0]


# ── 기관 태그 출처: catalog → text → default ─────────────────
ALL_INSTITUTIONS = [
    {"code": "C0268", "name": "한국철도공사", "tag": "korail"},
    {"code": "C0269", "name": "한국철도기술연구원", "tag": "krri"},
    {"code": "C0270", "name": "국가철도공단", "tag": "kr"},
]


def _entry(tag):
    return CatalogEntry(catalog_id="c1", institution_tag=tag, title="카탈로그 제목").model_dump(
        mode="json"
    )


@pytest.mark.parametrize("tag", ["korail", "krri", "kr"])
def test_catalog_org_wins_and_default_is_not_used(tag):
    # 본문에 한국철도공사 기관명이 있어도, default_org 가 korail 이어도 카탈로그 기관을 쓴다
    text = ALIO_FORMAT.replace("* 저자", "* 기관명\n한국철도공사\n* 저자")
    doc = normalize_summary(
        raw_of(text, catalog=_entry(tag)), institutions=ALL_INSTITUTIONS, default_org="korail"
    )
    assert doc.orgs == [tag] and doc.raw["org_source"] == "catalog"
    assert AlioSummarySource(Path("."), limits=None).ingest_warnings(doc) == []


def test_text_org_used_when_catalog_unmatched():
    text = ALIO_FORMAT.replace("* 저자", "* 기관명\n한국철도기술연구원\n* 저자")
    doc = normalize_summary(raw_of(text), institutions=ALL_INSTITUTIONS, default_org="korail")
    assert doc.orgs == ["krri"] and doc.raw["org_source"] == "text"


def test_default_org_marked_and_warned():
    src = AlioSummarySource(Path("."), limits=None, default_org="korail")
    doc = src.normalize(raw_of(ALIO_FORMAT))
    assert doc.orgs == ["korail"] and doc.raw["org_source"] == "default"
    assert src.ingest_warnings(doc) == [("assumed_org", "korail")]
    bare = normalize_summary(raw_of(ALIO_FORMAT))
    assert bare.orgs == [] and bare.raw["org_source"] is None


async def test_end_to_end_catalog_match_by_filename_and_warning_for_unmatched(inbox, limits):
    from rra.domain.models import CatalogEntry as Entry
    from tests.fakes import FakeCatalog

    (inbox / "2026-krri-1.txt").write_text(ALIO_FORMAT, encoding="utf-8")  # 매칭됨
    (inbox / "unmatched.txt").write_text(ALIO_FORMAT.replace("자산개발", "궤도"), encoding="utf-8")
    catalog = FakeCatalog(
        [Entry(catalog_id="2026-krri-1", institution_tag="krri", title="KRRI 과제")]
    )
    src = AlioSummarySource(
        inbox, limits=limits, institutions=ALL_INSTITUTIONS, catalog=catalog, default_org="korail"
    )
    repo = InMemoryRepository()
    report = await IngestSources([src], repo)()

    assert repo.docs["alio:2026-krri-1"].orgs == ["krri"]
    [w] = report.warnings
    assert w.code == "assumed_org" and w.detail == "korail" and w.doc_id.startswith("alio:sum-")
    assert repo.docs[w.doc_id].orgs == ["korail"]
