"""② 유사과제 확인 v3 측정 (2026-10-28 밤 레인 A, ADR 0039) — 화면과 같은 순서로 골든셋.

화면 순서: POST /v1/precheck?stage=rule(표 먼저) → 곧바로 POST /v1/precheck/judgment 와
POST /v1/precheck/recommendations 를 함께(서버는 같은 판정 작업을 공유하고, 과제안은 AI 판정을 기다려
근거로 쓴다). 잰 것: 표까지·AI 판정까지·첫 카드까지 초, 상위 5 적중(규칙·AI), 거짓 차단, 카드 겹침
(처음 "같다" 수 → 한 번 다시 받은 뒤 남은 경고 수), 겹친 키워드 칸의 낱말.

측정 전용 API 를 따로 띄워 쓴다(운영 일일 카운터와 분리한 설정 사본 RRA_CONFIG_DIR, 포트 8021):

    RRA_CONFIG_DIR=<사본> PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli api --port 8021 &
    .venv/bin/python tools/with_heavy_lock.py -- env PYTHONPATH=src .venv/bin/python \
        tools/eval_precheck_v3.py --base http://127.0.0.1:8021 --out <json> \
        --counter data/cache/llm_budget_laneA.json --stop-at 100

토큰은 settings(.env RRA_API_TOKEN) 또는 RRA_EVAL_TOKEN 에서 읽고 출력하지 않는다. 결과에는 doc_id·건수·
시간·판정만 넣고 본문은 넣지 않는다.
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


def _token() -> str:
    tok = os.environ.get("RRA_EVAL_TOKEN", "")
    if tok:
        return tok
    from rra.settings import load_settings

    s = load_settings()
    return s.api_token.get_secret_value() if s.api_token else ""


def _cases() -> list[tuple[str, dict[str, Any], bool]]:
    out = []
    for p in sorted(GOLDEN.glob("*.yaml")):
        out.append((p.stem, yaml.safe_load(p.read_text(encoding="utf-8")), False))
    for p in sorted((GOLDEN / "not_similar").glob("*.yaml")):
        out.append((f"not_similar/{p.stem}", yaml.safe_load(p.read_text(encoding="utf-8")), True))
    return out


def _count(path: Path) -> int:
    try:
        return int(json.loads(path.read_text(encoding="utf-8")).get("count", 0))
    except (OSError, ValueError):
        return 0


def _top5(alerts: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for a in alerts[:5]:
        ids += [a["doc_id"], *a.get("merged_ids", [])]
    return ids


async def one(c: httpx.AsyncClient, name: str, case: dict[str, Any], not_similar: bool):
    req = {k: case.get(k) or "" for k in REQUEST_KEYS}
    expected = list(case.get("expected_similar") or [])
    must_not = list(case.get("must_not_block") or [])
    t0 = time.monotonic()
    r = await c.post("/v1/precheck?stage=rule", json=req)
    t_table = time.monotonic() - t0
    fast = r.json()

    async def timed(coro):
        out = await coro
        return out, time.monotonic() - t0

    (jr, t_judge), (rr, t_cards) = await asyncio.gather(
        timed(c.post("/v1/precheck/judgment", json=req)),
        timed(c.post("/v1/precheck/recommendations", json=req)),
    )
    judged = jr.json() if jr.status_code == 200 else {}
    rec = (rr.json().get("recommendations") or {}) if rr.status_code == 200 else {}
    alerts = judged.get("alerts") or fast.get("alerts") or []
    blocking = [a["doc_id"] for a in alerts if a.get("blocking")]
    rule_blocking = [a["doc_id"] for a in fast.get("alerts", []) if a.get("blocking")]
    cards = rec.get("recommendations") or []
    if not_similar:
        hit_rule = not set(must_not) & set(rule_blocking)
        hit_ai = not set(must_not) & set(blocking)
        false_block = bool(set(must_not) & set(blocking))
    elif expected:
        hit_rule = bool(set(expected) & set(_top5(fast.get("alerts", []))))
        hit_ai = bool(set(expected) & set(_top5(alerts)))
        false_block = False
    else:  # 정답 없음(03) — 차단 0 이어야
        hit_rule = not rule_blocking
        hit_ai = not blocking
        false_block = bool(blocking)
    return {
        "name": name,
        "not_similar": not_similar,
        "status": [r.status_code, jr.status_code, rr.status_code],
        "table_seconds": round(t_table, 1),
        "judgment_seconds": round(t_judge, 1),
        "cards_seconds": round(t_cards, 1),
        "alerts": len(alerts),
        "rule_blocking": len(rule_blocking),
        "ai_blocking": len(blocking),
        "levels": {
            lv: sum(1 for a in alerts if a.get("level") == lv) for lv in ("blocking", "near", "low")
        },
        "default_unrelated": len(judged.get("default_choices") or []),
        "judged_by": (judged.get("judgment") or {}).get("judged_by"),
        "judgment_status": (judged.get("judgment") or {}).get("status"),
        "hit_rule": hit_rule,
        "hit_ai": hit_ai,
        "false_block": false_block,
        "expected_blocked": len(set(expected) & set(blocking)),
        "cards": len(cards),
        "cards_skipped": rec.get("skipped_reason"),
        "overlap_found": rec.get("overlap_found", 0),
        "overlap_regenerated": rec.get("overlap_regenerated", 0),
        "overlap_after": sum(1 for x in cards if x.get("overlap_titles")),
        "overlap_reason_after": sum(1 for x in cards if x.get("overlap_reason")),
        "difference": [x.get("difference") for x in cards],
        "refs_titled": sum(1 for x in cards for f in x.get("refs", []) if f.get("title")),
        "keywords": sorted({k for a in alerts for k in a.get("keywords", [])}),
        "relevance": [a.get("relevance") for a in alerts],
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8021")
    ap.add_argument("--out", required=True)
    ap.add_argument("--counter", required=True)
    ap.add_argument("--stop-at", type=int, default=100)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    counter = Path(args.counter)
    if not counter.is_absolute():
        counter = ROOT / counter
    headers = {"Authorization": f"Bearer {_token()}"}
    rows = []
    start = _count(counter)
    async with httpx.AsyncClient(base_url=args.base, headers=headers, timeout=None) as c:
        for name, case, ns in _cases():
            if args.only and args.only not in name:
                continue
            before = _count(counter)
            if before >= args.stop_at:
                print(f"stop: counter {before} >= {args.stop_at}", file=sys.stderr)
                break
            row = await one(c, name, case, ns)
            row["gemini_calls"] = _count(counter) - before
            rows.append(row)
            print(json.dumps({k: row[k] for k in list(row)[:12]}, ensure_ascii=False))
    out = {"label": "precheck-v3", "counter_start": start, "counter_end": _count(counter), "rows": rows}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
