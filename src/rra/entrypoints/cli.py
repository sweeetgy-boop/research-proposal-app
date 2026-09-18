"""CLI 진입점. 유스케이스 호출과 출력만 담당한다 (로직 없음).

종료 코드: 0 정상 / 1 실행 오류 / 2 사용법 오류 / 3 차단 경보 있음
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import asdict
from pathlib import Path

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_BLOCKED = 3

SLOTS = ("current_state", "root_cause", "limitation", "goal", "constraints")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
DEFAULT_LLM_CHECK_PROMPT = "연결 확인입니다. 정확히 다음만 출력하십시오: []"


def _safe(text: str, limit: int = 120) -> str:
    """비신뢰 텍스트를 터미널에 찍기 전 제어문자 제거 + 절단 (ANSI 주입 방지)."""
    clean = _CONTROL.sub(" ", str(text)).strip()
    return clean if len(clean) <= limit else clean[:limit] + "…"


def _eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


# ── precheck ──────────────────────────────────────────────
def _read_slots(args: argparse.Namespace) -> dict[str, str]:
    if args.file:
        import yaml

        data = yaml.safe_load(Path(args.file).read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("입력 파일은 5슬롯 매핑이어야 합니다.")
        return {k: str(data.get(k, "")) for k in SLOTS}
    return {k: getattr(args, k) or "" for k in SLOTS}


def cmd_precheck(args: argparse.Namespace) -> int:
    from rra.composition import build_precheck, load_settings
    from rra.domain.models import ProposalRequest

    slots = _read_slots(args)
    missing = [k for k in SLOTS[:4] if not slots[k].strip()]
    if missing:
        _eprint(f"필수 슬롯이 비었습니다: {', '.join(missing)}")
        return EXIT_USAGE

    req = ProposalRequest(**slots)
    alerts = build_precheck(load_settings())(req)

    if args.json:
        print(json.dumps([a.model_dump() for a in alerts], ensure_ascii=False, indent=2))
    else:
        blocking = sum(1 for a in alerts if a.blocking)
        print(f"[중복 경보] {len(alerts)}건 (차단 {blocking}건)")
        for a in alerts:
            mark = "!" if a.blocking else " "
            print(f" {mark} {a.similarity:.2f}  {a.tier:<14} {a.doc_id:<20} {_safe(a.title)}")
        if not alerts:
            print("  유사한 기수행 과제가 없습니다.")
    return EXIT_BLOCKED if any(a.blocking for a in alerts) else EXIT_OK


# ── search ────────────────────────────────────────────────
def cmd_search(args: argparse.Namespace) -> int:
    from rra.composition import (
        build_embedding,
        build_precheck,
        build_repository,
        load_settings,
        read_config,
    )
    from rra.entrypoints.mcp.tools import RraTools, ToolLimits

    settings = load_settings()
    repo = build_repository(build_embedding(settings), settings)
    limits = ToolLimits.from_security_config(read_config("security.yaml", settings))
    tools = RraTools(build_precheck(settings, repo=repo), repo, limits)
    orgs = [o.strip() for o in args.orgs.split(",")] if args.orgs else None
    print(_CONTROL.sub(" ", tools.search(args.query, orgs=orgs, k=args.k)))
    return EXIT_OK


# ── llm-check ─────────────────────────────────────────────
def cmd_llm_check(args: argparse.Namespace) -> int:
    from rra.composition import build_llm, build_prompt_library, llm_config, load_settings

    settings = load_settings()
    cfg = llm_config(settings, args.stage)
    print(f"provider={cfg['provider']} base_url={cfg['base_url']} stage={args.stage}")

    async def run() -> str:
        llm = build_llm(settings, stage=args.stage)
        try:
            system = build_prompt_library(settings).system() if args.system else None
            return await llm.complete(args.prompt, system=system, json_mode=args.json_mode)
        finally:
            await llm.aclose()

    started = time.monotonic()
    output = asyncio.run(run())
    print(f"model={cfg['model']} {time.monotonic() - started:.1f}s")
    print(_safe(output, limit=2000))
    return EXIT_OK


# ── ingest ────────────────────────────────────────────────
def cmd_ingest(args: argparse.Namespace) -> int:
    from rra.composition import build_ingest, build_sources, load_settings

    settings = load_settings()
    names = [n.strip() for n in args.source.split(",") if n.strip()]

    async def run():
        sources = build_sources(names, settings)
        try:
            ingest = build_ingest(settings, sources=sources, limit=args.limit)
            return await ingest(args.query)
        finally:
            for source in sources:
                await source.aclose()

    report = asyncio.run(run())
    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    else:
        for name in names:
            if name in report.failed:
                print(f"[{_safe(name)}] 실패: {report.failed[name]}")
                continue
            print(
                f"[{_safe(name)}] 수집 {report.fetched.get(name, 0)}건, "
                f"정규화 {report.normalized.get(name, 0)}건, "
                f"건너뜀 {report.skipped.get(name, 0)}건"
            )
        print(f"저장 {report.stored}건 (중복 제거 {report.deduped}건), 청크 {report.chunks}개")
    return EXIT_ERROR if report.failed else EXIT_OK


# ── mcp ───────────────────────────────────────────────────
def cmd_mcp(args: argparse.Namespace) -> int:
    from rra.entrypoints.mcp.server import main as mcp_main

    return mcp_main(["--transport", args.transport])


def cmd_todo(args: argparse.Namespace) -> int:
    _eprint(f"[rra] {args.cmd}: 아직 구현 전입니다 (설계 문서 §8 참조).")
    return EXIT_USAGE


# ── 파서 ──────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser("rra", description="연구과제 제안서 작성 보조")
    sub = parser.add_subparsers(dest="cmd")

    pre = sub.add_parser("precheck", help="제안 5슬롯으로 기수행 과제 중복 사전 점검")
    for slot in SLOTS:
        pre.add_argument(f"--{slot.replace('_', '-')}", dest=slot, default="")
    pre.add_argument("--file", help="5슬롯이 담긴 yaml/json 파일")
    pre.add_argument("--json", action="store_true", help="JSON 으로 출력")
    pre.set_defaults(handler=cmd_precheck)

    search = sub.add_parser("search", help="수집 문서 하이브리드 검색")
    search.add_argument("query")
    search.add_argument("--orgs", help="쉼표로 구분 (예: korail,krri)")
    search.add_argument("-k", type=int, default=10)
    search.set_defaults(handler=cmd_search)

    check = sub.add_parser("llm-check", help="LLM 서버 왕복 1회 확인")
    check.add_argument("--stage", default="compose")
    check.add_argument("--prompt", default=DEFAULT_LLM_CHECK_PROMPT)
    check.add_argument("--system", action="store_true", help="실제 시스템 프롬프트를 함께 보냄")
    check.add_argument("--json-mode", action="store_true", dest="json_mode")
    check.set_defaults(handler=cmd_llm_check)

    mcp = sub.add_parser("mcp", help="MCP 서버 실행 (stdio)")
    mcp.add_argument("--transport", default="stdio", choices=["stdio"])
    mcp.set_defaults(handler=cmd_mcp)

    ingest = sub.add_parser("ingest", help="외부 소스에서 문서 수집 → DB 적재")
    ingest.add_argument("--source", default="openalex", help="쉼표로 구분 (현재: openalex)")
    ingest.add_argument("--query", default=None, help="없으면 sources.yaml 기본 질의로 증분 수집")
    ingest.add_argument("--limit", type=int, default=200, help="소스당 최대 건수")
    ingest.add_argument("--json", action="store_true", help="JSON 으로 출력")
    ingest.set_defaults(handler=cmd_ingest)

    todo = sub.add_parser("generate", help="Step 6 이후")
    todo.set_defaults(handler=cmd_todo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "handler", None):
        parser.print_help()
        return EXIT_USAGE
    try:
        return args.handler(args)
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        _eprint(f"오류: {exc}")
        return EXIT_ERROR


def _entrypoint() -> None:  # pyproject 의 console_scripts 용
    raise SystemExit(main())


if __name__ == "__main__":
    _entrypoint()
