"""시범 오류·개선 17건 배포 기준 측정 (2026-10-28, 통합 담당) — 운영과 같은 REST 흐름으로 골든셋.

동료가 화면에서 하는 순서 그대로: ② POST /v1/precheck(실시간 검색·AI 같음 판정·자동 과제 추천) →
③ 보강 질문의 정책적 중요도 작성안 첫 안 고르기(POST /v1/ideas/policy-cards) → POST /v1/runs →
초안 → 12섹션 AI 다시 쓰기 후보·보완 질문 → ⑤ 최종 검토 → ⑥ 마무리(HWPX 서식 점검은 manifest
hwpx_format). "유사하지 않음" 사례(tests/golden/not_similar)는 ② 만.

측정 전용 API 를 따로 띄워 쓴다(운영 일일 카운터와 분리한 설정 사본 RRA_CONFIG_DIR, 포트 8012):

    RRA_CONFIG_DIR=<사본> .venv/bin/rra api --port 8012 &
    .venv/bin/python tools/with_heavy_lock.py -- .venv/bin/python tools/eval_pilot_fixes.py \
        --base http://127.0.0.1:8012 --out data/eval/pilot_fixes.json

토큰은 settings(.env RRA_API_TOKEN) 또는 RRA_EVAL_TOKEN 에서 읽고 출력하지 않는다. 결과에 본문·근거
원문은 넣지 않는다(건수·상태·시간·사유 코드만).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden"
SECTIONS = (
    "title",
    "task_type",
    "policy_importance",
    "tech_importance",
    "strategy_alignment",
    "objective",
    "method",
    "expected_management",
    "expected_technology",
    "expected_standing",
    "utilization",
    "overlap_review",
)
REQUEST_KEYS = (
    "title_hint",
    "current_state",
    "root_cause",
    "limitation",
    "goal",
    "constraints",
    "policy_basis",
    "beneficiaries",
    "remarks",
)
WAITING = {"queued", "running", "draft_reviewing", "final_reviewing"}


def _token() -> str:
    tok = os.environ.get("RRA_EVAL_TOKEN")
    if tok:
        return tok
    sys.path.insert(0, str(ROOT / "src"))
    from rra.settings import Settings

    secret = Settings().api_token
    if secret is None:
        raise SystemExit("RRA_API_TOKEN 이 없습니다.")
    return secret.get_secret_value()


def load_ideas(
    only: list[str] | None,
) -> list[tuple[str, dict[str, Any], list[str] | None, bool, list[str]]]:
    """(이름, 요청, 정답 유사과제, 유사하지 않음 사례 여부, 막으면 안 되는 과제)."""
    out = []
    for path in sorted(GOLDEN.glob("*.yaml")) + sorted((GOLDEN / "not_similar").glob("*.yaml")):
        name = ("ns_" if path.parent.name == "not_similar" else "") + path.stem
        if only and not any(name.startswith(o) for o in only):
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        req = {k: str(raw.get(k) or "") for k in REQUEST_KEYS}
        expected = raw.get("expected_similar")
        not_similar = path.parent.name == "not_similar"
        must_not = [str(x) for x in raw.get("must_not_block") or []]
        out.append(
            (name, req, list(expected) if expected is not None else None, not_similar, must_not)
        )
    return out


def _alert_ids(alert: dict[str, Any]) -> list[str]:
    return [str(alert.get("doc_id"))] + [str(x) for x in alert.get("merged_ids") or []]


def _rec_items(rec: Any) -> list[Any]:
    if not isinstance(rec, dict):
        return []
    for key in ("items", "recommendations", "cards"):
        if isinstance(rec.get(key), list):
            return rec[key]
    return []


class Driver:
    def __init__(self, base: str, token: str, *, timeout: float = 900.0):
        self.c = httpx.AsyncClient(
            base_url=base, headers={"X-RRA-Token": token}, timeout=httpx.Timeout(timeout)
        )

    async def close(self) -> None:
        await self.c.aclose()

    async def j(self, method: str, url: str, **kw: Any) -> tuple[int, Any]:
        r = await self.c.request(method, url, **kw)
        try:
            body = r.json()
        except ValueError:
            body = None
        return r.status_code, body

    async def wait_status(self, rid: str, *, limit: float = 1200.0) -> dict[str, Any]:
        t0 = time.perf_counter()
        while True:
            code, run = await self.j("GET", f"/v1/runs/{rid}")
            if code == 200 and run.get("status") not in WAITING:
                return run
            if time.perf_counter() - t0 > limit:
                return run if isinstance(run, dict) else {"status": "timeout"}
            await asyncio.sleep(2)

    async def precheck(
        self,
        req: dict[str, Any],
        expected: list[str] | None,
        not_similar: bool,
        must_not: list[str] | None = None,
    ) -> dict[str, Any]:
        """② 화면 순서(2026-10-28 밤, 레인 A): 표 먼저(stage=rule) → AI 판정·과제안 동시.
        점수 규칙(소유자 지시): 정답 밖에서 걸린 과제는 오답이 아니라 "새로 찾은 후보"
        (제목·자료원·판정 이유)로만 보고, API 실패·IP 차단으로 빠진 결과는 따로 표시하고
        점수에서 뺀다."""
        t = time.perf_counter()
        code, fast = await self.j("POST", "/v1/precheck?stage=rule", json=req)
        out: dict[str, Any] = {
            "precheck_status": code,
            "table_seconds": round(time.perf_counter() - t, 1),
        }
        if code != 200 or not isinstance(fast, dict):
            out["excluded"] = f"precheck {code}"
            return out

        async def timed(method: str, url: str) -> tuple[int, Any, float]:
            c, b = await self.j(method, url, json=req)
            return c, b, round(time.perf_counter() - t, 1)

        (jc, judged, t_judge), (rc, recb, t_cards) = await asyncio.gather(
            timed("POST", "/v1/precheck/judgment"), timed("POST", "/v1/precheck/recommendations")
        )
        out.update(judgment_status=jc, judgment_seconds=t_judge, cards_seconds=t_cards)
        out["precheck_seconds"] = max(t_judge, t_cards)
        body = judged if jc == 200 and isinstance(judged, dict) else fast
        judgment = body.get("judgment") or {}
        alerts = body.get("alerts") or []
        blocking = [a for a in alerts if a.get("blocking")]
        top5 = [i for a in alerts[:5] for i in _alert_ids(a)]
        # 실시간 검색 상태는 표 먼저 응답(stage=rule)에 있다 — 판정 응답의 live_search 는 비어 "off"
        live = fast.get("live_search") or body.get("live_search") or {}
        live_fail = [
            {"source": s.get("source"), "status": s.get("status")}
            for s in live.get("sources") or []
            if s.get("status") not in ("ok", "cached", "empty", "off", None)
        ]
        out["live"] = live.get("status")
        out["live_failures"] = live_fail
        if jc != 200 or judgment.get("status") in ("error", "failed"):
            out["excluded"] = f"AI 판정 실패({jc}, {judgment.get('status')})"
        exp = set(expected or [])
        bad = set(must_not or [])
        out["false_block"] = sum(1 for a in blocking if set(_alert_ids(a)) & bad)
        if expected:
            hit: bool | None = any(d in top5 for d in expected)
        elif expected == []:  # 정답 없음(03) — 차단이 없어야 적중
            hit = not blocking
        else:
            hit = None
        out["new_candidates"] = [
            {
                "title": a.get("title"),
                "source": a.get("source_label") or a.get("source"),
                "level": a.get("level_label"),
                "reason": a.get("judgment_reason"),
            }
            for a in blocking
            if not (set(_alert_ids(a)) & (exp | bad))
        ]
        out["blocking_detail"] = [
            {
                "doc_id": a.get("doc_id"),
                "title": a.get("title"),
                "expected": bool(set(_alert_ids(a)) & exp),
                "rerank": a.get("rerank_score"),
                "judgment": a.get("judgment"),
                "reason": a.get("judgment_reason"),
            }
            for a in blocking
        ]
        rec = (recb or {}).get("recommendations") if rc == 200 and isinstance(recb, dict) else None
        # 제안자처럼 고른다: 정답 유사과제는 [유사함], 나머지 차단 행은 [관련 없음]
        choices = []
        for a in alerts:
            ids = set(_alert_ids(a))
            if ids & exp:
                choices.append({"doc_id": a["doc_id"], "choice": "similar"})
            elif a.get("blocking"):
                choices.append({"doc_id": a["doc_id"], "choice": "unrelated"})
        out["_choices"] = choices
        out["similar_chosen"] = sum(1 for c in choices if c["choice"] == "similar")
        cards = _rec_items(rec)
        out.update(
            alerts=len(alerts),
            blocking=len(blocking),
            levels={
                lv: sum(1 for a in alerts if a.get("level") == lv)
                for lv in ("blocking", "near", "low")
            },
            hit=hit,
            judged_by=judgment.get("judged_by"),
            judgment_state=judgment.get("status"),
            recommendations=len(cards),
            recommendation_status=(rec or {}).get("status") if isinstance(rec, dict) else rc,
            recommendation_overlap_after=sum(1 for x in cards if x.get("overlap_titles")),
        )
        return out

    async def policy_choice(
        self, req: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        if req.get("policy_basis"):
            return None, {"policy_cards": None, "policy_mode": "input"}
        code, body = await self.j("POST", "/v1/ideas/policy-cards", json=req)
        cards = (body or {}).get("cards") or [] if code == 200 else []
        info = {
            "policy_cards": len(cards),
            "policy_cards_status": (body or {}).get("status") if code == 200 else code,
        }
        if not cards:
            info["policy_mode"] = "none"
            return {"mode": "none", "sentences": [], "sources": []}, info
        c = cards[0]
        info["policy_mode"] = "card"
        info["policy_direction"] = c.get("direction")
        return {
            "mode": "card",
            "card_ids": [c["id"]],
            "sentences": c["sentences"],
            "sources": c["sources"],
        }, info

    async def sections(self, rid: str) -> dict[str, Any]:
        rewrite: dict[str, Any] = {}
        questions: dict[str, Any] = {}
        t = time.perf_counter()
        for key in SECTIONS:
            t1 = time.perf_counter()
            code, body = await self.j("POST", f"/v1/runs/{rid}/sections/{key}/rewrite")
            b = body if isinstance(body, dict) else {}
            n = b.get("new_count")
            if n is None:
                n = len(b.get("candidates") or b.get("sentences") or [])
            writer = b.get("writer") or {}
            rewrite[key] = {
                "status": code,
                "new": n,
                "reason": b.get("reason"),
                "mode": b.get("mode"),
                "provider": writer.get("provider") if isinstance(writer, dict) else None,
                "seconds": round(time.perf_counter() - t1, 1),
            }
            t2 = time.perf_counter()
            code, body = await self.j("GET", f"/v1/runs/{rid}/sections/{key}/questions")
            b = body if isinstance(body, dict) else {}
            questions[key] = {
                "status": code,
                "count": len(b.get("questions") or []),
                "source": b.get("source"),
                "reason": b.get("reason"),
                "seconds": round(time.perf_counter() - t2, 1),
            }
        return {
            "rewrite": rewrite,
            "questions": questions,
            "sections_seconds": round(time.perf_counter() - t, 1),
        }

    async def one(
        self,
        name: str,
        req: dict[str, Any],
        expected: list[str] | None,
        not_similar: bool,
        *,
        full: bool,
        sweep: bool = True,
        must_not: list[str] | None = None,
    ) -> dict[str, Any]:
        row: dict[str, Any] = {"name": name, "not_similar": not_similar}
        row.update(await self.precheck(req, expected, not_similar, must_not))
        if not_similar:
            row.pop("_choices", None)
            return row
        choice, info = await self.policy_choice(req)
        row.update(info)
        choices = row.pop("_choices", [])
        body = {**req, "acknowledged": True}
        if choices:
            body["similar_choices"] = choices
        if choice is not None:
            body["policy_choice"] = choice
        t0 = time.perf_counter()
        code, run = await self.j("POST", "/v1/runs", json=body)
        if code != 202:
            row.update(
                run_status=code,
                run_error=(run or {}).get("detail") if isinstance(run, dict) else None,
            )
            return row
        rid = run["run_id"]
        row["run_id"] = rid
        run = await self.wait_status(rid)
        row["draft_seconds"] = round(time.perf_counter() - t0, 1)
        row["status"] = run.get("status")
        row["writer"] = run.get("writer")
        row["local_sections"] = len(run.get("local_sections") or [])
        code, draft = await self.j("GET", f"/v1/runs/{rid}/draft")
        secs = (draft or {}).get("sections") or [] if code == 200 else []
        by_key = {s.get("key"): s for s in secs}
        pol = by_key.get("policy_importance") or {}
        row["policy_sentences"] = len(pol.get("sentences") or [])
        row["empty_sections"] = [
            k for k in SECTIONS if k in by_key and not (by_key[k].get("sentences") or [])
        ]
        row["failed_sections"] = (
            len((draft or {}).get("failed_sections") or []) if code == 200 else None
        )
        row["sentences"] = sum(len(s.get("sentences") or []) for s in secs)
        row["figures"] = len((draft or {}).get("figures") or []) if code == 200 else None
        if full and sweep and row["status"] in ("drafted", "editing"):
            row.update(await self.sections(rid))
        if full:
            code, _ = await self.j("POST", f"/v1/runs/{rid}/final-review")
            run = await self.wait_status(rid)
            row["final_status"] = run.get("status")
            code, fin = await self.j(
                "POST", f"/v1/runs/{rid}/finalize", json={"department": "철도연구원"}
            )
            row["finalize_status"] = code
            manifest = _manifest(rid)
            row["hwpx_format"] = manifest.get("hwpx_format")
            # [23] 그림이 본문 폭에 맞게 들어감 — 넣은 그림마다 마무리 때 HWPX 실측(figure_fit)
            figs = [f for f in manifest.get("figures") or [] if f.get("included", True)]
            row["figure_fit"] = [
                {
                    k: (f.get("figure_fit") or {}).get(k)
                    for k in ("ratio", "width_mm", "height_mm", "fits", "min_text_pt", "text_ok")
                }
                | {"kind": f.get("kind"), "renderer": f.get("renderer")}
                for f in figs
            ]
        return row


def colleague_active(own: set[str]) -> int:
    """동료 run(측정이 만든 것 제외) 중 대기·실행 중인 수 — runs/<사용자>/<run>/state.json."""
    n = 0
    for path in (ROOT / "runs").glob("*/*/state.json"):
        if path.parent.name in own:
            continue
        try:
            status = json.loads(path.read_text(encoding="utf-8")).get("status")
        except (OSError, ValueError):
            continue
        if status in ("queued", "running"):
            n += 1
    return n


async def wait_quiet(own: set[str], *, limit: float = 5400.0) -> float:
    """동료 생성이 있으면 끝날 때까지 기다린다(시범 규칙: 동료가 쓰는 동안 mlx 측정 금지)."""
    t0 = time.perf_counter()
    while colleague_active(own) and time.perf_counter() - t0 < limit:
        await asyncio.sleep(30)
    return round(time.perf_counter() - t0, 1)


def _manifest(rid: str) -> dict[str, Any]:
    for path in (ROOT / "runs").glob(f"*/{rid}/manifest.json"):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    return {}


async def _concurrent(d: Driver, ideas: list[Any], out: Path, label: str) -> int:
    """여러 건을 동시에 ② → 생성(초안까지). 각 건 시간과 묶음 전체 시간."""
    await wait_quiet(set())
    t0 = time.perf_counter()
    started = time.strftime("%Y-%m-%dT%H:%M:%S")

    async def go(idea: Any) -> dict[str, Any]:
        name, req, expected, ns, must_not = idea
        t = time.perf_counter()
        row = await d.one(name, req, expected, ns, full=False, must_not=must_not)
        row["seconds"] = round(time.perf_counter() - t, 1)
        return row

    try:
        rows = await asyncio.gather(*(go(i) for i in ideas))
    finally:
        await d.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "label": label,
                "started_at": started,
                "concurrent": len(ideas),
                "batch_seconds": round(time.perf_counter() - t0, 1),
                "rows": rows,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    for r in rows:
        print(
            json.dumps(
                {k: r.get(k) for k in ("name", "status", "draft_seconds")}, ensure_ascii=False
            )
        )
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://127.0.0.1:8012")
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", help="이름 접두어 쉼표 구분 (예: 01,ns_)")
    ap.add_argument(
        "--gen-only", action="store_true", help="② + 생성만 (다시 쓰기·보완 질문·검토·마무리 생략)"
    )
    ap.add_argument("--label", default="pilot_fixes")
    ap.add_argument(
        "--sweep", default="", help="12섹션 다시 쓰기·보완 질문을 할 이름 접두어(쉼표). 비면 전부"
    )
    ap.add_argument(
        "--append",
        action="store_true",
        help="--out 의 기존 결과에 이어 붙이고 있는 이름은 건너뛴다",
    )
    ap.add_argument(
        "--concurrent",
        type=int,
        default=0,
        help="N 건을 동시에(② + 생성만) — 동시 생성 시간 측정. 0 이면 한 건씩",
    )
    args = ap.parse_args()
    only = [s.strip() for s in args.only.split(",")] if args.only else None
    ideas = load_ideas(only)
    d = Driver(args.base, _token())
    if args.concurrent > 0:
        return await _concurrent(d, ideas[: args.concurrent], Path(args.out), args.label)
    rows: list[dict[str, Any]] = []
    out = Path(args.out)
    if args.append and out.exists():
        rows = json.loads(out.read_text(encoding="utf-8")).get("rows") or []
        done = {r["name"] for r in rows}
        ideas = [i for i in ideas if i[0] not in done]
    sweep = [x.strip() for x in args.sweep.split(",") if x.strip()]
    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        own: set[str] = set()
        for name, req, expected, ns, must_not in ideas:
            waited = await wait_quiet(own)
            t = time.perf_counter()
            do_sweep = not sweep or any(name.startswith(x) for x in sweep)
            row = await d.one(
                name, req, expected, ns, full=not args.gen_only, sweep=do_sweep, must_not=must_not
            )
            row["seconds"] = round(time.perf_counter() - t, 1)
            row["waited_for_colleagues"] = waited
            if row.get("run_id"):
                own.add(row["run_id"])
            rows.append(row)
            print(
                json.dumps(
                    {
                        k: row.get(k)
                        for k in (
                            "name",
                            "hit",
                            "false_block",
                            "recommendations",
                            "status",
                            "draft_seconds",
                            "policy_sentences",
                            "seconds",
                        )
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            out.write_text(
                json.dumps(
                    {"label": args.label, "started_at": started, "rows": rows},
                    ensure_ascii=False,
                    indent=1,
                ),
                encoding="utf-8",
            )
    finally:
        await d.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
