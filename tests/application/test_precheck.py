from rra.application.usecases.precheck_overlap import PrecheckOverlap

from tests.fakes import InMemoryRepository


def test_precheck_orders_blocking_first(req, docs):
    repo = InMemoryRepository()
    repo.similar = [(docs[1], 0.95), (docs[0], 0.81)]
    alerts = PrecheckOverlap(repo)(req)
    assert [a.blocking for a in alerts] == [True, True]
    assert alerts[0].tier in ("own", "external")
