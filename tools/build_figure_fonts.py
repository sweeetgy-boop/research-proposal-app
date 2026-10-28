"""그림(인포그래픽) 렌더용 Pretendard 서브셋 만들기 — `config/templates/figures/fonts/` (G, 2026-10-28).

원본: web/node_modules/pretendard/dist/public/static/Pretendard-{Regular,Bold}.otf (OFL-1.1, 1.6MB 씩).
서브셋: 한글 음절 전체(가~힣)·호환 자모·기본 라틴·구두점·화살표·도형 기호 → 각 2.0MB 이하.
    .venv/bin/python tools/build_figure_fonts.py
렌더러(adapters/figures/render.py)는 resvg 에 이 두 파일만 넘긴다(시스템 폰트 사용 안 함 — 운영기·CI 결과 동일).
"""

from __future__ import annotations

import sys
from pathlib import Path

from fontTools import subset

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "web/node_modules/pretendard/dist/public/static"
OUT = ROOT / "config/templates/figures/fonts"
UNICODES = (
    "U+0020-007E,U+00A0-00FF,U+2000-206F,U+2190-21FF,U+2200-22FF,U+2460-24FF,"
    "U+25A0-25FF,U+3000-303F,U+3131-318E,U+AC00-D7A3,U+FF01-FF60"
)


def main() -> int:
    if not SRC.exists():
        print(f"원본 폰트가 없습니다: {SRC} (web/ 에서 npm ci)", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    for weight in ("Regular", "Bold"):
        out = OUT / f"Pretendard-{weight}.otf"
        subset.main(
            [
                str(SRC / f"Pretendard-{weight}.otf"),
                f"--unicodes={UNICODES}",
                f"--output-file={out}",
                "--layout-features=*",
                "--no-hinting",
                "--desubroutinize",
            ]
        )
        print(f"{out.relative_to(ROOT)}  {out.stat().st_size / 1024 / 1024:.2f}MB")
    (OUT / "LICENSE.txt").write_bytes((SRC.parent.parent / "LICENSE.txt").read_bytes())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
