"""CLI 진입점. 유스케이스 호출과 출력만 담당한다 (로직 없음).

종료 코드: 0 정상 / 1 실행 오류·중단 / 2 사용법 오류 / 3 차단 경보 있음 / 4 초안 lint 실패
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import asdict
from pathlib import Path

from pydantic import ValidationError

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_BLOCKED = 3
EXIT_INVALID = 4

SLOTS = ("current_state", "root_cause", "limitation", "goal", "constraints")
# generate 전용 추가 입력 (모두 선택). 제안자 성명·연락처는 받지 않는다 — 렌더 시점 입력.
EXTRA_SLOTS = (
    "title_hint",
    "policy_basis",
    "beneficiaries",
    "remarks",
    "department",
    "differentiation",
)
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
    from rra.domain.models.request import validation_message

    try:
        req = ProposalRequest(**_read_slots(args))  # 필수 슬롯·길이 규칙은 도메인이 검사한다
    except ValidationError as exc:
        _eprint(validation_message(exc))
        return EXIT_USAGE
    alerts = asyncio.run(build_precheck(load_settings())(req))

    if args.json:
        print(json.dumps([a.model_dump() for a in alerts], ensure_ascii=False, indent=2))
    else:
        blocking = sum(1 for a in alerts if a.blocking)
        print(f"[중복 경보] {len(alerts)}건 (차단 {blocking}건)")
        for a in alerts:
            mark = "!" if a.blocking else " "
            basis = "요약" if a.basis == "summary" else "  "  # 공개 요약만으로 판정
            # 키워드는 제안자 입력에서 온 토큰(문서에도 등장한 것)이라 비신뢰 텍스트가 아니다
            words = f"  [키워드: {', '.join(a.keywords)}]" if a.keywords else "  [키워드 없음]"
            status = f"  [상태: {_STATUS_TEXT.get(a.status, a.status)}]" if a.status else ""
            print(
                f" {mark} {a.similarity:.2f}  {a.tier:<14} {basis} {a.doc_id:<20} {_safe(a.title)}"
                f"{words}{status}"
            )
        if not alerts:
            print("  유사한 기수행 과제가 없습니다.")
    return EXIT_BLOCKED if any(a.blocking for a in alerts) else EXIT_OK


def cmd_differentiate(args: argparse.Namespace) -> int:
    """기능 2 — precheck 뒤 차단·근접 유사과제별 활용·차별화 방향 (Gemini, 키 없으면 로컬)."""
    from rra.composition import build_differentiator, build_precheck, load_settings
    from rra.domain.models import ProposalRequest
    from rra.domain.models.request import validation_message
    from rra.entrypoints.views import differentiation_payload

    try:
        req = ProposalRequest(**_read_slots(args))
    except ValidationError as exc:
        _eprint(validation_message(exc))
        return EXIT_USAGE
    settings = load_settings()

    async def run():
        precheck = build_precheck(settings)
        differentiate = build_differentiator(settings, repo=getattr(precheck, "repo", None))
        try:
            alerts = await precheck(req)
            return alerts, await differentiate(req, alerts)
        finally:
            await differentiate.llm.aclose()

    alerts, proposal = asyncio.run(run())
    payload = differentiation_payload(proposal, clean=lambda t: _safe(t, 600))
    if args.json:
        print(
            json.dumps(
                {"alerts": [a.model_dump() for a in alerts], **payload},
                ensure_ascii=False,
                indent=2,
            )
        )
        return EXIT_OK
    where = (
        "로컬 모델(대체)" if proposal.fallback_local else f"{proposal.provider}/{proposal.model}"
    )
    print(
        f"[차별화 제안] 알림 {len(alerts)}건 → 제안 {len(proposal.items)}건, "
        f"폐기 {len(proposal.discarded)}건 ({where})"
    )
    if proposal.skipped_reason:
        print(f"  건너뜀: {proposal.skipped_reason}")
    for item in payload["items"]:
        status = (
            f" [상태: {_STATUS_TEXT.get(item['status'], item['status'])}]" if item["status"] else ""
        )
        print(f"\n■ {item['doc_id']} ({item['tier']}){status} {item['title']}")
        print(f"  겹치는 점: {item['overlap_summary']}")
        if item["build_on"]:
            print(f"  이어받을 점: {item['build_on']}")
        for n, d in enumerate(item["differentiation"], 1):
            print(f"  방향 {n}: {d}")
    for d in payload["discarded"]:
        print(f"  (폐기) {_safe(d.get('doc_id', ''), 64)}: {_safe(d.get('reason', ''), 40)}")
    t = payload["transfer"]
    print(
        f"\n전송: public {len(t['public_doc_ids'])}건, internal {len(t['internal_doc_ids'])}건, "
        f"제외 {len(t['excluded_doc_ids'])}건 — 고른 방향은 generate --differentiation 으로 넣는다"
    )
    return EXIT_OK


_STATUS_TEXT = {
    "completed": "완료",
    "ongoing": "진행중",
    "stopped": "중단",
    "rejected": "미채택 — 보완 재제안 검토",
    "proposed": "제안·검토 중",
}


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
    print(_CONTROL.sub(" ", asyncio.run(tools.search(args.query, orgs=orgs, k=args.k))))
    return EXIT_OK


# ── llm-bench ─────────────────────────────────────────────
def cmd_llm_bench(args: argparse.Namespace) -> int:
    """골든셋으로 로컬 모델을 벤치해 JSON 으로 남기거나(--label), JSON 들을 표로 합친다."""
    from rra.entrypoints.views import bench_markdown

    if args.report:
        results = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.report]
        out = Path(args.out or f"docs/llm-bench-{time.strftime('%Y-%m-%d')}.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            bench_markdown(results, date=time.strftime("%Y-%m-%d"), baseline=args.baseline),
            encoding="utf-8",
        )
        print(f"저장: {out} (모델 {len(results)}개)")
        return EXIT_OK
    if not args.label:
        _eprint("--label <이름> (벤치 실행) 또는 --report <json…> (표 작성) 중 하나가 필요합니다.")
        return EXIT_USAGE
    import yaml

    from rra.composition import build_bench, load_settings
    from rra.domain.models import ProposalRequest

    golden = sorted(Path(args.golden).glob("*.yaml"))
    if not golden:
        _eprint(f"골든셋이 없습니다: {args.golden}")
        return EXIT_USAGE
    ideas = [
        (p.stem, ProposalRequest(**yaml.safe_load(p.read_text(encoding="utf-8")))) for p in golden
    ]

    async def run():
        bench = build_bench(load_settings(), label=args.label)
        try:
            return await bench(ideas)
        finally:
            await bench.generate.llm.aclose()

    result = asyncio.run(run())
    out = Path(args.out or f"data/bench/{args.label}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    totals = result.totals()
    print(
        f"[{result.label}] 모델 {result.model} 프로필 {result.profile} — "
        f"JSON {result.json_success_rate * 100:.1f}% ({result.parse_ok}/{result.sections_llm}), "
        f"폴백 {result.fallbacks}, 폐기 {totals['dropped']}, 수치 {totals['unsupported_numbers']}, "
        f"외국문자 {totals['foreign_script']}, 정책명 {totals['ungrounded']}, "
        f"전체 {result.total_seconds:.0f}s, 섹션 평균 {result.avg_section_seconds:.1f}s, "
        f"최대 프롬프트 토큰 {result.max_prompt_tokens}, RSS {result.max_rss_mb or '-'}MB"
    )
    print(f"저장: {out}")
    return EXIT_OK


# ── DB 유지보수 ───────────────────────────────────────────
def cmd_reindex(args: argparse.Namespace) -> int:
    """모든 청크를 설정된 임베딩 모델로 다시 색인 (모델·차원이 바뀌었을 때)."""
    from rra.composition import build_db_maintenance, load_settings

    reindex, _ = build_db_maintenance(load_settings())
    stats = asyncio.run(reindex())
    model = stats["model"] or "-"
    print(f"재색인 완료: 청크 {stats['chunks']:,}개, 차원 {stats['dim']}, 모델 {model}")
    return EXIT_OK


def cmd_db_backup(args: argparse.Namespace) -> int:
    """VACUUM INTO 사본. --out 이 폴더면 rra-YYYYMMDD-HHMMSS.sqlite 로 저장, 보관 --keep 벌."""
    from rra.composition import build_db_maintenance, load_settings

    _, backup = build_db_maintenance(load_settings())
    report = asyncio.run(backup(args.out, keep=args.keep))
    print(f"백업: {report.path} (보관 {len(report.kept)}벌, 삭제 {len(report.removed)}벌)")
    return EXIT_OK


# ── llm-check ─────────────────────────────────────────────
def cmd_llm_check(args: argparse.Namespace) -> int:
    from rra.composition import (
        LLMUnavailable,
        build_llm,
        build_prompt_library,
        build_served_model_check,
        llm_config,
        llm_key_present,
        load_settings,
    )

    settings = load_settings()
    cfg = llm_config(settings, args.stage, provider=args.provider)
    print(f"provider={cfg['provider']} base_url={cfg['base_url']} stage={args.stage}")
    if cfg.get("served_model"):
        print(f"served_model={_safe(cfg['served_model'], 200)} (manifest 에 기록)")
    if cfg.get("api_key_field"):  # 키 유무만 (값 미표시, 보안 D)
        present = "있음" if llm_key_present(settings, cfg) else "없음"
        print(f"api_key=RRA_{cfg['api_key_field'].upper()} {present}")
    if cfg.get("reasoning_effort"):
        print(f"reasoning_effort={cfg['reasoning_effort']} json_mode={cfg['json_mode']}")

    async def run() -> str:
        llm = build_llm(settings, stage=args.stage, provider=args.provider)
        try:
            check = build_served_model_check(
                settings, llm, stage=args.stage, provider=args.provider
            )
            if warning := await check:
                _eprint(f"경고: {_safe(warning, 500)}")
            system = build_prompt_library(settings).system() if args.system else None
            return await llm.complete(args.prompt, system=system, json_mode=args.json_mode)
        finally:
            await llm.aclose()

    started = time.monotonic()
    try:
        output = asyncio.run(run())
    except LLMUnavailable as exc:
        _eprint(f"LLM 사용 불가: {exc}")
        return EXIT_USAGE
    print(f"model={cfg['model']} {time.monotonic() - started:.1f}s")
    print(_safe(output, limit=2000))
    return EXIT_OK


# ── ingest ────────────────────────────────────────────────
def cmd_ingest(args: argparse.Namespace) -> int:
    from rra.composition import build_ingest, build_sources, load_settings

    settings = load_settings()
    names = [n.strip() for n in args.source.split(",") if n.strip()]
    skipped: list[tuple[str, str]] = []

    async def run():
        if getattr(args, "skip_unavailable", False):
            from rra.composition import build_available_sources

            sources, missing = build_available_sources(names, settings)
            skipped.extend(missing)
        else:
            sources = build_sources(names, settings)
        try:
            ingest = build_ingest(settings, sources=sources, limit=args.limit)
            return await ingest(args.query)
        finally:
            for source in sources:
                await source.aclose()

    report = asyncio.run(run())
    for name, reason in skipped:  # 키 없는 소스 — 이름과 변수 이름만 (값 없음)
        _eprint(f"[{_safe(name)}] 건너뜀: {_safe(reason, 160)}")
    names = [n for n in names if n not in {name for name, _ in skipped}]
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
        kept = f", 원문 보존 {report.kept_existing}건" if report.kept_existing else ""
        print(
            f"저장 {report.stored}건 (중복 제거 {report.deduped}건{kept}), 청크 {report.chunks}개"
        )
        for w in report.warnings:
            _eprint(_warning_line(w))
    return EXIT_ERROR if report.failed else EXIT_OK


_WARNING_TEXT = {
    "unlisted_department": (
        "own 부서 목록(sources.yaml own_unit)에 없는 부서: {detail} ({doc_id})"
        " — 철도연구원 소속이면 목록에 추가하세요."
    ),
    "assumed_org": (
        "카탈로그 매칭 없이 기본 기관({detail})으로 태깅: {doc_id}"
        " — 파일명을 <catalog_id>.txt 로 바꾸면 카탈로그 기관코드로 정해집니다."
    ),
}


def _warning_line(w) -> str:
    template = _WARNING_TEXT.get(w.code, "{code}: {detail} ({doc_id})")
    text = template.format(
        code=_safe(w.code, 40), detail=_safe(w.detail, 40), doc_id=_safe(w.doc_id, 64)
    )
    return f"[경고] {text}"


# ── alio ──────────────────────────────────────────────────
def cmd_alio_catalog(args: argparse.Namespace) -> int:
    from rra.composition import build_alio_catalog, build_alio_catalog_fetcher, load_settings

    settings = load_settings()
    if args.fetch:
        saved = asyncio.run(build_alio_catalog_fetcher(settings).fetch())
        print(f"카탈로그 저장: {saved.name}")
    entries = asyncio.run(build_alio_catalog(settings).entries())
    counts: dict[str, int] = {}
    for e in entries:
        counts[e.institution_tag] = counts.get(e.institution_tag, 0) + 1
    summary = ", ".join(f"{k} {v}건" for k, v in sorted(counts.items())) or "없음"
    print(f"[알리오 카탈로그] 대상 기관 {len(entries)}건 ({summary})")
    return EXIT_OK


def cmd_alio_missing(args: argparse.Namespace) -> int:
    from datetime import date

    from rra.composition import build_list_missing, load_settings

    use = build_list_missing(load_settings())

    async def run():
        return await use(), await use.upgradable(date.today())

    missing, upgradable = asyncio.run(run())
    if args.json:
        rows = upgradable if args.upgradable else missing
        print(json.dumps([e.model_dump(mode="json") for e in rows], ensure_ascii=False, indent=2))
        return EXIT_OK
    print(
        f"[미수집] {len(missing)}건 — 알리오에서 받아 inbox 에 <catalog_id>.<확장자> 로 저장하세요."
        " 원문 비공개면 상세 페이지 요약을 alio_summary inbox 에 <catalog_id>.txt 로."
    )
    _print_entries(missing)
    if upgradable:
        print(
            f"[원문 확보 가능] {len(upgradable)}건 — 요약만 적재됐는데 원문이 공개됐습니다"
            " (공개예정일 경과). 받아서 inbox 에 넣으면 원문으로 대체됩니다."
        )
        _print_entries(upgradable)
    return EXIT_OK


def _print_entries(entries) -> None:
    for e in entries:
        published = e.published.isoformat() if e.published else "-"
        cid = _safe(e.catalog_id, 64)
        print(f"  {cid:<20} {e.institution_tag:<7} {published:<10} {_safe(e.title)}")


def cmd_alio_status(args: argparse.Namespace) -> int:
    from rra.composition import build_sources, load_settings

    labels = {"alio": "알리오 inbox", "alio_summary": "알리오 요약 inbox"}
    for src in build_sources(list(labels), load_settings()):
        st = src.inbox_status()  # InboxSource
        counts = f"대기 {st['pending']} / 완료 {st['done']} / 격리 {st['quarantine']}"
        print(f"[{labels[src.source]}] {counts}")
    return EXIT_OK


# ── generate · runs ───────────────────────────────────────
_STATUS_EXIT = {"done": EXIT_OK, "invalid": EXIT_INVALID}


def _step_line(state, step) -> str:
    done, total = state.progress
    detail = ""
    if step.name.startswith("section:"):
        if step.parse == "skipped":
            detail = " (입력·목록이 비어 LLM 생략 — 빈칸)"
        elif step.parse == "app":
            detail = f" (앱 확정 문장 {step.sentences})"
        else:
            detail = f" (문장 {step.sentences}, 폐기 {step.dropped}, 응답 {step.raw_chars}자"
            if step.parse == "ok":
                detail += ")"
            elif step.parse == "choices_only":
                detail += ", 선택지만 수용 — 문장 스키마 오류)"
            else:
                detail += f", 파싱 실패: {step.parse})"
    return f"[{done}/{total}] {step.name} 완료{detail}"


def _draft_payload(view) -> dict:
    from rra.entrypoints.views import draft_payload

    return draft_payload(view)


def _print_draft(payload: dict) -> None:
    done, total = payload["progress"]
    print(f"[run {payload['run_id']}] {payload['status']} ({done}/{total})")
    if payload["legacy"]:
        print("  (이전 양식으로 만든 run — 조회만 가능. rra generate --reuse-input 으로 새로 생성)")
    for sec in payload["sections"]:
        print(f"\n## {sec['key']}")
        choices = sec.get("choices")
        if choices is not None:
            proposed = ", ".join(c["id"] for c in choices["proposed"]) or "없음"
            confirmed = choices["confirmed"]
            shown = ", ".join(c["id"] for c in confirmed) if confirmed is not None else "미확정"
            print(f"  선택 — 제안: {_safe(proposed)} / 확정: {_safe(shown)}")
        for sent in sec["sentences"]:
            if sent["source"] == "app":
                ev = "앱 판정"
            else:
                ev = ", ".join(sent["evidence"]) if sent["evidence"] else "제안자 입력"
            print(f"- {_safe(sent['text'], 500)}  [{_safe(ev, 200)}]")
    if payload["citations"]:
        print("\n## 근거 문서")
        for c in payload["citations"]:
            print(f"  {_safe(c['id'], 80):<24} {_safe(c['title'] or '-')}")
    for pr in payload["problems"]:
        mark = "!" if pr["severity"] == "error" else "~"
        print(f"{mark} {pr['section']}: {pr['code']} — {_safe(pr['message'])}")


def _read_request_fields(args: argparse.Namespace) -> dict:
    """generate 입력. --file 이 있으면 파일만, 없으면 플래그.

    budget 은 {account, amount_thousand_krw} 매핑.
    """
    keys = SLOTS + EXTRA_SLOTS
    if args.file:
        import yaml

        data = yaml.safe_load(Path(args.file).read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("입력 파일은 매핑이어야 합니다.")
        fields: dict = {k: str(data.get(k) or "") for k in keys}
        budget = data.get("budget")
        if budget is not None and not isinstance(budget, dict):
            raise ValueError("budget 은 {account, amount_thousand_krw} 매핑이어야 합니다.")
        fields["budget"] = budget or None
        return fields
    fields = {k: getattr(args, k) or "" for k in keys}
    if args.budget_account or args.budget_amount is not None:
        fields["budget"] = {
            "account": args.budget_account or "",
            "amount_thousand_krw": args.budget_amount,
        }
    return fields


def cmd_generate(args: argparse.Namespace) -> int:
    from rra.composition import LOCAL_USER, build_run_manager, load_settings
    from rra.domain.models import ProposalRequest
    from rra.domain.models.request import validation_message

    req = None
    if not args.resume and not args.reuse_input:
        try:
            req = ProposalRequest(**_read_request_fields(args))
        except ValidationError as exc:
            _eprint(validation_message(exc))
            return EXIT_USAGE

    started: dict[str, str] = {}

    def on_step(state, step) -> None:
        _eprint(_step_line(state, step))

    async def run():
        mgr = build_run_manager(load_settings())
        try:
            if args.resume:
                state = await mgr.resume(LOCAL_USER, args.resume, on_step=on_step)
            else:
                request = req or await mgr.load_request(LOCAL_USER, args.reuse_input)
                state = await mgr.submit(LOCAL_USER, request, on_step=on_step)
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


def _csv(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def cmd_runs_confirm(args: argparse.Namespace) -> int:
    from rra.application.services import ConfirmRejected
    from rra.composition import LOCAL_USER, build_run_manager, load_settings

    choices: dict[str, list[str]] = {}
    if args.task_type:
        choices["task_type"] = [args.task_type]
    if args.utilization:
        choices["utilization"] = _csv(args.utilization)
    if args.strategy:
        choices["strategy_alignment"] = _csv(args.strategy)
    if not choices:
        _eprint("확정할 값이 없습니다 (--task-type / --utilization / --strategy).")
        return EXIT_USAGE

    async def run():
        mgr = build_run_manager(load_settings())
        try:
            return await mgr.confirm(LOCAL_USER, args.run_id, choices)
        finally:
            await mgr.generate.llm.aclose()

    try:
        confirmation = asyncio.run(run())
    except ConfirmRejected as exc:
        _eprint(f"확정 거부: {exc}")
        return EXIT_USAGE
    if args.json:
        print(json.dumps(confirmation.choices, ensure_ascii=False, indent=2))
    else:
        for key, values in confirmation.choices.items():
            print(f"{key}: {', '.join(values)}")
    return EXIT_OK


def cmd_runs_purge(args: argparse.Namespace) -> int:
    """보존 기간(security.yaml retention_days) 지난 run 폴더 삭제. --dry-run 없으면 실제 삭제."""
    from rra.composition import build_purge_runs, load_settings

    report = build_purge_runs(load_settings())(dry_run=args.dry_run)
    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
        return EXIT_OK
    verb = "삭제 대상" if args.dry_run else "삭제"
    print(
        f"[runs purge] 보존 {report.retention_days}일, 기준 {report.cutoff} — "
        f"{verb} {len(report.expired)}건"
        + (f", 실행 중이라 건너뜀 {len(report.skipped_active)}건" if report.skipped_active else "")
    )
    for row in report.expired:
        mark = "-" if args.dry_run else "x"
        print(f" {mark} {row.user}/{row.run_id}  {row.status:<11} {row.updated_at}")
    for row in report.skipped_active:
        print(f" ! {row.user}/{row.run_id}  {row.status:<11} {row.updated_at} (건너뜀)")
    return EXIT_OK


def _proposer_from_args(args: argparse.Namespace):
    from rra.domain.models import ProposerInfo
    from rra.domain.models.proposer import Person

    return ProposerInfo(
        proposed_on=args.proposed_on or "",
        department=getattr(args, "department", None) or "",
        proposer=Person(
            name=args.proposer_name or "",
            rank=args.proposer_rank or "",
            phone=args.proposer_phone or "",
        ),
        head=Person(
            name=args.head_name or "", rank=args.head_rank or "", phone=args.head_phone or ""
        ),
    )


def _write_owner_only(out: Path, data: bytes) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def cmd_runs_finalize(args: argparse.Namespace) -> int:
    """최종 마무리: 선택형 확정(인자 없으면 제안값) + 제안자 정보 + 렌더 전 점검 → finalized → HWPX.

    제안자 정보·제안부서·제안일자는 플래그로만 받고 run 폴더·로그에 남기지 않는다.
    """
    from rra.application.ports.renderer import RenderRejected
    from rra.application.services import ConfirmRejected, RenderUnavailable
    from rra.application.services.run_manager import FinalizeRejected
    from rra.composition import LOCAL_USER, build_run_manager, load_settings
    from rra.entrypoints.views import render_check_lines, render_check_payload

    proposer = _proposer_from_args(args)
    choices: dict[str, list[str]] = {}
    if args.task_type:
        choices["task_type"] = [args.task_type]
    if args.utilization:
        choices["utilization"] = _csv(args.utilization)
    if args.strategy:
        choices["strategy_alignment"] = _csv(args.strategy)

    async def run():
        mgr = build_run_manager(load_settings())
        try:
            result = await mgr.finalize(
                LOCAL_USER, args.run_id, choices=choices or None, proposer=proposer
            )
            payload = render_check_payload(result.check, titles=mgr.generate.rules.titles)
            return result, render_check_lines(payload)
        finally:
            await mgr.generate.llm.aclose()

    try:
        result, lines = asyncio.run(run())
    except (RenderRejected, RenderUnavailable, FinalizeRejected, ConfirmRejected) as exc:
        _eprint(f"마무리 거부: {exc}")
        return EXIT_USAGE
    for line in lines:  # 렌더 전 점검 — 알림이 있어도 저장은 한다
        print(line)
    out = Path(args.out)
    _write_owner_only(out, result.data)
    confirmed = ", ".join(f"{k}={'/'.join(v)}" for k, v in result.confirmation.choices.items())
    print(f"상태: finalized (v{result.version}) 확정: {confirmed}")
    print(f"저장: {out} ({len(result.data):,} bytes)")
    return EXIT_OK


def cmd_runs_review(args: argparse.Namespace) -> int:
    """검토(n차) 시작. 검토 LLM 이 없으면 건너뛰고 review_skipped 기록. --wait 는 끝까지 대기."""
    from rra.application.ports import RunBusy
    from rra.application.services import QueueFull
    from rra.composition import LOCAL_USER, build_run_manager, load_settings
    from rra.domain.rules.review_flow import InvalidTransition
    from rra.entrypoints.views import review_payload

    async def run():
        mgr = build_run_manager(load_settings())
        try:
            state = await mgr.review(LOCAL_USER, args.run_id)
            if args.wait and state.status == "reviewing":
                state = await mgr.wait(LOCAL_USER, args.run_id)
            review = await mgr.get_review(LOCAL_USER, args.run_id)
            return state, review
        finally:
            await mgr.generate.llm.aclose()

    try:
        state, review = asyncio.run(run())
    except (QueueFull, RunBusy, InvalidTransition) as exc:
        _eprint(f"검토 거부: {exc}")
        return EXIT_USAGE
    if args.json:
        print(
            json.dumps(
                review_payload(review) if review else {"status": state.status},
                ensure_ascii=False,
                indent=2,
            )
        )
        return EXIT_OK
    if state.review_skipped and state.review_rounds == 0:
        print(f"[run {state.run_id}] 검토 LLM 없음 — 건너뜀 기록(review_skipped). 마무리 가능.")
        return EXIT_OK
    print(f"[run {state.run_id}] 상태 {state.status}, 검토 {state.review_rounds}차 완료")
    if review and review.status == "done":
        usable = sum(1 for c in review.comments if c.usable)
        discarded = sum(1 for c in review.comments if c.status == "discarded")
        t = review.transfer
        print(
            f" {review.round}차: 의견 {len(review.comments)}건 (수정안 사용 가능 {usable}, "
            f"폐기 {discarded}), 보낸 문장 {t.sentences_sent}, 검토 제외 {t.sentences_excluded}"
        )
        for s in review.scores:
            flag = " ← 보완 필요" if s.weak else ""
            print(f"  [채점] {s.criterion} {s.score}/5 — {_safe(s.reason, 100)}{flag}")
        for c in review.comments:
            where = f"s:{c.section}:{c.sentence}" if c.sentence is not None else c.section
            mark = "✔" if c.usable else ("✘" if c.status == "discarded" else "·")
            print(f"  {mark} {c.id} [{c.issue_type}] {where}: {_safe(c.comment, 120)}")
    return EXIT_OK


def cmd_runs_edit(args: argparse.Namespace) -> int:
    """편집 반영 (--from <json>: {sentences:[…], sections:[…], note}) → 새 버전."""
    from pydantic import ValidationError

    from rra.application.services.run_manager import EditRejected
    from rra.composition import LOCAL_USER, build_run_manager, load_settings
    from rra.domain.models.request import validation_message
    from rra.domain.models.review import EditRequest

    try:
        edits = EditRequest.model_validate(
            json.loads(Path(args.from_file).read_text(encoding="utf-8"))
        )
    except (OSError, ValueError) as exc:
        _eprint(f"편집 파일을 읽을 수 없습니다: {type(exc).__name__}")
        return EXIT_USAGE
    except ValidationError as exc:
        _eprint(f"편집 형식 오류: {validation_message(exc)}")
        return EXIT_USAGE

    async def run():
        mgr = build_run_manager(load_settings())
        try:
            return await mgr.apply_edits(LOCAL_USER, args.run_id, edits)
        finally:
            await mgr.generate.llm.aclose()

    try:
        version = asyncio.run(run())
    except EditRejected as exc:
        _eprint(f"편집 거부: {exc}")
        return EXIT_USAGE
    print(f"[run {args.run_id}] v{version.version} 저장 ({version.origin}) — 상태 editing")
    return EXIT_OK


def cmd_runs_versions(args: argparse.Namespace) -> int:
    from rra.composition import LOCAL_USER, build_run_manager, load_settings
    from rra.entrypoints.views import versions_payload

    async def run():
        mgr = build_run_manager(load_settings())
        try:
            return await mgr.versions(LOCAL_USER, args.run_id)
        finally:
            await mgr.generate.llm.aclose()

    rows = versions_payload(asyncio.run(run()))
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return EXIT_OK
    for r in rows:
        extra = f" ← v{r['reverted_from']}" if r["reverted_from"] else ""
        print(
            f" v{r['version']:<3} {r['origin']:<7} {r['created_at'] or '-'}  "
            f"문장 {r['sentences']}{extra}  {_safe(r['note'], 60)}"
        )
    return EXIT_OK


def cmd_runs_revert(args: argparse.Namespace) -> int:
    from rra.application.services.run_manager import EditRejected
    from rra.composition import LOCAL_USER, build_run_manager, load_settings

    target = args.to.lower().lstrip("v")
    if not target.isdigit():
        _eprint("--to 는 v3 처럼 버전 번호입니다.")
        return EXIT_USAGE

    async def run():
        mgr = build_run_manager(load_settings())
        try:
            return await mgr.revert(LOCAL_USER, args.run_id, int(target))
        finally:
            await mgr.generate.llm.aclose()

    try:
        version = asyncio.run(run())
    except EditRejected as exc:
        _eprint(f"되돌리기 거부: {exc}")
        return EXIT_USAGE
    print(f"[run {args.run_id}] v{version.reverted_from} → v{version.version} 저장 — 상태 editing")
    return EXIT_OK


def cmd_runs_reopen(args: argparse.Namespace) -> int:
    from rra.application.services.run_manager import EditRejected
    from rra.composition import LOCAL_USER, build_run_manager, load_settings

    async def run():
        mgr = build_run_manager(load_settings())
        try:
            return await mgr.reopen(LOCAL_USER, args.run_id)
        finally:
            await mgr.generate.llm.aclose()

    try:
        state = asyncio.run(run())
    except EditRejected as exc:
        _eprint(f"다시 열기 거부: {exc}")
        return EXIT_USAGE
    print(f"[run {state.run_id}] 상태 {state.status}")
    return EXIT_OK


# ── sources check ─────────────────────────────────────────
def cmd_sources_check(args: argparse.Namespace) -> int:
    from rra.composition import KEYED_SOURCES, build_sources_check, load_settings

    names = [n.strip() for n in args.source.split(",") if n.strip()] if args.source else None
    results = asyncio.run(build_sources_check(load_settings(), names or KEYED_SOURCES)())
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            keys = ", ".join(
                f"{k}={'있음' if ok else '없음'}" for k, ok in r["credentials"].items()
            )
            allowed = "허용" if r["host_allowed"] else "허용목록에 없음"
            head = f"[{r['source']}] 키: {keys} / 호스트 {r['host']} {allowed}"
            print(f"{head} / 왕복: {r['roundtrip']}")
            if r.get("result"):
                print(f"    {_safe(json.dumps(r['result'], ensure_ascii=False), 300)}")
                for line in _record_tag_hints(r):
                    print(f"    → {line}")
            if r.get("error"):
                print(f"    {_safe(r['error'], 300)}")
    return EXIT_OK if all(r["roundtrip"] == "ok" for r in results) else EXIT_ERROR


def _record_tag_hints(r: dict) -> list[str]:
    """NTIS·KIPRIS 레코드 태그 진단 — probe 후보와 설정값을 대조해 다음 할 일을 알려 준다."""
    from rra.composition import load_settings, source_config

    result = r.get("result") or {}
    candidates = result.get("record_tag_candidates") or []
    if not candidates:
        return []
    try:
        configured = str(source_config(load_settings(), r["source"]).get("record_tag") or "")
    except Exception:  # 설정을 읽을 수 없으면(테스트 스텁 등) 진단을 생략한다
        return []
    safe = [_safe(c, 40) for c in candidates[:5]]
    if not configured:
        return [
            f"record_tag 가 비어 있습니다 — 후보 {safe} 중 레코드 하나를 감싸는 요소를 "
            f"config/sources.yaml {r['source']}.record_tag 에 적으세요 (수집은 그때부터)."
        ]
    if configured not in candidates and result.get("record_tag_matches") is False:
        return [f"설정된 record_tag {configured!r} 가 응답에 없습니다 — 후보 {safe} 로 바꾸세요."]
    return [f"record_tag {configured!r} 확인됨."]


# ── mcp ───────────────────────────────────────────────────
def cmd_mcp(args: argparse.Namespace) -> int:
    from rra.entrypoints.mcp.server import main as mcp_main

    argv = ["--transport", args.transport]
    if args.enable_generate:
        argv.append("--enable-generate")
    return mcp_main(argv)


# ── ui ────────────────────────────────────────────────────
def cmd_api_schema(args: argparse.Namespace) -> int:
    """OpenAPI 스키마를 파일로 (프론트 타입 생성용). 토큰·DB 없이 가짜 부품으로 만든다."""
    from rra.composition import build_api_schema, load_settings

    schema = build_api_schema(load_settings())
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"저장: {out} (경로 {len(schema.get('paths', {}))}개)")
    return EXIT_OK


def cmd_api(args: argparse.Namespace) -> int:
    """REST API (uvicorn). 기본 127.0.0.1:8000. 토큰 없으면 기동 거부 (G)."""
    if getattr(args, "api_cmd", None) == "schema":
        return cmd_api_schema(args)
    import uvicorn

    from rra.composition import FAKE_MODE_WARNING, ApiTokenMissing, build_api, load_settings

    settings = load_settings()
    host = args.host or settings.api_host
    port = args.port or settings.api_port
    try:
        app = build_api(settings)
    except ApiTokenMissing as exc:
        _eprint(str(exc))
        return EXIT_USAGE
    if settings.fake_llm:
        _eprint(FAKE_MODE_WARNING)
    if host not in ("127.0.0.1", "::1", "localhost"):
        _eprint(
            f"경고: {host} 에 바인딩합니다 — HTTPS 역프록시 뒤에서만 공개하십시오. deploy/README.md"
        )
    uvicorn.run(
        app, host=host, port=port, log_level="warning", access_log=False, server_header=False
    )
    return EXIT_OK


def cmd_ui(args: argparse.Namespace) -> int:
    from rra.entrypoints.ui.__main__ import main as ui_main

    return ui_main(["--server.port", str(args.port)])


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

    diff = sub.add_parser(
        "differentiate",
        help="차단·근접 유사과제별 활용·차별화 방향 제안 (기능 2, Gemini — 키 없으면 로컬)",
    )
    for slot in SLOTS:
        diff.add_argument(f"--{slot.replace('_', '-')}", dest=slot, default="")
    diff.add_argument("--file", help="5슬롯이 담긴 yaml/json 파일")
    diff.add_argument("--json", action="store_true", help="JSON 으로 출력")
    diff.set_defaults(handler=cmd_differentiate)

    search = sub.add_parser("search", help="수집 문서 하이브리드 검색")
    search.add_argument("query")
    search.add_argument("--orgs", help="쉼표로 구분 (예: korail,krri)")
    search.add_argument("-k", type=int, default=10)
    search.set_defaults(handler=cmd_search)

    lb = sub.add_parser(
        "llm-bench", help="골든셋으로 로컬 작성 모델 비교 (JSON 저장 / --report 로 표)"
    )
    lb.add_argument("--label", help="이 실행의 이름 (예: qwen, midm)")
    lb.add_argument("--golden", default="tests/golden", help="아이디어 yaml 폴더")
    lb.add_argument("--out", help="JSON(실행) 또는 Markdown(--report) 경로")
    lb.add_argument("--report", nargs="*", help="합칠 결과 JSON 들 → docs/llm-bench-<날짜>.md")
    lb.add_argument("--baseline", help="--report 에 적을 기준 모델 이름")
    lb.set_defaults(handler=cmd_llm_bench)
    ri = sub.add_parser("reindex", help="모든 청크를 설정 임베딩 모델로 재색인")
    ri.set_defaults(handler=cmd_reindex)
    db = sub.add_parser("db", help="DB 유지보수")
    db_sub = db.add_subparsers(dest="db_cmd", required=True)
    bk = db_sub.add_parser("backup", help="DB 사본 (VACUUM INTO, 권한 600)")
    bk.add_argument("--out", required=True, help="저장 경로 또는 폴더(폴더면 날짜 이름)")
    bk.add_argument("--keep", type=int, default=7, help="같은 폴더에 남길 사본 수 (기본 7)")
    bk.set_defaults(handler=cmd_db_backup)
    check = sub.add_parser("llm-check", help="LLM 서버 왕복 1회 확인")
    check.add_argument("--stage", default="compose")
    check.add_argument(
        "--provider", default=None, help="단계 설정을 무시하고 이 provider 로 (mlx|gemini|openai)"
    )
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
    ingest.add_argument(
        "--source",
        default="openalex",
        help="쉼표로 구분 (openalex, alio, alio_summary, own_projects, own_docs, scienceon, ntis, "
        "kipris)",
    )
    ingest.add_argument("--query", default=None, help="없으면 sources.yaml 기본 질의로 증분 수집")
    ingest.add_argument(
        "--skip-unavailable",
        action="store_true",
        dest="skip_unavailable",
        help="키가 없는 소스는 건너뛰고 나머지를 적재 (야간 적재용)",
    )
    ingest.add_argument("--limit", type=int, default=200, help="소스당 최대 건수")
    ingest.add_argument("--json", action="store_true", help="JSON 으로 출력")
    ingest.set_defaults(handler=cmd_ingest)

    src = sub.add_parser("sources", help="키가 필요한 수집 소스 점검")
    src_sub = src.add_subparsers(dest="sources_cmd", required=True)
    chk = src_sub.add_parser("check", help="키 유무(값 미표시)·허용목록·왕복 1회")
    chk.add_argument("--source", help="쉼표로 구분 (기본: scienceon,ntis,kipris)")
    chk.add_argument("--json", action="store_true")
    chk.set_defaults(handler=cmd_sources_check)

    alio = sub.add_parser("alio", help="알리오 공시 보고서 카탈로그·filedrop 관리")
    alio_sub = alio.add_subparsers(dest="alio_cmd", required=True)
    cat = alio_sub.add_parser("catalog", help="카탈로그 CSV 요약 (--fetch: 설정 URL 에서 받기)")
    cat.add_argument("--fetch", action="store_true")
    cat.set_defaults(handler=cmd_alio_catalog)
    miss = alio_sub.add_parser("missing", help="카탈로그 중 아직 적재되지 않은 보고서")
    miss.add_argument("--json", action="store_true")
    miss.add_argument(
        "--upgradable", action="store_true", help="--json 과 함께: 원문 확보 가능한 요약 목록"
    )
    miss.set_defaults(handler=cmd_alio_missing)
    status = alio_sub.add_parser("status", help="inbox 대기·완료·격리 파일 수")
    status.set_defaults(handler=cmd_alio_status)

    gen = sub.add_parser("generate", help="제안서 초안 생성 (섹션별 저장, 중단 후 --resume)")
    for slot in SLOTS + EXTRA_SLOTS:
        gen.add_argument(f"--{slot.replace('_', '-')}", dest=slot, default="")
    gen.add_argument("--budget-account", default="", help="예산과목 (양식 칸에만 쓰임)")
    gen.add_argument("--budget-amount", type=int, default=None, help="소요예산 (천원)")
    gen.add_argument(
        "--file", help="입력이 담긴 yaml/json 파일 (budget: {account, amount_thousand_krw})"
    )
    once = gen.add_mutually_exclusive_group()
    once.add_argument("--resume", metavar="RUN_ID", help="중단된 run 을 이어서 생성")
    once.add_argument(
        "--reuse-input", metavar="RUN_ID", help="기존 run(이전 양식 포함)의 입력으로 새로 생성"
    )
    gen.add_argument("--json", action="store_true", help="JSON 으로 출력")
    gen.set_defaults(handler=cmd_generate)

    api = sub.add_parser("api", help="REST API (기본 127.0.0.1:8000, RRA_API_TOKEN 필요)")
    api.add_argument("--port", type=int, default=None, help="기본 RRA_API_PORT 또는 8000")
    api.add_argument("--host", default=None, help="기본 RRA_API_HOST 또는 127.0.0.1")
    api.set_defaults(handler=cmd_api)
    api_sub = api.add_subparsers(dest="api_cmd")
    sch = api_sub.add_parser("schema", help="OpenAPI 스키마를 docs/openapi.json 으로 내보낸다")
    sch.add_argument("--out", default="docs/openapi.json")
    sch.set_defaults(handler=cmd_api_schema)

    ui = sub.add_parser("ui", help="Streamlit 화면 (127.0.0.1 전용, RRA_API_TOKEN 필요)")
    ui.add_argument("--port", type=int, default=8501)
    ui.set_defaults(handler=cmd_ui)

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
    rc = runs_sub.add_parser("confirm", help="과제유형·활용계획·전략과제 선택 확정")
    rc.add_argument("run_id")
    rc.add_argument("--task-type", choices=["basic", "applied", "development"])
    rc.add_argument("--utilization", help="쉼표로 구분 (예: software,manual,commercialization)")
    rc.add_argument("--strategy", help="전략과제 id, 쉼표로 구분 (1~2개)")
    rc.add_argument("--json", action="store_true")
    rc.set_defaults(handler=cmd_runs_confirm)
    rr = runs_sub.add_parser(
        "finalize", help="최종 마무리 → 별지 제2호서식 HWPX (검토 1회 이상 또는 건너뜀 뒤)"
    )
    rr.add_argument("run_id")
    rr.add_argument("--out", required=True, help="저장할 .hwpx 경로")
    rr.add_argument("--task-type", choices=["basic", "applied", "development"], help="과제유형")
    rr.add_argument("--utilization", help="활용계획 id (쉼표)")
    rr.add_argument("--strategy", help="전략과제 id (쉼표, 1~2개)")
    rr.add_argument("--department", help="제안부서 (양식 하단에만, 저장되지 않음)")
    rr.add_argument("--proposed-on", help="제안일자 (비면 오늘, 저장되지 않음)")
    for who, label in (("proposer", "제안자"), ("head", "제안부서장")):
        for field_name, desc in (("rank", "직급"), ("name", "성명"), ("phone", "연락처")):
            rr.add_argument(
                f"--{who}-{field_name}", help=f"{label} {desc} (양식 하단에만, 저장되지 않음)"
            )
    rr.set_defaults(handler=cmd_runs_finalize)
    rv = runs_sub.add_parser("review", help="검토(Argon) n차 시작 — 키 없으면 건너뜀 기록")
    rv.add_argument("run_id")
    rv.add_argument("--wait", action="store_true", help="검토가 끝날 때까지 기다린다")
    rv.add_argument("--json", action="store_true")
    rv.set_defaults(handler=cmd_runs_review)
    re_ = runs_sub.add_parser("edit", help="편집 반영 → 새 초안 버전")
    re_.add_argument("run_id")
    re_.add_argument("--from", dest="from_file", required=True, help="편집 JSON 파일")
    re_.set_defaults(handler=cmd_runs_edit)
    rvs = runs_sub.add_parser("versions", help="초안 버전 목록")
    rvs.add_argument("run_id")
    rvs.add_argument("--json", action="store_true")
    rvs.set_defaults(handler=cmd_runs_versions)
    rrv = runs_sub.add_parser("revert", help="이전 버전으로 되돌리기 (새 버전으로 저장)")
    rrv.add_argument("run_id")
    rrv.add_argument("--to", required=True, help="예: v2")
    rrv.set_defaults(handler=cmd_runs_revert)
    ro = runs_sub.add_parser("reopen", help="마무리된 run 다시 열기 → editing")
    ro.add_argument("run_id")
    ro.set_defaults(handler=cmd_runs_reopen)
    rp = runs_sub.add_parser("purge", help="보존 기간(security.yaml retention_days) 지난 run 삭제")
    rp.add_argument("--dry-run", action="store_true", help="지울 대상만 보여 주고 삭제하지 않는다")
    rp.add_argument("--json", action="store_true")
    rp.set_defaults(handler=cmd_runs_purge)

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
