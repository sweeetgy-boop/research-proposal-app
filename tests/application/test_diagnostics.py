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


def test_models_prefix_is_ignored_on_both_sides():
    # Gemini OpenAI 호환 목록은 "models/gemini-…" — llm.yaml 의 "gemini-4-argon" 과 같은 모델
    assert served_model_listed({"gemini-4-argon"}, ["models/gemini-4-argon", "models/other"])
    assert served_model_listed({"models/gemini-4-argon"}, ["gemini-4-argon"])
    assert not served_model_listed({"gemini-4-argon"}, ["models/gemini-4-argon-mini"])
    assert not served_model_listed({"models/"}, ["models/"])  # 접두어만 있는 이름은 빈 이름


async def test_gemini_listing_with_prefix_does_not_warn():
    llm = ListingLLM(["models/gemini-4-argon", "models/gemini-4-flash"])
    assert await check_served_model(llm, "gemini-4-argon") is None


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


# ── 자료원 IP 확인 (레인 I) ───────────────────────────────
from rra.domain.rules.source_ip import IpPolicy, SourceIpBlocked  # noqa: E402

NTIS_POLICY = IpPolicy(True, ("59.0.166.199", "59.0.251.250"), "NTIS 국가R&D 과제")
NTIS_NOTICE = "현재 IP 203.0.113.9 가 NTIS 국가R&D 과제 등록 IP 에 없습니다. 활용신청에 추가하세요"


class FakePublicIp:
    def __init__(self, ip=None, *, error=None):
        self.ip, self.error, self.calls, self.closed = ip, error, 0, False

    async def current_ip(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.ip

    async def aclose(self):
        self.closed = True


class DictAvailability:
    def __init__(self):
        self.data = {}

    def record(self, source, notice):
        if notice is None:
            self.data.pop(source, None)
        else:
            self.data[source] = notice

    def notice(self, source):
        return self.data.get(source)

    def notices(self):
        return dict(self.data)


async def test_unregistered_ip_is_reported_with_the_exact_notice():
    src = FakeProbingSource("ntis", {"total": 3})
    ip, store = FakePublicIp("203.0.113.9"), DictAvailability()
    rows = await CheckSources(
        [
            target("ntis", connect=lambda: src).__class__(
                "ntis", "ntis.example", True, {"K": True}, lambda: src, ip_policy=NTIS_POLICY
            ),
            SourceTarget("scienceon", "sci.example", True, {"K": True}, None, IpPolicy(False)),
        ],
        public_ip=ip,
        availability=store,
    )()
    ntis, sci = rows
    assert ntis["roundtrip"] == "ok" and ntis["current_ip"] == "203.0.113.9"
    assert ntis["registered_ips"] == ["59.0.166.199", "59.0.251.250"]
    assert ntis["ip_registered"] is False and ntis["ip_notice"] == NTIS_NOTICE
    assert sci["ip_restricted"] is False and sci["ip_notice"] is None and sci["current_ip"] is None
    assert ip.calls == 1 and ip.closed
    assert store.data == {"ntis": NTIS_NOTICE}


async def test_registered_ip_clears_notice_and_lookup_failure_is_diagnostic_only():
    src = FakeProbingSource("ntis", {"total": 3})
    store = DictAvailability()
    store.record("ntis", "옛 안내")
    rows = await CheckSources(
        [SourceTarget("ntis", "h", True, {"K": True}, lambda: src, NTIS_POLICY)],
        public_ip=FakePublicIp("59.0.251.250"),
        availability=store,
    )()
    assert rows[0]["ip_registered"] is True and rows[0]["ip_notice"] is None
    assert store.data == {}  # 정상 왕복 → 해제
    rows = await CheckSources(
        [SourceTarget("ntis", "h", True, {"K": True}, lambda: src, NTIS_POLICY)],
        public_ip=FakePublicIp(error=ConnectionError("https://ip.example/?key=S")),
    )()
    assert rows[0]["roundtrip"] == "ok" and rows[0]["ip_lookup_error"] == "ConnectionError"
    assert rows[0]["current_ip"] is None and rows[0]["ip_notice"] is None
    assert "key=S" not in str(rows)


async def test_ip_blocked_roundtrip_always_notifies_even_if_registered():
    bad = FakeProbingSource("ntis", error=SourceIpBlocked("NTIS 오류: 접근 허용 IP가 아닙니다."))
    store = DictAvailability()
    rows = await CheckSources(
        [SourceTarget("ntis", "h", True, {"K": True}, lambda: bad, NTIS_POLICY)],
        public_ip=FakePublicIp("59.0.166.199"),
        availability=store,
    )()
    assert rows[0]["roundtrip"] == "SourceIpBlocked" and rows[0]["ip_registered"] is True
    assert rows[0]["ip_notice"] == (
        "현재 IP 59.0.166.199 가 NTIS 국가R&D 과제 등록 IP 에 없습니다. 활용신청에 추가하세요"
    )
    assert store.data["ntis"] == rows[0]["ip_notice"]


async def test_no_lookup_without_a_ready_restricted_target():
    ip = FakePublicIp("1.2.3.4")
    rows = await CheckSources(
        [
            SourceTarget("ntis", "h", True, {"K": False}, None, NTIS_POLICY),  # 키 없음
            SourceTarget(
                "sci", "h", True, {"K": True}, lambda: FakeProbingSource("sci"), IpPolicy()
            ),
        ],
        public_ip=ip,
    )()
    assert ip.calls == 0
    assert rows[0]["roundtrip"] == "skipped" and rows[0]["current_ip"] is None
    assert rows[0]["ip_notice"] is None
    # ip_policy 가 없는 대상은 IP 항목을 내지 않는다 (기존 출력 그대로)
    rows = await CheckSources([target("x", connect=lambda: FakeProbingSource("x"))])()
    assert "ip_restricted" not in rows[0]
