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


def load_ideas(only: list[str] | None) -> list[tuple[str, dict[str, Any], list[str] | None, bool]]:
    """(이름, 요청, 정답 유사과제, 유사하지 않음 사례 여부)."""
    out = []
    for path in sorted(GOLDEN.glob("*.yaml")) + sorted((GOLDEN / "not_similar").glob("*.yaml")):
        name = ("ns_" if path.parent.name == "not_similar" else "") + path.stem
        if only and not any(name.startswith(o) for o in only):
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        req = {k: str(raw.get(k) or "") for k in REQUEST_KEYS}
        expected = raw.get("expected_similar")
        not_similar = path.parent.name == "not_similar"
        out.append((name, req, list(expected) if expected is not None else None, not_similar))
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
        self, req: dict[str, Any], expected: list[str] | None, not_similar: bool
    ) -> dict[str, Any]:
        t = time.perf_counter()
        code, body = await self.j("POST", "/v1/precheck", json=req)
        out: dict[str, Any] = {
            "precheck_status": code,
            "precheck_seconds": round(time.perf_counter() - t, 1),
        }
        if code != 200 or not isinstance(body, dict):
            return out
        alerts = body.get("alerts") or []
        blocking = [a for a in alerts if a.get("blocking")]
        top5 = [i for a in alerts[:5] for i in _alert_ids(a)]
        if not_similar or expected == []:
            hit = not blocking
        elif expected:
            hit = any(d in top5 for d in expected)
        else:
            hit = None
        rec = body.get("recommendations")
        # 제안자처럼 고른다: 정답 유사과제가 표에 있으면 [유사함], 나머지 차단 행은 [관련 없음]
        choices = []
        for a in alerts:
            ids = set(_alert_ids(a))
            if expected and ids & set(expected):
                choices.append({"doc_id": a["doc_id"], "choice": "similar"})
            elif a.get("blocking"):
                choices.append({"doc_id": a["doc_id"], "choice": "unrelated"})
        out["_choices"] = choices
        out["similar_chosen"] = sum(1 for c in choices if c["choice"] == "similar")
        out.update(
            alerts=len(alerts),
            blocking=len(blocking),
            blocking_expected=sum(
                1 for a in blocking if expected and set(_alert_ids(a)) & set(expected)
            ),
            blocking_unrelated=sum(
                1 for a in blocking if not (expected and set(_alert_ids(a)) & set(expected))
            ),
            hit=hit,
            judged_by=(body.get("judgment") or {}).get("judged_by"),
            judgment_status=(body.get("judgment") or {}).get("status"),
            recommendations=len(_rec_items(rec)),
            recommendation_status=(rec or {}).get("status") if isinstance(rec, dict) else None,
            recommendation_discarded=len((rec or {}).get("discarded") or [])
            if isinstance(rec, dict)
            else 0,
            recommendation_regenerated=bool((rec or {}).get("regenerated"))
            if isinstance(rec, dict)
            else False,
            live=(body.get("live_search") or {}).get("status"),
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
            code, body = await self.j("POST", f"/v1/runs/{rid}/sections/{key}/rewrite")
            b = body if isinstance(body, dict) else {}
            n = b.get("new_count")
            if n is None:
                n = len(b.get("candidates") or b.get("sentences") or [])
            rewrite[key] = {
                "status": code,
                "new": n,
                "reason": b.get("reason"),
                "mode": b.get("mode"),
                "writer": b.get("writer"),
            }
            code, body = await self.j("GET", f"/v1/runs/{rid}/sections/{key}/questions")
            b = body if isinstance(body, dict) else {}
            qs = b.get("questions") or []
            questions[key] = {
                "status": code,
                "count": len(qs),
                "source": b.get("source"),
                "reason": b.get("reason"),
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
    ) -> dict[str, Any]:
        row: dict[str, Any] = {"name": name, "not_similar": not_similar}
        row.update(await self.precheck(req, expected, not_similar))
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
        if full and row["status"] in ("drafted", "editing"):
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
        return row


def _manifest(rid: str) -> dict[str, Any]:
    for path in (ROOT / "runs").glob(f"*/{rid}/manifest.json"):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    return {}


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://127.0.0.1:8012")
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", help="이름 접두어 쉼표 구분 (예: 01,ns_)")
    ap.add_argument(
        "--gen-only", action="store_true", help="② + 생성만 (다시 쓰기·보완 질문·검토·마무리 생략)"
    )
    ap.add_argument("--label", default="pilot_fixes")
    args = ap.parse_args()
    only = [s.strip() for s in args.only.split(",")] if args.only else None
    ideas = load_ideas(only)
    d = Driver(args.base, _token())
    rows: list[dict[str, Any]] = []
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        for name, req, expected, ns in ideas:
            t = time.perf_counter()
            row = await d.one(name, req, expected, ns, full=not args.gen_only)
            row["seconds"] = round(time.perf_counter() - t, 1)
            rows.append(row)
            print(
                json.dumps(
                    {
                        k: row.get(k)
                        for k in (
                            "name",
                            "hit",
                            "blocking_unrelated",
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
