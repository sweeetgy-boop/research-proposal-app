"""시험 계정 표시 (ADR 0056 2026-11-04 덧붙임) — 저장소·로그인 주체·기록 줄 규칙.

배포 확인용 임시 사번은 `add_staff(test=True)` 로 등록되고 HMAC 목록의 표시(`test_hmacs`)로만
남는다. remove 는 표시도 지우고, 목록 교체(import --replace)로 빠진 사번의 표시도 빠진다.
로그인하면 `Principal.test` 가 True. 공용 계정·관리 토큰은 늘 False.
"""

from __future__ import annotations

import json
import stat

from rra.adapters.auth import FileAuthStore
from rra.adapters.fake.auth import FAKE_STAFF, ScriptedAuthStore
from rra.adapters.logging.recommend_metrics import JsonlRecommendMetrics
from rra.application.ports import AuthStorePort
from rra.application.usecases.login import Login
from rra.domain.models import OverlapAlert, Principal, RecommendationResult
from rra.domain.rules import auth_policy
from rra.domain.rules.recommend_metrics import FIELDS, metrics_row
from rra.domain.rules.similar_choice import choice_records
from tests.application.test_login import FakeAuthStore

TEST_NO = "T-9999-0001"
REAL_NO = "K-2026-0001"


def test_file_store_marks_counts_and_removes_test_account(tmp_path):
    store = FileAuthStore(tmp_path / "auth")
    assert isinstance(store, AuthStorePort)
    assert store.add_staff(REAL_NO) is True
    assert store.add_staff(TEST_NO, test=True) is True
    assert store.staff_count() == 2 and store.test_staff_count() == 1
    real, test = store.verify_staff(REAL_NO), store.verify_staff(TEST_NO)
    assert real and test
    assert store.is_test_staff(test) is True and store.is_test_staff(real) is False
    assert store.is_test_staff("") is False and store.is_test_staff("0" * 64) is False
    assert store.status()["test_staff_count"] == 1

    data = json.loads((tmp_path / "auth" / "staff.json").read_text())
    assert set(data) == {"hmacs", "test_hmacs"} and data["test_hmacs"] == [test]
    assert set(data["test_hmacs"]) <= set(data["hmacs"])
    root = tmp_path / "auth"
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in root.iterdir())

    # 이미 있는 사번의 표시는 add 로 바뀌지 않는다 (실제 직원 사번에 시험 표시가 붙지 않게)
    assert store.add_staff(REAL_NO, test=True) is False
    assert store.is_test_staff(real) is False and store.test_staff_count() == 1

    # remove 는 표시도 지운다 — 다시 일반 사번으로 등록해도 시험 계정이 아니다
    assert store.remove_staff(TEST_NO) is True
    assert store.staff_count() == 1 and store.test_staff_count() == 0
    assert "test_hmacs" not in json.loads((tmp_path / "auth" / "staff.json").read_text())
    store.add_staff(TEST_NO)
    assert store.is_test_staff(store.verify_staff(TEST_NO)) is False

    for path in root.iterdir():  # 원문 사번은 어느 파일에도 없다
        text = path.read_text()
        assert TEST_NO not in text and REAL_NO not in text
        assert TEST_NO.replace("-", "") not in text and REAL_NO.replace("-", "") not in text


def test_old_file_without_marks_and_import_keeps_or_drops_marks(tmp_path):
    store = FileAuthStore(tmp_path / "auth")
    store.add_staff(REAL_NO)
    assert store.test_staff_count() == 0  # 옛 모양(hmacs 만)
    store.add_staff(TEST_NO, test=True)
    # 추가 방식 일괄 등록 — 표시는 그대로
    store.import_staff(["K-1", "K-2"])
    assert store.staff_count() == 4 and store.test_staff_count() == 1
    # 목록 교체로 시험 사번이 빠지면 표시도 빠진다
    store.import_staff([REAL_NO, "K-1"], replace=True)
    assert store.staff_count() == 2 and store.test_staff_count() == 0
    # 손으로 고친 파일 — 목록에 없는 표시는 무시
    path = tmp_path / "auth" / "staff.json"
    data = json.loads(path.read_text())
    data["test_hmacs"] = ["f" * 64]
    path.write_text(json.dumps(data))
    assert store.test_staff_count() == 0


def test_login_sets_principal_test_only_for_marked_staff(tmp_path):
    store = FileAuthStore(tmp_path / "auth")
    store.add_staff(REAL_NO)
    store.add_staff(TEST_NO, test=True)
    store.set_guest("team", "pw-secret-99")
    login = Login(store)
    tested = login.staff(TEST_NO).principal
    normal = login.staff(REAL_NO).principal
    assert tested.kind == "staff" and tested.test is True
    assert normal.test is False and tested.id != normal.id
    assert TEST_NO not in tested.model_dump_json()  # 가명 ID 뿐
    assert login.guest("team", "pw-secret-99").principal.test is False
    assert auth_policy.admin_principal().test is False
    assert Principal(kind="staff", id="staff:ab12cd34ef56").test is False  # 기본값

    fake = Login(FakeAuthStore(staff={REAL_NO}, test={TEST_NO}))
    assert fake.staff(TEST_NO).principal.test is True
    assert fake.staff(REAL_NO).principal.test is False


def test_scripted_fake_store_supports_marks():
    store = ScriptedAuthStore()
    assert isinstance(store, AuthStorePort)
    assert store.test_staff_count() == 0
    assert store.add_staff(TEST_NO, test=True) and store.test_staff_count() == 1
    assert store.is_test_staff(store.verify_staff(TEST_NO))
    assert not store.is_test_staff(store.verify_staff(FAKE_STAFF[0]))
    assert store.remove_staff(TEST_NO) and store.test_staff_count() == 0


def _alert() -> OverlapAlert:
    return OverlapAlert(
        doc_id="alio:1",
        title="과제",
        tier="own",
        similarity=0.9,
        blocking=True,
        rule_blocking=True,
    )


def test_choice_records_carry_test_only_when_asked():
    common = {"idea": "abcd" * 4, "at": "2026-11-04T00:00:00+00:00"}
    plain = choice_records([_alert()], {"alio:1": "similar"}, **common)
    marked = choice_records([_alert()], {"alio:1": "similar"}, **common, test=True)
    assert "test" not in plain[0]
    assert marked[0]["test"] is True
    assert {k: v for k, v in marked[0].items() if k != "test"} == plain[0]


def test_metrics_row_and_file_write_test_key_only_for_test_sessions(tmp_path):
    result = RecommendationResult(provider="gemini", calls=1)
    plain = metrics_row(result, mode="initial", similar=0, seconds=1.0)
    marked = metrics_row(result, mode="initial", similar=0, seconds=1.0, test=True)
    assert "test" not in plain and marked["test"] is True
    path = tmp_path / "cache" / "recommend_metrics.jsonl"
    sink = JsonlRecommendMetrics(path)
    sink.record(plain)
    sink.record(marked)
    sink.record({**plain, "test": False})  # False 는 쓰지 않는다 (키 없음)
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    assert tuple(lines[0]) == FIELDS and tuple(lines[2]) == FIELDS
    assert tuple(lines[1]) == (*FIELDS, "test") and lines[1]["test"] is True
