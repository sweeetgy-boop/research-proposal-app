"""사번 일괄 등록 유스케이스 (A2, 2026-10-28).

흐름: 파일 읽기(어댑터, 사번 열만) → `domain/rules/staff_roster.plan_import`(정규화·검증·중복
합침) → `AuthStorePort.import_staff`(HMAC 만 저장). 결과 `ImportReport` 는 개수뿐이다 — 사번 값·
다이제스트 없음.
원본 파일은 읽기만 하고 어디에도 복사하지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from rra.application.ports.auth import AuthStorePort, StaffImportResult
from rra.domain.rules.staff_roster import RosterCounts, plan_import


@dataclass(frozen=True)
class ImportReport:
    counts: RosterCounts
    result: StaffImportResult
    registered_after: int  # 저장 뒤(또는 dry_run 이면 저장했을 때의) 등록 수

    @property
    def dry_run(self) -> bool:
        return not self.result.saved

    def as_lines(self) -> list[str]:
        lines = list(self.counts.as_lines())
        lines.append(
            f"등록(신규): {self.result.added}, 이미 있음: {self.result.existing}"
            + (f", 목록에서 빠짐: {self.result.removed}" if self.result.removed else "")
        )
        if self.dry_run:
            lines.append(
                f"(--dry-run: 저장하지 않음. 저장하면 등록 사번 {self.registered_after}건)"
            )
        else:
            lines.append(f"등록된 사번: {self.registered_after}건")
        return lines


class ImportStaff:
    def __init__(self, store: AuthStorePort):
        self.store = store

    def run(
        self,
        cells: Iterable[tuple[int, object]],
        *,
        pad: int = 0,
        replace: bool = False,
        dry_run: bool = False,
    ) -> ImportReport:
        plan = plan_import(cells, pad=pad)
        result = self.store.import_staff(plan.values, replace=replace, dry_run=dry_run)
        if result.saved:
            after = self.store.staff_count()
        else:
            before = self.store.staff_count()
            after = result.added + result.existing if replace else before + result.added
        return ImportReport(counts=plan.counts, result=result, registered_after=after)
