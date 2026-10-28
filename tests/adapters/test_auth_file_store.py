"""data/auth 파일 저장소 (레인 A): 권한 700/600, 원문 없음, HMAC·scrypt, 일일 예산 카운터."""

import json
import stat

import pytest

from rra.adapters.auth import FileAuthStore
from rra.adapters.llm.daily_budget import BudgetedLLM, FileDailyBudget
from rra.application.ports import AuthStorePort, BudgetExhausted, DailyBudgetPort

STAFF_NO = "K-2026-0001"
PASSWORD = "correct-horse-9"  # noqa: S105 — 테스트용


def test_store_satisfies_port_and_creates_secret_with_owner_only_permissions(tmp_path):
    store = FileAuthStore(tmp_path / "auth")
    assert isinstance(store, AuthStorePort)
    assert store.status()["secret"] is False and store.staff_enabled() is False
    assert store.add_staff(STAFF_NO) is True
    assert store.add_staff(STAFF_NO) is False
    root = tmp_path / "auth"
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    for name in ("secret", "staff.json"):
        assert stat.S_IMODE((root / name).stat().st_mode) == 0o600
    assert store.permissions_ok() and store.status()["secret"] is True


def test_staff_number_never_appears_in_any_file_and_verify_returns_digest(tmp_path):
    store = FileAuthStore(tmp_path / "auth")
    store.add_staff(STAFF_NO)
    store.set_guest("team", PASSWORD)
    for path in (tmp_path / "auth").iterdir():
        text = path.read_text()
        assert STAFF_NO not in text and PASSWORD not in text
    digest = store.verify_staff(STAFF_NO)
    assert digest and len(digest) == 64 and store.verify_staff("K-0000") is None
    assert store.verify_staff(" " + STAFF_NO + " ") == digest  # 앞뒤 공백 무시
    assert store.staff_count() == 1 and store.remove_staff(STAFF_NO) and store.staff_count() == 0
    assert store.verify_staff(STAFF_NO) is None  # 목록이 비면 비활성


def test_secret_is_stable_so_pseudonyms_survive_restart(tmp_path):
    a = FileAuthStore(tmp_path / "auth")
    a.add_staff(STAFF_NO)
    b = FileAuthStore(tmp_path / "auth")
    assert b.verify_staff(STAFF_NO) == a.verify_staff(STAFF_NO)


def test_guest_scrypt_roundtrip_disable_and_malformed_file(tmp_path):
    store = FileAuthStore(tmp_path / "auth")
    assert store.guest_id() is None and not store.verify_guest("team", PASSWORD)
    store.set_guest("team", PASSWORD)
    data = json.loads((tmp_path / "auth" / "guest.json").read_text())
    assert set(data) == {"id", "salt", "hash", "n", "r", "p"} and data["id"] == "team"
    assert store.verify_guest("team", PASSWORD)
    assert not store.verify_guest("team", PASSWORD + "x")
    assert not store.verify_guest("other", PASSWORD)
    assert not store.verify_guest("team", "")
    store.set_guest("team", "new-password-2")  # 다시 설정하면 새 salt
    assert not store.verify_guest("team", PASSWORD) and store.verify_guest("team", "new-password-2")
    with pytest.raises(ValueError):
        store.set_guest("team", "")
    (tmp_path / "auth" / "guest.json").write_text(
        json.dumps({"id": "team", "salt": "zz", "hash": "00"})
    )
    assert not store.verify_guest("team", PASSWORD)
    assert store.disable_guest() and store.guest_id() is None and not store.disable_guest()


def test_daily_budget_counts_per_day_and_wrapper_refuses_calls_when_exhausted(tmp_path):
    day = ["2026-10-27"]
    budget = FileDailyBudget(tmp_path / "cache" / "llm_budget.json", 2, today=lambda: day[0])
    assert isinstance(budget, DailyBudgetPort)
    assert budget.remaining() == 2 and budget.try_spend() and budget.try_spend()
    assert budget.exhausted() and not budget.try_spend() and budget.remaining() == 0
    day[0] = "2026-10-28"  # 날짜가 바뀌면 0 부터
    assert not budget.exhausted() and budget.try_spend()
    assert stat.S_IMODE((tmp_path / "cache" / "llm_budget.json").stat().st_mode) == 0o600

    class Inner:
        calls = 0

        async def complete(self, prompt, *, system=None, max_tokens=None, json_mode=False):
            self.calls += 1
            return "ok"

        async def aclose(self):
            return None

    inner = Inner()
    llm = BudgetedLLM(inner, budget)

    async def run():
        assert await llm.complete("p") == "ok"
        with pytest.raises(BudgetExhausted):
            await llm.complete("p")
        await llm.aclose()  # 위임

    import asyncio

    asyncio.run(run())
    assert inner.calls == 1


def test_budgeted_llm_logs_latency_without_content(tmp_path):
    """호출마다 응답 시간 한 줄 — 단계·초·성공 여부만, 프롬프트·응답 본문 없음 (보안 D)."""
    import asyncio
    import json

    from rra.adapters.llm.daily_budget import BudgetedLLM, FileDailyBudget, latency_path

    budget = FileDailyBudget(tmp_path / "llm_budget.json", 5)

    class Inner:
        async def complete(self, prompt, *, system=None, max_tokens=None, json_mode=False):
            if prompt == "boom":
                raise RuntimeError("x")
            return "비밀 응답"

    llm = BudgetedLLM(Inner(), budget, stage="review")

    async def run():
        await llm.complete("비밀 프롬프트")
        with pytest.raises(RuntimeError):
            await llm.complete("boom")

    asyncio.run(run())
    text = latency_path(budget).read_text(encoding="utf-8")
    rows = [json.loads(x) for x in text.splitlines()]
    assert [(r["stage"], r["ok"], r["error"]) for r in rows] == [
        ("review", True, None),
        ("review", False, "RuntimeError"),
    ]
    assert all(r["seconds"] >= 0 for r in rows)
    assert "비밀" not in text
