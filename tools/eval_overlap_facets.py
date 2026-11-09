"""② 유사과제 고도화 1단계 측정 (2026-11-09 레인 E, ADR 0059) — 스위치 off / facets on / idf on.

골든셋 10건(`tests/golden/*.yaml`) + 유사하지 않음 2건(`not_similar/`)을 `build_precheck`
유스케이스로 직접 돌린다(REST 아님, docs/eval-2026-10-28-precheck.md 와 같은 방식): 실제 e5 +
reranker, 원 저장소 데이터(읽기만), **LLM 호출 없음** — 같음 판정은 규칙(rule_stage), 4축 분해는
규칙 사전(로컬 모델 없음, `facet_split` 규칙만), 핵심어는 아이디어 제목(Argon 키워드 대신
`title_hint`). 잰 것: 상위 5 적중(expected_similar ∩ 행 doc_id·merged_ids), 거짓 차단
(must_not_block·03 차단), 규칙 차단 행 수, 표 줄 수, 벽시계 초(2회 중 최소).

    RRA_HEAVY_LOCK=<원 저장소>/runs/.heavy.lock PYTHONPATH=src .venv/bin/python \\
        tools/with_heavy_lock.py -- .venv/bin/python tools/eval_overlap_facets.py --out <json> \\
        [--modes off,facets,idf] [--repeat 2]

결과 JSON 에는 doc_id·건수·초만 들어간다(본문 없음). idf 모드는 `rra db idf` 로 만든 캐시가 있어야
한다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden"
REQUEST_KEYS = ("title_hint", "current_state", "root_cause", "limitation", "goal")


def _cases() -> list[tuple[str, dict[str, Any], bool]]:
    out = []
    for p in sorted(GOLDEN.glob("*.yaml")):
        out.append((p.stem, yaml.safe_load(p.read_text(encoding="utf-8")), False))
    for p in sorted((GOLDEN / "not_similar").glob("*.yaml")):
        out.append((f"not_similar/{p.stem}", yaml.safe_load(p.read_text(encoding="utf-8")), True))
    return out


def _ids(alerts, n: int) -> list[str]:
    ids: list[str] = []
    for a in alerts[:n]:
        ids += [a.doc_id, *a.merged_ids]
    return ids


async def _one(precheck, name: str, case: dict[str, Any], not_similar: bool, repeat: int):
    from rra.domain.models import ProposalRequest

    req = ProposalRequest(**{k: case.get(k) or "" for k in REQUEST_KEYS})
    core = [req.title_hint or req.goal]
    expected = list(case.get("expected_similar") or [])
    must_not = list(case.get("must_not_block") or [])
    best = None
    seconds: list[float] = []
    for _ in range(repeat):
        t0 = time.monotonic()
        result = await precheck.rule_stage(req, core_keywords=core, keyword_origin="eval")
        seconds.append(time.monotonic() - t0)
        best = result
        precheck._memo.clear()  # 메모 없이 매번 검색
    alerts = best.alerts
    blocking = [i for a in alerts if a.blocking for i in [a.doc_id, *a.merged_ids]]
    top5 = _ids(alerts, 5)
    if not_similar:
        hit = not set(must_not) & set(blocking)
        if expected:
            hit = hit and bool(set(expected) & set(top5))
        false_block = bool(set(must_not) & set(blocking))
    elif expected:
        hit = bool(set(expected) & set(top5))
        false_block = False
    else:
        hit = not blocking
        false_block = bool(blocking)
    rank = None
    for i, a in enumerate(alerts, 1):
        if set(expected) & {a.doc_id, *a.merged_ids}:
            rank = i
            break
    return {
        "name": name,
        "hit5": hit,
        "hit_rank": rank,
        "false_block": false_block,
        "rows": len(alerts),
        "rule_blocking_rows": sum(1 for a in alerts if a.blocking),
        "seconds": round(min(seconds), 2),
        "facets": best.facets.as_dict() if best.facets is not None else None,
        "top5": [a.doc_id for a in alerts[:5]],
    }


async def _run_mode(mode: str, repeat: int, only: str) -> dict[str, Any]:
    from rra.application.usecases.facet_split import FacetSplitter
    from rra.composition import apply_overlap_switches, build_precheck, load_settings
    from rra.config_loader import keyword_rule
    from rra.domain.rules.overlap_switches import OverlapSwitches

    settings = load_settings()
    precheck = build_precheck(settings)
    sw = OverlapSwitches(facets=mode == "facets", idf_weighting=mode == "idf")
    precheck = apply_overlap_switches(precheck, settings, switches=sw, local_llm=None)
    if sw.facets:  # 로컬 모델 없이 규칙 분해만 (측정 재현성)
        precheck.facet_split = FacetSplitter(local=None, keyword_rule=keyword_rule(settings))
    rows = []
    for name, case, ns in _cases():
        if only and only not in name:
            continue
        row = await _one(precheck, name, case, ns, repeat)
        rows.append(row)
        print(
            mode,
            json.dumps(
                {k: row[k] for k in ("name", "hit5", "hit_rank", "false_block", "seconds")},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
    return {
        "mode": mode,
        "idf_loaded": getattr(precheck, "idf", None) is not None,
        "hits": sum(1 for r in rows if r["hit5"]),
        "false_blocks": sum(1 for r in rows if r["false_block"]),
        "median_seconds": round(statistics.median(r["seconds"] for r in rows), 2) if rows else None,
        "rows": rows,
    }


async def main_async(args) -> dict[str, Any]:
    out = {"label": "overlap-facets", "modes": []}
    for mode in [m.strip() for m in args.modes.split(",") if m.strip()]:
        out["modes"].append(await _run_mode(mode, args.repeat, args.only))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--modes", default="off,facets,idf")
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    result = asyncio.run(main_async(args))
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    for m in result["modes"]:
        print(
            f"{m['mode']}: 적중 {m['hits']}/{len(m['rows'])} · 거짓 차단 {m['false_blocks']} · "
            f"중앙 {m['median_seconds']}s · idf {m['idf_loaded']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
