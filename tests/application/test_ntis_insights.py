"""NtisProjectInsights 유스케이스 — fake 포트·캐시·저장소. 네트워크 없음."""

import pytest

from rra.application.usecases.ntis_insights import NtisProjectInsights
from rra.domain.models import Document, OverlapAlert


def alert(doc_id, sim=0.85, blocking=False, tier="national_rnd"):
    return OverlapAlert(
        doc_id=doc_id, title=f"과제 {doc_id}", tier=tier, similarity=sim, blocking=blocking
    )


class FakeOutcomes:
    def __init__(self, fail=()):
        self.calls, self.fail = [], set(fail)

    async def outcomes(self, project_no):
        self.calls.append(project_no)
        if project_no in self.fail:
            raise RuntimeError("boom secret-url")
        return [
            {"kind": "paper", "title": f"논문 {project_no}", "year": "2023"},
            {"kind": "x", "title": "무시"},
        ]


class FakeRelated:
    def __init__(self):
        self.calls = []

    async def related(self, project_no):
        self.calls.append(project_no)
        return [
            {"project_no": "1415199001", "title": "새 과제", "score": 0.9, "rank": 1},
            {"project_no": "1415100002", "title": "알림에 있음", "score": 0.8, "rank": 2},
            {"project_no": "1415100009", "title": "저장소에 있음", "score": 0.7, "rank": 3},
        ]


class DictCache:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value


class FakeRepo:
    async def get_document(self, doc_id):
        if doc_id == "ntis:1415100009":
            return Document(doc_id=doc_id, source="ntis", doc_type="rnd_project", title="있음")
        return None


ALERTS = [
    alert("ntis:1415100001", blocking=True),
    alert("ntis:1415100002", sim=0.83),
    alert("own:7", tier="own", sim=0.99),
]


async def test_outcomes_and_recommendations_with_cache():
    out, rel, cache = FakeOutcomes(), FakeRelated(), DictCache()
    uc = NtisProjectInsights(out, rel, cache=cache, repo=FakeRepo())
    res = await uc(ALERTS)
    assert [p.project_no for p in res.projects] == ["1415100001", "1415100002"]
    assert [o.title for o in res.projects[0].outcomes] == ["논문 1415100001"]  # 모르는 종류 제외
    assert res.projects[0].blocking and not res.projects[0].cached and res.projects[0].error is None
    assert [r.project_no for r in res.recommended] == ["1415199001"]  # 알림·저장소에 있는 과제 제외
    assert res.recommended[0].source_project_no == "1415100001"
    # 두 번째 호출은 캐시만 — API 호출 수 그대로
    res2 = await uc(ALERTS)
    assert out.calls == ["1415100001", "1415100002"] and rel.calls == ["1415100001", "1415100002"]
    assert all(p.cached for p in res2.projects) and res2.recommended == res.recommended


async def test_one_failure_does_not_stop_others_and_hides_message():
    uc = NtisProjectInsights(FakeOutcomes(fail={"1415100001"}), FakeRelated(), cache=DictCache())
    res = await uc(ALERTS)
    assert res.projects[0].error == "RuntimeError" and res.projects[0].outcomes == []
    assert "secret" not in str(res.model_dump())
    assert res.projects[1].outcomes and res.recommended


async def test_disabled_when_no_ports():
    uc = NtisProjectInsights(None, None)
    assert not uc.enabled
    res = await uc(ALERTS)
    assert [p.project_no for p in res.projects] == [
        "1415100001",
        "1415100002",
    ] and res.recommended == []


@pytest.mark.parametrize("max_projects", [1, 5])
async def test_max_projects(max_projects):
    uc = NtisProjectInsights(FakeOutcomes(), None, max_projects=max_projects)
    assert len((await uc(ALERTS)).projects) == min(max_projects, 2)


# ── IP 거부 (레인 I) ───────────────────────────────────────
from rra.domain.rules.source_ip import SourceIpBlocked  # noqa: E402


class BlockedOutcomes:
    def __init__(self):
        self.calls = []

    async def outcomes(self, project_no):
        self.calls.append(project_no)
        raise SourceIpBlocked("NTIS 오류: 접근 허용 IP가 아닙니다.")


class FakePublicIp:
    async def current_ip(self):
        return "203.0.113.9"

    async def aclose(self):
        pass


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


async def test_ip_blocked_skips_remaining_calls_and_reports_notice(caplog):
    outcomes, related, store = BlockedOutcomes(), FakeRelated(), DictAvailability()
    uc = NtisProjectInsights(
        outcomes, related, cache=DictCache(), public_ip=FakePublicIp(), availability=store
    )
    with caplog.at_level("WARNING", logger="rra.ntis_insights"):
        result = await uc([alert("ntis:1415100001"), alert("ntis:1415100002", sim=0.84)])
    notice = "현재 IP 203.0.113.9 가 NTIS 국가R&D 과제 등록 IP 에 없습니다. 활용신청에 추가하세요"
    assert result.unavailable == notice
    assert outcomes.calls == ["1415100001"] and related.calls == []  # 거부 뒤 더 두드리지 않는다
    assert [p.error for p in result.projects] == ["SourceIpBlocked", "SourceIpBlocked"]
    assert result.recommended == []
    assert store.data == {"ntis": notice}
    assert any(notice in r.getMessage() for r in caplog.records)
    # 다음 호출이 정상이면 해제된다
    ok = NtisProjectInsights(FakeOutcomes(), FakeRelated(), cache=DictCache(), availability=store)
    assert (await ok([alert("ntis:1415100001")])).unavailable is None
    assert store.data == {}


def test_payload_carries_unavailable():
    from rra.domain.rules.ntis_insights import NtisInsights
    from rra.entrypoints.views import ntis_insights_payload

    assert ntis_insights_payload(NtisInsights())["unavailable"] is None
    assert ntis_insights_payload(NtisInsights(unavailable="안내"))["unavailable"] == "안내"
