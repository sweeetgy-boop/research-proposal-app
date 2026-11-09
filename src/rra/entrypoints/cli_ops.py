"""`rra ops` 서브명령 — 운영 점검 (계약 docs/contracts/healthz-status.md §3, ADR 0062, 레인 C).

cli.py 는 공용 파일이라 여기서 `register(sub)` 로 파서를 더한다 (통합 때 cli.py 에
`from rra.entrypoints.cli_ops import register as register_ops` + `register_ops(sub)` 두 줄).
`rra ops check`: tailscale status/funnel status + 로컬 모델 GET /v1/models(5초) 1회 →
data/cache/ops_status.json. 출력은 열거값 한 줄 — IP·호스트명·명령 출력 원문은 어디에도 남기지
않는다. 읽기만 한다(설정·서비스 변경 없음).
"""

from __future__ import annotations

import argparse
import json

EXIT_OK = 0


def cmd_ops_check(args: argparse.Namespace) -> int:
    from rra.composition import build_ops_check, load_settings

    result = build_ops_check(load_settings())()
    if getattr(args, "json", False):
        print(json.dumps({"tunnel": result.tunnel, "llm_local": result.llm_local}))
    else:
        print(result.line())
    return EXIT_OK


def register(sub: argparse._SubParsersAction) -> None:
    """`ops` 서브명령 등록 — cli.py 의 `sub = parser.add_subparsers(dest="cmd")` 뒤에 한 번."""
    ops = sub.add_parser("ops", help="운영 점검 (터널·로컬 모델 → data/cache/ops_status.json)")
    ops_sub = ops.add_subparsers(dest="ops_cmd", required=True)
    check = ops_sub.add_parser(
        "check", help="tailscale status/funnel status + 로컬 모델 GET /v1/models 1회 → 상태 파일"
    )
    check.add_argument("--json", action="store_true")
    check.set_defaults(handler=cmd_ops_check)
