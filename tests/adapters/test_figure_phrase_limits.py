"""칸 글자 수 상한(figure_phrases.FIELD_LIMITS)까지 채운 명세도 밑그림에서 본문 폭 9pt 이상·넘침
없음 — 상한이 배치에서 나온 값인지 고정한다 (2026-10-29, ADR 0044)."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
import yaml

from rra.adapters.figures import render_svg
from rra.domain.models.figure import parse_spec
from rra.domain.rules import figure_fit as fit
from rra.domain.rules import figure_phrases as fp

ROOT = Path(__file__).parents[2]
PALETTE = yaml.safe_load((ROOT / "config/figures.yaml").read_text(encoding="utf-8"))["palette"]
sys.path.insert(0, str(ROOT / "tools"))
from figure_samples import SAMPLE_SPECS, TECHNIQUE_SAMPLES, WIDE_SAMPLES  # noqa: E402

WORDS = ["궤도", "검측", "이력", "기반", "보수", "우선순위", "산정", "선로", "상태", "진단"]
SAMPLES = {
    "as_is_to_be": ("as_is_to_be", SAMPLE_SPECS["as_is_to_be"]),
    "as_is_to_be-4칸": ("as_is_to_be", WIDE_SAMPLES["as_is_to_be-long"][1]),
    "swot": ("technique", SAMPLE_SPECS["technique"]),
    "pugh": ("technique", TECHNIQUE_SAMPLES["pugh"]),
    "cost_benefit": ("technique", TECHNIQUE_SAMPLES["cost_benefit"]),
    "pestel": ("technique", WIDE_SAMPLES["technique-pestel"][1]),
    "schedule": ("schedule", SAMPLE_SPECS["schedule"]),
    "roadmap": ("roadmap", SAMPLE_SPECS["roadmap"]),
    "concept": ("concept", SAMPLE_SPECS["concept"]),
    "process": ("process", SAMPLE_SPECS["process"]),
}


def _phrase(n: int) -> str:
    """낱말로 n 자를 채운다 (띄어쓰기 포함, 모자라면 마지막을 늘린다)."""
    out, i = "", 0
    while len((out + " " + WORDS[i % len(WORDS)]).strip()) <= n:
        out = (out + " " + WORDS[i % len(WORDS)]).strip()
        i += 1
    return out + "가" * (n - len(out))


def _filled(kind: str, data: dict) -> dict:
    d = copy.deepcopy(data)
    for s in fp.slots(kind, d):
        parts = s.path.split(".")
        node = d
        for p in parts[:-1]:
            node = node[int(p)] if isinstance(node, list) else node[p]
        node[int(parts[-1]) if isinstance(node, list) else parts[-1]] = _phrase(s.limit)
    return d


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_texts_at_the_limit_fit_the_baseline_at_9pt(name):
    kind, data = SAMPLES[name]
    spec = parse_spec(kind, _filled(kind, data))
    assert all(len(s.text) == s.limit for s in fp.slots(kind, spec.model_dump()))
    svg = render_svg(spec, palette=PALETTE, aspect=fit.choose_aspect(spec))
    m = fit.svg_metrics(svg)
    assert m.overflow == 0
    assert m.min_font is not None and fit.font_pt(m.min_font, 153.8) + fit.PT_TOLERANCE >= 9.0
