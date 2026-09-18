"""알리오 카탈로그 — normalize_catalog_row(순수), FileCatalog(샌드박스 csv), fetch_catalog."""

import stat
from datetime import date
from pathlib import Path

import httpx
import pytest

from rra.adapters.sources._base import FetchError, GuardedClient
from rra.adapters.sources.alio.catalog import (
    DEFAULT_COLUMNS,
    FileCatalog,
    catalog_id_for,
    fetch_catalog,
    normalize_catalog_row,
)
from rra.adapters.sources.alio.filecheck import MagicMismatch

INSTITUTIONS = [
    {"code": "C0268", "name": "한국철도공사", "tag": "korail"},
    {"code": "C0269", "name": "한국철도기술연구원", "tag": "krri"},
    {"code": "C0270", "name": "국가철도공단", "tag": "kr"},
]
SAMPLE = Path(__file__).parents[2] / "fixtures" / "alio" / "catalog" / "sample.csv"


def norm(row):
    return normalize_catalog_row(row, DEFAULT_COLUMNS, INSTITUTIONS)


# ── normalize_catalog_row (순수 함수) ─────────────────────
def test_match_by_code():
    e = norm(
        {
            "기관코드": "C0268",
            "공시번호": "2024-117",
            "제목": " 궤도\t틀림 연구 ",
            "공시일": "2024.03.05",
            "URL": "https://www.alio.go.kr/x?id=1",
        }
    )
    assert e.catalog_id == "2024-117"
    assert e.institution_tag == "korail"
    assert e.title == "궤도 틀림 연구"
    assert e.published == date(2024, 3, 5)
    assert e.url == "https://www.alio.go.kr/x?id=1"


def test_match_by_name_ignoring_spaces():
    e = norm({"기관명": "국가 철도공단", "보고서명": "교량 점검", "등록일": "20230101"})
    assert e.institution_tag == "kr" and e.published == date(2023, 1, 1)


def test_other_institution_or_no_title_is_dropped():
    assert norm({"기관코드": "C9999", "제목": "무관"}) is None
    assert norm({"기관코드": "C0268", "제목": "  "}) is None


def test_non_https_url_and_bad_date_dropped():
    e = norm(
        {"기관코드": "C0269", "제목": "t", "URL": "javascript:alert(1)", "공시일": "2024-13-40"}
    )
    assert e.url is None and e.published is None


def test_catalog_id_is_filename_safe_or_stable_hash():
    assert catalog_id_for("../../etc", "C0268", "t", "") == "etc"
    a = catalog_id_for("", "C0268", "궤도 연구", "2024-01-01")
    assert a == catalog_id_for("", "C0268", "궤도 연구", "2024-01-01")
    assert a.startswith("h") and len(a) == 16 and a.isalnum()
    assert a != catalog_id_for("", "C0268", "궤도 연구", "2024-01-02")


def test_control_chars_removed_from_title():
    assert norm({"기관코드": "C0268", "제목": "a\x1b[31mb\x00c"}).title == "a [31mb c"


# ── FileCatalog (실제 샌드박스) ───────────────────────────
@pytest.fixture
def catalog_dir(tmp_path):
    d = tmp_path / "catalog"
    d.mkdir()
    return d


async def test_file_catalog_filters_and_dedups(catalog_dir, limits):
    (catalog_dir / "c.csv").write_bytes(
        "기관코드,기관명,공시번호,제목,공시일\n"
        "C0268,한국철도공사,1,궤도 연구,2024-01-02\n"
        "C0268,한국철도공사,1,궤도 연구(중복),2024-01-02\n"
        "C0001,다른기관,2,무관,2024-01-02\n"
        "C0270,국가철도공단,3,교량 연구,2023-05-01\n".encode("cp949")
    )
    cat = FileCatalog(catalog_dir, limits=limits, institutions=INSTITUTIONS)
    entries = await cat.entries()
    assert [(e.catalog_id, e.institution_tag, e.title) for e in entries] == [
        ("1", "korail", "궤도 연구"),
        ("3", "kr", "교량 연구"),
    ]


async def test_empty_catalog_dir(tmp_path, limits):
    assert (
        await FileCatalog(tmp_path / "none", limits=limits, institutions=INSTITUTIONS).entries()
        == []
    )


async def test_disguised_xlsx_rejected_before_parsing(catalog_dir, limits):
    (catalog_dir / "c.csv").write_bytes(b"PK\x03\x04xlsx")

    async def never(*a):
        raise AssertionError("파서에 도달하면 안 된다")

    with pytest.raises(MagicMismatch):
        await FileCatalog(
            catalog_dir, limits=limits, institutions=INSTITUTIONS, runner=never
        ).entries()


@pytest.mark.skipif(not SAMPLE.exists(), reason="실제 카탈로그 샘플 미투입")
async def test_real_sample_has_target_institutions(tmp_path, limits):
    d = tmp_path / "c"
    d.mkdir()
    (d / "sample.csv").write_bytes(SAMPLE.read_bytes())
    entries = await FileCatalog(d, limits=limits, institutions=INSTITUTIONS).entries()
    assert entries, "sample.csv 헤더가 DEFAULT_COLUMNS / sources.yaml columns 와 맞지 않는다"
    assert {e.institution_tag for e in entries} <= {"korail", "krri", "kr"}


# ── fetch_catalog (GuardedClient) ────────────────────────
def client_for(handler):
    return GuardedClient(
        ["www.data.go.kr"], transport=httpx.MockTransport(handler), resolver=lambda host: False
    )


async def test_fetch_saves_atomically_with_0600(catalog_dir):
    body = "기관코드,제목\nC0268,t\n".encode("cp949")
    client = client_for(
        lambda r: httpx.Response(200, content=body, headers={"content-type": "text/csv"})
    )
    async with client:
        dest = await fetch_catalog(
            client, "https://www.data.go.kr/f.csv", catalog_dir, max_bytes=1024
        )
    assert dest.read_bytes() == body and dest.suffix == ".csv"
    assert stat.S_IMODE(dest.stat().st_mode) == 0o600
    assert [p.name for p in catalog_dir.iterdir()] == [dest.name]  # tmp 파일 남지 않음


async def test_fetch_rejects_binary_and_html(catalog_dir):
    zipped = client_for(
        lambda r: httpx.Response(
            200, content=b"PK\x03\x04", headers={"content-type": "application/octet-stream"}
        )
    )
    async with zipped:
        with pytest.raises(MagicMismatch):
            await fetch_catalog(zipped, "https://www.data.go.kr/f", catalog_dir, max_bytes=1024)
    html = client_for(
        lambda r: httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"})
    )
    async with html:
        with pytest.raises(FetchError):
            await fetch_catalog(html, "https://www.data.go.kr/f", catalog_dir, max_bytes=1024)
    assert list(catalog_dir.iterdir()) == []
