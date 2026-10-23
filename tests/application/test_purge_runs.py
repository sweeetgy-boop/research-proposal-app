"""PurgeRuns — 가짜 시계로 만료 판정. 실행 중·락 잡힌 run 은 지우지 않는다."""

from datetime import UTC, datetime

import pytest

from rra.application.usecases.purge_runs import PurgeRuns
from tests.fakes import InMemoryRunStore

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def seed(store, user, stamp, status="done", steps=("a",)):
    from rra.domain.models import ProposalRequest

    req = ProposalRequest(current_state="a", root_cause="b", limitation="c", goal="d")
    st = store.create(user, req, list(steps), stamp)
    st.status = status
    st.updated_at = stamp
    store.save_state(st)
    return st.run_id


def test_expired_runs_are_listed_then_deleted_only_without_dry_run():
    store = InMemoryRunStore()
    old = seed(store, "local", "2026-04-01T00:00:00+00:00")  # 205일 전
    edge = seed(store, "local", "2026-04-26T12:00:00+00:00")  # 정확히 180일 → 보존
    fresh = seed(store, "local", "2026-10-01T00:00:00+00:00")
    other = seed(store, "alice", "2026-01-01T00:00:00+00:00", status="invalid")
    purge = PurgeRuns(store, 180, clock=lambda: NOW)

    report = purge(dry_run=True)
    assert report.cutoff == "2026-04-26T12:00:00+00:00" and report.dry_run
    assert {(r.user, r.run_id) for r in report.expired} == {("local", old), ("alice", other)}
    assert report.deleted == [] and ("local", old) in store.states

    report = purge(dry_run=False)
    assert [(r.user, r.run_id) for r in report.deleted] == sorted(
        [("alice", other), ("local", old)]
    )
    assert set(store.states) == {("local", edge), ("local", fresh)}
    assert store.deleted == [("alice", other), ("local", old)]


def test_active_or_locked_runs_are_skipped_even_if_old():
    store = InMemoryRunStore()
    running = seed(store, "local", "2026-01-01T00:00:00+00:00", status="running")
    locked = seed(store, "local", "2026-01-02T00:00:00+00:00", status="interrupted")
    store.claim("local", locked)  # 다른 프로세스가 재개 중
    gone = seed(store, "local", "2026-01-03T00:00:00+00:00", status="interrupted")
    report = PurgeRuns(store, 30, clock=lambda: NOW)(dry_run=False)
    assert [r.run_id for r in report.deleted] == [gone]
    assert {r.run_id for r in report.skipped_active} == {running, locked}
    assert ("local", running) in store.states and ("local", locked) in store.states


def test_unparseable_timestamps_are_kept():
    store = InMemoryRunStore()
    seed(store, "local", "언젠가")
    report = PurgeRuns(store, 1, clock=lambda: NOW)(dry_run=False)
    assert report.expired == [] and len(store.states) == 1


def test_retention_must_be_positive():
    with pytest.raises(ValueError):
        PurgeRuns(InMemoryRunStore(), 0)
