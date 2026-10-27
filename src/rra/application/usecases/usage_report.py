"""U8 `rra usage report` — 모든 사용자의 run usage.json 을 모아 집계한다 (본문·개인정보 없음)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rra.application.ports import RunStorePort
from rra.domain.models import UsageRecord
from rra.domain.rules.usage import aggregate


@dataclass
class UsageReport:
    store: RunStorePort
    limit_per_user: int = 500

    def records(self) -> list[UsageRecord]:
        out: list[UsageRecord] = []
        for user in self.store.list_users():
            for state in self.store.list_runs(user, self.limit_per_user):
                record = self.store.load_usage(user, state.run_id)
                if record is not None:
                    out.append(record)
        return out

    def __call__(self) -> dict[str, Any]:
        return aggregate(self.records())
