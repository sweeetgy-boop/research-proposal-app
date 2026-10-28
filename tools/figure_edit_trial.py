"""[말로 고치기] 새 경로 실호출 시험 — 명세 변경(Argon) → 밑그림 → Nano Banana ([2] 2026-10-28).

    PYTHONPATH=src .venv/bin/python tools/with_heavy_lock.py -- \
        .venv/bin/python tools/figure_edit_trial.py --out docs/history/screens --reps 2

개념도 샘플 명세(`tools/figure_samples.SAMPLE_SPECS["concept"]`, 가짜 과제)에서 요청 3개를 차례로
쌓지 않고 **각각 같은 시작 명세에서** 돌린다. 로컬 모델(mlx)은 부르지 않는다 — Argon 이 실패하면
그 요청은 실패로 적는다. 결과 그림은 macOS Vision OCR(`build_vision_ocr`)로 읽어 명세 글자 목록과
글자 단위로 대조한다(OCR 오독도 차이로 잡히므로 그림을 눈으로 함께 본다). 이미지 캐시는 끄고(매번
새 호출) 공용 제한기·일일 상한은 그대로 쓴다. 출력: `<out>/2026-10-28-figures-edit-v2-<n>.jpg` +
표준출력 JSON 줄.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUESTS = [
    "상자 테두리를 조금 더 굵게 하고 화살표를 진하게",
    "기대효과 상자만 강조 색으로",
    "해결 방안 상자의 두 번째 줄을 '구간별 궤도 상태 지수 자동 산출'로 유지하고 "
    "기대효과 첫 줄을 '이상 구간 조기 발견'으로 바꿔",
]


class _NoLocal:
    """시험에서는 로컬 모델(mlx)을 띄우지 않는다 — 부르면 실패."""

    async def complete(self, prompt, *, system=None, max_tokens=None, json_mode=False) -> str:
        raise RuntimeError("local model disabled for trial")


_KEEP = re.compile(r"[0-9A-Za-z가-힣]")


def _norm(text: str) -> str:
    """한글·영숫자만 — 가운뎃점(·)·글머리표는 OCR 이 •·.·- 로 읽어 차이에서 뺀다."""
    return "".join(_KEEP.findall(text))


def substring_distance(needle: str, hay: str) -> int:
    """needle 과 hay 의 가장 가까운 부분 문자열 사이 편집 거리 (Sellers)."""
    if not needle:
        return 0
    prev = [0] * (len(hay) + 1)
    for i, a in enumerate(needle, 1):
        cur = [i] + [0] * len(hay)
        for j, b in enumerate(hay, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a != b))
        prev = cur
    return min(prev)


def glyph_report(texts: list[str], ocr_text: str) -> tuple[int, list[dict]]:
    hay = _norm(ocr_text)
    rows = []
    for t in texts:
        d = substring_distance(_norm(t), hay)
        if d:
            rows.append({"text": t, "distance": d})
    return sum(r["distance"] for r in rows), rows


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--start", type=int, default=1, help="파일 번호 시작")
    parser.add_argument("--env-file", default=None, help="worktree 에서는 원 저장소 .env 경로")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "tools"))
    from figure_samples import SAMPLE_SPECS

    from rra.composition import (
        build_figures,
        build_image_generator,
        build_llm,
        build_vision_ocr,
        load_settings,
    )
    from rra.domain.models import ProposalRequest, Section, Sentence
    from rra.domain.models.figure import Figure, parse_spec
    from rra.domain.rules import figures as rules
    from rra.settings import Settings

    settings = Settings(_env_file=args.env_file) if args.env_file else load_settings()
    images = build_image_generator(settings)
    if images is None:
        print("gemini 키 없음", file=sys.stderr)
        return 2
    images.cache_dir = None  # 매번 새 호출 (시간·글자 변형을 재려고)
    uc = build_figures(
        settings, llm=_NoLocal(), images=images, argon=build_llm(settings, stage="review")
    )
    ocr = build_vision_ocr(settings)
    data = json.loads(json.dumps(SAMPLE_SPECS["concept"], ensure_ascii=False))
    for box, label in zip(data["boxes"], rules.CONCEPT_LABELS, strict=True):
        box["label"] = label  # 지금 생성되는 개념도와 같게 (repair_spec 고정 라벨)
    spec = parse_spec("concept", data)
    figure = Figure(id="f:objective:1", kind="concept", section="objective", spec=spec)
    sections = [
        Section(key="objective", sentences=[Sentence(text=t) for t in rules.texts_of(spec)])
    ]
    request = ProposalRequest(
        current_state="궤도 틀림 점검을 주기 순회로 수작업 측정",
        root_cause="상시 감지 센서 부재",
        limitation="점검 주기 사이 이상 발생 시 대응 지연",
        goal="구간별 궤도 상태 지수 자동 산출",
    )
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    n = args.start
    for rep in range(args.reps):
        for text in REQUESTS:
            t0 = time.monotonic()
            row: dict = {"n": n, "rep": rep + 1, "request": text}
            try:
                build = await uc.edit_by_words(
                    figure, text, sections=sections, request=request, snapshot=None
                )
            except Exception as exc:  # 사유 코드만
                row.update(ok=False, error=str(exc)[:80], seconds=round(time.monotonic() - t0, 1))
                print(json.dumps(row, ensure_ascii=False), flush=True)
                n += 1
                continue
            fig = build.figure
            path = out_dir / f"2026-10-28-figures-edit-v2-{n}.jpg"
            path.write_bytes(build.adopted)
            texts = rules.texts_of(fig.spec)
            row.update(
                ok=True,
                seconds=round(time.monotonic() - t0, 1),
                renderer=fig.renderer,
                error=fig.error,
                change=fig.last_change.model_dump() if fig.last_change else None,
                file=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                bytes=len(build.adopted),
            )
            if ocr is not None:
                result = await ocr.recognize(build.adopted, mime=build.adopted_mime)
                total, diffs = glyph_report(texts, result.text)
                row.update(ocr_glyph_diff=total, ocr_diffs=diffs, ocr_text=result.text)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            n += 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
