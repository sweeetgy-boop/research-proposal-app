"""의존성 조립. 전 계층을 아는 유일한 모듈. Step 2에서 실제 어댑터 연결."""

from __future__ import annotations

from rra.settings import Settings, load_settings

__all__ = ["Settings", "load_settings"]
