"""`rra auth staff import` (A2): 출력·로그에 사번 값 없음, --dry-run 무저장, --replace, --pad."""

import logging

import pytest

from rra.adapters.auth import FileAuthStore, RosterReader
from rra.application.usecases.login import Login
from rra.entrypoints import cli
from tests.adapters.test_staff_roster_reader import LIMITS, NAMES, VALUES, make_csv, make_xlsx


@pytest.fixture
def store(tmp_path, monkeypatch):
    holder = FileAuthStore(tmp_path / "data" / "auth")
    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr("rra.config_loader.auth_config", lambda *a, **k: {"min_password_length": 4})
    monkeypatch.setattr("rra.composition.build_auth_store", lambda *a, **k: holder)
    monkeypatch.setattr("rra.composition.build_roster_reader", lambda *a, **k: RosterReader(LIMITS))
    return holder


def run(capsys, caplog, *argv):
    with caplog.at_level(logging.DEBUG):
        code = cli.main(["auth", "staff", "import", *argv])
    captured = capsys.readouterr()
    text = captured.out + captured.err + caplog.text
    for secret in (*VALUES, "00-123-47", "12346", *NAMES, "연구기획처"):
        assert secret not in text, "사번·이름·부서 값이 출력에 섞였다"
    return code, captured.out, captured.err


def test_dry_run_counts_only_and_saves_nothing(store, tmp_path, capsys, caplog):
    path = make_xlsx(tmp_path / "명단.xlsx")
    code, out, _ = run(capsys, caplog, "--file", str(path), "--dry-run")
    assert code == cli.EXIT_OK
    assert "머리글 2행" in out and "미리 보기(저장 없음)" in out
    assert "읽은 행: 6" in out and "빈칸: 1, 형식 오류: 1, 파일 안 중복(합침): 1" in out
    assert "등록 대상(고유): 3" in out and "형식 오류 행 번호: 8" in out
    assert "7자리 2건, 5자리 1건" not in out and "5자리 1건, 7자리 2건" in out
    assert "--pad" in out  # 길이가 섞여 있으니 0 빠짐 안내
    assert "등록(신규): 3, 이미 있음: 0" in out and "저장하지 않음" in out
    assert store.staff_count() == 0 and not (tmp_path / "data" / "auth" / "staff.json").exists()
    assert not any(p.suffix == ".xlsx" for p in (tmp_path / "data").rglob("*"))  # 원본 미복사


def test_import_then_pad_replace_and_login(store, tmp_path, capsys, caplog):
    path = make_csv(tmp_path / "명단.csv")
    code, out, _ = run(capsys, caplog, "--file", str(path))
    assert code == cli.EXIT_OK and "등록된 사번: 3건" in out and "방식: 추가" in out
    code, out, _ = run(capsys, caplog, "--file", str(path))
    assert "등록(신규): 0, 이미 있음: 3" in out
    code, out, _ = run(capsys, caplog, "--file", str(path), "--pad", "7", "--replace")
    assert code == cli.EXIT_OK and "방식: 목록 교체" in out
    assert "등록(신규): 1, 이미 있음: 2, 목록에서 빠짐: 1" in out and "7자리 3건" in out
    assert "--pad" not in out and store.staff_count() == 3
    login = Login(store)
    assert login.staff("00-123-46").principal.kind == "staff"  # 0 복원 + 하이픈 무시


def test_errors_show_guidance_without_values(store, tmp_path, capsys, caplog):
    path = make_xlsx(tmp_path / "명단.xlsx", header=("이름", "번호", "부서"))
    code, _, err = run(capsys, caplog, "--file", str(path))
    assert code == cli.EXIT_ERROR and "--column" in err
    code, out, _ = run(capsys, caplog, "--file", str(path), "--column", "번호", "--dry-run")
    assert code == cli.EXIT_OK and "등록 대상(고유): 3" in out
    code, _, err = run(capsys, caplog, "--file", str(tmp_path / "없음.xlsx"))
    assert code == cli.EXIT_ERROR and "열 수 없습니다" in err
    code, _, err = run(capsys, caplog, "--file", str(path), "--pad", "99")
    assert code == cli.EXIT_USAGE
