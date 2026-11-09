"""L0 고정 문제·판정 캐시 만들기 (ADR 0058, 레인 D) — 합성 코퍼스(tests/eval/l0_corpus.jsonl)만
쓴다.

사용: PYTHONPATH=src python tools/eval_l0_record.py [--seed 20261109] [--n 20] [--oracle | --real]
- 문제: ProblemGenerator(합성 코퍼스 메모리 저장소) → tests/eval/l0_problems.jsonl (덮어씀).
- 캐시(--oracle, 기본): 판정 프롬프트마다 "정답 과제면 same, 아니면 different" 응답을 캐시 파일로
  녹화한다 — 실제 Gemini 응답이 아니라 정답표 기반 대본이다(CI 는 외부 호출 없이 판정 경로의 회귀를
  본다). `--real` 은 평가 예산 LLM(Gemini)으로 녹화한다(`rra eval run --suite l0 --record` 와 같다).
운영 DB·키·사내 자료를 읽지 않는다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from rra.adapters.eval import CacheReplayLLM, L0Repository, load_corpus
from rra.application.usecases.eval_problems import ProblemGenerator, precheck_blocks
from rra.composition import build_eval_precheck, load_settings
from rra.config_loader import eval_config, keyword_rule
from rra.domain.models.eval_problem import ProblemMix

_DOC = re.compile(r'<doc id="([^"]+)">')


class OracleJudge:
    """정답표 대본 LLM — 프롬프트의 후보 doc_id 중 정답 집합에 든 것만 same."""

    def __init__(self, answers: set[str]):
        self.answers = answers
        self.calls = 0

    async def complete(self, prompt, *, system=None, max_tokens=None, json_mode=False) -> str:
        self.calls += 1
        items = [
            {
                "doc_id": d,
                "verdict": "same" if d in self.answers else "different",
                "reason": "대본 판정 (합성 코퍼스 정답표)",
            }
            for d in _DOC.findall(prompt)
        ]
        return json.dumps({"items": items}, ensure_ascii=False)


async def run(args: argparse.Namespace) -> int:
    settings = load_settings()
    cfg = eval_config(settings)
    repo = L0Repository(load_corpus(Path(cfg.l0.corpus)))
    rule_precheck = build_eval_precheck(settings, repo=repo, judge=False)
    generator = ProblemGenerator(
        repo,
        sources=cfg.l1.sources,
        topics=cfg.novel_topics,
        keywords=keyword_rule(settings),
        rule_check=precheck_blocks(rule_precheck),
        min_text_chars=args.min_chars,
    )
    problems = await generator.generate(
        seed=args.seed, n=args.n, mix=ProblemMix(reverse=0.5, trap=0.3, novel=0.2)
    )
    # 고정 문제는 공개 fixture — 봉인 저장소(600)가 아니라 보통 파일로 쓴다
    Path(cfg.l0.problems).write_text(
        "".join(json.dumps(p.model_dump(), ensure_ascii=False) + "\n" for p in problems),
        encoding="utf-8",
    )
    oracle = OracleJudge(
        set()
    )  # 문제마다 정답 집합을 바꿔 준다 (역방향만 same, 함정·새 영역은 없음)
    if args.real:
        from rra.composition import build_eval_llm

        inner, _budget = build_eval_llm(settings)
        if inner is None:
            print("평가용 LLM 키가 없습니다 (--oracle 로).", file=sys.stderr)
            return 2
    else:
        inner = oracle
    replay = CacheReplayLLM(Path(cfg.l0.cache_dir), inner=inner)
    precheck = build_eval_precheck(settings, repo=repo, llm=replay)
    for p in problems:
        oracle.answers = set(p.answers) if p.kind == "reverse" else set()
        await precheck.run(p.to_request(), ai=True)
    kinds = {k: sum(1 for p in problems if p.kind == k) for k in ("reverse", "trap", "novel")}
    print(
        f"문제 {len(problems)}건 {kinds} → {cfg.l0.problems}; "
        f"캐시 적중 {replay.hits} 녹화 {replay.recorded}"
        f" → {cfg.l0.cache_dir}"
    )
    close = getattr(inner, "aclose", None)
    if close is not None:
        await close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="L0 고정 문제·캐시 만들기")
    parser.add_argument("--seed", type=int, default=20261109)
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--min-chars", type=int, default=60)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--oracle", action="store_true", help="정답표 대본으로 녹화 (기본)")
    mode.add_argument("--real", action="store_true", help="평가 예산 LLM(Gemini)으로 녹화")
    return asyncio.run(run(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
