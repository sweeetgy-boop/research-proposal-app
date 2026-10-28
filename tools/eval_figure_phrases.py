"""그림 칸 글자 측정 — 시범 run(골든 아이디어)의 초안·입력·근거로 명세를 Argon 에게 다시 받고
(칸별 글자 수 상한 + 완결 구절 규칙), 밑그림 → Nano Banana → OCR 글자 크기 → 9pt 미달이면 칸 글자
다시 쓰기 → 1회 다시 그림까지 돌린 뒤 기록한다 (2026-10-29, ADR 0044).

    .venv/bin/python tools/eval_figure_phrases.py --runs-dir <시범 run 사본 폴더> --config-dir <임시
    config> \\
        --env-file .env --data-dir data --out <출력 폴더> [--thumb <Quick Look 실행 파일>] [--real]

- run 폴더는 사본을 쓴다(시범 run 은 읽기 전용). 읽는 것:
request.json·context.json·versions/draft_v1.json,
  "이전" 그림(figures/<sha>) — 새 그림은 출력 폴더에만 쓴다.
- 로컬 모델은 쓰지 않는다 — 로컬 자리에는 부르면 오류를 내는 가짜를 둔다(Argon 오류면 그 그림은
실패로 센다).
- 예산: config 사본의 llm.yaml budget.counter·figures.yaml budget_counter(레인 전용) 를 그대로
따른다.
- 출력: results.json(그림마다 비율·글자 pt·다시 그림·다시 쓴 칸·호출·초·최종 글자의 미완 구절),
그림·밑그림·
  미리보기 HWPX·쪽 미리보기(PNG), 이전/이번 나란히 JPG. 키·본문 원문은 화면에 찍지 않는다.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

# run → 그릴 것 (기본 그림 종류, 분석 기법 key)
PLAN: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "20261028155411-a38d20ef": (("as_is_to_be",), ("swot",)),
    "20261028162955-6584b758": (("as_is_to_be", "schedule"), ("swot",)),
    "20261028163931-9cb5dafa": (("as_is_to_be", "schedule"), ("cost_benefit",)),
    "20261028165110-ec1ee944": (("as_is_to_be",), ("pestel",)),
    "20261028161903-55d65737": (("as_is_to_be",), ("pugh",)),
}


class _NoLocal:
    """로컬 모델 자리 — 시범 운영 중이라 부르지 않는다(부르면 오류 → Argon 실패로 센다)."""

    model_name = "none"

    async def complete(self, *a: Any, **k: Any) -> str:
        raise RuntimeError("측정 도구는 로컬 모델을 부르지 않습니다")


class _Counting:
    """Argon 호출 머리·교정 여부만 센다 (본문은 남기지 않는다)."""

    def __init__(self, inner: Any):
        self.inner = inner
        self.heads: list[str] = []
        self.model_name = getattr(inner, "model_name", "argon")

    async def complete(self, prompt: str, **k: Any) -> str:
        head = prompt.split("\n", 1)[0][:40]
        tag = "교정" if "[형식 교정" in prompt else "첫 요청"
        self.heads.append(f"{head} {tag}")
        return await self.inner.complete(prompt, **k)


def _count(path: Path) -> int:
    try:
        return int(json.loads(path.read_text(encoding="utf-8")).get("count", 0))
    except (OSError, ValueError):
        return 0


def _side_by_side(before: bytes | None, after: bytes, out: Path, labels=("이전", "이번")) -> None:
    from PIL import Image, ImageDraw, ImageFont

    font_path = ROOT / "config/templates/figures/fonts/Pretendard-Bold.otf"
    font = ImageFont.truetype(str(font_path), 40)
    imgs = [Image.open(io.BytesIO(b)).convert("RGB") for b in (before, after) if b]
    w = 1400
    imgs = [im.resize((w, int(im.height * w / im.width))) for im in imgs]
    h = max(im.height for im in imgs) + 70
    sheet = Image.new("RGB", (w * len(imgs) + 20 * (len(imgs) - 1), h), "white")
    draw = ImageDraw.Draw(sheet)
    x = 0
    for label, im in zip(labels[-len(imgs) :], imgs, strict=True):
        draw.text((x + 10, 10), label, fill="black", font=font)
        sheet.paste(im, (x, 70))
        x += w + 20
    sheet.save(out, "JPEG", quality=85)


async def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs-dir", required=True, help="시범 run 사본 (<user>/<run_id>/…)")
    ap.add_argument("--user", default="local")
    ap.add_argument("--config-dir", required=True)
    ap.add_argument("--env-file", default=".env")
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--thumb", default="")
    ap.add_argument("--runs", default=",".join(PLAN))
    ap.add_argument(
        "--jobs",
        default="",
        help="계획 대신 run:종류[:기법] 목록 (예: 20261028163931-9cb5dafa:technique:pestel)",
    )
    ap.add_argument("--real", action="store_true", help="Argon·Nano Banana 실제 호출")
    args = ap.parse_args(argv)

    from eval_figures_wide import _draft, _thumb

    from rra.adapters.runs import FileRunStore
    from rra.composition import build_figure_renderer, build_figures, build_renderer
    from rra.config_loader import figures_config, llm_config
    from rra.domain.models import Confirmation
    from rra.domain.rules import figure_phrases as phrases
    from rra.domain.rules import figures as frules
    from rra.settings import Settings

    rewrites: list[str] = []

    class _Log(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            msg = record.getMessage()
            if msg.startswith(("figure.rewritten", "figure.rewrite_failed")):
                rewrites.append(msg)

    logging.getLogger("rra.figures").addHandler(_Log())
    logging.getLogger("rra.figures").setLevel(logging.INFO)

    settings = Settings(
        _env_file=args.env_file,  # type: ignore[call-arg]
        config_dir=Path(args.config_dir),
        data_dir=Path(args.data_dir),
    )
    if not args.real:
        print("--real 없이는 실제 호출을 하지 않습니다 (계획만 출력)")
        for r, (kinds, techs) in PLAN.items():
            print(r, kinds, techs)
        return 0
    uc = build_figures(settings, llm=_NoLocal(), renderer=build_figure_renderer(settings))
    if uc is None or uc.argon is None or uc.images is None:
        print("Argon·Nano Banana 를 쓸 수 없습니다 (키·설정 확인)")
        return 2
    uc.argon = _Counting(uc.argon)
    uc.fallback_llm = None
    print("argon:", llm_config(settings, "review")["served_model"] or "-")
    fcfg = figures_config(settings)
    from rra.config_loader import llm_budget

    text_counter = Path(llm_budget(settings)["path"])
    image_counter = Path(fcfg["budget_counter"])
    text0, image0 = _count(text_counter), _count(image_counter)
    print(f"카운터: 텍스트 {text_counter.name}={text0}, 그림 {image_counter.name}={image0}")

    store = FileRunStore(Path(args.runs_dir))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    thumb = Path(args.thumb) if args.thumb else None
    hwpx_renderer = build_renderer(settings)
    conf = Confirmation(choices={"task_type": ["applied"], "utilization": ["software"]})
    rows: list[dict[str, Any]] = []
    plan: dict[str, tuple[list[str], list[str]]] = {}
    if args.jobs:
        for job in [j for j in args.jobs.split(",") if j]:
            run_id, kind, *rest = job.split(":")
            ks, ts = plan.setdefault(run_id, ([], []))
            (ts.append(rest[0]) if kind == "technique" else ks.append(kind))
    else:
        plan = {
            r: (list(PLAN[r][0]), list(PLAN[r][1])) for r in [x for x in args.runs.split(",") if x]
        }
    for run_id, (kinds, techs) in plan.items():
        version = store.load_version(args.user, run_id, 1)
        request = store.load_request(args.user, run_id)
        snapshot = store.load_snapshot(args.user, run_id)
        if version is None:
            print(run_id, "초안 없음")
            continue
        sections = version.sections
        old = {(f.kind, getattr(f.spec, "technique", None)): f for f in version.figures}
        pool = uc.pool(sections, request, snapshot)
        jobs: list[tuple[str, str | None]] = [(k, None) for k in kinds] + [
            ("technique", t) for t in techs
        ]
        for kind, tech in jobs:
            heads0, rw0 = len(uc.argon.heads), len(rewrites)
            t0 = time.monotonic()
            if kind == "technique":
                build, reason = await uc.build_technique(tech, None, sections, request, snapshot)
                builds = [build] if build else []
                skipped = [] if build else [{"reason": reason}]
                _, _, pool_k = uc._tech_context(sections, request, snapshot, True)
            else:
                section = "objective" if kind == "as_is_to_be" else "method"
                builds, skipped = await uc.build_all([(kind, section)], sections, request, snapshot)
                pool_k = pool
            secs = round(time.monotonic() - t0, 1)
            name = f"{run_id[-8:]}-{kind}" + (f"-{tech}" if tech else "")
            heads = uc.argon.heads[heads0:]
            row: dict[str, Any] = {
                "run": run_id,
                "sample": name,
                "kind": kind,
                "technique": tech,
                "seconds": secs,
                "argon_calls": len(heads),
                "spec_corrections": sum(1 for h in heads if "교정" in h and "다시 쓰기" not in h),
                "rewrite_calls": sum(1 for h in heads if "다시 쓰기" in h),
                "rewrites": rewrites[rw0:],
            }
            if not builds:
                row["skipped"] = skipped
                rows.append(row)
                print(f"{name:40s} 건너뜀 {skipped}")
                continue
            b = builds[0]
            f = b.figure
            final_bad = phrases.problems(f.kind, f.spec.model_dump(), pool_k)
            texts = [s.text for s in phrases.slots(f.kind, f.spec.model_dump())]
            row.update(
                {
                    "renderer": f.renderer,
                    "error": f.error,
                    "image_calls": f.calls,
                    "spec_model": f.spec_model,
                    "fit": f.fit.model_dump() if f.fit else None,
                    "slot_texts": len(texts),
                    "max_len": max((len(t) for t in texts), default=0),
                    "incomplete_final": [
                        {"code": p.code, "len": len(p.slot.text), "limit": p.slot.limit}
                        for p in final_bad
                    ],
                    "incomplete_no_pool": sum(1 for t in texts if not phrases.is_complete(t)),
                }
            )
            ext = "jpg" if b.adopted_mime == "image/jpeg" else "png"
            (out / f"{name}.figure.{ext}").write_bytes(b.adopted)
            (out / f"{name}.baseline.png").write_bytes(b.baseline_png)
            (out / f"{name}.texts.json").write_text(
                json.dumps(frules.texts_of(f.spec), ensure_ascii=False, indent=1), encoding="utf-8"
            )
            pf = f.model_copy(
                update={"section": "policy_importance", "id": "f:policy_importance:1"}
            )
            hwpx, placements = hwpx_renderer.render_with_figures(
                _draft(["policy_importance"]),
                confirmation=conf,
                figures=[(pf, b.adopted, b.adopted_mime)],
            )
            (out / f"{name}.hwpx").write_bytes(hwpx)
            row["page_preview"] = _thumb(thumb, out / f"{name}.hwpx", out / f"{name}.page.png")
            row["hwpx_fit"] = placements[0].fit.model_dump() if placements[0].fit else None
            prev = old.get((kind, tech))
            if prev is not None and prev.image_sha:
                src = next(
                    iter(
                        sorted(
                            (Path(args.runs_dir) / args.user / run_id / "figures").glob(
                                f"{prev.image_sha}.*"
                            )
                        )
                    ),
                    None,
                )
                if src is not None:
                    _side_by_side(src.read_bytes(), b.adopted, out / f"{name}.before-after.jpg")
                    row["before"] = {
                        "min_text_pt": prev.fit.min_text_pt if prev.fit else None,
                        "shortened": prev.fit.shortened if prev.fit else None,
                        "redraws": prev.fit.redraws if prev.fit else None,
                        "incomplete": sum(
                            1
                            for s in phrases.slots(prev.kind, prev.spec.model_dump())
                            if not phrases.is_complete(s.text, pool_k)
                        ),
                        "texts": frules.texts_of(prev.spec),
                    }
            rows.append(row)
            fit = f.fit
            print(
                f"{name:40s} {f.renderer:11s} ratio={fit.ratio if fit else '-':6s} "
                f"min={fit.min_text_pt if fit else '-'}pt({fit.text_method if fit else '-'}) "
                f"redraws={fit.redraws if fit else '-'} rewritten={fit.shortened if fit else '-'} "
                f"img={f.calls} argon={len(heads)} 미완={len(final_bad)} {secs}s"
            )
    (out / "results.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    text1, image1 = _count(text_counter), _count(image_counter)
    print(f"Gemini 텍스트 {text1 - text0}회, 그림 {image1 - image0}회")
    (out / "calls.json").write_text(
        json.dumps({"text": text1 - text0, "image": image1 - image0}), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
