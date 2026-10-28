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
from typing import Any

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
    settings = load_settings()
    alerts = asyncio.run(build_precheck(settings)(req))
    proposal = None
    if any(a.blocking for a in alerts) and not getattr(args, "no_differentiate", False):
        proposal = _auto_differentiate(settings, req, alerts)  # 차단 → 자동 (기능 2)
    recommendation = None
    if not getattr(args, "no_recommend", False):
        recommendation = _auto_recommend(settings, req, alerts)  # precheck 완료 → 자동 1회

    if args.json:
        payload: dict = {"alerts": [a.model_dump() for a in alerts]}
        if proposal is not None:
            from rra.entrypoints.views import differentiation_payload

            payload["differentiation"] = differentiation_payload(
                proposal, clean=lambda t: _safe(t, 600)
            )
        if recommendation is not None:
            from rra.entrypoints.views import recommendations_payload

            payload["recommendations"] = recommendations_payload(
                recommendation, clean=lambda t: _safe(t, 600)
            )
        bare = proposal is None and recommendation is None
        print(json.dumps(payload["alerts"] if bare else payload, ensure_ascii=False, indent=2))
    else:
        blocking = sum(1 for a in alerts if a.blocking)
        print(f"[중복 경보] {len(alerts)}건 (차단 {blocking}건)")
        for a in alerts:
            mark = "!" if a.blocking else " "
            basis = "요약" if a.basis == "summary" else "  "  # 공개 요약만으로 판정
            # 키워드는 제안자 입력에서 온 토큰(문서에도 등장한 것)이라 비신뢰 텍스트가 아니다
            words = f"  [키워드: {', '.join(a.keywords)}]" if a.keywords else "  [키워드 없음]"
            status = f"  [상태: {_STATUS_TEXT.get(a.status, a.status)}]" if a.status else ""
            tier = a.tier if a.tier != "own" else f"own:{a.own_detail or 'institute'}"
            print(
                f" {mark} {a.similarity:.2f}  {tier:<14} {basis} {a.doc_id:<20} {_safe(a.title)}"
                f"{words}{status}"
            )
        if not alerts:
            print("  유사한 기수행 과제가 없습니다.")
        if proposal is not None:
            _print_differentiation(proposal, auto=True)
        if recommendation is not None:
            _print_recommendations(recommendation, auto=True)
    return EXIT_BLOCKED if any(a.blocking for a in alerts) else EXIT_OK


def _auto_recommend(settings, req, alerts):
    """precheck 완료 → 차별화 과제 추천 자동 1회 (recommend.auto). LLM 이 없으면 None."""
    from rra.composition import LLMUnavailable, build_recommender, recommend_policy

    if not recommend_policy(settings)["auto"]:
        return None

    async def run():
        recommend = build_recommender(settings)
        try:
            return await recommend(req, alerts)
        finally:
            await recommend.llm.aclose()

    try:
        return asyncio.run(run())
    except LLMUnavailable as exc:
        _eprint(f"과제 추천 생략 (LLM 없음): {exc}")
        return None


def _print_recommendations(result, *, auto: bool = False) -> None:
    from rra.entrypoints.views import recommendations_payload

    payload = recommendations_payload(result, clean=lambda t: _safe(t, 600))
    where = "로컬 모델(대체)" if result.fallback_local else f"{result.provider}/{result.model}"
    head = "[차별화 과제 추천 — precheck 완료 후 자동]" if auto else "[차별화 과제 추천]"
    print(
        f"\n{head} 추천 {len(result.recommendations)}건, 제외 {len(result.discarded)}건 ({where})"
    )
    if result.skipped_reason:
        print(f"  건너뜀: {result.skipped_reason}")
    if payload["no_recommendation_reason"]:
        print(f"  추천하지 않음: {payload['no_recommendation_reason']}")
    for r in payload["recommendations"]:
        print(f"\n■ 추천 {r['index'] + 1}: {r['title']}")
        print(f"  요약: {r['summary']}")
        print(f"  차별점: {r['differentiation']}")
        for n, reason in enumerate(r["reasons"], 1):
            print(f"  이유 {n}: {reason}")
        if r["build_on"]:
            print(f"  이어받을 성과: {r['build_on']}")
        if r["risks"]:
            print(f"  위험·확인: {r['risks']}")
        compared = ", ".join(r["compared_with"]) or "-"
        evidence = ", ".join(r["evidence"]) or "-"
        print(f"  비교 과제: {compared} · 근거: {evidence}")
        if r["overlap_warning"]:
            print(f"  ! 기존 과제와 겹칠 수 있음(사람이 판단): {', '.join(r['overlap_warning'])}")
    for d in payload["discarded"]:
        print(f"  (제외) {_safe(d.get('title', ''), 64)}: {_safe(d.get('reason', ''), 40)}")
    t = payload["transfer"]
    print(
        f"전송: public {len(t['public_doc_ids'])}건, internal {len(t['internal_doc_ids'])}건, "
        f"제외 {len(t['excluded_doc_ids'])}건 — 고른 추천은 generate 의 --title-hint·"
        "--differentiation 으로 넣는다"
    )


def cmd_recommend(args: argparse.Namespace) -> int:
    """차별화 과제 추천(ADR 0012) — 기존 과제와 다른 과제 0~5건 (Gemini, 키 없으면 로컬)."""
    from rra.composition import build_precheck, build_recommender, load_settings
    from rra.domain.models import ProposalRequest
    from rra.domain.models.request import validation_message
    from rra.entrypoints.views import recommendations_payload

    try:
        req = ProposalRequest(**_read_slots(args))
    except ValidationError as exc:
        _eprint(validation_message(exc))
        return EXIT_USAGE
    settings = load_settings()

    async def run():
        precheck = build_precheck(settings)
        recommend = build_recommender(
            settings, repo=getattr(precheck, "repo", None), precheck=precheck
        )
        try:
            alerts = await precheck(req)
            return alerts, await recommend(req, alerts)
        finally:
            await recommend.llm.aclose()

    alerts, result = asyncio.run(run())
    if args.json:
        payload = recommendations_payload(result, clean=lambda t: _safe(t, 600))
        print(
            json.dumps(
                {"alerts": [a.model_dump() for a in alerts], **payload},
                ensure_ascii=False,
                indent=2,
            )
        )
        return EXIT_OK
    print(f"[유사과제] 알림 {len(alerts)}건 (차단 {sum(1 for a in alerts if a.blocking)}건)")
    _print_recommendations(result)
    return EXIT_OK


def _auto_differentiate(settings, req, alerts):
    """차단 알림 → 차별화 제안 자동 실행. LLM 이 없으면 None (precheck 는 계속)."""
    from rra.composition import LLMUnavailable, build_differentiator, build_precheck

    async def run():
        differentiate = build_differentiator(
            settings, repo=getattr(build_precheck(settings), "repo", None)
        )
        try:
            return await differentiate(req, alerts)
        finally:
            await differentiate.llm.aclose()

    try:
        return asyncio.run(run())
    except LLMUnavailable as exc:
        _eprint(f"차별화 제안 생략 (LLM 없음): {exc}")
        return None


def _print_differentiation(proposal, *, auto: bool = False) -> None:
    from rra.entrypoints.views import differentiation_payload

    payload = differentiation_payload(proposal, clean=lambda t: _safe(t, 600))
    where = (
        "로컬 모델(대체)" if proposal.fallback_local else f"{proposal.provider}/{proposal.model}"
    )
    head = "[차별화 제안 — 차단 알림으로 자동 실행]" if auto else "[차별화 제안]"
    print(f"\n{head} 제안 {len(proposal.items)}건, 폐기 {len(proposal.discarded)}건 ({where})")
    if proposal.skipped_reason:
        print(f"  건너뜀: {proposal.skipped_reason}")
    for item in payload["items"]:
        status = (
            f" [상태: {_STATUS_TEXT.get(item['status'], item['status'])}]" if item["status"] else ""
        )
        tier = item["tier"] if item["tier"] != "own" else "own"
        print(f"\n■ {item['doc_id']} ({tier}){status} {item['title']}")
        print(f"  겹치는 점: {item['overlap_summary']}")
        if item["build_on"]:
            print(f"  이어받을 점: {item['build_on']}")
        for n, d in enumerate(item["differentiation"], 1):
            print(f"  방향 {n}: {d}")
    for d in payload["discarded"]:
        print(f"  (폐기) {_safe(d.get('doc_id', ''), 64)}: {_safe(d.get('reason', ''), 40)}")
    t = payload["transfer"]
    print(
        f"전송: public {len(t['public_doc_ids'])}건, internal {len(t['internal_doc_ids'])}건, "
        f"제외 {len(t['excluded_doc_ids'])}건 — 고른 방향은 generate --differentiation 으로 넣는다"
    )


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
    "procuring": "용역으로 진행 중/예정",  # 발주 용역 공고 (P2-6)
}


# ── U2 간편 입력 · U4 비교표 · U5 브리핑 ──────────────────────
def cmd_structure(args: argparse.Namespace) -> int:
    """U2 자유 문장 → 필수 4칸 + 보완 질문 (로컬 모델 1회). 저장하지 않는다."""
    from rra.composition import build_structurer, load_settings
    from rra.entrypoints.views import structure_payload

    settings = load_settings()
    structure = build_structurer(settings)
    if structure is None:
        _eprint("간편 입력이 꺼져 있습니다 (config/usability.yaml quick_input).")
        return EXIT_USAGE

    async def run():
        try:
            return await structure(args.text, title=args.title or "")
        finally:
            await structure.llm.aclose()

    payload = structure_payload(asyncio.run(run()), clean=lambda t: _safe(t, 2000))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK
    for key, label in payload["labels"].items():
        print(f"{label}: {payload['fields'].get(key) or '(비어 있음)'}")
    if payload["questions"]:
        print("\n보완 질문 (답은 generate --<칸> 으로 보충하거나 건너뛸 수 있음):")
        for i, q in enumerate(payload["questions"], 1):
            print(f" {i}. [{q['label']}] {q['question']}")
    else:
        print("\n필수 4칸이 모두 채워졌습니다 — 그대로 generate 에 쓸 수 있습니다.")
    return EXIT_OK


def cmd_compare(args: argparse.Namespace) -> int:
    """U4 차별성 비교표 — precheck 상위 5건 × 항목 (LLM 없음, 화면·API 표만)."""
    from rra.composition import build_comparer, build_precheck, load_settings
    from rra.domain.models import ProposalRequest
    from rra.domain.models.request import validation_message
    from rra.entrypoints.views import comparison_payload

    try:
        req = ProposalRequest(**_read_slots(args), differentiation=args.differentiation or "")
    except ValidationError as exc:
        _eprint(validation_message(exc))
        return EXIT_USAGE
    settings = load_settings()
    precheck = build_precheck(settings)
    compare = build_comparer(settings, repo=getattr(precheck, "repo", None), precheck=precheck)
    if compare is None:
        _eprint("차별성 비교표가 꺼져 있습니다 (config/usability.yaml comparison).")
        return EXIT_USAGE
    table = asyncio.run(compare(req))
    payload = comparison_payload(table, clean=lambda t: _safe(t, 400))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK
    cols = [payload["proposal"], *payload["projects"]]
    print(f"[차별성 비교표] 유사과제 {len(payload['projects'])}건 (양식 밖 — 화면·API 표)")
    print(
        " 열: 제안 | " + " | ".join(f"{c['doc_id']} {c['title'][:24]}" for c in payload["projects"])
    )
    for aspect in payload["aspects"]:
        print(f"\n■ {aspect['label']}")
        for c in cols:
            name = "제안" if c["doc_id"] is None else c["doc_id"]
            print(f"  - {name}: {c['cells'].get(aspect['key'], '')[:160]}")
    return EXIT_OK


def cmd_brief(args: argparse.Namespace) -> int:
    """U5 선행연구 브리핑 — 검색 상위 논문·보고서 10건 한 줄 요약·연도·키워드·연구 공백 후보."""
    from rra.composition import build_briefer, load_settings
    from rra.domain.models import ProposalRequest
    from rra.domain.models.request import validation_message
    from rra.entrypoints.views import brief_payload

    try:
        req = ProposalRequest(**_read_slots(args))
    except ValidationError as exc:
        _eprint(validation_message(exc))
        return EXIT_USAGE
    settings = load_settings()
    brief = build_briefer(settings)
    if brief is None:
        _eprint("선행연구 브리핑이 꺼져 있습니다 (config/usability.yaml brief).")
        return EXIT_USAGE

    async def run():
        try:
            return await brief(req)
        finally:
            await brief.llm.aclose()

    payload = brief_payload(asyncio.run(run()), clean=lambda t: _safe(t, 400))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK
    where = (
        "로컬 모델(대체)"
        if payload["fallback_local"]
        else f"{payload['provider']}/{payload['model']}"
    )
    print(f"[선행연구 브리핑] {len(payload['items'])}건 ({where})")
    if payload["skipped_reason"]:
        print(f"  건너뜀: {payload['skipped_reason']}")
    for i, item in enumerate(payload["items"], 1):
        year = item["year"] or "미상"
        summary = item["summary"] or "(요약 없음 — 검증 실패 또는 모델 미응답)"
        print(f" {i:>2}. [{year}] {item['chunk_id']} {item['title'][:50]}\n     {summary}")
    print("\n연도별: " + ", ".join(f"{y} {n}건" for y, n in payload["years"].items()))
    print("키워드: " + (", ".join(payload["keywords"]) or "-"))
    print(f"\n{payload['gap_label']}:")
    for g in payload["gaps"] or []:
        print(f"  - {g['text']}  [{', '.join(g['evidence'])}]")
    if not payload["gaps"]:
        print("  (없음)")
    print(
        "\n고른 항목의 id 는 generate --priority-evidence 또는 POST /v1/runs priority_evidence 로."
    )
    return EXIT_OK


def _or_dash(value) -> str:
    return "-" if value is None else str(value)


def cmd_usage_report(args: argparse.Namespace) -> int:
    """U8 runs/ 의 usage.json 집계."""
    from rra.composition import build_usage_report, load_settings

    report = build_usage_report(load_settings())()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return EXIT_OK
    if not report.get("runs"):
        print("기록된 run 이 없습니다.")
        return EXIT_OK
    print(f"[시범운영 측정] run {report['runs']}건")
    print(f"  평균 총 시간: {report['avg_total_seconds'] or '-'}초")
    for k, v in (report.get("avg_step_seconds") or {}).items():
        print(f"    - {k}: {v}초")
    print("  필수 요소 충족률 평균: " + _or_dash(report.get("checklist_coverage_avg")))
    ratios = report.get("evidence_ratio_avg")
    if ratios:
        print(
            f"  근거 판단 비율 평균 (판단한 run {report['evidence_decided_runs']}건): "
            f"승인 {ratios['approve']}, 교체 {ratios['replace']}, 제외 {ratios['exclude']}"
        )
    print(f"  AI 다시 쓰기 반영: {report['rewrites_total']}회")
    print(f"  HWPX 성공 {report['hwpx_success']}건 / 실패 {report['hwpx_failed']}건")
    print(
        f"  만족도: 평균 {_or_dash(report.get('satisfaction_avg'))} "
        f"({report['satisfaction_count']}건) 분포 {report['satisfaction_distribution']}"
    )
    return EXIT_OK


def cmd_runs_submit_check(args: argparse.Namespace) -> int:
    """U7 제출 전 점검 체크리스트."""
    from rra.composition import LOCAL_USER, build_run_manager, load_settings
    from rra.entrypoints.views import submit_check_payload

    async def run():
        mgr = build_run_manager(load_settings())
        try:
            return await mgr.submit_check(LOCAL_USER, args.run_id), mgr.generate.rules.titles
        finally:
            await mgr.generate.llm.aclose()

    check, titles = asyncio.run(run())
    payload = submit_check_payload(check, titles=titles, clean=lambda t: _safe(t, 300))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK
    verdict = "통과" if payload["ok"] else f"확인 필요 {payload['failing']}건"
    print(f"[제출 전 점검] {verdict} — run {args.run_id}")
    for item in payload["items"]:
        mark = "✔" if item["ok"] else "!"
        target = f"  → {item['target']}" if item.get("target") else ""
        print(f" {mark} {item['label']}: {item['detail']}{target}")
    return EXIT_OK


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

    from rra.composition import build_bench, data_location, load_settings
    from rra.domain.models import ProposalRequest

    settings = load_settings()
    golden = sorted(Path(args.golden).glob("*.yaml"))
    if not golden:
        _eprint(f"골든셋이 없습니다: {args.golden}")
        return EXIT_USAGE
    ideas = [
        (p.stem, ProposalRequest(**yaml.safe_load(p.read_text(encoding="utf-8")))) for p in golden
    ]

    async def run():
        bench = build_bench(settings, label=args.label)
        try:
            return await bench(ideas)
        finally:
            await bench.generate.llm.aclose()

    result = asyncio.run(run())
    out = Path(args.out) if args.out else data_location(settings, "bench") / f"{args.label}.json"
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


# ── eval (Q9 초안 품질 강화 효과 측정) ─────────────────────
QUALITY_STEPS = (
    "clarify",
    "outline",
    "section_search",
    "exemplars",
    "rule_check",
    "additions",
    "two_candidates",
    "reranker",
)


def _eval_pipeline(settings, args: argparse.Namespace):
    """--pipeline none|all|default 에 --on/--off 를 덮어쓴 PipelineConfig."""
    from rra.composition import pipeline_config
    from rra.domain.models import PipelineConfig

    base = pipeline_config(settings)
    if args.pipeline == "none":
        values = {k: False for k in QUALITY_STEPS}
    elif args.pipeline == "all":
        values = {k: True for k in QUALITY_STEPS}
    else:
        values = {k: getattr(base, k) for k in QUALITY_STEPS}
    for name in _csv(args.on):
        values[name] = True
    for name in _csv(args.off):
        values[name] = False
    unknown = set(values) - set(QUALITY_STEPS)
    if unknown:
        raise ValueError(f"모르는 단계: {sorted(unknown)} (가능: {list(QUALITY_STEPS)})")
    return PipelineConfig(
        **values,
        draft_review=not args.no_review,
        draft_review_retries=base.draft_review_retries,
    )


def _csv(value: str | None) -> list[str]:
    return [x.strip() for x in (value or "").split(",") if x.strip()]


def cmd_eval(args: argparse.Namespace) -> int:
    """골든셋으로 ③ 흐름(precheck → 생성 → v1 → 1차 검토 → v2)을 돌려 지표 JSON 을 남기거나
    (--label), JSON 들을 비교표(docs/eval-<날짜>.md "초안 품질 강화 비교")로 합친다(--report)."""
    from rra.entrypoints.views import eval_markdown

    if args.report:
        results = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.report]
        out = Path(args.out or f"docs/eval-{time.strftime('%Y-%m-%d')}.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        text = eval_markdown(results, date=time.strftime("%Y-%m-%d"))
        if out.exists() and args.append:
            out.write_text(out.read_text(encoding="utf-8").rstrip() + "\n\n" + text, "utf-8")
        else:
            out.write_text(text, encoding="utf-8")
        print(f"저장: {out} (구성 {len(results)}개)")
        return EXIT_OK
    if not args.label:
        _eprint("--label <이름> (측정 실행) 또는 --report <json…> (표 작성) 중 하나가 필요합니다.")
        return EXIT_USAGE
    import yaml

    from rra.composition import build_eval, data_location, load_settings
    from rra.domain.models import ProposalRequest

    settings = load_settings()
    try:
        pipeline = _eval_pipeline(settings, args)
    except ValueError as exc:
        _eprint(str(exc))
        return EXIT_USAGE
    only = set(_csv(args.only))
    golden = [
        p
        for p in sorted(Path(args.golden).glob("*.yaml"))
        if not only or any(p.stem.startswith(o) for o in only)
    ]
    if not golden:
        _eprint(f"골든셋이 없습니다: {args.golden}")
        return EXIT_USAGE
    ideas, expected = [], {}
    for p in golden:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        exp = data.pop("expected_similar", None)
        if exp is not None:
            expected[p.stem] = [str(x) for x in (exp or [])]
        ideas.append((p.stem, ProposalRequest(**data)))
    if args.runs_dir:
        runs_dir = Path(args.runs_dir)
    else:
        runs_dir = data_location(settings, "eval") / "runs" / args.label

    async def run():
        ev = build_eval(
            settings, label=args.label, pipeline=pipeline, runs_dir=runs_dir, expected=expected
        )
        try:
            return await ev(ideas)
        finally:
            await ev.manager.generate.llm.aclose()

    result = asyncio.run(run())
    out = Path(args.out) if args.out else data_location(settings, "eval") / f"{args.label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    t = result.totals()
    print(
        f"[{result.label}] 켠 단계 {[k for k, v in result.pipeline.items() if v is True]} — "
        f"알림 v1 {t['v1_alerts']}→v2 {t['v2_alerts']}, "
        f"문장 {t['sentences_v1']}→{t['sentences_v2']}, "
        f"무관 인용 {t['irrelevant_citations']}, 논문 인용 {t['paper_citations']}, "
        f"점수합 {t['score_sum']}, 충족률 {t['checklist_coverage']}, "
        f"precheck 적중 {t['precheck_hits']}/{t['precheck_known']}, "
        f"평균 {t['seconds_avg']}s, Gemini {t['gemini_calls']}회, RSS {result.max_rss_mb or '-'}MB"
    )
    for i in result.ideas:
        print(
            f"  {i.name}: {i.status} v1 알림 {i.v1_alerts} v2 알림 {i.v2_alerts} "
            f"점수 {i.scores} 반영 {i.applied}+{i.additions_applied} {i.seconds}s run {i.run_id}"
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
    from rra.composition import build_db_maintenance, data_path, load_settings

    settings = load_settings()
    _, backup = build_db_maintenance(settings)
    # `data/backups` 처럼 data/ 로 시작하는 상대 경로는 데이터 폴더(원 저장소) 아래로
    report = asyncio.run(backup(data_path(settings, args.out, only_prefixed=True), keep=args.keep))
    print(f"백업: {report.path} (보관 {len(report.kept)}벌, 삭제 {len(report.removed)}벌)")
    for extra in report.extras:
        print(f"  + {extra.name}")
    return EXIT_OK


# ── auth (레인 A) ───────────────────────────────────────────
def _prompt_secret(label: str) -> str:
    """getpass — 화면·인자·셸 기록에 남지 않게. 값은 돌려주기만 한다."""
    import getpass

    return getpass.getpass(f"{label}: ").strip()


def cmd_auth(args: argparse.Namespace) -> int:
    """`rra auth staff add|remove|count`, `rra auth guest set --id <아이디>|disable`,
    `rra auth status`.
    사번·비밀번호는 getpass 로만 받고 출력·기록하지 않는다. 저장은 <data_dir>/auth (700/600)."""
    from rra.composition import build_auth_store, load_settings
    from rra.config_loader import auth_config
    from rra.domain.rules.auth_policy import valid_guest_id, valid_password, valid_staff_no

    settings = load_settings()
    store = build_auth_store(settings)
    auth_cfg = auth_config(settings)
    group = args.auth_cmd
    if group == "status":
        info = store.status()
        staff_state = "활성" if info["staff_count"] else "비활성"
        guest_state = "설정됨" if info["guest"] else "없음"
        secret_state = "있음" if info["secret"] else "없음"
        print(
            f"직원 사번 등록: {info['staff_count']}건 ({staff_state}), "
            f"공용 계정: {guest_state}, 비밀 키: {secret_state}"
        )
        if not store.permissions_ok():
            _eprint("경고: auth 폴더·파일 권한이 700/600 이 아닙니다.")
        return EXIT_OK
    if group == "staff":
        if args.staff_cmd == "count":
            print(f"등록된 사번: {store.staff_count()}건")
            return EXIT_OK
        if args.staff_cmd == "import":
            return _auth_staff_import(args, settings, store)
        staff_no = _prompt_secret("사번")
        if not valid_staff_no(staff_no):
            _eprint("사번 형식이 올바르지 않습니다 (영숫자·하이픈 2~32자).")
            return EXIT_USAGE
        if args.staff_cmd == "add":
            added = store.add_staff(staff_no)
            print("등록했습니다." if added else "이미 등록된 사번입니다.")
        else:
            removed = store.remove_staff(staff_no)
            print("삭제했습니다." if removed else "등록되지 않은 사번입니다.")
        print(f"등록된 사번: {store.staff_count()}건")
        return EXIT_OK
    if group == "guest":
        if args.guest_cmd == "disable":
            print("공용 계정을 껐습니다." if store.disable_guest() else "공용 계정이 없습니다.")
            return EXIT_OK
        guest_id = (args.id or "").strip().lower()
        if not valid_guest_id(guest_id):
            _eprint("아이디 형식이 올바르지 않습니다 (소문자·숫자·_·- 2~20자).")
            return EXIT_USAGE
        first = _prompt_secret("비밀번호")
        second = _prompt_secret("비밀번호 (확인)")
        if not first or first != second:
            _eprint("비밀번호가 비어 있거나 두 입력이 다릅니다.")
            return EXIT_USAGE
        min_len = int(auth_cfg.get("min_password_length", 8))
        if not valid_password(first, min_len):
            _eprint(f"비밀번호는 {min_len}자 이상이어야 합니다.")
            return EXIT_USAGE
        store.set_guest(guest_id, first)
        print(f"공용 계정을 설정했습니다 (아이디 {guest_id}).")
        return EXIT_OK
    return EXIT_USAGE


def _auth_staff_import(args: argparse.Namespace, settings: Any, store: Any) -> int:
    """`rra auth staff import --file <xlsx|csv>` — 사번 열만 샌드박스로 읽어 HMAC 으로 저장.
    출력은 개수뿐(읽은 행·신규·이미 있음·빈칸·형식 오류 행 번호·길이별 분포). 사번 값은 절대
    출력하지 않는다. 원본 파일은 복사하지 않는다."""
    from rra.application.ports import RosterReadError
    from rra.composition import build_roster_reader, build_staff_importer

    path = Path(args.file).expanduser()
    if args.pad < 0 or args.pad > 32:
        _eprint("--pad 는 0~32 사이여야 합니다.")
        return EXIT_USAGE
    reader = build_roster_reader(settings)
    try:
        roster = asyncio.run(reader.read(path, sheet=args.sheet, column=args.column))
    except RosterReadError as exc:
        _eprint(f"명부를 읽지 못했습니다: {exc}")
        return EXIT_ERROR
    importer = build_staff_importer(settings, store=store)
    try:
        report = importer.run(
            roster.cells, pad=args.pad, replace=args.replace, dry_run=args.dry_run
        )
    except ValueError as exc:
        _eprint(str(exc))
        return EXIT_ERROR
    where = f"시트 '{roster.sheet}', " if roster.sheet else ""
    mode = "미리 보기(저장 없음)" if args.dry_run else ("목록 교체" if args.replace else "추가")
    print(f"사번 일괄 등록 — {where}머리글 {roster.header_row}행, 방식: {mode}")
    for line in report.as_lines():
        print(line)
    if len(report.counts.length_histogram) > 1:
        print(
            "안내: 사번 길이가 여러 가지입니다. 엑셀에서 앞자리 0 이 빠졌다면 "
            "--pad <자릿수> 로 다시 실행하십시오."
        )
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
        if getattr(args, "full", False):
            for source in sources:  # 전체 기간 수집을 지원하는 소스만 (OpenAlex backfill_years)
                if hasattr(source, "full_window"):
                    source.full_window = True
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
    # IP 거부로 건너뛴 소스 (레인 I): --skip-unavailable 이면 실패로 치지 않는다 (야간 적재 유지)
    unavailable = dict(report.unavailable)
    for name, notice in unavailable.items():
        _eprint(f"[{_safe(name)}] 건너뜀(IP 거부): {_safe(notice, 300)}")
    failed = {
        n: why
        for n, why in report.failed.items()
        if not (getattr(args, "skip_unavailable", False) and n in unavailable)
    }
    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    else:
        for name in names:
            if name in unavailable:
                continue  # 위에 안내를 냈다
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
    return EXIT_ERROR if failed else EXIT_OK


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


# ── policy-suggest (정책 근거 추천) ────────────────────────
def cmd_policy_suggest(args: argparse.Namespace) -> int:
    """① 입력 → 정책 문서 문구 3~5개.

    --pick N 이면 그 문구를 policy_basis 에 붙인 입력(JSON)을 출력한다."""
    from rra.composition import build_policy_suggest, load_settings
    from rra.domain.models import ProposalRequest
    from rra.domain.models.request import validation_message
    from rra.domain.rules.policy_phrases import apply_policy_suggestion
    from rra.entrypoints.views import policy_suggestions_payload

    settings = load_settings()
    fields = _read_slots(args)
    fields["policy_basis"] = getattr(args, "policy_basis", "") or ""
    try:
        req = ProposalRequest(**fields)
    except ValidationError as exc:
        _eprint(f"입력 오류: {validation_message(exc)}")
        return EXIT_USAGE
    suggestions = asyncio.run(build_policy_suggest(settings)(req))
    rows = policy_suggestions_payload(suggestions, clean=_safe)
    if args.pick is not None:
        if not (1 <= args.pick <= len(suggestions)):
            _eprint(f"--pick 은 1~{len(suggestions)} 사이여야 합니다.")
            return EXIT_USAGE
        chosen = apply_policy_suggestion(req, suggestions[args.pick - 1])
        print(json.dumps(chosen.model_dump(), ensure_ascii=False, indent=2))
        return EXIT_OK
    if args.json:
        print(json.dumps({"suggestions": rows}, ensure_ascii=False, indent=2))
        return EXIT_OK
    if not rows:
        print("정책 문서에서 고를 문구가 없습니다 (korail_web 적재 전이거나 관련 문서 없음).")
        return EXIT_OK
    for i, r in enumerate(rows, 1):
        where = ", ".join(p for p in (str(r["year"]) if r["year"] else "", r["page"] or "") if p)
        print(f"{i}. {r['title']}{' (' + where + ')' if where else ''} — {r['url'] or ''}")
        print(f"   “{r['quote']}”  [키워드 {', '.join(r['keywords']) or '-'}]")
    print("고른 번호를 --pick N 으로 주면 policy_basis 에 붙인 입력을 돌려줍니다 (자동 삽입 없음).")
    return EXIT_OK


# ── notices match (공고문 대조, #13 선행) ─────────────────
def cmd_notices_match(args: argparse.Namespace) -> int:
    """① 입력 → 접수 중인 정부 R&D 공고 상위 3건 (LLM 없음, 자동 삽입 없음)."""
    from rra.composition import build_notice_match, load_settings
    from rra.domain.models import ProposalRequest
    from rra.domain.models.request import validation_message
    from rra.entrypoints.views import notice_matches_payload

    settings = load_settings()
    try:
        req = ProposalRequest(**_read_slots(args))
    except ValidationError as exc:
        _eprint(f"입력 오류: {validation_message(exc)}")
        return EXIT_USAGE
    matches = asyncio.run(build_notice_match(settings)(req))
    rows = notice_matches_payload(matches, clean=_safe)
    if args.json:
        print(json.dumps({"items": rows, "count": len(rows)}, ensure_ascii=False, indent=2))
        return EXIT_OK
    if not rows:
        print("접수 중인 관련 공고가 없습니다 (rnd_notice 적재 전이거나 마감 지난 공고뿐).")
        return EXIT_OK
    for i, r in enumerate(rows, 1):
        left = f"D-{r['days_left']}" if isinstance(r["days_left"], int) else "마감 미상"
        sim = f", 유사도 {r['similarity']:.2f}" if r["similarity"] is not None else ""
        print(
            f"{i}. {r['title']} — {r['agency'] or '기관 미상'}, "
            f"마감 {r['deadline'] or '-'} ({left}{sim})"
        )
        print(f"   {r['url'] or ''}")
    print("공고는 제안서에 자동으로 들어가지 않습니다 (공고 요건 대조는 #13).")
    return EXIT_OK


# ── crawl (정부 R&D 공고 스냅샷) ──────────────────────────
def cmd_crawl_rnd_notice(args: argparse.Namespace) -> int:
    """`rra crawl rnd-notice --explore | --download [--limit N] [--incremental]` (P2-7)."""
    from rra.composition import build_rnd_notice_crawler, load_settings

    crawler = build_rnd_notice_crawler(load_settings())

    async def run():
        try:
            if args.explore:
                return await crawler.explore()
            return await crawler.download(limit=args.limit, incremental=bool(args.incremental))
        finally:
            await crawler.aclose()

    result = asyncio.run(run())
    if args.explore:
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return EXIT_OK
        print(f"탐색 {result['date']} (최근 {result['since']} 이후)")
        for s in result["sites"]:
            if s.get("held"):
                print(f"- {s['site']}: 보류 {_safe(s['held'], 60)}")
                continue
            print(
                f"- {s['site']} ({s['base_url']}): robots {s.get('robots')}, "
                f"전체 {s.get('total')}, 표본 {[_safe(t, 50) for t in s.get('sample') or []]}"
            )
        return EXIT_OK
    data = result.to_dict()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return EXIT_OK
    print(
        f"스냅샷 {data['snapshot']}: 공고 {sum(data['notices'].values())}건 {data['notices']}, "
        f"중복 합침 {data['duplicates']}, 이어 받음 {data['carried']}, 파일 {data['files']}개 "
        f"{data['bytes'] / 1024 / 1024:.1f}MB, 건너뛴 파일 {data['skipped_files']}, "
        f"보류 {len(data['held'])}, 오류 {data['errors']}, robots 차단 {data['robots_blocked']}"
    )
    return EXIT_OK


# ── crawl (공사 홈페이지 스냅샷) ───────────────────────────
def cmd_crawl_bai(args: argparse.Namespace) -> int:
    """`rra crawl bai [--incremental]` — 감사원 감사결과 전문 PDF 스냅샷 (Playwright, 공개 화면
    조작만)."""
    from rra.composition import build_bai_crawler, load_settings

    settings = load_settings()
    try:
        crawler = build_bai_crawler(settings)
    except ImportError:
        _eprint("playwright 가 없습니다: uv pip install playwright && playwright install chromium")
        return EXIT_USAGE

    report = asyncio.run(crawler.download(incremental=bool(args.incremental)))
    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
        return EXIT_OK
    totals = ", ".join(
        f"{q} {n if n is not None else '?'}건" for q, n in report.total_by_query.items()
    )
    print(
        f"스냅샷 {report.snapshot}: 항목 {report.items}건(건너뜀 {report.skipped_existing}), "
        f"파일 {report.files}개 {report.bytes / 1024 / 1024:.1f}MB, 보류 {len(report.held)}, "
        f"검색 결과 {totals}"
    )
    return EXIT_OK


def cmd_crawl_korail(args: argparse.Namespace) -> int:
    """`rra crawl korail --explore | --download [--incremental]`. 예약 실행 없음 (사람이 돌린다)."""
    from rra.composition import build_korail_web_crawler, load_settings

    settings = load_settings()
    crawler = build_korail_web_crawler(settings)

    async def run():
        try:
            if args.explore:
                return await crawler.explore()
            return await crawler.download(incremental=bool(args.incremental))
        finally:
            await crawler.aclose()

    result = asyncio.run(run())
    if args.explore:
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return EXIT_OK
        print(
            f"탐색 {result['date']} {result['base_url']} robots "
            f"{'비어 있음(제한 없음)' if result['robots_empty'] else '있음'}"
        )
        for m in result["menus"]:
            if m.get("held") or m.get("blocked"):
                print(
                    f"- {_safe(m['path'], 60)}: {'보류' if m.get('held') else '차단'} "
                    f"{_safe(m.get('held') or m.get('blocked'), 80)}"
                )
                continue
            if m["kind"] == "contents":
                print(
                    f"- {_safe(m['path'], 60)}: 본문 {m.get('chars', 0):,}자, "
                    f"첨부 {m.get('attachments', 0)}"
                    f"{' ' + str(m.get('attachment_kinds')) if m.get('attachment_kinds') else ''}, "
                    f"이미지 {m.get('images', 0)}"
                )
            else:
                print(
                    f"- {_safe(m['path'], 60)}: {m.get('posts') or '?'}건 / "
                    f"{m.get('pages') or '?'}쪽, {m.get('earliest') or '?'} ~ "
                    f"{m.get('latest') or '?'}, "
                    f"1쪽 첨부 {m.get('attachment_kinds_page1')}"
                    f"{' (since ' + m['since'] + ')' if m.get('since') else ''}"
                )
        return EXIT_OK
    data = result.to_dict()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        total = sum(data["items"].values())
        carried = sum(data["carried"].values())
        print(
            f"스냅샷 {data['snapshot']}{' (증분)' if data['incremental'] else ''}: 항목 {total:,}건"
            f"(이어 적음 {carried:,}), 파일 {data['files']:,}, 이미지 {data['images']:,}, "
            f"{data['bytes'] / 1024 / 1024:,.1f}MB, 건너뜀 {data['skipped_files']}, "
            f"삭제 표시 {data['removed']}, "
            f"보류 {len(data['held'])}, robots 차단 {data['robots_blocked']}"
        )
        for menu, n in data["items"].items():
            print(f"- {_safe(menu, 40)}: {n:,}건 (이어 적음 {data['carried'].get(menu, 0):,})")
        for url in data["held"]:
            _eprint(f"[보류] {_safe(url, 160)}")
    return EXIT_ERROR if data["held"] else EXIT_OK


# ── strategy (전략체계 초안·확정) ───────────────────────────
def cmd_strategy_draft(args: argparse.Namespace) -> int:
    """공사 홈페이지 "중장기 경영목표" 표 → korail_strategy.draft.yaml (basis: text)."""
    import yaml

    from rra.composition import build_strategy_drafter, load_settings
    from rra.config_loader import STRATEGY_DRAFT_FILE, korail_web_config

    settings = load_settings()
    cfg = korail_web_config(settings)
    key = str(
        args.key
        or next((m["key"] for m in cfg.get("menus") or [] if m.get("id") == "mgmt_goal"), "1900")
    )
    draft = asyncio.run(build_strategy_drafter(settings)(key, time.strftime("%Y-%m-%d")))
    url = str(draft["directions"][0]["source"]["url"]) if draft["directions"] else ""
    out = Path(args.out) if args.out else Path(settings.config_dir) / STRATEGY_DRAFT_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# 전략체계 초안 — 공사 홈페이지 ‘중장기 경영목표’ 표에서 자동 추출\n"
        "# (rra strategy draft, basis: text). 사람이 확인한 뒤 `rra strategy promote` 로\n"
        "# korail_strategy.yaml 에 복사한다. 항목을 지어내지 않는다.\n"
    )
    out.write_text(
        header + yaml.safe_dump(draft, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    tasks = sum(len(d["tasks"]) for d in draft["directions"])
    print(
        f"초안 저장: {out} — 전략방향 {len(draft['directions'])}개, 전략과제 {tasks}개 "
        f"(출처 {_safe(url, 80)})"
    )
    return EXIT_OK


def cmd_strategy_promote(args: argparse.Namespace) -> int:
    """초안 → 확정 파일 복사 (백업 유지) + strategy.yaml source: confirmed. 사람만 실행한다."""
    from rra.application.usecases.strategy_catalog import promote_strategy
    from rra.composition import load_settings
    from rra.config_loader import STRATEGY_DRAFT_FILE, STRATEGY_FILE

    settings = load_settings()
    base = Path(settings.config_dir)
    report = promote_strategy(
        base / STRATEGY_DRAFT_FILE, base / STRATEGY_FILE, base / "strategy.yaml"
    )
    print(
        f"확정: {report.target} (전략방향 {report.directions}, 전략과제 {report.tasks})"
        + (f", 백업 {report.backup.name}" if report.backup else "")
    )
    return EXIT_OK


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
# 검토 LLM 이 있으면 초안 뒤 1차 검토가 자동으로 붙어 reviewing/reviewed 로 끝난다 — 생성은 성공.
_STATUS_EXIT = {
    "drafted": EXIT_OK,
    "draft_reviewing": EXIT_OK,
    "editing": EXIT_OK,
    "final_reviewing": EXIT_OK,
    "final_reviewed": EXIT_OK,
    "finalized": EXIT_OK,
    "done": EXIT_OK,  # 옛 이름
    "reviewing": EXIT_OK,
    "reviewed": EXIT_OK,
    "invalid": EXIT_INVALID,
}


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
                priority = _csv(getattr(args, "priority_evidence", None)) or None
                state = await mgr.submit(
                    LOCAL_USER, request, on_step=on_step, priority_evidence=priority
                )
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


def cmd_runs_active(args: argparse.Namespace) -> int:
    """모든 사용자의 대기·실행 중 run (배포 전 확인, tools/deploy.sh). 출력은 run_id·상태·시각."""
    from rra.composition import build_run_manager, load_settings
    from rra.domain.models.run import ACTIVE

    states = build_run_manager(load_settings()).list_all_runs(limit=200)
    active = [s for s in states if s.status in ACTIVE]
    if args.json:
        print(
            json.dumps(
                {
                    "count": len(active),
                    "runs": [
                        {"run_id": s.run_id, "status": s.status, "created_at": s.created_at}
                        for s in active
                    ],
                },
                ensure_ascii=False,
            )
        )
    elif active:
        print(f"대기·실행 중인 생성: {len(active)}건")
        for s in active:
            print(f"  {s.run_id}  {s.status}  {s.created_at}")
    else:
        print("대기·실행 중인 생성: 0건")
    return EXIT_OK


def cmd_runs_figures(args: argparse.Namespace) -> int:
    """[G] run 의 그림 목록 — 종류·섹션·채택 방식·확인 여부·호출 수 (그림 파일·명세 본문 없음)."""
    from rra.composition import LOCAL_USER, build_run_manager, load_settings
    from rra.entrypoints.views import figures_payload

    async def run():
        mgr = build_run_manager(load_settings())
        try:
            return await mgr.get_draft(LOCAL_USER, args.run_id)
        finally:
            await mgr.generate.llm.aclose()

    view = asyncio.run(run())
    rows = figures_payload(view.figures, args.run_id, clean=lambda t: _safe(t, 120))
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return EXIT_OK
    print(f"[그림] run {args.run_id} v{view.version} — {len(rows)}개")
    for r in rows:
        mark = "✔" if r["confirmed"] else "확인 전"
        inc = "" if r["included"] else " (뺌)"
        print(
            f"  {r['id']}  {r['label']}  {r['renderer_label']}  호출 {r['calls']}  {mark}{inc}"
            + (f"  오류 {r['error']}" if r.get("error") else "")
        )
    return EXIT_OK


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
        raw = json.loads(Path(args.from_file).read_text(encoding="utf-8"))
        if getattr(args, "memo", None):
            raw["note"] = args.memo
        edits = EditRequest.model_validate(raw)
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
    print(
        f"[run {args.run_id}] v{version.version} 저장 ({version.origin}, 바뀐 섹션 "
        f"{', '.join(version.changed_sections) or '-'}, 알림 {version.alerts}, "
        f"메모 {version.open_annotations}) — 상태 editing"
    )
    return EXIT_OK


def cmd_runs_diff(args: argparse.Namespace) -> int:
    """두 버전의 섹션·문장 단위 차이."""
    from rra.application.services.run_manager import EditRejected
    from rra.composition import LOCAL_USER, build_run_manager, load_settings
    from rra.entrypoints.views import diff_payload

    a, b = (x.lower().lstrip("v") for x in (args.from_v, args.to_v))
    if not (a.isdigit() and b.isdigit()):
        _eprint("--from/--to 는 v1 처럼 버전 번호입니다.")
        return EXIT_USAGE

    async def run():
        mgr = build_run_manager(load_settings())
        try:
            va = await mgr.get_version(LOCAL_USER, args.run_id, int(a))
            vb = await mgr.get_version(LOCAL_USER, args.run_id, int(b))
            return va, vb, await mgr.diff(LOCAL_USER, args.run_id, int(a), int(b))
        finally:
            await mgr.generate.llm.aclose()

    try:
        va, vb, rows = asyncio.run(run())
    except EditRejected as exc:
        _eprint(f"비교 거부: {exc}")
        return EXIT_USAGE
    payload = diff_payload(va, vb, rows, clean=lambda t: _safe(t, 300))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK
    print(
        f"[run {args.run_id}] v{payload['from']} → v{payload['to']}: "
        f"바뀐 섹션 {len(payload['sections'])}"
    )
    for d in payload["sections"]:
        print(f"■ {d['section']} (문장 {d['sentences'][0]} → {d['sentences'][1]})")
        for x in d["removed"]:
            print(f"  - {x['text']}")
        for x in d["added"]:
            print(f"  + {x['text']}")
        for x in d["moved"]:
            print(f"  ~ {x['to']}")
    return EXIT_OK


def cmd_runs_final_review(args: argparse.Namespace) -> int:
    """⑤ Argon 최종 검토 — 최신 저장 버전으로 1회 (다시 받기도 같은 명령, 횟수 기록).
    --apply-passed 는 끝난 뒤 검증 통과 수정안을 전부 반영해 새 버전을 만든다."""
    from rra.application.ports import RunBusy
    from rra.application.services import QueueFull
    from rra.application.services.run_manager import EditRejected
    from rra.composition import LOCAL_USER, build_run_manager, load_settings
    from rra.domain.models.review import EditRequest, SentenceEdit
    from rra.domain.rules.review_flow import InvalidTransition
    from rra.entrypoints.views import review_payload

    async def run():
        mgr = build_run_manager(load_settings())
        try:
            state = await mgr.final_review(LOCAL_USER, args.run_id)
            if (args.wait or args.apply_passed) and state.status == "final_reviewing":
                state = await mgr.wait(LOCAL_USER, args.run_id)
            review = await mgr.get_review(LOCAL_USER, args.run_id, kind="final")
            applied = None
            if args.apply_passed and review is not None and review.status == "done":
                usable = [c for c in review.comments if c.usable and c.sentence is not None]
                if usable:
                    applied = await mgr.apply_edits(
                        LOCAL_USER,
                        args.run_id,
                        EditRequest(
                            sentences=[
                                SentenceEdit(
                                    sentence_id=f"s:{c.section}:{c.sentence}",
                                    action="use_revision",
                                    comment_id=c.id,
                                )
                                for c in usable
                            ],
                            note="최종 검토 수정안 반영",
                        ),
                    )
            return state, review, applied
        finally:
            await mgr.generate.llm.aclose()

    try:
        state, review, applied = asyncio.run(run())
    except (QueueFull, RunBusy, InvalidTransition, EditRejected) as exc:
        _eprint(f"최종 검토 거부: {exc}")
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
    print(
        f"[run {state.run_id}] 상태 {state.status}, 최종 검토 {state.final_reviews}회"
        + (f", 최종 검토 이후 수정 {state.stale_edits}건" if state.stale else "")
    )
    if review and review.status == "done":
        for s in review.scores:
            delta = review.score_delta.get(s.criterion)
            change = f" ({delta:+d} vs 1차)" if delta is not None else ""
            print(f"  [채점] {s.criterion} {s.score}/5{change} — {_safe(s.reason, 100)}")
        usable = sum(1 for c in review.comments if c.usable)
        print(f"  의견 {len(review.comments)}건 (수정안 사용 가능 {usable})")
        for c in review.comments:
            where = f"s:{c.section}:{c.sentence}" if c.sentence is not None else c.section
            mark = "✔" if c.usable else ("✘" if c.status == "discarded" else "·")
            print(f"  {mark} {c.id} [{c.issue_type}] {where}: {_safe(c.comment, 120)}")
    if applied is not None:
        print(f"  → 통과 수정안 반영: v{applied.version} 저장 (최종 검토 반영)")
    return EXIT_OK


def cmd_runs_outline(args: argparse.Namespace) -> int:
    """③ 섹션 설계도(Q2). pipeline.outline 이 꺼져 있으면 없음."""
    from rra.composition import LOCAL_USER, build_run_manager, load_settings

    async def run():
        mgr = build_run_manager(load_settings())
        try:
            await mgr.status(LOCAL_USER, args.run_id)
            loader = getattr(mgr, "load_outline", None)
            return await loader(LOCAL_USER, args.run_id) if loader is not None else None
        finally:
            await mgr.generate.llm.aclose()

    outline = asyncio.run(run())
    if not outline:
        print("설계도가 없습니다 (config/pipeline.yaml outline 이 꺼져 있거나 아직 전).")
        return EXIT_OK
    print(json.dumps(outline, ensure_ascii=False, indent=2))
    return EXIT_OK


def cmd_clarify(args: argparse.Namespace) -> int:
    """③ 시작 전 입력 보강 질문(Q1, 최대 3개). pipeline.clarify 가 꺼져 있으면 질문 0개."""
    from rra.composition import load_settings, pipeline_config
    from rra.domain.models import ProposalRequest
    from rra.domain.models.request import validation_message

    try:
        req = ProposalRequest(**_read_slots(args))
    except ValidationError as exc:
        _eprint(validation_message(exc))
        return EXIT_USAGE
    settings = load_settings()
    questions: list[str] = []
    if pipeline_config(settings).clarify:
        from rra.composition import build_clarifier

        clarify = build_clarifier(settings)
        questions = asyncio.run(clarify(req)) if clarify is not None else []
    if args.json:
        print(json.dumps({"questions": questions, "skip_allowed": True}, ensure_ascii=False))
        return EXIT_OK
    if not questions:
        print("보강 질문 없음 — 입력이 충분합니다. 바로 생성할 수 있습니다.")
        return EXIT_OK
    for i, q in enumerate(questions, 1):
        print(f"{i}. {_safe(q, 300)}")
    print("답은 generate --constraints / --remarks 등 입력에 보충하거나 건너뛸 수 있습니다.")
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
            f" v{r['version']:<3} {r['origin_label']:<8} {r['created_at'] or '-'}  "
            f"문장 {r['sentences']} 알림 {r['alerts']} 메모 {r['open_annotations']}{extra}  "
            f"[{', '.join(r['changed_sections']) or '-'}] {_safe(r['note'], 60)}"
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
            for line in _ip_lines(r):
                print(f"    {line}")
    return EXIT_OK if all(r["roundtrip"] == "ok" for r in results) else EXIT_ERROR


def _ip_lines(r: dict) -> list[str]:
    """자료원 IP 제한 표시 (레인 I) — 등록 IP 목록·현재 공인 IP·안내. 판단은 유스케이스 결과."""
    if "ip_restricted" not in r:
        return []
    if not r["ip_restricted"]:
        return ["IP 제한 없음"]
    registered = ", ".join(_safe(ip, 45) for ip in r.get("registered_ips") or []) or "(없음)"
    if r.get("ip_lookup_error"):
        current = f"확인 실패 ({_safe(r['ip_lookup_error'], 60)})"
    else:
        current = _safe(r.get("current_ip") or "", 45) or "미확인"
    lines = [f"등록 IP: {registered} / 현재 공인 IP: {current}"]
    if r.get("ip_notice"):
        lines.append(f"[안내] {_safe(r['ip_notice'], 300)}")
        if r.get("ip_registered") is True:  # 목록에는 있는데 API 가 거부 — 반영·서비스별 IP 확인
            lines.append(
                "등록 목록에는 있으나 API 가 거부했습니다 — 활용신청 반영 여부, 서비스별 서버 IP, "
                "실제 송신 IP(회선·프록시)를 확인하세요."
            )
    return lines


def cmd_sources_status(args: argparse.Namespace) -> int:
    """자료원별 적재 건수·최근 적재일 + 공사 홈페이지 스냅샷 날짜."""
    from rra.composition import (
        build_embedding,
        build_korail_web_source,
        build_repository,
        build_rnd_notice_source,
        build_source_availability,
        load_settings,
    )
    from rra.domain.rules.overlap import ALL_SOURCES, SOURCE_LABELS

    settings = load_settings()
    repo = build_repository(build_embedding(settings), settings)
    status = asyncio.run(repo.source_status())
    snap = build_korail_web_source(settings).status()
    notice_snap = build_rnd_notice_source(settings).status()
    notices = build_source_availability(settings).notices()  # IP 거부 등 차단 안내 (레인 I)
    rows = [
        {
            "source": s,
            "label": SOURCE_LABELS.get(s, s),
            "count": int(status.get(s, {}).get("count", 0)),
            "last_ingested": status.get(s, {}).get("last_ingested"),
            "notice": _safe(notices[s], 300) if notices.get(s) else None,
        }
        for s in ALL_SOURCES
    ]
    if args.json:
        print(
            json.dumps(
                {"sources": rows, "korail_web_snapshot": snap, "rnd_notice_snapshot": notice_snap},
                ensure_ascii=False,
                indent=2,
            )
        )
        return EXIT_OK
    for r in rows:
        print(f"- {r['label']}: {r['count']:,}건, 최근 적재 {r['last_ingested'] or '-'}")
        if r["notice"]:
            print(f"  [안내] {r['notice']}")
    if snap.get("snapshot"):
        print(
            f"공사 홈페이지 자료: {snap['snapshot']} 기준 스냅샷 (항목 {snap.get('items', 0):,}건, "
            f"삭제 표시 {snap.get('removed', 0)})"
        )
    else:
        print("공사 홈페이지 자료: 스냅샷 없음 (rra crawl korail --download)")
    if notice_snap.get("snapshot"):
        print(
            f"정부 R&D 공고: {notice_snap['snapshot']} 기준 스냅샷 "
            f"(공고 {notice_snap.get('items', 0):,}건, "
            f"중복 합침 {notice_snap.get('duplicates', 0)})"
        )
    else:
        print("정부 R&D 공고: 스냅샷 없음 (rra crawl rnd-notice --download)")
    return EXIT_OK


def _record_tag_hints(r: dict) -> list[str]:
    """NTIS·KIPRIS 레코드 태그 진단 — probe 후보와 설정값을 대조해 다음 할 일을 알려 준다."""
    from rra.composition import load_settings, source_config

    result = r.get("result") or {}
    candidates = result.get("record_tag_candidates") or []
    if not candidates:
        return []
    # ntis_reports·ntis_insights 는 ntis 설정을 같이 쓴다 (composition 과 같은 대응)
    cfg_name = "ntis" if r["source"] in ("ntis_reports", "ntis_insights") else r["source"]
    try:
        configured = str(source_config(load_settings(), cfg_name).get("record_tag") or "")
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


# ── vision (P3 이미지 판독) ───────────────────────────────
def _vision_plan_lines(summary: dict) -> list[str]:
    f, p = summary["filter"], summary["plan"]
    reasons = ", ".join(f"{k} {v}" for k, v in f.items() if k not in ("kept", "excluded"))
    lines = [
        f"스냅샷 {summary['snapshot']} — 거르기: 유지 {f['kept']} / 제외 {f['excluded']} "
        f"({reasons or '없음'})",
        f"판독 계획: 대상 {p['planned']}건, 캐시 {p['cached']}건, "
        f"예상 호출 {p['expected_calls']}건 (상한 {p['cap']}), OCR 만 {p['ocr_only']}건, "
        f"사진(OCR 판정, Argon 제외) {p.get('photos', 0)}건",
        "순서 그룹: " + ", ".join(f"{k} {v}" for k, v in p["groups"].items()),
    ]
    return lines


def cmd_vision_extract(args: argparse.Namespace) -> int:
    """첨부(hwpx·hwp·pdf·pptx·xlsx) 속 내장 이미지를 꺼내 스냅샷에 더한다 — read 전에 한 번."""
    from rra.composition import build_extract_attachment_images, load_settings

    use = build_extract_attachment_images(load_settings(), snapshot=args.snapshot)
    report = asyncio.run(use(limit=args.limit))
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(
            f"첨부 {report.attachments}개 중 파싱 {report.parsed}, 새 이미지 {report.images}장"
            f"(중복 {report.duplicates}), 형식별 {report.by_ext}, 거부 {report.rejected}, "
            f"건너뜀 {report.skipped}"
        )
    return EXIT_OK


def cmd_vision_read(args: argparse.Namespace) -> int:
    from rra.composition import build_read_images, load_settings

    usecase = build_read_images(
        load_settings(), snapshot=args.snapshot, cap=args.cap, with_reader=not args.ocr_only
    )
    if usecase.ocr is None:
        _eprint("OCR 없음 — macOS Vision(ocrmac) 을 쓸 수 없어 수치 대조 없이 진행합니다.")
    if usecase.reader is None and not args.ocr_only:
        _eprint("판독기 없음 — RRA_GEMINI_API_KEY 가 없어 OCR 만 합니다.")
    report = asyncio.run(usecase(dry_run=args.dry_run, limit=args.limit))
    summary = report.summary()
    if args.json:
        payload = {**summary, "ocr_only_hashes": report.ocr_only_hashes}
        if not args.dry_run:
            payload["results"] = [
                {
                    "sha256": r.sha256,
                    "status": r.status,
                    "cached": r.cached,
                    "image_type": r.reading.image_type if r.reading else None,
                    "unconfirmed_numbers": r.unconfirmed_numbers,
                    "ocr_error": r.ocr_error,
                    "vision_error": r.vision_error,
                }
                for r in report.results
            ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK
    for line in _vision_plan_lines(summary):
        print(line)
    if args.dry_run:
        print("dry-run: 호출하지 않았습니다.")
        return EXIT_OK
    print(
        f"결과: {summary['status']} / 실제 호출 {summary['calls']}건 / 미확인 수치 "
        f"{summary['unconfirmed_numbers']}건 / {summary['elapsed_sec']}초"
    )
    if report.ocr_only_hashes:
        print(f"상한으로 OCR 만 한 이미지 {len(report.ocr_only_hashes)}건 (다음 실행에서 이어서):")
        for h in report.ocr_only_hashes[:20]:
            print(f"  {h}")
    return EXIT_OK


def cmd_vision_sample(args: argparse.Namespace) -> int:
    from rra.application.usecases.vision_sample import build_sample
    from rra.composition import build_read_images, load_settings, vision_config

    settings = load_settings()
    vcfg = vision_config(settings)
    usecase = build_read_images(settings, snapshot=args.snapshot, with_reader=not args.cached_only)
    report = asyncio.run(usecase(limit=args.limit))
    sample = build_sample(report.results, per_type=args.per_type or vcfg["sample_per_type"])
    out = Path(args.out or vcfg["sample_dir"])
    out.mkdir(parents=True, exist_ok=True)
    for name, content in sample.files().items():
        (out / name).write_text(content, encoding="utf-8")
    print(sample.markdown())
    print(
        f"표본 {sum(len(v) for v in sample.entries.values())}건 → {out}/ "
        f"(실제 호출 {report.calls}건)"
    )
    return EXIT_OK


def cmd_vision_ingest(args: argparse.Namespace) -> int:
    from rra.composition import build_ingest_image_readings, load_settings

    usecase = build_ingest_image_readings(load_settings(), snapshot=args.snapshot)
    report = asyncio.run(usecase(dry_run=args.dry_run, limit=args.limit))
    summary = report.summary()
    if args.json:
        print(json.dumps({**summary, "doc_ids": report.doc_ids}, ensure_ascii=False, indent=2))
        return EXIT_OK
    skipped = ", ".join(f"{k} {v}" for k, v in summary["skipped"].items()) or "없음"
    print(
        f"스냅샷 {summary['snapshot']} — 판독 결과 {summary['results']}건 → "
        f"문서 {summary['documents']}건 / 청크 {summary['chunks']}건 "
        f"(페이지 문서 {summary['pages_found']}건, 건너뜀: {skipped})"
    )
    if summary["removed_personal"]:
        print(
            "개인정보 제거: "
            + ", ".join(f"{k} {v}" for k, v in summary["removed_personal"].items())
        )
    print("dry-run: 적재하지 않았습니다." if args.dry_run else "적재했습니다.")
    return EXIT_OK


# ── facts (P2-8) · terms (P2-9) ─────────────────────────
def cmd_facts_extract(args: argparse.Namespace) -> int:
    """적재된 문서의 표 → 사실 저장 (적재 뒤에 돈다). --dry-run 은 건수만."""
    from rra.composition import build_extract_facts, load_settings
    from rra.entrypoints.views import fact_line

    usecase = build_extract_facts(load_settings(), source=args.source, snapshot=args.snapshot)
    report = asyncio.run(usecase(dry_run=args.dry_run, limit=args.limit))
    summary = report.summary()
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return EXIT_OK
    basis = ", ".join(f"{k} {v}" for k, v in summary["by_basis"].items()) or "없음"
    print(
        f"{summary['source']}: 표 {summary['tables']}장 → 사실 {summary['facts']}건 "
        f"(문서 {summary['documents']}건, 사실 없는 표 {summary['empty_tables']}장, "
        f"근거 종류: {basis})"
    )
    if summary["missing_docs"]:
        ids = ", ".join(_safe(d, 40) for d in summary["missing_doc_ids"])
        print(f"  ! 아직 적재되지 않은 문서 {summary['missing_docs']}건 (사실은 저장됨): {ids}")
    for f in report.samples:
        print("  - " + fact_line(f, clean=_safe))
    print("dry-run: 저장하지 않았습니다." if args.dry_run else "저장했습니다.")
    return EXIT_OK


def cmd_facts_search(args: argparse.Namespace) -> int:
    from rra.composition import build_embedding, build_repository, load_settings
    from rra.domain.rules.trust import UNTRUSTED_NOTICE
    from rra.entrypoints.views import fact_line, facts_payload

    settings = load_settings()
    repo = build_repository(build_embedding(settings), settings)
    facts = asyncio.run(repo.search_facts(args.query, k=args.k))
    if args.json:
        print(
            json.dumps(
                {"notice": UNTRUSTED_NOTICE, "facts": facts_payload(facts, clean=_safe)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return EXIT_OK
    print(UNTRUSTED_NOTICE)
    if not facts:
        print("(사실 없음)")
    for f in facts:
        print("- " + fact_line(f, clean=_safe))
    return EXIT_OK


def cmd_terms_candidates(args: argparse.Namespace) -> int:
    """코퍼스 표본 → 철도 용어·흔한 단어 후보 YAML 두 개 (config/*.candidates.yaml). 자동 반영
    없음."""
    from rra.composition import build_term_candidates, load_settings

    settings = load_settings()
    usecase, write = build_term_candidates(settings)
    report = asyncio.run(usecase(sample=args.sample, limit=args.limit))
    out_dir = Path(args.out_dir) if args.out_dir else Path(settings.config_dir)
    written = write(out_dir, usecase.payloads(report))
    sources = ", ".join(f"{k} {v}" for k, v in report.sources.items()) or "없음"
    print(
        f"표본 청크 {report.chunks}건 / 문서 {report.documents}건 ({sources}) → "
        f"철도 용어 후보 {len(report.rail)}건, 흔한 단어 후보 {len(report.generic)}건"
    )
    for path in written:
        print(f"  {path}")
    print("후보일 뿐입니다 — config/overlap.yaml 반영은 사람이 검토해 결정합니다.")
    return EXIT_OK


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
    pre.add_argument(
        "--no-differentiate",
        action="store_true",
        dest="no_differentiate",
        help="차단 알림이 있어도 차별화 제안(기능 2)을 자동 실행하지 않는다",
    )
    pre.add_argument(
        "--no-recommend",
        action="store_true",
        dest="no_recommend",
        help="precheck 뒤 차별화 과제 추천을 자동 실행하지 않는다",
    )
    pre.set_defaults(handler=cmd_precheck)

    cla = sub.add_parser("clarify", help="③ 시작 전 입력 보강 질문 (최대 3개, pipeline.clarify)")
    for slot in SLOTS:
        cla.add_argument(f"--{slot.replace('_', '-')}", dest=slot, default="")
    cla.add_argument("--file", help="5슬롯이 담긴 yaml/json 파일")
    cla.add_argument("--json", action="store_true", help="JSON 으로 출력")
    cla.set_defaults(handler=cmd_clarify)

    rec = sub.add_parser(
        "recommend",
        help="기존 과제와 차별성을 갖는 과제 0~5건 추천 (Gemini, 키 없으면 로컬; 없으면 사유)",
    )
    for slot in SLOTS:
        rec.add_argument(f"--{slot.replace('_', '-')}", dest=slot, default="")
    rec.add_argument("--file", help="5슬롯이 담긴 yaml/json 파일")
    rec.add_argument("--json", action="store_true", help="JSON 으로 출력")
    rec.set_defaults(handler=cmd_recommend)

    diff = sub.add_parser(
        "differentiate",
        help="차단·근접 유사과제별 활용·차별화 방향 제안 (기능 2, Gemini — 키 없으면 로컬)",
    )
    for slot in SLOTS:
        diff.add_argument(f"--{slot.replace('_', '-')}", dest=slot, default="")
    diff.add_argument("--file", help="5슬롯이 담긴 yaml/json 파일")
    diff.add_argument("--json", action="store_true", help="JSON 으로 출력")
    diff.set_defaults(handler=cmd_differentiate)

    ps = sub.add_parser(
        "policy-suggest", help="① 입력 → 정책 문서 문구 3~5개 추천 (LLM 없음, 자동 삽입 없음)"
    )
    for slot in SLOTS:
        ps.add_argument(f"--{slot.replace('_', '-')}", dest=slot, default="")
    ps.add_argument("--policy-basis", dest="policy_basis", default="", help="이미 적은 정책 근거")
    ps.add_argument("--file", help="5슬롯이 담긴 yaml/json 파일")
    ps.add_argument(
        "--pick", type=int, default=None, help="고른 번호 → policy_basis 에 붙인 입력 출력"
    )
    ps.add_argument("--json", action="store_true")
    ps.set_defaults(handler=cmd_policy_suggest)
    st = sub.add_parser("structure", help="U2 자유 문장 → 필수 4칸 + 보완 질문 (로컬 모델)")
    st.add_argument("--text", required=True, help="아이디어 1~2문장")
    st.add_argument("--title", default="", help="가제 (선택)")
    st.add_argument("--json", action="store_true")
    st.set_defaults(handler=cmd_structure)

    cmp_ = sub.add_parser("compare", help="U4 차별성 비교표 (precheck 상위 5건, LLM 없음)")
    for slot in SLOTS:
        cmp_.add_argument(f"--{slot.replace('_', '-')}", dest=slot, default="")
    cmp_.add_argument("--file", help="5슬롯이 담긴 yaml/json 파일")
    cmp_.add_argument("--differentiation", default="", help="제안자가 정한 차별화 방향")
    cmp_.add_argument("--json", action="store_true")
    cmp_.set_defaults(handler=cmd_compare)

    br = sub.add_parser("brief", help="U5 선행연구 브리핑 (Gemini, 키 없으면 로컬)")
    for slot in SLOTS:
        br.add_argument(f"--{slot.replace('_', '-')}", dest=slot, default="")
    br.add_argument("--file", help="5슬롯이 담긴 yaml/json 파일")
    br.add_argument("--json", action="store_true")
    br.set_defaults(handler=cmd_brief)

    usage = sub.add_parser("usage", help="U8 시범운영 측정 기록")
    usage_sub = usage.add_subparsers(dest="usage_cmd", required=True)
    ur = usage_sub.add_parser("report", help="runs/ 의 usage.json 집계")
    ur.add_argument("--json", action="store_true")
    ur.set_defaults(handler=cmd_usage_report)

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
    ev = sub.add_parser(
        "eval", help="골든셋으로 초안 품질 강화 효과 측정 (JSON 저장 / --report 로 비교표)"
    )
    ev.add_argument("--label", help="이 구성의 이름 (예: baseline, all, minus-outline)")
    ev.add_argument("--pipeline", choices=["none", "all", "default"], default="default")
    ev.add_argument("--on", help="켤 단계 (쉼표 구분)")
    ev.add_argument("--off", help="끌 단계 (쉼표 구분)")
    ev.add_argument("--no-review", action="store_true", help="Argon 1차 검토 없이 (Gemini 0회)")
    ev.add_argument("--golden", default="tests/golden", help="아이디어 yaml 폴더")
    ev.add_argument("--only", help="골든셋 이름 접두어 (쉼표 구분, 예: 01,02)")
    ev.add_argument("--runs-dir", help="run 저장 폴더 (기본 data/eval/runs/<label>)")
    ev.add_argument("--out", help="JSON(실행) 또는 Markdown(--report) 경로")
    ev.add_argument("--report", nargs="*", help="합칠 결과 JSON 들 → docs/eval-<날짜>.md")
    ev.add_argument("--append", action="store_true", help="--report: 기존 문서 끝에 덧붙인다")
    ev.set_defaults(handler=cmd_eval)
    ri = sub.add_parser("reindex", help="모든 청크를 설정 임베딩 모델로 재색인")
    ri.set_defaults(handler=cmd_reindex)
    auth = sub.add_parser(
        "auth", help="로그인 계정 관리 (사번 HMAC·공용 계정 scrypt, 값은 getpass)"
    )
    auth_sub = auth.add_subparsers(dest="auth_cmd", required=True)
    a_staff = auth_sub.add_parser("staff", help="철도연구원 직원 사번 목록")
    a_staff_sub = a_staff.add_subparsers(dest="staff_cmd", required=True)
    for name, desc in (
        ("add", "사번 등록 (getpass 입력)"),
        ("remove", "사번 삭제 (getpass 입력)"),
        ("count", "등록된 사번 개수만"),
    ):
        a_staff_sub.add_parser(name, help=desc).set_defaults(handler=cmd_auth)
    a_imp = a_staff_sub.add_parser(
        "import", help="xlsx·csv 명부에서 사번 열만 읽어 일괄 등록 (출력은 개수만, 파일 복사 없음)"
    )
    a_imp.add_argument("--file", required=True, help="명부 파일 (.xlsx 또는 .csv)")
    a_imp.add_argument("--sheet", default=None, help="시트 이름 (기본: 첫 시트)")
    a_imp.add_argument("--column", default=None, help='사번 열 제목 (기본: "사번")')
    a_imp.add_argument(
        "--pad",
        type=int,
        default=0,
        help="숫자만인 사번을 이 자릿수까지 앞에 0 을 채운다 (엑셀 0 빠짐 보정)",
    )
    a_imp.add_argument(
        "--replace", action="store_true", help="기존 목록을 이 파일로 바꾼다 (기본: 추가)"
    )
    a_imp.add_argument("--dry-run", action="store_true", help="저장 없이 집계만")
    a_imp.set_defaults(handler=cmd_auth)
    a_guest = auth_sub.add_parser("guest", help="공용 계정 (아이디 1개)")
    a_guest_sub = a_guest.add_subparsers(dest="guest_cmd", required=True)
    a_set = a_guest_sub.add_parser("set", help="아이디·비밀번호 설정 (비밀번호 두 번 getpass)")
    a_set.add_argument("--id", required=True, help="아이디 (소문자·숫자·_·- 2~20자)")
    a_set.set_defaults(handler=cmd_auth)
    a_guest_sub.add_parser("disable", help="공용 계정 끄기").set_defaults(handler=cmd_auth)
    auth_sub.add_parser("status", help="설정 여부만 (값 없음)").set_defaults(handler=cmd_auth)
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
        "kipris, korail_web, molit, rnd_notice)",
    )
    ingest.add_argument("--query", default=None, help="없으면 sources.yaml 기본 질의로 증분 수집")
    ingest.add_argument(
        "--full",
        action="store_true",
        help="증분(lookback_days) 대신 전체 기간(openalex.backfill_years) 수집 — 최초 적재용",
    )
    ingest.add_argument(
        "--skip-unavailable",
        action="store_true",
        dest="skip_unavailable",
        help="키가 없거나 API 가 호출 IP 를 거부한 소스는 건너뛰고 나머지를 적재 (야간 적재용)",
    )
    ingest.add_argument("--limit", type=int, default=200, help="소스당 최대 건수")
    ingest.add_argument("--json", action="store_true", help="JSON 으로 출력")
    ingest.set_defaults(handler=cmd_ingest)

    src = sub.add_parser("sources", help="키가 필요한 수집 소스 점검")
    src_sub = src.add_subparsers(dest="sources_cmd", required=True)
    chk = src_sub.add_parser("check", help="키 유무(값 미표시)·허용목록·왕복 1회")
    chk.add_argument(
        "--source",
        help="쉼표로 구분 (기본: scienceon,ntis,kipris,g2b; 추가 가능: ntis_reports,ntis_insights)",
    )
    chk.add_argument("--json", action="store_true")
    chk.set_defaults(handler=cmd_sources_check)
    sst = src_sub.add_parser(
        "status", help="자료원별 적재 건수·최근 적재일, 공사 홈페이지 스냅샷 날짜"
    )
    sst.add_argument("--json", action="store_true")
    sst.set_defaults(handler=cmd_sources_status)

    crawl = sub.add_parser("crawl", help="공개 웹 자료 스냅샷 수집 (예약 실행 없음)")
    crawl_sub = crawl.add_subparsers(dest="crawl_cmd", required=True)
    ck = crawl_sub.add_parser(
        "korail", help="공사 홈페이지(info.korail.com) — config/korail_web.yaml 메뉴를 2초 간격으로"
    )
    mode = ck.add_mutually_exclusive_group(required=True)
    mode.add_argument("--explore", action="store_true", help="메뉴별 건수·기간·첨부 형식만 조사")
    mode.add_argument(
        "--download", action="store_true", help="data/korail_web/snapshots/<오늘>/ 에 저장"
    )
    ck.add_argument(
        "--incremental",
        action="store_true",
        help="이전 스냅샷과 같은 항목은 다시 받지 않고, 사라진 항목은 '원본 삭제됨' 으로 표시",
    )
    ck.add_argument("--json", action="store_true")
    ck.set_defaults(handler=cmd_crawl_korail)
    cn = crawl_sub.add_parser(
        "rnd-notice",
        help="정부 R&D 사업공고(KAIA·IRIS 국토교통부) — config/rnd_notice.yaml, 최근 2년·상한 500",
    )
    nmode = cn.add_mutually_exclusive_group(required=True)
    nmode.add_argument("--explore", action="store_true", help="사이트별 건수·robots·표본만")
    nmode.add_argument(
        "--download", action="store_true", help="data/rnd_notice/snapshots/<오늘>/ 에 저장"
    )
    cn.add_argument("--limit", type=int, default=None, help="공고 수 상한 (기본 max_notices)")
    cn.add_argument(
        "--incremental", action="store_true", help="이전 스냅샷과 같은 공고는 다시 받지 않음"
    )
    cn.add_argument("--json", action="store_true")
    cn.set_defaults(handler=cmd_crawl_rnd_notice)

    notices = sub.add_parser("notices", help="정부 R&D 공고 — 입력과 맞는 접수 중 공고 (#13 선행)")
    notices_sub = notices.add_subparsers(dest="notices_cmd", required=True)
    nm = notices_sub.add_parser("match", help="① 입력 → 접수 중 공고 상위 3건 (LLM 없음)")
    for slot in SLOTS:
        nm.add_argument(f"--{slot.replace('_', '-')}", dest=slot, default="")
    nm.add_argument("--file", help="5슬롯이 담긴 yaml/json 파일")
    nm.add_argument("--json", action="store_true")
    nm.set_defaults(handler=cmd_notices_match)
    cb = crawl_sub.add_parser(
        "bai",
        help=(
            "감사원 감사결과 전문 PDF — config/bai.yaml 질의를 Playwright 공개 화면 조작으로 "
            "(2초 간격, /api/ 직접 호출 없음)"
        ),
    )
    cb.add_argument(
        "--incremental", action="store_true", help="같은 날 스냅샷에 이미 받은 항목은 건너뛴다"
    )
    cb.add_argument("--json", action="store_true")
    cb.set_defaults(handler=cmd_crawl_bai)

    strat = sub.add_parser("strategy", help="전략체계 목록 — 초안 추출·확정")
    strat_sub = strat.add_subparsers(dest="strategy_cmd", required=True)
    sd = strat_sub.add_parser(
        "draft", help="공사 홈페이지 중장기 경영목표 표 → korail_strategy.draft.yaml"
    )
    sd.add_argument("--key", help="contents.do key (기본: korail_web.yaml 의 mgmt_goal)")
    sd.add_argument("--out", help="저장 경로 (기본 config/templates/korail_strategy.draft.yaml)")
    sd.set_defaults(handler=cmd_strategy_draft)
    sp = strat_sub.add_parser(
        "promote", help="초안을 korail_strategy.yaml 로 (백업 유지, 사람만 실행)"
    )
    sp.set_defaults(handler=cmd_strategy_promote)

    vis = sub.add_parser("vision", help="웹 이미지 판독 (P3): OCR 대조 + Argon, 캐시·상한")
    vis_sub = vis.add_subparsers(dest="vision_cmd", required=True)
    ve = vis_sub.add_parser(
        "extract", help="첨부 속 내장 이미지 추출 → attachment_images.jsonl (판독 전)"
    )
    ve.add_argument("--snapshot", help="data/korail_web/snapshots/<date> (기본: 최신)")
    ve.add_argument("--limit", type=int, help="처리 첨부 수 상한 (시험용)")
    ve.add_argument("--json", action="store_true")
    ve.set_defaults(handler=cmd_vision_extract)
    vr = vis_sub.add_parser("read", help="스냅샷 이미지 판독 (--dry-run: 계획만, 호출 없음)")
    vr.add_argument("--snapshot", help="data/korail_web/snapshots/<date> (기본: 최신)")
    vr.add_argument("--dry-run", action="store_true", help="거르기·순서·예상 호출 수만 출력")
    vr.add_argument("--limit", type=int, help="처리 이미지 수 상한 (시험용)")
    vr.add_argument("--cap", type=int, help="Argon 호출 상한 (기본 vision.yaml cap)")
    vr.add_argument("--ocr-only", action="store_true", help="Argon 없이 OCR 만")
    vr.add_argument("--json", action="store_true")
    vr.set_defaults(handler=cmd_vision_read)
    vs = vis_sub.add_parser("sample", help="측정 표본: 종류별 원본·OCR·Argon 나란히 + 요약표")
    vs.add_argument("--snapshot")
    vs.add_argument("--out", help="출력 폴더 (기본 vision.yaml paths.sample = docs/ocr-sample)")
    vs.add_argument("--limit", type=int)
    vs.add_argument("--per-type", type=int, help="종류별 표본 수 (기본 30)")
    vs.add_argument(
        "--cached-only", action="store_true", help="Argon 호출 없이 캐시·OCR 결과만으로"
    )
    vs.set_defaults(handler=cmd_vision_sample)
    vi = vis_sub.add_parser(
        "ingest", help="판독 캐시(OCR·Argon) → DB 적재 (호출 없음, basis=image_vision)"
    )
    vi.add_argument("--snapshot")
    vi.add_argument("--dry-run", action="store_true", help="적재하지 않고 문서·청크 수만")
    vi.add_argument("--limit", type=int)
    vi.add_argument("--json", action="store_true")
    vi.set_defaults(handler=cmd_vision_ingest)

    facts = sub.add_parser(
        "facts", help="표 사실 (P2-8): 적재된 문서의 표 칸 → (항목·연도·단위·값)"
    )
    facts_sub = facts.add_subparsers(dest="facts_cmd", required=True)
    fx = facts_sub.add_parser("extract", help="표 → 사실 저장 (적재 뒤에 실행)")
    fx.add_argument(
        "--source",
        required=True,
        choices=("korail_web", "molit", "vision"),
        help="korail_web=스냅샷 첨부 xlsx·xls·pdf, molit=DB 본문, vision=판독 캐시의 표",
    )
    fx.add_argument("--snapshot", help="korail_web: data/korail_web/snapshots/<date> (기본: 최신)")
    fx.add_argument("--dry-run", action="store_true", help="저장하지 않고 건수만")
    fx.add_argument("--limit", type=int, help="표(첨부·문서) 수 상한 (시험용)")
    fx.add_argument("--json", action="store_true")
    fx.set_defaults(handler=cmd_facts_extract)
    fs = facts_sub.add_parser("search", help="항목으로 사실 검색")
    fs.add_argument("query")
    fs.add_argument("--k", type=int, default=20)
    fs.add_argument("--json", action="store_true")
    fs.set_defaults(handler=cmd_facts_search)

    terms = sub.add_parser("terms", help="용어 후보 (P2-9): 코퍼스 표본의 철도 용어·흔한 단어 후보")
    terms_sub = terms.add_subparsers(dest="terms_cmd", required=True)
    tc = terms_sub.add_parser(
        "candidates", help="config/rail_terms.candidates.yaml·generic_terms.candidates.yaml 쓰기"
    )
    tc.add_argument("--limit", type=int, help="후보 수 상한 (기본 200)")
    tc.add_argument("--sample", type=int, default=5000, help="표본 청크 수 (자료원별로 고르게)")
    tc.add_argument("--out-dir", help="출력 폴더 (기본 config/)")
    tc.set_defaults(handler=cmd_terms_candidates)

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
    gen.add_argument(
        "--priority-evidence",
        dest="priority_evidence",
        help="U5 브리핑에서 고른 근거 id (쉼표) — 검색 집합 안의 것만 우선 근거로",
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
    ra = runs_sub.add_parser("active", help="모든 사용자의 대기·실행 중 run (배포 전 확인)")
    ra.add_argument("--json", action="store_true")
    ra.set_defaults(handler=cmd_runs_active)
    rf = runs_sub.add_parser("figures", help="[G] run 의 그림 목록 (종류·채택 방식·확인 여부)")
    rf.add_argument("run_id")
    rf.add_argument("--json", action="store_true")
    rf.set_defaults(handler=cmd_runs_figures)
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
    rv = runs_sub.add_parser(
        "review", help="③ Argon 1차 검토(draft_review) 시작 — 보통 자동, 키 없으면 건너뜀 기록"
    )
    rv.add_argument("run_id")
    rv.add_argument("--wait", action="store_true", help="검토가 끝날 때까지 기다린다")
    rv.add_argument("--json", action="store_true")
    rv.set_defaults(handler=cmd_runs_review)
    re_ = runs_sub.add_parser("edit", help="④ 편집 반영·저장 → 새 초안 버전 (외부 LLM 없음)")
    re_.add_argument("run_id")
    re_.add_argument("--from", dest="from_file", required=True, help="편집 JSON 파일")
    re_.add_argument("--memo", help="저장 메모 (200자 이내)")
    re_.set_defaults(handler=cmd_runs_edit)
    rd = runs_sub.add_parser("diff", help="두 버전의 섹션·문장 단위 차이")
    rd.add_argument("run_id")
    rd.add_argument("--from", dest="from_v", required=True, help="예: v1")
    rd.add_argument("--to", dest="to_v", required=True, help="예: v3")
    rd.add_argument("--json", action="store_true")
    rd.set_defaults(handler=cmd_runs_diff)
    rst = runs_sub.add_parser("restore", help="이전 버전 내용으로 새 버전을 만든다 (= revert)")
    rst.add_argument("run_id")
    rst.add_argument("--to", required=True, help="예: v2")
    rst.set_defaults(handler=cmd_runs_revert)
    rfr = runs_sub.add_parser(
        "final-review", help="⑤ Argon 최종 검토 — 최신 저장 버전으로 1회 (다시 받기는 같은 명령)"
    )
    rfr.add_argument("run_id")
    rfr.add_argument("--wait", action="store_true", help="검토가 끝날 때까지 기다린다")
    rfr.add_argument(
        "--apply-passed", action="store_true", help="끝난 뒤 검증 통과 수정안을 전부 반영(새 버전)"
    )
    rfr.add_argument("--json", action="store_true")
    rfr.set_defaults(handler=cmd_runs_final_review)
    rol = runs_sub.add_parser("outline", help="③ 섹션 설계도 (pipeline.outline)")
    rol.add_argument("run_id")
    rol.set_defaults(handler=cmd_runs_outline)
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
    rsc = runs_sub.add_parser("submit-check", help="U7 제출 전 점검 체크리스트")
    rsc.add_argument("run_id")
    rsc.add_argument("--json", action="store_true")
    rsc.set_defaults(handler=cmd_runs_submit_check)
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
