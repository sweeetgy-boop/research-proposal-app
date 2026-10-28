# ruff: noqa: E501 — 표 머리 문자열
"""항목 12 HWPX 서식 측정 — 골든 초안을 LLM 없이 렌더해 서식 점검 전/후를 비교한다.

    PYTHONPATH=src .venv/bin/python tools/hwpx_format_report.py \\
        --runs data/eval/runs/final10_review/local \\
        --template config/templates/proposal_korail.hwpx --out-dir /tmp/hwpx-format [--figure]

- 각 run 의 draft.json 을 읽어(읽기만) 선택형은 초안 제안값으로 확정해 렌더한다. 제안자 정보 없음.
- 전: 서식 점검을 끈 렌더 결과를 점검만 해서 불일치 단락 수(종류별)를 센다.
- 후: 점검을 켠 렌더(고침 포함)의 남은 불일치 — 0 이어야 통과. 결과는 defusedxml 재파싱(보안 F).
- --figure: 기본 그림(밑그림 PNG) 하나를 2-다 섹션에 넣어 그림 캡션 서식까지 본다.
- 표준 출력에 마크다운 표(run 별 + 단계별 단락 속성 표). 본문은 찍지 않는다(머리표만).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

KINDS = ("level_style", "font_size", "leading_spaces", "cell_style", "caption")


def _figure():
    import yaml

    from rra.adapters.figures import render_svg, svg_to_png
    from rra.domain.models.figure import Figure, parse_spec

    palette = yaml.safe_load((ROOT / "config/figures.yaml").read_text(encoding="utf-8"))["palette"]
    spec = parse_spec(
        "concept",
        {
            "boxes": [
                {"label": "현황"},
                {"label": "문제"},
                {"label": "해결 방안"},
                {"label": "기대효과"},
            ]
        },
    )
    fonts = sorted((ROOT / "config/templates/figures/fonts").glob("*.otf"))
    png = svg_to_png(render_svg(spec, palette=palette, width_px=800), font_files=fonts, dpi=96)
    fig = Figure(
        id="f:method:1",
        kind="concept",
        section="method",
        caption="연구 개념도",
        spec=spec,
        source_caption="출처: 제안자 입력",
    )
    return fig, png


def main(argv: list[str] | None = None) -> int:
    from rra.adapters.rendering.hwpx import verify_hwpx
    from rra.adapters.rendering.hwpx_format import LEVEL_LABELS, format_hwpx, inspect_hwpx
    from rra.composition import build_renderer, load_settings
    from rra.domain.models import Confirmation, Draft

    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--figure", action="store_true")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args(argv)

    renderer = build_renderer(load_settings())
    renderer.template_path = args.template
    figure = _figure() if args.figure else None
    captions = (
        [f"그림 1. {figure[0].caption}", figure[0].source_caption, "별첨 그림"] if figure else []
    )
    rows, sample = [], None
    for run in sorted(p for p in args.runs.iterdir() if (p / "draft.json").is_file()):
        draft = Draft.model_validate(json.loads((run / "draft.json").read_text(encoding="utf-8")))
        choices = {
            s.key: list(s.choices)
            for s in draft.sections
            if s.key in ("task_type", "utilization") and s.choices
        }
        conf = Confirmation(choices=choices)

        def render(check: bool, draft: Draft = draft, conf: Confirmation = conf) -> bytes:
            renderer.format_check = check
            if figure is not None:
                data, _ = renderer.render_with_figures(
                    draft, confirmation=conf, figures=[(figure[0], figure[1], "image/png")]
                )
                return data
            return renderer.render(draft, confirmation=conf)

        before = render(False)
        _, found = format_hwpx(before, captions=captions)  # 점검만 (고친 결과는 버린다)
        after = render(True)
        report = dict(renderer.last_format or {})
        verify_hwpx(after)
        _, again = format_hwpx(after, captions=captions)  # 다시 돌려도 고칠 것이 없어야 한다
        row = {
            "run": run.name,
            "paragraphs": report.get("paragraphs", 0),
            "before": {k: found.fixed[k] for k in KINDS},
            "remaining": dict(report.get("remaining") or {}),
            "idempotent": again.fixed_total == 0,
            "levels": report.get("levels", {}),
            "ok": bool(report.get("ok")) and again.fixed_total == 0,
        }
        rows.append(row)
        if args.out_dir:
            args.out_dir.mkdir(parents=True, exist_ok=True)
            (args.out_dir / f"{run.name}-before.hwpx").write_bytes(before)
            (args.out_dir / f"{run.name}-after.hwpx").write_bytes(after)
        if sample is None:
            sample = (
                run.name,
                inspect_hwpx(before, captions=captions),
                inspect_hwpx(after, captions=captions),
            )

    passed = sum(1 for r in rows if r["ok"])
    print(f"통과 {passed}/{len(rows)}\n")
    print(
        "| run | 점검 단락 | 전: 단계 모양 | 전: 글자 크기 | 전: 앞 공백 | 전: 표 칸 | 전: 캡션 | 후: 남은 불일치 | 다시 점검 | 결과 |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        b = r["before"]
        print(
            f"| {r['run'][-8:]} | {r['paragraphs']} | {b['level_style']} | {b['font_size']} | "
            f"{b['leading_spaces']} | {b['cell_style']} | {b['caption']} | "
            f"{sum(r['remaining'].values())} | {'고칠 것 없음' if r['idempotent'] else '다시 고침'} | "
            f"{'통과' if r['ok'] else '실패'} |"
        )
    if sample:
        name, b_rows, a_rows = sample
        print(f"\n단락 속성 (예: run …{name[-8:]}, 본문 없이 머리표만)\n")
        print(
            "| # | 단계 | 머리표 | 전: 정렬·왼쪽·내어쓰기·줄간격·크기·앞공백 | 후: 정렬·왼쪽·내어쓰기·줄간격·크기·앞공백 |"
        )
        print("|---|---|---|---|---|")

        def cell(x: dict) -> str:
            pts = "/".join(f"{p:g}" for p in x["pt"]) or "-"
            return (
                f"{x['align'][:1]} · {x['left']} · {x['hang']} · {x['spacing']}% · {pts}pt · "
                f"{'있음' if x['leading_space'] else '없음'}"
            )

        for i, (b, a) in enumerate(zip(b_rows, a_rows, strict=False), start=1):
            if a["level"] == "-" and not b["leading_space"]:
                continue
            level = {"표 칸": "표 칸(점검 밖·양식 그대로)"}.get(a["level"]) or LEVEL_LABELS.get(
                a["level"], a["level"]
            )
            print(f"| {i} | {level} | {a['marker'] or '(빈 줄)'} | {cell(b)} | {cell(a)} |")
    if args.json:
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
