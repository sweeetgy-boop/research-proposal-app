"""CLI 진입점. 유스케이스 호출과 출력만 담당한다 (로직 없음).

종료 코드: 0 정상 / 1 실행 오류·중단 / 2 사용법 오류 / 3 차단 경보 있음 / 4 초안 lint 실패
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
EXIT_INVALID = 4

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
    from rra.composition import (
        build_llm,
        build_prompt_library,
        check_served_model,
        llm_config,
        load_settings,
    )

    settings = load_settings()
    cfg = llm_config(settings, args.stage)
    print(f"provider={cfg['provider']} base_url={cfg['base_url']} stage={args.stage}")
    if cfg.get("served_model"):
        print(f"served_model={_safe(cfg['served_model'], 200)} (manifest 에 기록)")

    async def run() -> str:
        llm = build_llm(settings, stage=args.stage)
        try:
            if warning := await check_served_model(cfg, llm):
                _eprint(f"경고: {_safe(warning, 500)}")
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


# ── alio ──────────────────────────────────────────────────
def cmd_alio_catalog(args: argparse.Namespace) -> int:
    from rra.composition import build_alio_catalog, fetch_alio_catalog, load_settings

    settings = load_settings()
    if args.fetch:
        saved = asyncio.run(fetch_alio_catalog(settings))
        print(f"카탈로그 저장: {saved.name}")
    entries = asyncio.run(build_alio_catalog(settings).entries())
    counts: dict[str, int] = {}
    for e in entries:
        counts[e.institution_tag] = counts.get(e.institution_tag, 0) + 1
    summary = ", ".join(f"{k} {v}건" for k, v in sorted(counts.items())) or "없음"
    print(f"[알리오 카탈로그] 대상 기관 {len(entries)}건 ({summary})")
    return EXIT_OK


def cmd_alio_missing(args: argparse.Namespace) -> int:
    from rra.composition import build_list_missing, load_settings

    missing = asyncio.run(build_list_missing(load_settings())())
    if args.json:
        print(
            json.dumps([e.model_dump(mode="json") for e in missing], ensure_ascii=False, indent=2)
        )
        return EXIT_OK
    print(
        f"[미수집] {len(missing)}건 — 알리오에서 받아 inbox 에 <catalog_id>.<확장자> 로 저장하세요."
    )
    for e in missing:
        published = e.published.isoformat() if e.published else "-"
        cid = _safe(e.catalog_id, 64)
        print(f"  {cid:<20} {e.institution_tag:<7} {published:<10} {_safe(e.title)}")
    return EXIT_OK


def cmd_alio_status(args: argparse.Namespace) -> int:
    from rra.composition import alio_inbox_status, load_settings

    st = alio_inbox_status(load_settings())
    print(f"[알리오 inbox] 대기 {st['pending']} / 완료 {st['done']} / 격리 {st['quarantine']}")
    return EXIT_OK


# ── generate · runs ───────────────────────────────────────
_STATUS_EXIT = {"done": EXIT_OK, "invalid": EXIT_INVALID}


def _step_line(state, step) -> str:
    done, total = state.progress
    detail = (
        f" (문장 {step.sentences}, 폐기 {step.dropped})" if step.name.startswith("section:") else ""
    )
    return f"[{done}/{total}] {step.name} 완료{detail}"


def _draft_payload(view) -> dict:
    from rra.entrypoints.views import draft_payload

    return draft_payload(view)


def _print_draft(payload: dict) -> None:
    done, total = payload["progress"]
    print(f"[run {payload['run_id']}] {payload['status']} ({done}/{total})")
    for sec in payload["sections"]:
        print(f"\n## {sec['key']}")
        for sent in sec["sentences"]:
            ev = ", ".join(sent["evidence"]) if sent["evidence"] else "제안자 입력"
            print(f"- {_safe(sent['text'], 500)}  [{_safe(ev, 200)}]")
    if payload["citations"]:
        print("\n## 근거 문서")
        for c in payload["citations"]:
            print(f"  {_safe(c['id'], 80):<24} {_safe(c['title'] or '-')}")
    for pr in payload["problems"]:
        print(f"! {pr['section']}: {pr['code']} — {_safe(pr['message'])}")


def cmd_generate(args: argparse.Namespace) -> int:
    from rra.composition import LOCAL_USER, build_run_manager, load_settings
    from rra.domain.models import ProposalRequest

    if args.resume:
        req = None
    else:
        slots = _read_slots(args)
        missing = [k for k in SLOTS[:4] if not slots[k].strip()]
        if missing:
            _eprint(f"필수 슬롯이 비었습니다: {', '.join(missing)}")
            return EXIT_USAGE
        req = ProposalRequest(**slots)

    started: dict[str, str] = {}

    def on_step(state, step) -> None:
        _eprint(_step_line(state, step))

    async def run():
        mgr = build_run_manager(load_settings())
        try:
            if req is None:
                state = await mgr.resume(LOCAL_USER, args.resume, on_step=on_step)
            else:
                state = await mgr.submit(LOCAL_USER, req, on_step=on_step)
            started["run_id"] = state.run_id
            _eprint(f"[run {state.run_id}] 시작 — 다른 생성이 진행 중이면 끝날 때까지 기다립니다.")
            final = await mgr.wait(LOCAL_USER, state.run_id)
            return final, await mgr.get_draft(LOCAL_USER, final.run_id)
        finally:
            await mgr.generate.llm.aclose()

    try:
        final, view = asyncio.run(run())
    except KeyboardInterrupt:
        rid = started.get("run_id", "<run_id>")
        _eprint(f"\n중단했습니다. 완료된 섹션은 저장돼 있습니다: rra generate --resume {rid}")
        return EXIT_ERROR
    payload = _draft_payload(view)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_draft(payload)
    if final.status == "interrupted":  # stderr 라 --json 출력과 섞이지 않는다
        failed = next((s for s in final.steps if s.status == "error"), None)
        where = f"{failed.name} ({failed.error})" if failed else "알 수 없음"
        _eprint(f"중단: {where} — rra generate --resume {final.run_id}")
    return _STATUS_EXIT.get(final.status, EXIT_ERROR)


def cmd_runs_list(args: argparse.Namespace) -> int:
    from rra.composition import LOCAL_USER, build_run_manager, load_settings

    runs = build_run_manager(load_settings()).list_runs(LOCAL_USER, limit=args.limit)
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "run_id": r.run_id,
                        "status": r.status,
                        "progress": list(r.progress),
                        "created_at": r.created_at,
                        "updated_at": r.updated_at,
                    }
                    for r in runs
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return EXIT_OK
    if not runs:
        print("생성 기록이 없습니다.")
    for r in runs:
        done, total = r.progress
        print(f"{r.run_id}  {r.status:<11} {done:>2}/{total:<2}  {r.updated_at}")
    return EXIT_OK


def cmd_runs_show(args: argparse.Namespace) -> int:
    from rra.composition import LOCAL_USER, build_run_manager, load_settings

    async def run():
        mgr = build_run_manager(load_settings())
        try:
            return await mgr.get_draft(LOCAL_USER, args.run_id)
        finally:
            await mgr.generate.llm.aclose()

    payload = _draft_payload(asyncio.run(run()))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_draft(payload)
    return EXIT_OK


# ── mcp ───────────────────────────────────────────────────
def cmd_mcp(args: argparse.Namespace) -> int:
    from rra.entrypoints.mcp.server import main as mcp_main

    argv = ["--transport", args.transport]
    if args.enable_generate:
        argv.append("--enable-generate")
    return mcp_main(argv)


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
    mcp.add_argument(
        "--enable-generate", action="store_true", help="쓰기 도구(생성·초안 조회)도 등록"
    )
    mcp.set_defaults(handler=cmd_mcp)

    ingest = sub.add_parser("ingest", help="외부 소스에서 문서 수집 → DB 적재")
    ingest.add_argument("--source", default="openalex", help="쉼표로 구분 (openalex, alio)")
    ingest.add_argument("--query", default=None, help="없으면 sources.yaml 기본 질의로 증분 수집")
    ingest.add_argument("--limit", type=int, default=200, help="소스당 최대 건수")
    ingest.add_argument("--json", action="store_true", help="JSON 으로 출력")
    ingest.set_defaults(handler=cmd_ingest)

    alio = sub.add_parser("alio", help="알리오 공시 보고서 카탈로그·filedrop 관리")
    alio_sub = alio.add_subparsers(dest="alio_cmd", required=True)
    cat = alio_sub.add_parser("catalog", help="카탈로그 CSV 요약 (--fetch: 설정 URL 에서 받기)")
    cat.add_argument("--fetch", action="store_true")
    cat.set_defaults(handler=cmd_alio_catalog)
    miss = alio_sub.add_parser("missing", help="카탈로그 중 아직 적재되지 않은 보고서")
    miss.add_argument("--json", action="store_true")
    miss.set_defaults(handler=cmd_alio_missing)
    status = alio_sub.add_parser("status", help="inbox 대기·완료·격리 파일 수")
    status.set_defaults(handler=cmd_alio_status)

    gen = sub.add_parser("generate", help="제안서 초안 생성 (섹션별 저장, 중단 후 --resume)")
    for slot in SLOTS:
        gen.add_argument(f"--{slot.replace('_', '-')}", dest=slot, default="")
    gen.add_argument("--file", help="5슬롯이 담긴 yaml/json 파일")
    gen.add_argument("--resume", metavar="RUN_ID", help="중단된 run 을 이어서 생성")
    gen.add_argument("--json", action="store_true", help="JSON 으로 출력")
    gen.set_defaults(handler=cmd_generate)

    runs = sub.add_parser("runs", help="생성 기록 조회")
    runs_sub = runs.add_subparsers(dest="runs_cmd", required=True)
    rl = runs_sub.add_parser("list", help="최근 생성 기록")
    rl.add_argument("--limit", type=int, default=20)
    rl.add_argument("--json", action="store_true")
    rl.set_defaults(handler=cmd_runs_list)
    rs = runs_sub.add_parser("show", help="초안(문장별 근거 포함)·진행 상태")
    rs.add_argument("run_id")
    rs.add_argument("--json", action="store_true")
    rs.set_defaults(handler=cmd_runs_show)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "handler", None):
        parser.print_help()
        return EXIT_USAGE
    try:
        return args.handler(args)
    except (ValueError, OSError, RuntimeError, LookupError) as exc:
        _eprint(f"오류: {exc}")
        return EXIT_ERROR


def _entrypoint() -> None:  # pyproject 의 console_scripts 용
    raise SystemExit(main())


if __name__ == "__main__":
    _entrypoint()
