"""그림 밑그림 어댑터 — 명세 → SVG(render) → PNG(png).

`SvgFigureRenderer` 가 application/ports/figures.FigureRendererPort 구현.
[23] `min_font`(본문 폭에서 9pt 가 되는 글자 하한)·`arrangements`(분석 기법 key → 배치)를 composition 이 준다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from rra.adapters.figures.png import fit_aspect, image_size, shrink_image, svg_to_png
from rra.adapters.figures.render import MIN_FONT, render_svg

__all__ = [
    "SvgFigureRenderer",
    "fit_aspect",
    "image_size",
    "render_svg",
    "shrink_image",
    "svg_to_png",
]


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
        min_font: float = MIN_FONT,
        arrangements: Mapping[str, str] | None = None,
    ):
        self.palette = dict(palette)
        self.aspects = dict(aspects)
        self.width_px = int(width_px)
        self.font_files = [str(p) for p in font_files]
        self.dpi = int(dpi)
        self.max_bytes = int(max_bytes)
        self.min_font = float(min_font)
        self.arrangements = dict(arrangements or {})

    def svg(self, spec: BaseModel, *, caption: str = "", aspect: str | None = None) -> str:
        aspect = aspect or self.aspects.get(str(getattr(spec, "kind", "")), "16:9")
        return render_svg(
            spec,
            palette=self.palette,
            aspect=aspect,
            width_px=self.width_px,
            caption=caption,
            min_font=self.min_font,
            arrange=self.arrangements.get(str(getattr(spec, "technique", "") or "")),
        )

    def png(self, svg: str) -> bytes:
        return svg_to_png(svg, font_files=self.font_files, dpi=self.dpi, max_bytes=self.max_bytes)
