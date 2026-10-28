"""그림 밑그림 샘플 6종 렌더 — `<dir>/<kind>.baseline.svg`·`.png` ([G] 2026-10-28).

    .venv/bin/python tools/figure_samples.py --out /tmp/figure_samples

팔레트·비율·폭은 config/figures.yaml, 폰트는 config/templates/figures/fonts. `SAMPLE_SPECS` 는
tests/adapters/test_figure_render.py 도 같이 쓴다(가짜 명세 — 실제 과제 아님).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/figures.yaml"
FONTS = ROOT / "config/templates/figures/fonts"

SAMPLE_SPECS: dict[str, dict[str, Any]] = {
    "concept": {
        "boxes": [
            {
                "label": "현황",
                "lines": [
                    "궤도 틀림 점검을 주기 순회로 수작업 측정",
                    "야간 차단 시간에만 점검 가능",
                ],
            },
            {
                "label": "문제",
                "lines": [
                    "상시 감지 센서 부재로 급격한 변화 미탐지",
                    "점검 주기 사이 이상 발생 시 대응 지연",
                ],
            },
            {
                "label": "해결 방안",
                "lines": [
                    "영업열차 탑재 IMU·가속도 센서로 상시 수집",
                    "구간별 궤도 상태 지수 자동 산출",
                ],
            },
            {
                "label": "기대효과",
                "lines": ["이상 구간 조기 발견·유지보수 우선순위 결정", "점검 인력·차단 시간 절감"],
            },
        ]
    },
    "process": {
        "stages": [
            {"name": "현황 분석", "outputs": ["점검 데이터 수집 현황", "요구사항 정의서"]},
            {"name": "센서 체계 설계", "outputs": ["센서 배치안", "데이터 규격"]},
            {"name": "시작품 제작·시험", "outputs": ["탑재 시작품", "시험 성적서"]},
            {"name": "현장 실증", "outputs": ["실증 구간 운영 결과", "정확도 검증 보고서"]},
            {"name": "운영 지침화", "outputs": ["유지보수 적용 지침(안)"]},
        ]
    },
    "schedule": {
        "total_months": 24,
        "stages": [
            {"name": "현황 분석·요구사항 정의", "start_month": 1, "end_month": 4},
            {"name": "센서 체계 설계", "start_month": 3, "end_month": 8},
            {"name": "시작품 제작·시험", "start_month": 7, "end_month": 14},
            {"name": "현장 실증", "start_month": 13, "end_month": 21},
            {"name": "운영 지침화·보고서", "start_month": 20, "end_month": 24},
        ],
    },
    "stat_chart": {
        "chart": "bar",
        "title": "연도별 궤도 틀림 검출 건수",
        "categories": ["2021년", "2022년", "2023년", "2024년"],
        "series": [
            {"name": "고속선", "values": [1512, 1388, 1275, 1190]},
            {"name": "일반선", "values": [2904, 2755, 2610, 2498]},
            {"name": "광역선", "values": [820, 790, 765, 702]},
        ],
        "unit": "건",
        "value_texts": [
            "1,512",
            "1,388",
            "1,275",
            "1,190",
            "2,904",
            "2,755",
            "2,610",
            "2,498",
            "820",
            "790",
            "765",
            "702",
        ],
        "source": {
            "doc_id": "alio:2024-01",
            "title": "궤도 유지보수 통계",
            "year": 2024,
            "page": 12,
        },
    },
    "comparison": {
        "aspects": ["연구목표", "연구방법", "적용범위"],
        "projects": [
            {
                "title": "궤도검측차 측정 자동화 연구",
                "cells": {
                    "연구목표": "검측차 측정 주기 단축",
                    "연구방법": "검측차 센서 고도화",
                    "적용범위": "고속선",
                },
            },
            {
                "title": "열차 진동 기반 궤도 상태 추정",
                "cells": {
                    "연구목표": "진동 데이터로 궤도 상태 추정",
                    "연구방법": "가속도 센서 분석",
                },
            },
        ],
        "proposal": {
            "title": "영업열차 탑재 센서 기반 궤도 상태 상시 감지",
            "cells": {
                "연구목표": "상시 감지로 이상 구간 조기 발견",
                "연구방법": "IMU·가속도 센서 + 구간별 상태 지수 산출",
                "적용범위": "고속선·일반선·광역선 전체",
            },
        },
    },
    "roadmap": {
        "metrics": [
            {"name": "이상 구간 검출 정확도", "target": "90% 이상"},
            {"name": "점검 차단 시간", "target": "30% 절감"},
            {"name": "유지보수 적용 지침", "target": "목표치 확인 필요"},
        ],
        "stages": [
            {"name": "시범 구간 적용", "desc": "고속선 1개 구간"},
            {"name": "전 노선 확대", "desc": "일반선·광역선 순차 적용"},
            {"name": "유지보수 체계 반영", "desc": "점검 주기·우선순위 규정 개정"},
        ],
    },
}


def load_config() -> dict[str, Any]:
    with CONFIG.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def font_files() -> list[Path]:
    return sorted(FONTS.glob("Pretendard-*.otf"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="그림 밑그림 샘플 6종 렌더")
    parser.add_argument("--out", required=True, help="출력 폴더")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT / "src"))
    from rra.adapters.figures import SvgFigureRenderer
    from rra.domain.models.figure import parse_spec

    cfg = load_config()
    renderer = SvgFigureRenderer(
        palette=cfg.get("palette") or {},
        aspects=cfg.get("aspect") or {},
        width_px=int(cfg.get("width_px") or 1600),
        font_files=font_files(),
        dpi=int(cfg.get("dpi") or 300),
        max_bytes=int(cfg.get("max_png_bytes") or 512_000),
    )
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for kind, data in SAMPLE_SPECS.items():
        spec = parse_spec(kind, data)
        svg = renderer.svg(spec)
        png = renderer.png(svg)
        svg_path = out_dir / f"{kind}.baseline.svg"
        png_path = out_dir / f"{kind}.baseline.png"
        svg_path.write_text(svg, encoding="utf-8")
        png_path.write_bytes(png)
        print(f"{svg_path.name}: {len(svg.encode('utf-8')):,} bytes")
        print(f"{png_path.name}: {len(png):,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
