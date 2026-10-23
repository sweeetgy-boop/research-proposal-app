from __future__ import annotations

from typing import Protocol, runtime_checkable

from rra.domain.models import Draft


@runtime_checkable
class RendererPort(Protocol):
    def render(self, draft: Draft) -> bytes: ...
