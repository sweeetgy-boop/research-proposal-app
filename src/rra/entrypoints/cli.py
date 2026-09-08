from __future__ import annotations

import argparse


def main() -> None:
    p = argparse.ArgumentParser("rra")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("ingest")
    sub.add_parser("precheck")
    sub.add_parser("generate")
    args = p.parse_args()
    print(f"[rra] {args.cmd}: Step 2 이후 composition 연결 예정")
