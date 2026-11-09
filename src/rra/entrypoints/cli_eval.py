"""`rra eval run|compare|usage|seal` — 평가 체계 서브명령 (ADR 0058, 계약
docs/contracts/eval-results.md
§5, 절차 docs/eval-protocol.md). 레인 D.

cli.py 는 공용 파일이라 여기서 고치지 않는다. 통합 때 메인이 cli.py 의 `eval` 파서(`ev`) 뒤에
다음 두 줄을 넣는다(PR 설명 "통합 때 메인이 반영할 조립 변경"):

    from rra.entrypoints.cli_eval import register as register_eval   # 파일 위 import
    register_eval(sub, ev)   # ev.set_defaults(handler=cmd_eval) 뒤

`register(sub, eval_parser)` 는 기존 `eval` 파서에 서브파서(dest="eval_cmd", required=False)를
붙이므로
서브명령이 없으면 종전 `rra eval --label …`(cmd_eval) 그대로다. 통합 전에는 독립 실행
`python -m rra.entrypoints.cli_eval run --suite l0 …` 으로 같은 핸들러를 돈다(CI·launchd 는 이
형태).

봉인 묶음 규칙(사용자 지시 2026-11-09): 스위치를 켤지 판단하는 (가)(나)(다) 비교는 **연습용 묶음**
(`data/eval/practice/`, `--seed` 지정)으로 한다. 봉인 묶음(`--sealed`)은 판단이 끝난 뒤 보고서용
최종
확인 **한 번만** — 실행 때 경고 한 줄을 낸다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

from rra.domain.models.eval_result import SUITES

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
SEALED_WARNING = "봉인 묶음 — 보고서용 최종 확인 1회 (개선 작업 중 비교는 연습용 묶음으로)"
RUN_HELP = (
    "suite 실행 → 결과 JSON(eval/results/). l0: 고정 문제·캐시 재생(CI). l1: 자동 생성 문제(연습용 "
    "묶음 data/eval/practice/<suite>-<seed>.jsonl, 없으면 만든다). l2: 골든셋+초안(기존 rra eval "
    "재사용). "
    "스위치 비교(가·나·다)는 --seed 를 같게 한 연습용 묶음으로, --sealed(봉인 묶음)는 판단이 "
    "끝난 뒤 "
    "보고서용 최종 확인 1회만."
)


def _eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


# ── 파서 ─────────────────────────────────────────────────
def parse_mix(text: str):
    """`--mix 0.5,0.3,0.2` → ProblemMix(reverse, trap, novel). 세 수가 아니면 ValueError."""
    from rra.domain.models.eval_problem import ProblemMix

    parts = [float(x) for x in text.split(",")]
    if len(parts) != 3:
        raise ValueError("--mix 는 reverse,trap,novel 세 수여야 합니다 (예: 0.5,0.3,0.2)")
    return ProblemMix(reverse=parts[0], trap=parts[1], novel=parts[2])


def parse_ids(text: str | None) -> set[str] | None:
    """`--ids a,b,c` 또는 `--ids @파일`(한 줄 하나) → id 집합. 없으면 None(= 전부)."""
    if not text:
        return None
    if text.startswith("@"):
        raw = Path(text[1:]).read_text(encoding="utf-8").split()
    else:
        raw = text.split(",")
    return {t.strip() for t in raw if t.strip()}


def add_subcommands(ev_sub: argparse._SubParsersAction) -> None:
    run = ev_sub.add_parser("run", help=RUN_HELP, description=RUN_HELP)
    run.add_argument("--suite", required=True, choices=list(SUITES))
    run.add_argument(
        "--seed", type=int, help="문제 묶음 seed (기본 오늘 날짜 숫자, --sealed 면 sealed_seed)"
    )
    run.add_argument(
        "--sealed",
        action="store_true",
        help="봉인 묶음(data/eval/sealed/<suite>.jsonl)으로 — 보고서용 최종 확인 1회만. "
        "경고 한 줄 출력",
    )
    run.add_argument(
        "--repeats", type=int, help="같은 문제 반복 횟수 (l1 기본 eval.yaml l1.repeats=3)"
    )
    run.add_argument(
        "--n", type=int, help="l1 문제 수 (기본 eval.yaml l1.n=120, 새 묶음을 만들 때만)"
    )
    run.add_argument("--label", default="", help="비교표 열 이름 (예: 가-main)")
    run.add_argument(
        "--out", help="결과 JSON 경로 (기본 eval/results/<날짜>-<suite>[-<label>].json)"
    )
    run.add_argument("--real", action="store_true", help="l0 를 운영 DB·e5·reranker 로 (로컬 명령)")
    run.add_argument(
        "--record",
        action="store_true",
        help="l0 캐시 미스를 평가 예산 LLM 으로 채워 녹화 (tests/eval/l0_cache)",
    )
    run.add_argument("--no-recommend", action="store_true", help="l1 에서 과제안 단계를 건너뛴다")
    run.add_argument(
        "--mix",
        help="l1 새 묶음의 종류 비율 reverse,trap,novel (예: 0.5,0.3,0.2 → n=40 이면 20/12/8). "
        "기존 묶음을 재사용할 때는 무시",
    )
    run.add_argument(
        "--ids",
        help="이 문제 id 들만 돌린다 — 쉼표 목록 또는 @파일(한 줄 하나). 짝 비교에서 갈린 문제만 "
        "3회 반복할 때(`compare --discordant-out`)",
    )
    run.add_argument("--golden", default="tests/golden", help="l2 골든셋 폴더")
    run.set_defaults(handler=cmd_run)

    cmp = ev_sub.add_parser("compare", help="결과 JSON 2개 이상 → 지표별 비교표 (한국어 Markdown)")
    cmp.add_argument("results", nargs="+", help="결과 JSON 경로 (첫 파일이 기준)")
    cmp.add_argument("--out", help="Markdown 저장 경로 (예: docs/eval-<날짜>-compare.md)")
    cmp.add_argument(
        "--discordant-out",
        help="기준과 두 번째 열의 결과가 갈린 문제 id 를 한 줄에 하나씩 저장 (→ run --ids @파일)",
    )
    cmp.set_defaults(handler=cmd_compare)

    usage = ev_sub.add_parser(
        "usage", help="실사용 기록 지표 (source=user·시험 줄 제외) → eval/results/<날짜>-usage.json"
    )
    usage.add_argument("--since", help="YYYY-MM-DD 부터")
    usage.add_argument("--include-test", action="store_true", help="시험 계정 줄도 센다")
    usage.add_argument("--out", help="JSON 저장 경로")
    usage.set_defaults(handler=cmd_usage)

    seal = ev_sub.add_parser(
        "seal",
        help="봉인 묶음 만들기 (sealed_seed, data/eval/sealed/<suite>.jsonl 600) — 이미 있으면 "
        "덮어쓰지 않음",
    )
    seal.add_argument("--suite", default="l1", choices=["l1"])
    seal.add_argument("--n", type=int, help="문제 수 (기본 eval.yaml l1.n)")
    seal.add_argument("--force", action="store_true", help="있어도 다시 만든다")
    seal.set_defaults(handler=cmd_seal)


def register(sub: argparse._SubParsersAction, eval_parser: argparse.ArgumentParser) -> None:
    """cli.build_parser 의 `eval` 파서에 run·compare·usage·seal 을 붙인다. 서브명령이 없으면 기존
    handler(cmd_eval)가 그대로 돈다."""
    ev_sub = eval_parser.add_subparsers(dest="eval_cmd", required=False)
    add_subcommands(ev_sub)


def build_parser() -> argparse.ArgumentParser:
    """독립 실행용 — `python -m rra.entrypoints.cli_eval run …` (통합 전 CI·launchd)."""
    parser = argparse.ArgumentParser(prog="rra eval", description="평가 체계 (ADR 0058)")
    add_subcommands(parser.add_subparsers(dest="eval_cmd", required=True))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (ValueError, OSError, RuntimeError, LookupError) as exc:
        _eprint(f"오류: {exc}")
        return EXIT_ERROR


# ── 핸들러 ───────────────────────────────────────────────
def _progress(msg: str) -> None:
    _eprint(f"  … {msg}")


def cmd_run(args: argparse.Namespace) -> int:
    from rra.composition import build_eval_stores, build_eval_suite, load_settings
    from rra.config_loader import eval_config
    from rra.entrypoints.views_eval import summary_line

    settings = load_settings()
    cfg = eval_config(settings)
    results, problems_store = build_eval_stores(settings)
    if args.suite == "l2":
        return _run_l2(args, settings, cfg, results)
    sealed = bool(args.sealed)
    if sealed and args.suite != "l1":
        _eprint("--sealed 는 l1 에서만 씁니다.")
        return EXIT_USAGE
    if sealed and args.seed is not None and args.seed != cfg.sealed_seed:
        _eprint("--sealed 는 seed 를 받지 않습니다 (eval.yaml sealed_seed 고정).")
        return EXIT_USAGE
    from rra.application.usecases.eval_problems import today_seed

    seed = cfg.sealed_seed if sealed else (args.seed if args.seed is not None else today_seed())
    repeats = (
        args.repeats if args.repeats is not None else (cfg.l1.repeats if args.suite == "l1" else 1)
    )
    parts = build_eval_suite(
        settings,
        suite=args.suite,
        seed=seed,
        repeats=repeats,
        label=args.label,
        sealed=sealed,
        real=bool(args.real),
        record=bool(args.record),
        with_recommend=False if args.no_recommend else None,
        progress=_progress,
    )

    async def run():
        try:
            if args.suite == "l0":
                problems = problems_store.load(Path(cfg.l0.problems))
            elif sealed:
                path = problems_store.sealed_path("l1")
                if not problems_store.exists(path):
                    raise FileNotFoundError(
                        "봉인 묶음이 없습니다 — 먼저 `rra eval seal --suite l1`"
                    )
                _eprint(SEALED_WARNING)
                problems = problems_store.load(path)
            else:
                path = problems_store.practice_path("l1", seed)
                if problems_store.exists(path):
                    problems = problems_store.load(path)
                    _eprint(f"연습용 묶음 재사용: {len(problems)}건 (seed {seed})")
                else:
                    n = args.n if args.n is not None else cfg.l1.n
                    mix = parse_mix(args.mix) if getattr(args, "mix", None) else cfg.l1.mix
                    problems = await parts["generator"].generate(seed=seed, n=n, mix=mix)
                    problems_store.save(path, problems)
                    _eprint(f"연습용 묶음 생성: {len(problems)}건 (seed {seed})")
            wanted = parse_ids(getattr(args, "ids", None))
            if wanted is not None:
                from rra.domain.rules.eval_metrics import record_id

                problems = [p for p in problems if p.id in wanted or record_id(p.id) in wanted]
                _eprint(f"--ids: {len(problems)}건만 돌린다")
            return await parts["suite"](problems)
        finally:
            await parts["aclose"]()

    result = asyncio.run(run())
    out = results.write(result, path=Path(args.out) if args.out else None)
    print(summary_line(result))
    for note in result.notes:
        print(f"  - {note}")
    print(f"저장: {out}")
    return EXIT_OK


def _run_l2(args: argparse.Namespace, settings: Any, cfg: Any, results: Any) -> int:
    """l2 = 기존 `rra eval --label …`(cli.cmd_eval, 골든셋 + 초안)을 그대로 돌린 뒤 EvalResult 로
    담고
    사람 확인 표본(run id)을 뽑는다."""
    from rra.application.usecases.eval_problems import today_seed
    from rra.application.usecases.evaluate_suite import l2_from_quality
    from rra.composition import build_version_info
    from rra.config_loader import eval_config_flags
    from rra.entrypoints import cli
    from rra.entrypoints.views_eval import summary_line

    seed = args.seed if args.seed is not None else today_seed()
    label = args.label or f"l2-{seed}"
    tmp = (
        Path(args.out).with_suffix(".quality.json")
        if args.out
        else results.base_dir / f".l2-{seed}.quality.json"
    )
    tmp.parent.mkdir(parents=True, exist_ok=True)
    ns = argparse.Namespace(
        label=label,
        report=None,
        pipeline="default",
        on=None,
        off=None,
        no_review=False,
        golden=args.golden,
        only=None,
        runs_dir=None,
        out=str(tmp),
        append=False,
        final_review=False,
        finalize=False,
        concurrent=1,
        local_check=None,
        department=None,
    )
    code = cli.cmd_eval(ns)
    if code != EXIT_OK:
        return code
    data = json.loads(tmp.read_text(encoding="utf-8"))
    result, sample = l2_from_quality(
        data,
        seed=seed,
        sample_ratio=cfg.l2.sample_ratio,
        label=args.label,
        commit=(build_version_info(settings).get("commit") or "")[:7],
        config_flags=eval_config_flags(settings),
    )
    out = results.write(result, path=Path(args.out) if args.out else None)
    print(summary_line(result))
    print(
        "사람 확인 표본 (run id, "
        + f"{int(cfg.l2.sample_ratio * 100)}%): "
        + (", ".join(sample) or "없음")
    )
    print(f"저장: {out} (세부: {tmp})")
    return EXIT_OK


def cmd_compare(args: argparse.Namespace) -> int:
    from rra.composition import build_eval_stores
    from rra.entrypoints.views_eval import compare_markdown

    if len(args.results) < 2:
        _eprint("비교할 결과 JSON 이 2개 이상 필요합니다.")
        return EXIT_USAGE
    store, _ = build_eval_stores()  # 어댑터는 조립 지점을 거친다(계층 계약)
    results = [store.read(Path(p)) for p in args.results]
    text = compare_markdown(results, date=time.strftime("%Y-%m-%d"))
    if getattr(args, "discordant_out", None):
        from rra.domain.rules.eval_compare import paired

        st = paired(results[0], results[1])
        ids = list(st.discordant_ids) if st is not None else []
        dpath = Path(args.discordant_out)
        dpath.parent.mkdir(parents=True, exist_ok=True)
        dpath.write_text("\n".join(ids) + ("\n" if ids else ""), encoding="utf-8")
        print(f"갈린 문제 id {len(ids)}건 저장: {dpath}")
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"저장: {out}")
    print(text, end="")
    return EXIT_OK


def cmd_usage(args: argparse.Namespace) -> int:
    from rra.application.usecases.eval_usage import usage_lines
    from rra.composition import EVAL_RESULTS_DIR, build_eval_usage, load_settings

    since = date.fromisoformat(args.since) if args.since else None
    report = build_eval_usage(load_settings())(since=since, include_test=bool(args.include_test))
    out = (
        Path(args.out)
        if args.out
        else Path(EVAL_RESULTS_DIR) / f"{date.today().isoformat()}-usage.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for line in usage_lines(report):
        print(line)
    print(f"저장: {out}")
    return EXIT_OK


def cmd_seal(args: argparse.Namespace) -> int:
    from rra.composition import build_eval_stores, build_eval_suite, load_settings
    from rra.config_loader import eval_config

    settings = load_settings()
    cfg = eval_config(settings)
    _, store = build_eval_stores(settings)
    path = store.sealed_path(args.suite)
    if store.exists(path) and not args.force:
        print(f"봉인 묶음이 이미 있습니다 (덮어쓰지 않음): {path}")
        return EXIT_OK
    parts = build_eval_suite(settings, suite="l1", seed=cfg.sealed_seed, with_recommend=False)

    async def run():
        try:
            n = args.n if args.n is not None else cfg.l1.n
            return await parts["generator"].generate(seed=cfg.sealed_seed, n=n, mix=cfg.l1.mix)
        finally:
            await parts["aclose"]()

    problems = asyncio.run(run())
    store.save(path, problems)
    kinds = {k: sum(1 for p in problems if p.kind == k) for k in ("reverse", "trap", "novel")}
    print(f"봉인 묶음 저장: {len(problems)}건 {kinds} → {path} (600). 개선 작업 중 열람 금지.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
