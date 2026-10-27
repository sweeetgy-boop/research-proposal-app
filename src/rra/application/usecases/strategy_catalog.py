"""전략체계 초안 확정 (`rra strategy promote`) — 사람만 실행한다.

초안(korail_strategy.draft.yaml)을 확정 파일(korail_strategy.yaml)로 복사하고, 기존 확정 파일은
`korail_strategy.yaml.bak-<시각>` 으로 남긴 뒤 strategy.yaml 의 source 를 confirmed 로 바꾼다.
초안이 StrategyCatalog 로 검증되지 않으면 아무것도 바꾸지 않는다.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from rra.domain.models import StrategyCatalog


@dataclass(frozen=True)
class PromoteReport:
    target: Path
    backup: Path | None
    directions: int
    tasks: int


def promote_strategy(
    draft: Path,
    target: Path,
    strategy_cfg: Path,
    *,
    clock: Callable[[], datetime] = datetime.now,
) -> PromoteReport:
    if not draft.is_file():
        raise FileNotFoundError(f"초안 파일이 없습니다: {draft.name} (rra strategy draft)")
    data = yaml.safe_load(draft.read_text(encoding="utf-8")) or {}
    catalog = StrategyCatalog.model_validate(
        {"source": data.get("source") or "", "directions": data.get("directions") or []}
    )
    if not catalog.directions:
        raise ValueError("초안에 전략방향이 없습니다 — 확정할 것이 없습니다.")
    backup = None
    if target.is_file():
        backup = target.with_name(f"{target.name}.bak-{clock():%Y%m%d-%H%M%S}")
        shutil.copyfile(target, backup)
    shutil.copyfile(draft, target)
    strategy_cfg.write_text(
        "# 전략체계 목록의 출처 — draft | confirmed. `rra strategy promote` 가 confirmed 로 바꿨다 "
        f"({clock():%Y-%m-%d}).\nsource: confirmed\n",
        encoding="utf-8",
    )
    return PromoteReport(
        target=target,
        backup=backup,
        directions=len(catalog.directions),
        tasks=sum(len(d.tasks) for d in catalog.directions),
    )
