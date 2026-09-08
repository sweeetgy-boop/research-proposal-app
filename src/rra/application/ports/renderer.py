from __future__ import annotations

from typing import Protocol

from rra.domain.models import Draft


class RendererPort(Protocol):
    def render(self, draft: Draft) -> bytes: ...
