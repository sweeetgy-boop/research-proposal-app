"""info.korail.com 페이지 해석 — tests/fixtures/korail_web 의 실물 축약 샘플(이름·연락처 제거).
네트워크 없음."""

from pathlib import Path

from rra.adapters.sources.korail_web._html import (
    filename_from_disposition,
    head_title,
    parse_board_list,
    parse_board_view,
    parse_contents,
    parse_html,
    parse_preinfo_detail,
    parse_preinfo_list,
    parse_tables,
)

FIX = Path(__file__).parents[2] / "fixtures" / "korail_web"
BASE = "https://info.korail.com/info/"


def _read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_board_list_rows_total_pages_dates_and_icons():
    page = parse_board_list(
        _read("board_list_press.html"), BASE + "selectBbsNttList.do?bbsNo=199&key=911"
    )
    assert page.total == 6380 and page.pages == 638
    assert len(page.rows) == 10
    first = page.rows[0]
    assert first.native_id == "bbs:199:27437"
    assert first.url.startswith("https://info.korail.com/info/selectBbsNttView.do?")
    assert "nttNo=27437" in first.url
    assert first.posted == "2026-10-23"
    assert not first.title.endswith("새글")
    assert any(r.file_kinds == ("hwp",) for r in page.rows)
    assert all(r.posted and r.posted.startswith("2026-10") for r in page.rows)


def test_board_list_without_dates_still_lists_rows():
    page = parse_board_list(
        _read("board_list_esg.html"), BASE + "selectBbsNttList.do?bbsNo=699&key=2254"
    )
    assert page.total == 12 and page.pages == 1
    assert len(page.rows) == 12
    assert all(r.native_id.startswith("bbs:699:") for r in page.rows)
    assert "지속가능경영보고서" in page.rows[0].title


def test_board_view_title_date_text_attachments_terms():
    item = parse_board_view(
        _read("board_view_press.html"), BASE + "selectBbsNttView.do?key=911&bbsNo=199&nttNo=27436"
    )
    assert item.title.startswith("“운전은 쉬고")
    assert item.posted == "2026-10-22"
    assert "고흥유자축제" in item.text
    assert "<" not in item.text.split("\n")[0]
    assert [a.url for a in item.attachments] == [
        "https://info.korail.com/info/downloadBbsFile.do?atchmnflNo=28823",
        "https://info.korail.com/info/downloadBbsFile.do?atchmnflNo=28822",
    ]
    assert item.attachments[1].name.endswith(".hwp")
    assert item.terms and item.terms.startswith("공공누리 제4유형")
    assert item.images == []


def test_contents_page_title_from_head_and_images():
    item = parse_contents(_read("contents_716.html"), BASE + "contents.do?key=716")
    assert item.title == "경영가치체계"
    assert "경영목표" in item.text and "전략과제" in item.text
    assert len(item.images) == 1
    img = item.images[0]
    assert img.src.startswith("https://info.korail.com/") and img.alt == "전략경영체계도"
    assert item.terms and "제4유형" in item.terms
    assert head_title(parse_html(_read("contents_716.html"))) == (
        "공사소개 > 일반현황 > 경영가치체계",
        "경영가치체계",
    )


def test_tables_expand_rowspan_into_grid():
    tables = parse_tables(_read("contents_1900.html"))
    assert tables, "표가 있어야 한다"
    grid = tables[0]
    assert grid[0] == ["경영목표", "전략과제", "주요내용", "목표지표(KPI)"]
    goals = [row[0] for row in grid[1:16]]
    assert len(set(goals)) == 5  # 5대 경영목표가 rowspan 으로 3행씩
    assert all(goals[i] == goals[i + 1] for i in (0, 3, 6, 9, 12))
    assert grid[1][1].replace(" / ", " ") == "AI기반 예방적 안전관리 구축"


def test_preinfo_list_titles_and_detail_links_only():
    page = parse_preinfo_list(_read("preinfo_list.html"), BASE + "selectInfoRelWebList.do?key=746")
    assert page.total == 171 and page.pages == 18
    assert page.rows and all(r.native_id.startswith("preinfo:") for r in page.rows)
    assert page.rows[0].title == "[인사·총무·회계] 자산관리 현황"
    assert page.rows[0].posted == "2026-04-01"
    assert len(page.rows) < 10  # 링크형(상세 없음) 항목은 빠진다


def test_preinfo_detail():
    item = parse_preinfo_detail(
        _read("preinfo_detail.html"), BASE + "selectInfoRelWebDetail.do?infoRelNo=230"
    )
    assert item.title == "2026 정보공개심의회 결과"
    assert item.posted == "2026-08-13"
    assert item.department == "윤리경영처"
    assert item.attachments[0].url.endswith("downloadInfoRelFile.do?infoRelAtchNo=2808")
    assert item.attachments[0].name.endswith(".hwpx")


def test_filename_from_disposition():
    assert filename_from_disposition("attachment; filename=261022 %EA%B0%80.hwp") == "261022 가.hwp"
    assert filename_from_disposition('attachment;filename="2016.zip"') == "2016.zip"
    assert filename_from_disposition("attachment; filename=../x/../y.pdf") == ".._x_.._y.pdf"
    assert filename_from_disposition(None) is None
