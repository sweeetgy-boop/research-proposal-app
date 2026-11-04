"""`rra auth staff add --test`·`rra feedback stats` CLI (ADR 0056 2026-11-04 덧붙임).

임시 데이터 폴더만 쓴다(원 저장소 data/ 를 건드리지 않는다). 사번은 getpass 로만 들어오고 출력·
파일 어디에도 원문이 없다. stats 는 개수만 — doc_id·해시·시각을 출력하지 않는다.
"""

from __future__ import annotations

import json
import logging

import pytest

from rra.entrypoints import cli
from rra.settings import Settings

TEST_NO = "T-7777-0001"
REAL_NO = "K-2026-0042"
IDEA_HASH = "0123456789abcdef"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    root = tmp_path / "data"
    settings = Settings(_env_file=None, data_dir=root)
    monkeypatch.setattr("rra.composition.load_settings", lambda: settings)
    return root


def _cli(monkeypatch, capsys, caplog, *argv, secret: str | None = None):
    if secret is not None:
        monkeypatch.setattr("getpass.getpass", lambda prompt="": secret)
    with caplog.at_level(logging.DEBUG):
        code = cli.main(list(argv))
    out = capsys.readouterr()
    text = out.out + out.err + caplog.text
    for raw in (TEST_NO, REAL_NO, TEST_NO.replace("-", ""), REAL_NO.replace("-", "")):
        assert raw not in text, "사번 원문이 출력에 섞였다"
    return code, out.out


def _scan_no_raw(root):
    for path in root.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            for raw in (TEST_NO, REAL_NO, TEST_NO.replace("-", ""), REAL_NO.replace("-", "")):
                assert raw not in text, f"사번 원문이 {path.name} 에 있다"


def test_auth_staff_add_test_count_check_status_remove(data_dir, monkeypatch, capsys, caplog):
    code, out = _cli(monkeypatch, capsys, caplog, "auth", "staff", "add", secret=REAL_NO)
    assert code == cli.EXIT_OK and "등록했습니다." in out
    assert "등록된 사번: 1건 (시험 계정 0건)" in out
    code, out = _cli(monkeypatch, capsys, caplog, "auth", "staff", "add", "--test", secret=TEST_NO)
    assert code == cli.EXIT_OK and "시험 계정으로 등록했습니다." in out
    assert "등록된 사번: 2건 (시험 계정 1건)" in out

    _, out = _cli(monkeypatch, capsys, caplog, "auth", "staff", "count")
    assert out.strip() == "등록된 사번: 2건 (시험 계정 1건)"
    _, out = _cli(monkeypatch, capsys, caplog, "auth", "staff", "check", secret=TEST_NO)
    assert out.strip() == "등록됨(시험 계정)"
    _, out = _cli(monkeypatch, capsys, caplog, "auth", "staff", "check", secret=REAL_NO)
    assert out.strip() == "등록됨"
    _, out = _cli(monkeypatch, capsys, caplog, "auth", "status")
    assert "직원 사번 등록: 2건 (활성, 시험 계정 1건)" in out

    # 이미 있는 일반 사번에 --test — 표시를 붙이지 않고 안내
    _, out = _cli(monkeypatch, capsys, caplog, "auth", "staff", "add", "--test", secret=REAL_NO)
    assert "이미 등록된 사번입니다." in out and "시험 표시는 붙이지 않았습니다" in out
    assert "(시험 계정 1건)" in out
    _, out = _cli(monkeypatch, capsys, caplog, "auth", "staff", "add", secret=TEST_NO)
    assert "이미 등록된 사번입니다 (시험 계정)." in out

    staff = json.loads((data_dir / "auth" / "staff.json").read_text())  # 임시 폴더에만
    assert len(staff["hmacs"]) == 2 and len(staff["test_hmacs"]) == 1
    _scan_no_raw(data_dir)
    code, out = _cli(monkeypatch, capsys, caplog, "auth", "staff", "remove", secret=TEST_NO)
    assert code == cli.EXIT_OK and "삭제했습니다." in out
    assert "등록된 사번: 1건 (시험 계정 0건)" in out
    _, out = _cli(monkeypatch, capsys, caplog, "auth", "staff", "check", secret=TEST_NO)
    assert out.strip() == "미등록"
    _scan_no_raw(data_dir)


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def _seed(root):
    choice = {"at": "2026-11-04T06:00:00+00:00", "idea": IDEA_HASH, "choice": "similar"}
    _write_jsonl(
        root / "feedback" / "similar_choices.jsonl",
        [
            {**choice, "event": "apply", "source": "user", "doc_id": "alio:secret-1"},
            {**choice, "event": "generate", "source": "ai_prefill", "doc_id": "alio:secret-2"},
            {**choice, "doc_id": "alio:secret-3"},  # 옛 줄
            *[
                {**choice, "event": "apply", "source": "user", "doc_id": "alio:t", "test": True}
                for _ in range(3)
            ],
        ],
    )
    metric = {"ts": "2026-11-04T14:46:17+09:00", "calls": 1, "mode": "initial"}
    _write_jsonl(
        root / "cache" / "recommend_metrics.jsonl.1",
        [{**metric, "provider": "gemini", "fallback_local": False, "seconds": 10.0}],
    )
    with (root / "feedback" / "similar_choices.jsonl").open("a", encoding="utf-8") as f:
        f.write("not json\n")
    _write_jsonl(
        root / "cache" / "recommend_metrics.jsonl",
        [
            {**metric, "provider": "mlx", "fallback_local": True, "seconds": 30.0},
            {**metric, "provider": "gemini", "fallback_local": False, "seconds": 20.0},
            {
                **metric,
                "provider": "gemini",
                "fallback_local": False,
                "seconds": 90.0,
                "test": True,
            },
        ],
    )


def test_feedback_stats_excludes_test_lines_by_default(data_dir, monkeypatch, capsys, caplog):
    _seed(data_dir)
    before = {p: p.read_bytes() for p in data_dir.rglob("*") if p.is_file()}
    code, out = _cli(monkeypatch, capsys, caplog, "feedback", "stats")
    assert code == cli.EXIT_OK
    lines = out.splitlines()
    assert lines[0] == "선택 기록 (feedback/similar_choices.jsonl)"
    assert "  전체 줄: 6건, 시험 계정 줄: 3건 (제외), 센 줄: 3건" in lines
    assert "  읽지 못한 줄: 1건 (세지 않음)" in lines
    assert "  시점(event): apply 1, generate 1, 없음 1" in lines
    assert "  출처(source): user 1, ai_prefill 1, 없음 1" in lines
    assert "과제안 측정 (cache/recommend_metrics.jsonl)" in lines
    assert "  전체 줄: 4건, 시험 계정 줄: 1건 (제외), 센 줄: 3건" in lines
    assert "  provider: gemini 2, mlx 1" in lines
    assert "  로컬 대체(fallback_local): 1건" in lines
    assert "  seconds 중앙값: 20초" in lines
    assert lines[-1] == "(시험 계정 줄까지 세려면 --include-test)"
    for leaked in ("secret", "alio:", IDEA_HASH, "2026-11-04", "not json"):
        assert leaked not in out
    # 읽기만 — 파일은 그대로
    assert {p: p.read_bytes() for p in data_dir.rglob("*") if p.is_file()} == before

    _, out = _cli(monkeypatch, capsys, caplog, "feedback", "stats", "--include-test")
    assert "  전체 줄: 6건, 시험 계정 줄: 3건 (포함), 센 줄: 6건" in out.splitlines()
    assert "  시점(event): apply 4, generate 1, 없음 1" in out.splitlines()
    assert "  전체 줄: 4건, 시험 계정 줄: 1건 (포함), 센 줄: 4건" in out.splitlines()
    assert "  seconds 중앙값: 25초" in out.splitlines()
    assert "--include-test" not in out


def test_feedback_stats_without_files(data_dir, monkeypatch, capsys, caplog):
    code, out = _cli(monkeypatch, capsys, caplog, "feedback", "stats")
    assert code == cli.EXIT_OK and out.count("파일 없음") == 2
    assert not data_dir.exists()  # 폴더를 만들지 않는다
