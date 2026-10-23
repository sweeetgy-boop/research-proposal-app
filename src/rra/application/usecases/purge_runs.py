"""보존 기간이 지난 run 폴더 삭제 (보안 I — security.yaml retention_days).

만료 기준은 state.updated_at (마지막 변경 시각). 아직 실행 중이거나 락이 잡힌 run 은 지우지 않는다.
시계는 주입한다 — 테스트는 가짜 시계로 만료 판정을 검증한다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from rra.application.ports import RunStorePort
from rra.domain.models import RunState
from rra.domain.models.run import ACTIVE


@dataclass(frozen=True)
class ExpiredRun:
    user: str
    run_id: str
    status: str
    updated_at: str


@dataclass
class PurgeReport:
    retention_days: int
    cutoff: str
    expired: list[ExpiredRun] = field(default_factory=list)
    deleted: list[ExpiredRun] = field(default_factory=list)
    skipped_active: list[ExpiredRun] = field(default_factory=list)
    dry_run: bool = True


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse(stamp: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class PurgeRuns:
    def __init__(
        self,
        store: RunStorePort,
        retention_days: int,
        *,
        clock: Callable[[], datetime] = _utcnow,
        per_user_limit: int = 10_000,
    ):
        if retention_days <= 0:
            raise ValueError("retention_days 는 1 이상이어야 합니다.")
        self.store, self.retention_days = store, retention_days
        self._clock, self.per_user_limit = clock, per_user_limit

    def expired(self) -> tuple[list[ExpiredRun], list[ExpiredRun], datetime]:
        cutoff = self._clock() - timedelta(days=self.retention_days)
        expired: list[ExpiredRun] = []
        active: list[ExpiredRun] = []
        for user in self.store.list_users():
            for state in self.store.list_runs(user, self.per_user_limit):
                stamp = _parse(state.updated_at)
                if stamp is None or stamp >= cutoff:
                    continue
                row = ExpiredRun(user, state.run_id, state.status, state.updated_at)
                if self._is_active(state):
                    active.append(row)
                else:
                    expired.append(row)
        return expired, active, cutoff

    def _is_active(self, state: RunState) -> bool:
        return state.status in ACTIVE or self.store.is_alive(state.user, state.run_id)

    def __call__(self, *, dry_run: bool = True) -> PurgeReport:
        expired, active, cutoff = self.expired()
        report = PurgeReport(
            retention_days=self.retention_days,
            cutoff=cutoff.isoformat(timespec="seconds"),
            expired=expired,
            skipped_active=active,
            dry_run=dry_run,
        )
        if dry_run:
            return report
        for row in expired:
            self.store.delete_run(row.user, row.run_id)
            report.deleted.append(row)
        return report
