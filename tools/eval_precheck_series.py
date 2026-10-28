"""② 같은 연작 한 줄 측정 (2026-10-29 레인 A, ADR 0043) — 골든셋 10건 + 유사하지 않음 2건.

화면 순서의 앞 두 단계만 돈다: POST /v1/precheck?stage=rule(표 먼저) → POST /v1/precheck/judgment
(AI 같음 판정). 과제안·생성은 하지 않는다. 잰 것: 표 줄 수·연작 줄 수·상위 10 의 서로 다른 과제 수
(연작 키 기준 — 묶기 전 코드와 같은 잣대), 상위 5 적중(행 doc_id 또는 merged_ids), 거짓 차단
(must_not_block), 표까지·판정까지 초, 08 상위 10 제목.

측정 전용 API 를 따로 띄운다(설정 사본 RRA_CONFIG_DIR — 일일 카운터 분리):

    RRA_CONFIG_DIR=<사본> PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli api --port 8041 &
    .venv/bin/python tools/with_heavy_lock.py -- env PYTHONPATH=src .venv/bin/python \\
        tools/eval_precheck_series.py --base http://127.0.0.1:8041 --out <json> \\
        --counter data/cache/llm_budget_lane3A.json --stop-at 55 [--expected08 <json>]

--expected08: 08 정답을 넓힌 doc_id 목록(JSON 배열) — 골든셋 파일을 고치지 않고 측정만 한다.
토큰은 RRA_EVAL_TOKEN 또는 settings(.env RRA_API_TOKEN) 에서 읽고 출력하지 않는다. 결과에는
doc_id·건수·시간·판정·제목만 넣고 본문은 넣지 않는다.
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

from rra.domain.rules.series import series_key

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


def _ids(alerts: list[dict[str, Any]], n: int) -> list[str]:
    ids: list[str] = []
    for a in alerts[:n]:
        ids += [a["doc_id"], *a.get("merged_ids", [])]
    return ids


def _shown(a: dict[str, Any]) -> str:
    s = a.get("series")
    return s["display"] if s else a["title"]


async def one(
    c: httpx.AsyncClient, name: str, case: dict[str, Any], not_similar: bool, extra: list[str]
) -> dict[str, Any]:
    req = {k: case.get(k) or "" for k in REQUEST_KEYS}
    expected = list(case.get("expected_similar") or [])
    base = list(expected)  # 골든셋 파일의 정답만 (넓히기 전)
    if name.startswith("08") and extra:
        expected = list(dict.fromkeys([*expected, *extra]))
    must_not = list(case.get("must_not_block") or [])
    t0 = time.monotonic()
    r = await c.post("/v1/precheck?stage=rule", json=req)
    t_table = time.monotonic() - t0
    fast = r.json() if r.status_code == 200 else {}
    jr = await c.post("/v1/precheck/judgment", json=req)
    t_judge = time.monotonic() - t0
    judged = jr.json() if jr.status_code == 200 else {}
    alerts = judged.get("alerts") or fast.get("alerts") or []
    blocking = [i for a in alerts if a.get("blocking") for i in [a["doc_id"], *a["merged_ids"]]]
    top10 = alerts[:10]
    keys = {series_key(a["title"]) or a["doc_id"] for a in top10}
    if not_similar:
        hit = not set(must_not) & set(blocking)
        if expected:
            hit = hit and bool(set(expected) & set(_ids(alerts, 5)))
        false_block = bool(set(must_not) & set(blocking))
    elif expected:
        hit = bool(set(expected) & set(_ids(alerts, 5)))
        false_block = False
    else:  # 정답 없음(03) — 차단 0 이어야
        hit = not blocking
        false_block = bool(blocking)
    hit_base = bool(set(base) & set(_ids(alerts, 5))) if base else hit
    hit_rank = None
    for i, a in enumerate(alerts, 1):
        if set(expected) & {a["doc_id"], *a.get("merged_ids", [])}:
            hit_rank = i
            break
    live = fast.get("live_search") or {}
    return {
        "name": name,
        "status": [r.status_code, jr.status_code],
        "table_seconds": round(t_table, 1),
        "judgment_seconds": round(t_judge, 1),
        "rows": len(alerts),
        "series_rows": sum(1 for a in alerts if a.get("series")),
        "series_members": sum(len(a["series"]["members"]) for a in alerts if a.get("series")),
        "distinct_top10": len(keys),
        "merged_docs": sum(len(a.get("merged_ids", [])) for a in alerts),
        "hit5": hit,
        "hit5_base": hit_base,
        "hit_rank": hit_rank,
        "false_block": false_block,
        "blocking_rows": sum(1 for a in alerts if a.get("blocking")),
        "judgment_status": (judged.get("judgment") or {}).get("status"),
        "judged_by": (judged.get("judgment") or {}).get("judged_by"),
        "live_status": live.get("status"),
        "top10": [
            {
                "doc_id": a["doc_id"],
                "shown": _shown(a),
                "source": a.get("source_label"),
                "merged": len(a.get("merged_ids", [])),
                "judgment": a.get("judgment"),
                "level": a.get("level"),
            }
            for a in top10
        ],
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8041")
    ap.add_argument("--out", required=True)
    ap.add_argument("--counter", required=True)
    ap.add_argument("--stop-at", type=int, default=55)
    ap.add_argument("--only", default="")
    ap.add_argument("--label", default="precheck-series")
    ap.add_argument("--expected08", default="")
    args = ap.parse_args()
    counter = Path(args.counter)
    if not counter.is_absolute():
        counter = ROOT / counter
    extra: list[str] = []
    if args.expected08:
        extra = list(json.loads(Path(args.expected08).read_text(encoding="utf-8")))
    headers = {"Authorization": f"Bearer {_token()}"}
    rows = []
    start = _count(counter)
    async with httpx.AsyncClient(base_url=args.base, headers=headers, timeout=None) as c:  # noqa: S113 — AI 판정은 제한 시간 없음
        for name, case, ns in _cases():
            if args.only and args.only not in name:
                continue
            before = _count(counter)
            if before >= args.stop_at:
                print(f"stop: counter {before} >= {args.stop_at}", file=sys.stderr)
                break
            row = await one(c, name, case, ns, extra)
            row["gemini_calls"] = _count(counter) - before
            rows.append(row)
            print(json.dumps({k: row[k] for k in list(row)[:15]}, ensure_ascii=False))
    out = {
        "label": args.label,
        "counter_start": start,
        "counter_end": _count(counter),
        "expected08_extra": len(extra),
        "rows": rows,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
