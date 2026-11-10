"""REST — 문제 정의 카드 재사용·고정 (계약 problem-card.md 4.4절).

진단 응답의 `reused` 칸·`refresh`, 카드를 실은 과제안·생성 요청과 줄 수정이 그 사용자 몫으로
고정되는지,
공용 계정은 고정되지 않는지, 스위치가 꺼져 있으면 아무것도 저장하지 않는지. 조립은 가짜 모드(메모리
저장소) — 설정 사본에서만 `enabled: true`. 네트워크·모델 없음.
"""

from __future__ import annotations

from rra import composition
from rra.adapters.fake.llm import ScriptedComposeLLM
from rra.adapters.persistence.card_store import MemoryCache, PrivateFileCache
from rra.adapters.security import COOKIE_NAME, CSRF_HEADER, SessionStore
from rra.domain.models import Principal
from rra.domain.rules import auth_policy
from rra.entrypoints.api import create_app
from rra.entrypoints.api.app import SessionAuth
from rra.settings import Settings
from tests.entrypoints.test_api import AUTH, TOKEN
from tests.entrypoints.test_problem_card_api import GUEST, IDEA, STAFF, settings_for
from tests.entrypoints.test_recommend_api import FakeRecommend, client_for
from tests.entrypoints.ui.fake_app import make_assistant
from tests.fakes import InMemoryRepository

OTHER = Principal(kind="staff", id="staff:bbbbbbbbbbbb")
PEOPLE = {"staff": STAFF, "other": OTHER, "guest": GUEST}
HEADERS: dict[str, dict] = {}  # app_for 가 채운다 — 주체별 세션 헤더


class CountingLLM(ScriptedComposeLLM):
    def __init__(self):
        super().__init__()
        self.diagnoses = 0

    async def complete(self, prompt, **kw):
        if prompt.startswith("[문제 진단]"):
            self.diagnoses += 1
        return await super().complete(prompt, **kw)


def app_for(tmp_path, *, enabled: bool = True):
    settings = settings_for(tmp_path, enabled=enabled)
    a = make_assistant()
    llm = CountingLLM()
    reuse = composition.build_card_reuse(settings)
    sessions = SessionStore()
    app = create_app(
        manager=a.manager,
        precheck=a.precheck,
        recommend=FakeRecommend(),
        recommend_auto=False,
        repo=a.repo,
        user=a.user,
        middlewares=composition.api_middlewares(Settings(_env_file=None), TOKEN, sessions=sessions),
        session_auth=SessionAuth(TOKEN, sessions),
        problem_diagnosis=composition.build_problem_diagnosis(
            settings, repo=InMemoryRepository(), llm=llm, reuse=reuse
        ),
        card_editor=composition.build_card_editor(settings, repo=InMemoryRepository(), llm=llm),
        card_pin=reuse.pin if reuse is not None else None,
    )

    # 주체별 세션(쿠키 + CSRF) — 헤더가 없으면 관리 토큰(관리자)
    for name, who in PEOPLE.items():
        session = sessions.create(who)
        HEADERS[name] = {"Cookie": f"{COOKIE_NAME}={session.id}", CSRF_HEADER: session.csrf}
    return app, llm, reuse


def hdr(who: str | None = None) -> dict:
    return dict(HEADERS[who]) if who else dict(AUTH)


async def diagnose(c, who=None, **extra):
    r = await c.post("/v1/ideas/diagnose", json={**IDEA, **extra}, headers=hdr(who))
    assert r.status_code == 200, r.text
    return r.json()


def with_function(card: dict, text: str) -> dict:
    return {**card, "function_ko": {**card["function_ko"], "value": text}}


async def test_second_diagnose_is_cached_and_refresh_calls_again(tmp_path):
    app, llm, _ = app_for(tmp_path)
    async with client_for(app) as c:
        first = await diagnose(c, "staff")
        second = await diagnose(c, "other")
        assert (first["reused"], second["reused"]) == (None, "cached")
        assert second["card"] == first["card"] and second["lines"] == first["lines"]
        assert llm.diagnoses == 1
        fresh = await diagnose(c, "staff", refresh=True)
        assert fresh["reused"] is None and llm.diagnoses == 2
        r = await c.post("/v1/ideas/diagnose", json={**IDEA, "refresh": "네"}, headers=AUTH)
        assert r.status_code == 422


async def test_card_sent_with_plan_request_is_pinned_for_that_user_only(tmp_path):
    app, llm, reuse = app_for(tmp_path)
    async with client_for(app) as c:
        card = (await diagnose(c, "staff"))["card"]
        mine = with_function(card, "조류가 지붕 구조물에 내려앉지 못하게 한다")
        r = await c.post(
            "/v1/precheck/recommendations",
            json={**IDEA, "problem_card": mine},
            headers=hdr("staff"),
        )
        assert r.status_code == 200, r.text
        again = await diagnose(c, "staff")
        assert again["reused"] == "pinned"
        assert again["card"]["function_ko"]["value"] == "조류가 지붕 구조물에 내려앉지 못하게 한다"
        # 다른 사용자·공용 계정에는 그 카드가 나오지 않는다(공용 캐시의 AI 카드)
        for who in ("other", "guest"):
            out = await diagnose(c, who)
            assert out["reused"] == "cached" and out["card"] == card
        assert llm.diagnoses == 1
        # 카드 없는 요청은 고정하지 않는다
        before = len(reuse.pins._items)
        await c.post("/v1/precheck/recommendations", json=IDEA, headers=hdr("other"))
        assert len(reuse.pins._items) == before == 1


async def test_card_sent_with_run_request_is_pinned(tmp_path):
    app, _, _ = app_for(tmp_path)
    async with client_for(app) as c:
        card = (await diagnose(c))["card"]  # 관리자 토큰
        mine = with_function(card, "조류의 착좌를 막는다")
        r = await c.post(
            "/v1/runs", json={**IDEA, "problem_card": mine, "acknowledged": True}, headers=AUTH
        )
        assert r.status_code == 202, r.text
        again = await diagnose(c)
        assert again["reused"] == "pinned"
        assert again["card"]["function_ko"]["value"] == "조류의 착좌를 막는다"
        assert (await diagnose(c, "staff"))["reused"] == "cached"


async def test_edit_pins_the_edited_card(tmp_path):
    app, _, _ = app_for(tmp_path)
    async with client_for(app) as c:
        before = (await diagnose(c, "staff"))["card"]
        after = {**before, "causes": [{**before["causes"][0], "value": "천장 틈새가 넓어 드나듦"}]}
        r = await c.post(
            "/v1/ideas/diagnose/edit",
            json={"request": IDEA, "before": before, "after": after, "fields": ["cause"]},
            headers=hdr("staff"),
        )
        assert r.status_code == 200, r.text
        again = await diagnose(c, "staff")
        assert again["reused"] == "pinned" and again["card"] == r.json()["card"]
        assert again["card"]["causes"][0]["origin"] == "user"
        assert (await diagnose(c, "other"))["card"]["causes"][0]["origin"] == "ai"


async def test_guest_is_never_pinned(tmp_path):
    app, _, reuse = app_for(tmp_path)
    async with client_for(app) as c:
        card = (await diagnose(c, "guest"))["card"]
        mine = with_function(card, "조류의 착좌를 막는다")
        r = await c.post(
            "/v1/precheck/recommendations",
            json={**IDEA, "problem_card": mine},
            headers=hdr("guest"),
        )
        assert r.status_code == 200, r.text
        after = {**card, "causes": [{**card["causes"][0], "value": "천장 틈새가 넓어 드나듦"}]}
        await c.post(
            "/v1/ideas/diagnose/edit",
            json={"request": IDEA, "before": card, "after": after, "fields": ["cause"]},
            headers=hdr("guest"),
        )
        out = await diagnose(c, "guest")
        assert out["reused"] == "cached" and out["card"] == card
        assert reuse.pins._items == {}


async def test_switched_off_builds_no_store_and_keeps_the_old_response(tmp_path):
    app, llm, reuse = app_for(tmp_path, enabled=False)
    assert reuse is None
    async with client_for(app) as c:
        out = await diagnose(c, "staff", refresh=True)
        assert (out["status"], out["card"], out["reused"]) == ("off", None, None)
        r = await c.post(
            "/v1/precheck/recommendations",
            json={**IDEA, "problem_card": {"function_ko": {"value": "막는다"}}},
            headers=hdr("staff"),
        )
        assert r.status_code == 200, r.text
    assert llm.diagnoses == 0 and not (tmp_path / "data").exists()


def test_composition_picks_memory_in_fake_mode_and_private_files_otherwise(tmp_path):
    fake = settings_for(tmp_path / "fake", enabled=True)
    reuse = composition.build_card_reuse(fake)
    assert isinstance(reuse.cache, MemoryCache) and isinstance(reuse.pins, MemoryCache)
    real = fake.model_copy(update={"fake_llm": False})
    reuse = composition.build_card_reuse(real)
    root = tmp_path / "fake" / "data" / "cache" / "problem_cards"
    assert isinstance(reuse.cache, PrivateFileCache) and reuse.cache.root == root
    assert reuse.cache.ttl_sec == 30 * 86400
    assert reuse.pins.root == root / "pinned" and reuse.pins.ttl_sec == float("inf")
    assert not (tmp_path / "fake" / "data").exists()  # 만들기만 해서는 폴더가 생기지 않는다
    assert composition.build_card_reuse(settings_for(tmp_path / "off", enabled=False)) is None
    assert auth_policy.admin_principal().kind == "admin"
