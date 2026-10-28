"""그림 밑그림 어댑터 — 명세 → SVG(render) → PNG(png).

`SvgFigureRenderer` 가 application/ports/figures.FigureRendererPort 구현.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from rra.adapters.figures.png import image_size, shrink_image, svg_to_png
from rra.adapters.figures.render import render_svg

__all__ = ["SvgFigureRenderer", "image_size", "render_svg", "shrink_image", "svg_to_png"]


class SvgFigureRenderer:
    """팔레트·종류별 비율·폰트를 묶은 렌더러 (composition 이 figures.yaml 로 조립)."""

    def __init__(
        self,
        palette: Mapping[str, Any],
        aspects: Mapping[str, str],
        width_px: int = 1600,
        font_files: Sequence[Path | str] = (),
        dpi: int = 300,
        max_bytes: int = 512_000,
    ):
        self.palette = dict(palette)
        self.aspects = dict(aspects)
        self.width_px = int(width_px)
        self.font_files = [str(p) for p in font_files]
        self.dpi = int(dpi)
        self.max_bytes = int(max_bytes)

    def svg(self, spec: BaseModel, *, caption: str = "") -> str:
        aspect = self.aspects.get(str(getattr(spec, "kind", "")), "16:9")
        return render_svg(
            spec, palette=self.palette, aspect=aspect, width_px=self.width_px, caption=caption
        )

    def png(self, svg: str) -> bytes:
        return svg_to_png(svg, font_files=self.font_files, dpi=self.dpi, max_bytes=self.max_bytes)
