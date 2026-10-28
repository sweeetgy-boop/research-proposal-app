"""[23] 그림 가로 배치 측정 — 샘플 명세로 밑그림·Nano Banana 그림을 만들고 본문
폭
맞춤(비율·높이·글자 pt·
다시 그린 횟수)을 잰 뒤, 실물 양식 HWPX 에 넣어 한/글 Quick Look 으로 쪽 미리보기를 뽑는다
(2026-10-28 밤, ADR 0041).

    .venv/bin/python tools/eval_figures_wide.py --out /tmp/fw --config-dir <임시 config> \\
        --env-file .env --data-dir data [--real] [--thumb <thumb 실행 파일>] [--samples
        a,b]

- 실제 호출은 --real 일 때만(그림 1장 = Nano Banana 1회, OCR 로 잰 글자가 작으면 +1). 예산 카운터는
  config
  의
  figures.yaml budget_counter·daily_image_cap 을 그대로 따른다 — 측정은 레인 전용 카운터를 쓰는
  임시 config 로.
- 쪽 미리보기: macOS QuickLookThumbnailing + 한/글 Quick Look 확장(HwpQLExtViewAsThumbnails) — 첫
  쪽만 그린다.
  그래서 그림마다 그 그림이 1쪽에 오는 미리보기용 HWPX(본문은 짧은 가짜 문장)를 따로 만든다.
  제출용이 아니다.
- 명세는 tools/figure_samples.py 의 가짜 명세(실제 과제 아님). 키·본문은 출력하지 않는다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from figure_samples import SAMPLE_SPECS, TECHNIQUE_SAMPLES, WIDE_SAMPLES  # noqa: E402

SAMPLES: dict[str, tuple[str, str, dict[str, Any]]] = {
    "as_is_to_be": ("as_is_to_be", "objective", SAMPLE_SPECS["as_is_to_be"]),
    "as_is_to_be-long": ("as_is_to_be", "objective", WIDE_SAMPLES["as_is_to_be-long"][1]),
    "technique-swot": ("technique", "tech_importance", SAMPLE_SPECS["technique"]),
    "technique-pugh": ("technique", "method", TECHNIQUE_SAMPLES["pugh"]),
    "technique-cost_benefit": (
        "technique",
        "expected_management",
        TECHNIQUE_SAMPLES["cost_benefit"],
    ),
    "technique-pestel": ("technique", "tech_importance", WIDE_SAMPLES["technique-pestel"][1]),
    "schedule": ("schedule", "method", SAMPLE_SPECS["schedule"]),
    "schedule-4to1": ("schedule", "method", WIDE_SAMPLES["schedule-4to1"][1]),
    "roadmap": ("roadmap", "expected_technology", SAMPLE_SPECS["roadmap"]),
}


CONF: Any = None


class _NoLLM:
    """그림 단계(draw)는 LLM 을 부르지 않는다 — 명세는 샘플."""

    async def complete(self, *a: Any, **k: Any) -> str:  # pragma: no cover
        raise RuntimeError("측정 도구는 LLM 을 부르지 않습니다")


def _draft(section_keys: list[str]):
    from rra.domain.models import Draft, ProposalRequest, Section, Sentence

    keys = ["title", "task_type", "utilization", *section_keys]
    sections = []
    for k in dict.fromkeys(keys):
        text = {
            "title": "영업열차 탑재 센서 기반 궤도 상태 상시 감지 (측정용 가짜 과제)",
        }.get(k, "측정용 가짜 문장입니다. 그림이 본문 폭에 맞게 들어가는지 봅니다.")
        sections.append(
            Section(
                key=k,
                sentences=[] if k in ("task_type", "utilization") else [Sentence(text=text)],
                choices=["applied"]
                if k == "task_type"
                else (["software"] if k == "utilization" else []),
            )
        )
    req = ProposalRequest(current_state="a", root_cause="b", limitation="c", goal="d")
    return Draft(
        run_id="eval", request=req, sections=sections, template="korail_rnd_proposal_v2024"
    )


def _thumb(thumb: Path | None, hwpx: Path, png: Path, width: int = 1400) -> bool:
    if thumb is None:
        return False
    try:
        subprocess.run(  # noqa: S603 — 측정자가 준 Quick Look 실행 파일
            [str(thumb), str(hwpx), str(png), str(width)],
            check=True,
            timeout=120,
            capture_output=True,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return png.is_file()


async def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--config-dir", required=True)
    ap.add_argument("--env-file", default=".env")
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--real", action="store_true", help="Nano Banana 실제 호출")
    ap.add_argument(
        "--thumb", default="", help="Quick Look 미리보기 실행 파일 (없으면 미리보기 생략)"
    )
    ap.add_argument("--samples", default=",".join(SAMPLES))
    args = ap.parse_args(argv)

    from rra.composition import build_figure_renderer, build_figures, build_renderer
    from rra.domain.models import Confirmation

    global CONF
    CONF = Confirmation(choices={"task_type": ["applied"], "utilization": ["software"]})
    from rra.domain.models.figure import Figure, display_name, parse_spec
    from rra.settings import Settings

    settings = Settings(
        _env_file=args.env_file,  # type: ignore[call-arg]
        config_dir=Path(args.config_dir),
        data_dir=Path(args.data_dir),
    )
    uc = build_figures(settings, llm=_NoLLM(), renderer=build_figure_renderer(settings))
    if not args.real:
        uc.images = None
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    thumb = Path(args.thumb) if args.thumb else None
    renderer = build_renderer(settings)
    rows = []
    built: list[tuple[str, Any, bytes, str]] = []
    for name in [s for s in args.samples.split(",") if s]:
        kind, section, data = SAMPLES[name]
        spec = parse_spec(kind, data)
        fig = Figure(
            id=f"f:{section}:1",
            kind=kind,  # type: ignore[arg-type]
            section=section,
            caption=getattr(spec, "title", None) or display_name(kind),
            spec=spec,
        )
        t0 = time.monotonic()
        build = await uc.draw(fig)
        secs = round(time.monotonic() - t0, 1)
        f = build.figure
        ext = "jpg" if build.adopted_mime == "image/jpeg" else "png"
        (out / f"{name}.baseline.png").write_bytes(build.baseline_png)
        (out / f"{name}.figure.{ext}").write_bytes(build.adopted)
        built.append((name, f, build.adopted, build.adopted_mime))
        # 미리보기용 HWPX — 이 그림이 1쪽에 오도록 2-가-(1) 칸에 넣는다
        # (같은 본문 단락 모양 — 크기 계산은 같다)
        pf = f.model_copy(update={"section": "policy_importance", "id": "f:policy_importance:1"})
        hwpx, placements = renderer.render_with_figures(
            _draft(["policy_importance"]),
            confirmation=CONF,
            figures=[(pf, build.adopted, build.adopted_mime)],
        )
        (out / f"{name}.hwpx").write_bytes(hwpx)
        page = _thumb(thumb, out / f"{name}.hwpx", out / f"{name}.page.png")
        pfit = placements[0].fit
        rows.append(
            {
                "sample": name,
                "renderer": f.renderer,
                "error": f.error,
                "calls": f.calls,
                "seconds": secs,
                "fit": f.fit.model_dump() if f.fit else None,
                "hwpx_fit": pfit.model_dump() if pfit else None,
                "page_preview": page,
            }
        )
        print(
            f"{name:24s} {f.renderer:11s} ratio={f.fit.ratio if f.fit else '-':5s} "
            f"hwpx={pfit.width_mm if pfit else '-'}x{pfit.height_mm if pfit else '-'}mm "
            f"fits={pfit.fits if pfit else '-'} min={f.fit.min_text_pt if f.fit else '-'}pt"
            f"({f.fit.text_method if f.fit else '-'}) redraws={f.fit.redraws if f.fit else '-'} "
            f"short={f.fit.shortened if f.fit else '-'} calls={f.calls} {secs}s"
        )
    (out / "results.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    # 전체 HWPX (그림마다 제 섹션) — 통합 점검용
    secs = sorted({f.section for _n, f, _d, _m in built})
    figs = [
        (f.model_copy(update={"id": f"f:{f.section}:{i + 1}"}), d, m)
        for i, (_n, f, d, m) in enumerate(built)
    ]
    hwpx, placements = renderer.render_with_figures(_draft(secs), confirmation=CONF, figures=figs)
    (out / "all.hwpx").write_bytes(hwpx)
    ok = sum(1 for p in placements if p.fit and p.fit.fits)
    print(f"all.hwpx: 그림이 본문 폭에 맞게 들어감 {ok}/{len(placements)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
