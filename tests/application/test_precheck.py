from rra.application.usecases.precheck_overlap import PrecheckOverlap
from tests.fakes import InMemoryRepository


async def test_precheck_orders_blocking_first(req, docs, own):
    repo = InMemoryRepository()
    repo.similar = [(docs[1], 0.95), (docs[0], 0.81)]
    alerts = await PrecheckOverlap(repo, own=own)(req)
    assert [a.blocking for a in alerts] == [True, True]
    assert [a.tier for a in alerts] == ["external", "own"]


async def test_precheck_without_own_unit_has_no_own_tier(req, docs):
    repo = InMemoryRepository()
    repo.similar = [(docs[0], 0.81)]
    (alert,) = await PrecheckOverlap(repo)(req)
    assert alert.tier == "domestic_rail" and not alert.blocking


async def test_precheck_passes_query_and_keyword_rule_to_judge(req, docs, own):
    from rra.domain.rules.keywords import KeywordRule

    repo = InMemoryRepository()
    tracked = docs[0].model_copy(update={"body": "궤도 틀림 상시 감지 센서 연구"})
    repo.similar = [(tracked, 0.9), (docs[1], 0.95)]
    alerts = await PrecheckOverlap(repo, own=own, keywords=KeywordRule(min_hits=2))(req)
    by_id = {a.doc_id: a for a in alerts}
    assert by_id["alio:1"].blocking and {"궤도", "틀림", "감지"} <= set(by_id["alio:1"].keywords)
    assert not by_id["openalex:W1"].blocking  # 유사도 0.95 지만 공유 키워드 없음
