"""own_docs — 과제 폴더 순회, 요약 파일 선택·파싱(가짜 runner), 정규화(이름 제거), ingest."""

import logging
from pathlib import Path

from rra.adapters.sources._sandbox import ParseCrashed, SandboxLimits
from rra.adapters.sources.own.docs import (
    OwnDocsSource,
    normalize_own_summary,
    project_dirs,
    title_first,
)
from rra.application.usecases.ingest_sources import IngestSources
from tests.fakes import InMemoryRepository

HWP_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest"
SUMMARY_TEXT = """KTX-1 차세대차량 교체 타당성 평가 연구
1. 과제개요
◦ 과제유형 / 연구책임자 : 수시연구과제 / 경영연구처 박한균
◦ 연구기간 / 소요예산 : 2025. 3. 28. ~ 2026. 3. 31.(13개월) / 220백만원
2. 연구목적
◦ 기존차량 연장사용과 신규차량 도입간의 타당성 비교
3. 연구내용
◦ 국내외 유사 사례 검토
4. 기대효과
◦ 교체비용 부담 감소
5. 활용계획
◦ 정책 수립 근거 자료"""
INSTITUTIONS = [{"code": "C0268", "name": "한국철도공사", "tag": "korail", "aliases": ["코레일"]}]


def limits():
    return SandboxLimits(timeout_sec=5, mem_mb=256, max_input_mb=1)


def runner(text=SUMMARY_TEXT, *, fail_on: str | None = None):
    calls = []

    async def run(fd, fmt, lim):
        calls.append(fmt)
        if fmt == fail_on:
            raise ParseCrashed("c")
        return {"text": text, "toc": [], "pages": None}

    run.calls = calls
    return run


def make_inbox(tmp_path: Path) -> Path:
    inbox = tmp_path / "own_docs"
    for rel in (
        "2025/25.1.6 박한균-신규 철도차량 도입/붙임2. 요약문(공시용).hwp",
        "2025/25.1.6 박한균-신규 철도차량 도입/붙임3. 연구완료보고서.hwp",
        "260324_ktx-1 차세대차량 교체/붙임2. 요약문(공시용).hwpx",
        "_done/old/요약문(공시용).hwp",
        ".hidden/요약문(공시용).hwp",
    ):
        p = inbox / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(HWP_MAGIC if rel.endswith(".hwp") else b"PK\x03\x04rest")
    return inbox


def test_project_dirs_walks_year_folders_and_skips_done_hidden(tmp_path):
    inbox = make_inbox(tmp_path)
    names = [p.name for p in project_dirs(inbox)]
    assert names == ["25.1.6 박한균-신규 철도차량 도입", "260324_ktx-1 차세대차량 교체"]  # 이름순
    assert project_dirs(tmp_path / "없음") == []


def test_title_first_turns_leading_title_line_into_a_label():
    lines = ["", "KTX-1 평가 연구", "1. 과제개요", "◦ 연구목적 : x"]
    assert title_first(lines) == ["제목: KTX-1 평가 연구", "1. 과제개요", "◦ 연구목적 : x"]
    assert title_first(["제목: 이미 라벨", "본문"]) == ["제목: 이미 라벨", "본문"]
    assert title_first(["1. 과제개요", "본문"]) == ["1. 과제개요", "본문"]


async def test_search_selects_one_summary_per_project_and_normalizes_without_names(tmp_path):
    inbox = make_inbox(tmp_path)
    run = runner()
    src = OwnDocsSource(inbox, limits=limits(), institutions=INSTITUTIONS, runner=run)
    raws = await src.search(None, 10)
    assert [r["fmt"] for r in raws] == ["hwp", "hwpx"] and run.calls == ["hwp", "hwpx"]
    assert raws[1]["folder_title"] == "ktx-1 차세대차량 교체" and raws[1]["variant"] == ""
    assert raws[0]["folder_title"] == "신규 철도차량 도입"
    doc = src.normalize(raws[1])
    assert (
        doc.source == "alio" and doc.text_basis == "summary" and doc.doc_id.startswith("alio:sum-")
    )
    assert doc.title == "KTX-1 차세대차량 교체 타당성 평가 연구"
    assert doc.department == "경영연구처" and doc.orgs == ["korail"]
    assert doc.authors == [] and doc.raw["pi"] == "경영연구처"  # 이름 제거
    assert "박한균" not in doc.model_dump_json()
    assert doc.project_period is not None and doc.raw["budget_krw"] == 220_000_000
    assert "■ 연구목적" in doc.body and doc.raw["origin"] == "own_docs" and doc.raw["fmt"] == "hwpx"
    assert src.inbox_status() == {"pending": 2, "done": 1, "quarantine": 0}


async def test_same_bytes_in_two_folders_are_returned_once(tmp_path):
    inbox = make_inbox(tmp_path)
    src = OwnDocsSource(inbox, limits=limits(), runner=runner())
    raws = await src.search(None, 10)
    assert len(raws) == 2  # hwp 와 hwpx 는 바이트가 다르다
    (inbox / "2025/25.1.6 박한균-신규 철도차량 도입/붙임2. 요약문(공시용).hwp").write_bytes(
        b"PK\x03\x04rest"
    )
    # 확장자 hwp 인데 zip 매직 → MagicMismatch 로 거부, 나머지는 계속
    assert len(await src.search(None, 10)) == 1


async def test_failed_parse_is_logged_without_names_and_other_files_continue(tmp_path, caplog):
    inbox = make_inbox(tmp_path)
    src = OwnDocsSource(inbox, limits=limits(), runner=runner(fail_on="hwp"))
    with caplog.at_level(logging.WARNING, logger="rra.sources.own_docs"):
        raws = await src.search(None, 10)
    assert [r["fmt"] for r in raws] == ["hwpx"]  # hwp 는 실패, hwpx 는 계속
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "ParseCrashed" in text and "박한균" not in text and "신규 철도차량" not in text


async def test_acknowledge_moves_project_folder_keeping_year(tmp_path):
    inbox = make_inbox(tmp_path)
    src = OwnDocsSource(inbox, limits=limits(), runner=runner())
    raws = await src.search(None, 10)
    src.acknowledge(raws)
    assert (
        inbox / "_done/2025/25.1.6 박한균-신규 철도차량 도입/붙임3. 연구완료보고서.hwp"
    ).exists()
    assert (inbox / "_done/260324_ktx-1 차세대차량 교체").is_dir()
    assert project_dirs(inbox) == []
    src.acknowledge([{"_dir": str(tmp_path / "elsewhere"), "sha256": "x"}])  # 남의 폴더는 무시


def test_unlabeled_text_falls_back_to_folder_title_and_plain_body():
    raw = {
        "sha256": "ab" * 32,
        "fmt": "pdf",
        "lines": ["자유 형식 요약", "둘째 줄"],
        "variant": "고속",
        "folder_title": "수송수요 예측",
    }
    doc = normalize_own_summary(raw, institutions=INSTITUTIONS)
    assert doc.title == "수송수요 예측 고속" and doc.body == "자유 형식 요약\n둘째 줄"
    assert doc.doc_id.startswith("alio:own-") and doc.raw["unlabeled"] is True
    assert doc.orgs == ["korail"] and doc.raw["org_source"] == "default"


async def test_ingest_stores_summaries_and_warns_assumed_org(tmp_path):
    inbox = make_inbox(tmp_path)
    src = OwnDocsSource(inbox, limits=limits(), runner=runner())  # institutions 없음 → default_org
    repo = InMemoryRepository()
    report = await IngestSources([src], repo)()
    assert report.stored == 1 and report.deduped == 1  # 같은 제목 두 파일 → 하나
    assert {w.code for w in report.warnings} == {"assumed_org"}
    assert project_dirs(inbox) == []  # upsert 뒤 acknowledge
    [doc] = list(repo.docs.values())
    assert doc.visibility == "public" and doc.text_basis == "summary"


async def test_plain_summary_without_disclosure_copy_is_internal(tmp_path):
    inbox = tmp_path / "own_docs"
    p = inbox / "2023/23.01.01 홍길동_공시 없는 과제/붙임1 요약문.hwp"
    p.parent.mkdir(parents=True)
    p.write_bytes(HWP_MAGIC)
    src = OwnDocsSource(inbox, limits=limits(), institutions=INSTITUTIONS, runner=runner())
    [raw] = await src.search(None, 10)
    assert raw["disclosed"] is False
    doc = src.normalize(raw)
    assert doc.visibility == "internal" and doc.raw["disclosed"] is False
    assert normalize_own_summary({**raw, "disclosed": True}).visibility == "public"
