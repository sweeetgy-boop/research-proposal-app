"""own 폴더·파일 이름 해석 — NFD/NFC, 날짜·이름 제거, 꼬리말, 요약 파일 선택."""

import unicodedata
from pathlib import Path

from rra.adapters.sources.own._names import (
    folder_title,
    is_summary_file,
    select_summary_files,
    strip_person,
    variant_of,
)


def nfd(s: str) -> str:
    return unicodedata.normalize("NFD", s)


def test_folder_title_strips_date_and_person():
    assert folder_title("25.1.6 박한균-신규 철도차량의 효율적인 도입방안 연구") == (
        "신규 철도차량의 효율적인 도입방안 연구"
    )
    assert folder_title("22.01.06 김한수_포스트 코로나 시대의 철도관광사업 전략 자문") == (
        "포스트 코로나 시대의 철도관광사업 전략 자문"
    )
    assert folder_title("25.6.4 임형석 - 철도전력의 안정적인 공급") == "철도전력의 안정적인 공급"
    assert (
        folder_title("260324_ktx-1 차세대차량 교체 타당성 평가")
        == "ktx-1 차세대차량 교체 타당성 평가"
    )
    assert folder_title("260917_수송수요 예측 (4건)") == "수송수요 예측"
    assert folder_title("23.08.30 수송수요 예측 연구") == "수송수요 예측 연구"  # 이름 아님
    assert folder_title(nfd("260324_궤도 연구")) == "궤도 연구"  # macOS NFD 파일명


def test_variant_of_reads_bundle_tails_only():
    assert variant_of(Path("붙임2. 요약문(공시용).hwp")) == ""
    assert variant_of(Path("[붙임3] 연구요약보고서(공시용).hwp")) == ""
    assert variant_of(Path("1. 요약문(공시용, 고속).hwp")) == "고속"
    assert variant_of(Path("2-4. 요약문(화물)_공시용.hwpx")) == "화물"
    assert variant_of(Path("2-3. 요약문(광역)-공시용.hwpx")) == "광역"
    assert variant_of(Path("1-2. 요약문(공시용)_준고속.hwp")) == "준고속"
    assert variant_of(Path("2.1 요약문(고속 및 준고속)_공시용.hwp")) == "고속 및 준고속"
    assert variant_of(Path("붙임 4. 연구과제요약보고서(공시용)_0819.hwp")) == ""
    assert variant_of(Path("2.요약문_최종.hwpx")) == ""


def test_is_summary_file_and_strip_person():
    assert is_summary_file(Path("붙임2. 요약문(공시용).hwp"))
    assert is_summary_file(Path("공시용 요약문.pdf"))
    assert not is_summary_file(Path("붙임3. 연구완료보고서.hwp"))
    assert not is_summary_file(Path("~$요약문(공시용).hwp"))
    assert not is_summary_file(Path("요약문(공시용).docx"))
    assert strip_person("경영연구처 박한균") == "경영연구처"
    assert strip_person("철도연구원 기술연구처") == "철도연구원 기술연구처"
    assert strip_person("경영연구처") == "경영연구처"


def _touch(root: Path, rel: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


def test_select_prefers_disclosure_then_hwpx_then_shallow(tmp_path):
    _touch(tmp_path, "붙임1. 요약문.hwpx")
    best = _touch(tmp_path, "붙임2. 요약문(공시용).hwp")
    _touch(tmp_path, "공시용/1. 요약문(공시용).hwp")  # 같은 점수면 얕은 경로
    _touch(tmp_path, "붙임3. 연구완료보고서.hwpx")
    assert select_summary_files(tmp_path) == [("", best)]


def test_select_falls_back_to_plain_summary_and_prefers_hwpx(tmp_path):
    _touch(tmp_path, "1.요약문.hwp")
    best = _touch(tmp_path, "1.요약문.hwpx")
    _touch(tmp_path, "2.완료보고서.hwp")
    assert select_summary_files(tmp_path) == [("", best)]


def test_select_splits_bundles_by_variant_and_merges_prefix_variants(tmp_path):
    g = _touch(tmp_path, "붙임2. 요약문(공시용)/1-1. 요약문(공시용)_고속.hwp")
    h = _touch(tmp_path, "붙임2. 요약문(공시용)/2-4. 요약문(화물)_공시용.hwpx")
    _touch(tmp_path, "공시/붙임2. 요약문(공시용)/1-1. 요약문(공시용)_고속.hwp")  # 중복 복사본
    _touch(tmp_path, "붙임1. 요약문/1-1. 요약문(고속).hwp")  # 일반 요약은 진다
    assert select_summary_files(tmp_path) == [("고속", g), ("화물", h)]
    bundle2 = tmp_path / "b2"
    a = _touch(bundle2, "붙임 4. 연구요약보고서(공시용, 제동슈키 분리지그).hwp")
    _touch(bundle2, "붙임 3. 연구과제요약서(제동슈키).hwp")  # 접두 꼬리말 → 같은 과제
    assert select_summary_files(bundle2) == [("제동슈키 분리지그", a)]


def test_select_drops_untailed_copy_when_tails_split_a_bundle(tmp_path):
    _touch(tmp_path, "3. 요약문(공시용, 일반).hwp")
    _touch(tmp_path, "2. 공시용 요약문/1. 요약문(공시용, 고속).hwp")
    _touch(tmp_path, "2. 공시용 요약문/3. 요약문(공시용, 일반).hwp")
    _touch(tmp_path, "붙임1. 요약문(공시용).hwp")  # 꼬리말 없는 복사본은 빠진다
    assert [v for v, _ in select_summary_files(tmp_path)] == ["고속", "일반"]
    assert select_summary_files(tmp_path / "없음") == []
