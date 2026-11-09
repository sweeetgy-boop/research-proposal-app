"""`rra ops check`(entrypoints/cli_ops) — register 가 파서를 더하고, 핸들러는 조립을 monkeypatch 해
열거값 한 줄만 낸다."""

import argparse
import json

from rra.application.usecases.ops_check import OpsCheckResult
from rra.entrypoints import cli_ops


def _parser():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    cli_ops.register(sub)
    return parser


def test_register_adds_ops_check_with_handler_and_json_flag():
    args = _parser().parse_args(["ops", "check", "--json"])
    assert args.cmd == "ops" and args.ops_cmd == "check" and args.json is True
    assert args.handler is cli_ops.cmd_ops_check


def test_ops_check_prints_enums_only(monkeypatch, capsys):
    class Check:
        def __call__(self):
            return OpsCheckResult(tunnel="down", llm_local="ok")

    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr("rra.composition.build_ops_check", lambda settings: Check())
    args = _parser().parse_args(["ops", "check"])
    assert args.handler(args) == cli_ops.EXIT_OK
    assert capsys.readouterr().out.strip() == "tunnel=down llm_local=ok"
    args = _parser().parse_args(["ops", "check", "--json"])
    assert args.handler(args) == cli_ops.EXIT_OK
    assert json.loads(capsys.readouterr().out) == {"tunnel": "down", "llm_local": "ok"}
