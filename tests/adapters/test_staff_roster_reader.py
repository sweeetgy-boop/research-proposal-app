"""사번 명부 읽기(A2): 샌드박스로 xlsx·csv 의 사번 열만, 다른 열은 나오지 않음, 저장소 일괄 등록."""

import asyncio
import csv
import json

import openpyxl
import pytest

from rra.adapters.auth import FileAuthStore, RosterReader
from rra.adapters.sources._sandbox import SandboxLimits
from rra.application.ports import AuthStorePort, RosterReaderPort, RosterReadError
from rra.application.usecases.import_staff import ImportStaff
from rra.application.usecases.login import Login, LoginFailed

LIMITS = SandboxLimits(timeout_sec=60, mem_mb=1024, max_input_mb=2, max_output_mb=2)
NAMES = ("가짜이름일", "가짜이름이", "가짜이름삼")
# 가짜 사번: 앞자리 0 문자열, 숫자 셀(0 빠짐), 공백·하이픈, 중복, 빈칸, 형식 오류
ROWS = [
    ("가짜이름일", "0012345", "연구기획처"),
    ("가짜이름이", 12346, "기술연구처"),
    ("가짜이름삼", " 00-123-47 ", "경영연구처"),
    ("가짜이름일", "0012345", "연구기획처"),  # 중복
    ("", None, ""),  # 빈칸
    ("가짜이름이", "x", ""),  # 형식 오류 (행 8)
]
VALUES = ("0012345", "12346", "0012347")


def make_xlsx(path, *, header=("이름", "사번", "부서"), title_rows=1, sheet="명단"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for _ in range(title_rows):
        ws.append(["철도연구원 직원 명단"])
    ws.append(list(header))
    for row in ROWS:
        ws.append(list(row))
    other = wb.create_sheet("기타")
    other.append(["메모"])
    wb.save(path)
    return path


def make_csv(path, encoding="utf-8-sig"):
    with open(path, "w", newline="", encoding=encoding) as f:
        w = csv.writer(f)
        w.writerow(["이름", "사번", "부서"])
        for row in ROWS:
            w.writerow(["" if v is None else v for v in row])
    return path


def read(path, **kw):
    return asyncio.run(RosterReader(LIMITS).read(path, **kw))


def test_reader_satisfies_port_and_returns_only_staff_column(tmp_path):
    assert isinstance(RosterReader(LIMITS), RosterReaderPort)
    roster = read(make_xlsx(tmp_path / "명단.xlsx"))
    assert roster.sheet == "명단" and roster.header_row == 2
    assert [r for r, _ in roster.cells] == [3, 4, 5, 6, 7, 8]  # 파일 행 번호 (빈 행 포함)
    values = [v for _, v in roster.cells]
    assert values == ["0012345", "12346", "00-123-47", "0012345", None, "x"]
    dumped = repr(roster) + json.dumps(values, ensure_ascii=False)
    for name in NAMES:
        assert name not in dumped  # 이름·부서 열은 부모에 오지 않는다
    assert "연구기획처" not in dumped
    assert "0012345" not in repr(roster)


def test_reader_csv_cp949_and_sheet_column_options(tmp_path):
    roster = read(make_csv(tmp_path / "명단.csv", encoding="cp949"))
    assert roster.header_row == 1 and [v for _, v in roster.cells][:3] == [
        "0012345",
        "12346",
        "00-123-47",
    ]
    custom = read(
        make_xlsx(tmp_path / "b.xlsx", header=("이름", "직원번호", "부서")), column="직원번호"
    )
    assert [v for _, v in custom.cells][0] == "0012345"
    assert read(make_xlsx(tmp_path / "c.xlsx"), sheet="명단").sheet == "명단"


@pytest.mark.parametrize(
    ("make", "kw", "code"),
    [
        (lambda d: make_xlsx(d / "a.xlsx", header=("이름", "번호", "부서")), {}, "HeaderNotFound"),
        (lambda d: make_xlsx(d / "a.xlsx", title_rows=9), {}, "HeaderNotFound"),
        (lambda d: make_xlsx(d / "a.xlsx"), {"sheet": "없음"}, "SheetNotFound"),
        (lambda d: make_xlsx(d / "a.xls"), {}, "BadExtension"),
        (lambda d: (d / "e.csv").write_bytes(b"") or d / "e.csv", {}, "EmptyFile"),
    ],
)
def test_reader_errors_carry_code_only(tmp_path, make, kw, code):
    with pytest.raises(RosterReadError) as info:
        read(make(tmp_path), **kw)
    assert info.value.code == code and str(tmp_path) not in str(info.value)


def test_store_import_merges_replaces_dry_runs_and_login_normalizes(tmp_path):
    store = FileAuthStore(tmp_path / "auth")
    assert isinstance(store, AuthStorePort)
    store.add_staff("K-9999")
    importer = ImportStaff(store)
    cells = read(make_xlsx(tmp_path / "명단.xlsx")).cells

    preview = importer.run(cells, dry_run=True)
    assert preview.dry_run and preview.result.added == 3 and preview.registered_after == 4
    assert store.staff_count() == 1  # 저장 없음

    report = importer.run(cells)
    assert (report.result.added, report.result.existing, report.registered_after) == (3, 0, 4)
    assert report.counts.invalid_rows == (8,) and report.counts.length_histogram == {7: 2, 5: 1}
    text = "\n".join(report.as_lines()) + repr(report)
    for value in (*VALUES, "K-9999", "K9999", "00-123-47"):
        assert value not in text

    again = importer.run(cells)
    assert (again.result.added, again.result.existing) == (0, 3)

    padded = importer.run(cells, pad=7, replace=True)
    assert padded.result.added == 1 and padded.result.existing == 2  # 12346 → 0012346 만 새로
    assert padded.result.removed == 2  # K9999, 12346(0 없는 것)
    assert padded.registered_after == 3 and store.staff_count() == 3

    # 파일에는 HMAC 만
    for path in (tmp_path / "auth").iterdir():
        body = path.read_text()
        for value in (*VALUES, "K9999", "0012346"):
            assert value not in body

    # 로그인 입력도 같은 정규화: 공백·하이픈 무시
    login = Login(FileAuthStore(tmp_path / "auth"))
    assert login.staff(" 00-123-45 ").principal.kind == "staff"
    assert login.staff("0012346").principal.id == login.staff("00 12 346").principal.id
    with pytest.raises(LoginFailed):
        login.staff("12346")  # 0 빠진 값은 등록되지 않았다 (pad 로 교체했으므로)
    with pytest.raises(LoginFailed):
        login.staff("K-9999")  # replace 로 빠짐


def test_store_sees_file_changes_without_restart(tmp_path):
    """api 가 띄워 둔 저장소 객체는 로그인마다 staff.json 을 다시 읽는다."""
    running = FileAuthStore(tmp_path / "auth")
    login = Login(running)
    with pytest.raises(LoginFailed):
        login.staff("0012345")
    ImportStaff(FileAuthStore(tmp_path / "auth")).run([(2, "0012345")])
    assert login.staff("0012345").principal.kind == "staff"
