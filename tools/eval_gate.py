"""L0 게이트 (ADR 0058, 계약 docs/contracts/eval-results.md §6) — CI job `eval-l0`.

사용: python tools/eval_gate.py <새 결과.json> [--baseline eval/results/latest-l0.json]
                                [--max-recall-drop 0.05] [--max-false-block-rise 0.05]
기준(직전 main 의 latest-l0.json) 대비 recall_at5 가 max_recall_drop 넘게 떨어지거나 false_block 이
max_false_block_rise 넘게 오르면 종료 코드 1. 기준 파일이 없으면 비교 없이 통과(안내만) — 첫 PR 과
포크에서 막히지 않게. 표준 라이브러리만 쓴다(설치 없이 돈다).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_BASELINE = "eval/results/latest-l0.json"


def _metric(data: dict, key: str) -> float | None:
    value = (data.get("metrics") or {}).get(key)
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def check(
    base: dict, new: dict, *, max_recall_drop: float, max_false_block_rise: float
) -> list[str]:
    failures: list[str] = []
    b_recall, n_recall = _metric(base, "recall_at5"), _metric(new, "recall_at5")
    if b_recall is not None and n_recall is not None and b_recall - n_recall > max_recall_drop:
        failures.append(
            f"recall_at5 {b_recall:.3f} → {n_recall:.3f} "
            f"(−{b_recall - n_recall:.3f} > {max_recall_drop})"
        )
    b_fb, n_fb = _metric(base, "false_block"), _metric(new, "false_block")
    if b_fb is not None and n_fb is not None and n_fb - b_fb > max_false_block_rise:
        failures.append(
            f"false_block {b_fb:.3f} → {n_fb:.3f} (+{n_fb - b_fb:.3f} > {max_false_block_rise})"
        )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="L0 평가 게이트")
    parser.add_argument("result", help="이번 실행 결과 JSON")
    parser.add_argument("--baseline", default=DEFAULT_BASELINE)
    parser.add_argument("--max-recall-drop", type=float, default=0.05)
    parser.add_argument("--max-false-block-rise", type=float, default=0.05)
    args = parser.parse_args(argv)
    new = json.loads(Path(args.result).read_text(encoding="utf-8"))
    base_path = Path(args.baseline)
    if not base_path.is_file():
        print(
            f"[eval-gate] 기준 파일 없음 ({base_path}) — 비교 없이 통과. "
            "main 병합 뒤 통합 담당이 만든다."
        )
        return 0
    base = json.loads(base_path.read_text(encoding="utf-8"))
    print(
        "[eval-gate] 기준 recall_at5={} false_block={} → 이번 recall_at5={} false_block={}".format(
            _metric(base, "recall_at5"),
            _metric(base, "false_block"),
            _metric(new, "recall_at5"),
            _metric(new, "false_block"),
        )
    )
    failures = check(
        base,
        new,
        max_recall_drop=args.max_recall_drop,
        max_false_block_rise=args.max_false_block_rise,
    )
    for f in failures:
        print(f"[eval-gate] 실패: {f}")
    if not failures:
        print("[eval-gate] 통과")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
