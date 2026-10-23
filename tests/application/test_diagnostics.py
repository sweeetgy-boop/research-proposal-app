"""진단 유스케이스 — 포트(fake)만으로 돈다. 네트워크·설정 파일 없음."""

from rra.application.usecases.diagnostics import (
    CheckSources,
    SourceTarget,
    check_served_model,
    served_model_listed,
)
from tests.fakes import FakeLLM, FakeProbingSource, ListingLLM


# ── served_model ─────────────────────────────────────────
def test_served_model_listed_is_exact():
    assert served_model_listed({"a/b"}, [" a/b "])
    assert not served_model_listed({"a/B"}, ["a/b"])
    assert not served_model_listed({""}, [""])


async def test_served_model_listed_means_no_warning():
    llm = ListingLLM(["mlx-community/Qwen2.5-3B-Instruct-4bit", "other/model"])
    assert await check_served_model(llm, "mlx-community/Qwen2.5-3B-Instruct-4bit") is None


async def test_typo_in_served_model_warns_with_the_list():
    llm = ListingLLM(["mlx-community/Qwen2.5-3B-Instruct-4bit"])
    warning = await check_served_model(llm, "mlx-community/Qwen2.5-3b-Instruct-4bit")  # 대소문자
    assert "목록에 없습니다" in warning and "Qwen2.5-3B" in warning


async def test_aliases_count_as_the_declared_model():
    # 로컬 경로로 선언했고 서버는 절대경로를 싣는 경우 — 별칭은 조립(config_loader)이 넘긴다
    llm = ListingLLM(["/abs/models/qwen"])
    assert await check_served_model(llm, "models/qwen", aliases={"/abs/models/qwen"}) is None


async def test_listing_failure_and_missing_key_only_warn():
    failed = await check_served_model(ListingLLM(error=RuntimeError("down")), "x")
    assert "조회 실패 (RuntimeError)" in failed and "down" not in failed
    assert "served_model 이 없습니다" in await check_served_model(ListingLLM(), None)
    assert await check_served_model(FakeLLM(), "x") is None  # 목록 기능 없는 LLM 은 확인 안 함


async def test_long_listing_is_truncated():
    llm = ListingLLM([f"m/{i}" for i in range(9)])
    warning = await check_served_model(llm, "nope")
    assert "m/4 …" in warning and "m/5" not in warning


# ── 자료원 연결 확인 ──────────────────────────────────────
def target(name, *, creds=None, allowed=True, connect=None):
    return SourceTarget(name, f"{name}.example", allowed, creds or {"K": True}, connect)


async def test_ready_target_probes_and_closes():
    src = FakeProbingSource("ntis", {"total": 3})
    rows = await CheckSources([target("ntis", connect=lambda: src)])()
    assert rows == [
        {
            "source": "ntis",
            "credentials": {"K": True},
            "host": "ntis.example",
            "host_allowed": True,
            "roundtrip": "ok",
            "result": {"total": 3},
        }
    ]
    assert src.closed


async def test_missing_credentials_or_host_skip_the_roundtrip():
    called = []
    connect = lambda: called.append(1)  # noqa: E731 — 호출되면 안 된다
    rows = await CheckSources(
        [
            target("a", creds={"K": False}, connect=connect),
            target("b", allowed=False, connect=connect),
            target("c"),  # connect 없음
        ]
    )()
    assert [r["roundtrip"] for r in rows] == ["skipped"] * 3
    assert not called and all("result" not in r for r in rows)


async def test_failure_reports_class_name_and_continues():
    bad = FakeProbingSource("a", error=ConnectionError("https://a.example/?key=SECRET 실패"))
    good = FakeProbingSource("b", {"ok": 1})
    rows = await CheckSources(
        [target("a", connect=lambda: bad), target("b", connect=lambda: good)]
    )()
    assert rows[0]["roundtrip"] == "ConnectionError" and rows[1]["roundtrip"] == "ok"
    assert bad.closed and good.closed
    # 메시지는 어댑터가 넘긴 그대로 300자까지 — 비밀 제거는 어댑터(FetchError) 책임
    assert rows[0]["error"].startswith("https://a.example")
