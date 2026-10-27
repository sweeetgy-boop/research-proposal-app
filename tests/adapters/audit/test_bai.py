"""감사원 스냅샷 → Document.

크롤러는 Playwright 라 순수 부분(행 해석·srno 추출·robots 검사)만 테스트한다."""

import json
from pathlib import Path

import pytest

from rra.adapters.sources._sandbox import SandboxLimits
from rra.adapters.sources.audit import BaiAuditSource, normalize_bai_record
from rra.adapters.sources.audit._common import ext_of, strip_size
from rra.adapters.sources.audit.bai_crawler import (
    BaiConfig,
    BaiCrawler,
    parse_row_cells,
    srno_values,
)
from rra.adapters.sources.korail_web.snapshot import SnapshotDir
from rra.domain.rules.overlap import tier_of

INST = [{"name": "한국철도공사", "tag": "korail"}, {"name": "국가철도공단", "tag": "kr"}]
PDF = b"%PDF-1.4 " + b"x" * 100


def test_strip_size_and_ext():
    assert strip_size("공개문_전문.pdf (2.49 MB)") == "공개문_전문.pdf"
    assert ext_of("(20260309)보도자료(철도시설 안전관리 실태 점검).hwp (3.57 MB)") == "hwp"


def test_parse_row_cells_and_srno_values():
    row = parse_row_cells(
        ["한국철도공사 정기감사", "기관정기", "교통/물류", "Download", "", "2025-02-20"]
    )
    assert row == {
        "title": "한국철도공사 정기감사",
        "kind": "기관정기",
        "field": "교통/물류",
        "posted": "2025-02-20",
    }
    payload = {"data": {"list": [{"srno": 3287, "title": "a"}, {"SRNO": "3001"}], "total": 55}}
    assert srno_values(payload) == ["3287", "3001"]


def test_robots_blocks_api_and_disallowed_paths():
    cfg = BaiConfig.from_config({"queries": ["철도"]})

    async def robots() -> str:
        return "User-agent: *\nAllow: /\nDisAllow:/api/\n"

    crawler = BaiCrawler(cfg, Path("/nonexistent"), robots_text=robots)
    import asyncio

    asyncio.run(crawler.load_robots())
    crawler._check("https://www.bai.go.kr/bai/result/branch/list/")
    with pytest.raises(PermissionError):
        crawler._check("https://www.bai.go.kr/api/bak/dar/AWUBAKDAR001E?size=10")


def _snapshot(tmp_path: Path) -> SnapshotDir:
    snap = SnapshotDir(tmp_path / "bai", "2026-10-27")
    snap.ensure()
    import hashlib

    sha = hashlib.sha256(PDF).hexdigest()
    rel = f"files/{sha[:2]}/{sha}.pdf"
    snap.write_bytes(rel, PDF)
    snap.append_manifest(
        {
            "native_id": "3287",
            "source": "bai",
            "doc_type": "audit",
            "title": "철도시설 안전관리 실태 점검",
            "kind": "특정사안",
            "field": "교통/물류",
            "posted": "2026-03-09",
            "bai_department": "국토환경1과",
            "query": "철도",
            "url": "https://www.bai.go.kr/bai/result/branch/detail?srno=3287",
            "terms": "공공누리 제4유형(출처표시·상업적 이용금지·변경금지)",
            "snapshot": "2026-10-27",
            "files": [
                {"name": "보도자료.hwp", "ext": "hwp", "downloaded": False, "reason": "type"},
                {
                    "name": "공개문_전문.pdf",
                    "ext": "pdf",
                    "downloaded": True,
                    "sha256": sha,
                    "bytes": len(PDF),
                    "path": rel,
                },
            ],
        }
    )
    snap.append_manifest(
        {
            "native_id": "2001",
            "title": "한국철도공사 정기감사",
            "kind": "기관정기",
            "posted": "2025-02-20",
            "url": "https://www.bai.go.kr/bai/result/branch/detail?srno=2001",
            "snapshot": "2026-10-27",
            "files": [],  # 파일을 받지 못한 항목은 적재하지 않는다
        }
    )
    return snap


async def test_source_reads_snapshot_and_parses_pdf(tmp_path):
    snap = _snapshot(tmp_path)

    async def runner(fd, fmt, limits):
        assert fmt == "pdf"
        return {
            "text": "철도시설 안전관리 감사 결과 지적사항. 담당자 홍길동 02-123-4567. " * 5,
            "toc": ["Ⅰ"],
            "pages": 40,
        }

    src = BaiAuditSource(snap.root, limits=SandboxLimits(), institutions=INST, runner=runner)
    assert src.status()["items"] == 2 and src.status()["snapshot"] == "2026-10-27"
    raws = await src.search(None, 10)
    assert [r["native_id"] for r in raws] == ["3287"]
    doc = src.normalize(raws[0])
    assert doc.doc_id == "bai:3287" and doc.doc_type == "audit" and doc.source == "bai"
    assert doc.raw["audit_kind"] == "특정사안" and doc.raw["bai_department"] == "국토환경1과"
    assert doc.pub_date.isoformat() == "2026-03-09" and "홍길동" not in doc.body
    assert doc.orgs == [] and tier_of(doc) == "external"
    assert json.dumps(doc.raw, ensure_ascii=False).count("공공누리") == 1


def test_normalize_tags_rail_org_from_title():
    doc = normalize_bai_record(
        {
            "native_id": "2001",
            "title": "한국철도공사 정기감사",
            "posted": "2025-02-20",
            "text": "x" * 100,
            "url": "https://www.bai.go.kr/bai/result/branch/detail?srno=2001",
        },
        institutions=INST,
    )
    assert doc.orgs == ["korail"] and doc.doc_type == "audit"
