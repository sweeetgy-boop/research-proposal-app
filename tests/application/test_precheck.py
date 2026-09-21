from rra.application.usecases.precheck_overlap import PrecheckOverlap
from tests.fakes import InMemoryRepository


def test_precheck_orders_blocking_first(req, docs, own):
    repo = InMemoryRepository()
    repo.similar = [(docs[1], 0.95), (docs[0], 0.81)]
    alerts = PrecheckOverlap(repo, own=own)(req)
    assert [a.blocking for a in alerts] == [True, True]
    assert [a.tier for a in alerts] == ["external", "own"]


def test_precheck_without_own_unit_has_no_own_tier(req, docs):
    repo = InMemoryRepository()
    repo.similar = [(docs[0], 0.81)]
    (alert,) = PrecheckOverlap(repo)(req)
    assert alert.tier == "domestic_rail" and not alert.blocking
