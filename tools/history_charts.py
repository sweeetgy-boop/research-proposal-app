"""docs/history/metrics.csv → docs/history/charts/*.svg|png (발표용 그래프).

실행: .venv/bin/python tools/history_charts.py [--recount]
--recount 는 git 이력에서 코드 줄·test 함수 수를 다시 센다(체크아웃 없이 `git show`).
matplotlib 는 `history` extra (`uv pip install -e ".[history]"`).
"""

from __future__ import annotations

import argparse
import collections
import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "docs" / "history" / "metrics.csv"
OUT = ROOT / "docs" / "history" / "charts"
LAYERS = ("domain", "application", "adapters", "entrypoints")


def rows() -> list[dict[str, str]]:
    with CSV.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(v: str) -> float | None:
    try:
        return float(v) if v not in ("", None) else None
    except ValueError:
        return None


def recount(commit: str) -> dict[str, int]:
    """커밋 하나의 계층별 줄 수·test 함수 수 (git show, 체크아웃 없음)."""

    def git(*a: str) -> str:
        cmd = ["git", *a]  # noqa: S607 - PATH 의 git, 인자는 코드 상수·커밋 해시
        return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT).stdout  # noqa: S603

    listed = git("ls-tree", "-r", "--name-only", commit).splitlines()
    files = [f for f in listed if f.endswith(".py")]
    by: collections.Counter[str] = collections.Counter()
    funcs = 0
    for f in files:
        txt = git("show", f"{commit}:{f}")
        if f.startswith("src/rra/"):
            parts = f.split("/")
            layer = parts[2] if len(parts) > 3 and parts[2] in LAYERS else "other"
            by[layer] += len(txt.splitlines())
        elif f.startswith("tests/") and f.rsplit("/", 1)[-1].startswith("test_"):
            heads = ("def test_", "async def test_")
            funcs += sum(1 for line in txt.splitlines() if line.lstrip().startswith(heads))
    return {**{f"{k}_lines": by[k] for k in LAYERS}, "test_functions_git": funcs}


def setup():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = [
        "AppleGothic",
        "Apple SD Gothic Neo",
        "NanumGothic",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def save(plt, fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT / f"{name}.svg")
    fig.savefig(OUT / f"{name}.png", dpi=160)
    plt.close(fig)


def chart_tests(plt, data):
    fig, ax = plt.subplots(figsize=(8, 4))
    xs = [f"{r['date'][5:]}\n{r['label']}" for r in data]
    git = [num(r["test_functions_git"]) for r in data]
    rec = [num(r["tests_passed_recorded"]) for r in data]
    ax.plot(xs, git, marker="o", label="test 함수 수 (git)")
    ax.plot(xs, rec, marker="s", label="pytest 통과 수 (기록)")
    ax.set_title("테스트 수 추이")
    ax.set_ylabel("건")
    ax.tick_params(axis="x", labelsize=7)
    ax.legend()
    ax.grid(alpha=0.3)
    save(plt, fig, "tests")


def chart_code(plt, data):
    pts = [r for r in data if all(num(r[f"{k}_lines"]) is not None for k in LAYERS)]
    fig, ax = plt.subplots(figsize=(8, 4))
    xs = [f"{r['date'][5:]}\n{r['label']}" for r in pts]
    bottom = [0.0] * len(pts)
    for k in LAYERS:
        ys = [num(r[f"{k}_lines"]) or 0 for r in pts]
        ax.bar(xs, ys, bottom=bottom, label=k)
        bottom = [b + y for b, y in zip(bottom, ys, strict=True)]
    ax.set_title("계층별 코드 줄 수 (src/rra)")
    ax.set_ylabel("줄")
    ax.tick_params(axis="x", labelsize=7)
    ax.legend()
    save(plt, fig, "code_lines")


def chart_sources(plt, data):
    pts = [r for r in data if num(r["openalex_docs"]) is not None]
    fig, ax = plt.subplots(figsize=(8, 4))
    xs = [f"{r['date'][5:]}\n{r['label']}" for r in pts]
    for key, label in (("own_docs", "own"), ("alio_docs", "alio"), ("openalex_docs", "openalex")):
        ax.plot(xs, [num(r[key]) or 0 for r in pts], marker="o", label=label)
    ax.set_title("자료원별 적재 건수")
    ax.set_ylabel("문서")
    ax.set_yscale("symlog")
    ax.tick_params(axis="x", labelsize=7)
    ax.legend()
    ax.grid(alpha=0.3)
    save(plt, fig, "sources")


def chart_models(plt):
    # docs/llm-bench-2026-10-26.md 2차 비교 (JSON (b) 최종 성공률·근거 폐기·섹션당 시간)
    names = ["Qwen2.5-7B", "A.X 4.0 Light", "Mi:dm 2.0"]
    json_b = [96.5, 79.3, 3.5]
    dropped = [0, 7, 0]
    sec = [6.8, 4.7, 17.1]
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.6))
    axes[0].bar(names, json_b, color=["#2b5797", "#999", "#999"])
    axes[0].set_title("JSON 최종 성공률 (%)")
    axes[1].bar(names, dropped, color=["#2b5797", "#999", "#999"])
    axes[1].set_title("근거 대조 폐기 문장")
    axes[2].bar(names, sec, color=["#2b5797", "#999", "#999"])
    axes[2].set_title("섹션당 시간 (초)")
    for ax in axes:
        ax.tick_params(axis="x", labelsize=8)
    fig.suptitle("로컬 작성 모델 비교 (2026-10-26, 골든셋 3건)")
    save(plt, fig, "models")


def chart_evidence(plt):
    # 골든셋 01 근거 구성 (k=20): 적재 전 → OpenAlex 적재 직후 → 출처 다양성 규칙 뒤
    stages = ["적재 전 (P1)", "OpenAlex 적재 직후", "다양성 규칙 뒤 (6)"]
    comp = {"openalex": [16, 0, 6], "alio": [4, 15, 9], "own": [0, 5, 6]}
    fig, ax = plt.subplots(figsize=(7, 4))
    bottom = [0] * 3
    for k, ys in comp.items():
        ax.bar(stages, ys, bottom=bottom, label=k)
        bottom = [b + y for b, y in zip(bottom, ys, strict=True)]
    ax.set_title("골든셋 01 근거 구성 변화 (하한 통과 청크)")
    ax.set_ylabel("청크")
    ax.legend()
    save(plt, fig, "evidence_mix")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recount", action="store_true", help="git 이력에서 줄 수·test 함수 수 재계산")
    args = ap.parse_args(argv)
    data = rows()
    if args.recount:
        for r in data:
            r.update({k: str(v) for k, v in recount(r["commit"]).items()})
        with CSV.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            w.writeheader()
            w.writerows(data)
    plt = setup()
    chart_tests(plt, data)
    chart_code(plt, data)
    chart_sources(plt, data)
    chart_models(plt)
    chart_evidence(plt)
    print(f"charts → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
