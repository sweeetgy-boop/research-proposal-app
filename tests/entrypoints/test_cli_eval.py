"""`rra eval run|compare|usage|seal` 배선 (cli_eval, ADR 0058) — register 가 종전 `rra eval --label`
동작을 유지하는지, l0 는 실제 fixture 로(모델·DB 없음), 나머지는 composition 을 monkeypatch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rra.domain.models.eval_problem import EvalProblem
from rra.domain.models.eval_result import EvalMetrics, EvalResult
from rra.entrypoints import cli_eval


def _parent_with_eval():
    """cli.build_parser 의 `eval` 파서를 흉내 — 기존 handler(cmd_eval 대역)를 둔 채 register."""
    parser = argparse.ArgumentParser(prog="rra")
    sub = parser.add_subparsers(dest="cmd")
    ev = sub.add_parser("eval")
    ev.add_argument("--label")
    ev.add_argument("--report", nargs="*")
    ev.set_defaults(handler="legacy")
    cli_eval.register(sub, ev)
    return parser


def test_register_keeps_legacy_eval_when_no_subcommand():
    parser = _parent_with_eval()
    ns = parser.parse_args(["eval", "--label", "baseline"])
    assert ns.handler == "legacy" and ns.label == "baseline" and ns.eval_cmd is None
    ns = parser.parse_args(["eval", "run", "--suite", "l0", "--out", "x.json"])
    assert ns.handler is cli_eval.cmd_run and ns.eval_cmd == "run" and ns.suite == "l0"
    ns = parser.parse_args(["eval", "compare", "a.json", "b.json"])
    assert ns.handler is cli_eval.cmd_compare and ns.results == ["a.json", "b.json"]
    ns = parser.parse_args(["eval", "usage", "--since", "2026-11-01"])
    assert ns.handler is cli_eval.cmd_usage
    ns = parser.parse_args(["eval", "seal"])
    assert ns.handler is cli_eval.cmd_seal and ns.suite == "l1"


def test_run_help_states_sealed_rule():
    parser = cli_eval.build_parser()
    run = next(
        a for a in parser._subparsers._group_actions[0].choices.values() if a.prog.endswith("run")
    )
    text = run.format_help()
    assert "연습용" in text and "봉인" in text and "1회만" in text  # 줄바꿈 폭과 무관한 낱말


def test_l0_runs_offline_on_fixtures_and_writes_numbers_only(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(
        Path(__file__).parents[2]
    )  # 저장소 루트 — tests/eval fixture·config/eval.yaml
    monkeypatch.setenv("RRA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("RRA_GEMINI_API_KEY", raising=False)
    out = tmp_path / "l0.json"
    assert cli_eval.main(["run", "--suite", "l0", "--label", "ci", "--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    result = EvalResult.model_validate(data)
    assert result.suite == "l0" and result.n >= 15 and result.llm_calls == 0
    assert (
        result.cache_hits == result.n
    )  # 캐시가 지금 프롬프트와 맞는다 — 미스면 판정 경로가 바뀐 것
    assert result.metrics.recall_at5 is not None and result.metrics.false_block is not None
    text = out.read_text(encoding="utf-8")
    assert "own:" not in text and "l0-0" not in text  # doc_id·문제 본문 없음
    printed = capsys.readouterr().out
    assert "[l0 ci]" in printed and "저장:" in printed


def test_l0_fixture_problems_are_synthetic_and_valid():
    root = Path(__file__).parents[2]
    lines = (root / "tests/eval/l0_problems.jsonl").read_text(encoding="utf-8").splitlines()
    problems = [EvalProblem.model_validate(json.loads(line)) for line in lines if line.strip()]
    assert 15 <= len(problems) <= 30
    kinds = {p.kind for p in problems}
    assert kinds == {"reverse", "trap", "novel"}
    corpus_ids = {
        json.loads(line)["doc_id"]
        for line in (root / "tests/eval/l0_corpus.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    assert all(a in corpus_ids for p in problems for a in p.answers)
    assert all(":l0-" in i for i in corpus_ids)  # 합성 코퍼스만 (실제 DB id 없음)


def _result(label, recall, fb, seed=1):
    return EvalResult(
        suite="l1",
        seed=seed,
        n=3,
        repeats=3,
        label=label,
        metrics=EvalMetrics(recall_at5=recall, false_block=fb, latency_p50=1.0, latency_p90=2.0),
    )


def test_compare_writes_korean_table(tmp_path, capsys):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(_result("가", 0.8, 0.1).model_dump_json(), encoding="utf-8")
    b.write_text(_result("나", 0.9, 0.0).model_dump_json(), encoding="utf-8")
    out = tmp_path / "cmp.md"
    assert cli_eval.main(["compare", str(a), str(b), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "| 지표 | 가 | 나 | 차이(나) | 판정(나) |" in text
    assert "+0.100" in text and "구간 없음" in text and "## 실행 정보" in text
    assert cli_eval.main(["compare", str(a)]) == cli_eval.EXIT_USAGE


def test_usage_uses_composition_and_writes_json(tmp_path, monkeypatch, capsys):
    report = {
        "kind": "usage",
        "since": None,
        "include_test": False,
        "choices": {
            "found": True,
            "user_choices": 2,
            "similar_rate": 0.5,
            "ai_judged": 2,
            "ai_agreement": 1.0,
        },
        "recommend": {"found": False, "calls": 0, "by_branch": {}},
    }
    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr("rra.composition.build_eval_usage", lambda s: lambda **kw: report)
    out = tmp_path / "u.json"
    assert cli_eval.main(["usage", "--out", str(out)]) == 0
    assert json.loads(out.read_text())["choices"]["user_choices"] == 2
    printed = capsys.readouterr().out
    assert "제안자 선택 2건" in printed and "파일 없음" in printed


class _Store:
    def __init__(self, root):
        self.root = root
        self.saved = None

    def sealed_path(self, suite):
        return self.root / f"{suite}.jsonl"

    def exists(self, path):
        return path.exists()

    def save(self, path, problems):
        self.saved = list(problems)
        path.write_text("x", encoding="utf-8")
        return path


class _Gen:
    async def generate(self, *, seed, n, mix):
        return [EvalProblem(id=f"p{i}", kind="novel", request={"goal": "g"}) for i in range(n)]


def test_seal_creates_once_and_refuses_overwrite(tmp_path, monkeypatch, capsys):
    from rra.domain.models.eval_problem import EvalSuiteConfig

    store = _Store(tmp_path)

    async def aclose():
        return None

    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr("rra.config_loader.eval_config", lambda s: EvalSuiteConfig(sealed_seed=7))
    monkeypatch.setattr("rra.composition.build_eval_stores", lambda s: (None, store))
    monkeypatch.setattr(
        "rra.composition.build_eval_suite", lambda s, **kw: {"generator": _Gen(), "aclose": aclose}
    )
    assert cli_eval.main(["seal", "--n", "5"]) == 0
    assert len(store.saved) == 5 and "열람 금지" in capsys.readouterr().out
    store.saved = None
    assert cli_eval.main(["seal", "--n", "5"]) == 0
    assert store.saved is None and "덮어쓰지 않음" in capsys.readouterr().out


def test_sealed_is_l1_only_and_sealed_run_prints_warning(monkeypatch, capsys, tmp_path):
    from rra.domain.models.eval_problem import EvalSuiteConfig

    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr("rra.config_loader.eval_config", lambda s: EvalSuiteConfig(sealed_seed=7))
    monkeypatch.setattr("rra.composition.build_eval_stores", lambda s: (None, None))
    assert cli_eval.main(["run", "--suite", "l0", "--sealed"]) == cli_eval.EXIT_USAGE
    assert "--sealed 는 l1" in capsys.readouterr().err
    assert cli_eval.main(["run", "--suite", "l1", "--sealed", "--seed", "9"]) == cli_eval.EXIT_USAGE
    assert "sealed_seed" in capsys.readouterr().err

    # 봉인 묶음 실행 — 경고 한 줄, seed 는 sealed_seed, 결과 sealed=true
    class Store:
        def sealed_path(self, suite):
            return tmp_path / f"{suite}.jsonl"

        def exists(self, path):
            return True

        def load(self, path):
            return [EvalProblem(id="p", kind="novel", request={"goal": "g"})]

    class Results:
        def write(self, result, *, path=None):
            assert result.sealed is True and result.seed == 7
            out = tmp_path / "r.json"
            out.write_text(result.model_dump_json(), encoding="utf-8")
            return out

    async def fake_suite(problems):
        return EvalResult(suite="l1", seed=7, n=len(problems), sealed=True)

    async def aclose():
        return None

    monkeypatch.setattr("rra.composition.build_eval_stores", lambda s: (Results(), Store()))
    monkeypatch.setattr(
        "rra.composition.build_eval_suite",
        lambda s, **kw: {"suite": fake_suite, "generator": None, "aclose": aclose},
    )
    assert cli_eval.main(["run", "--suite", "l1", "--sealed"]) == 0
    captured = capsys.readouterr()
    assert cli_eval.SEALED_WARNING in captured.err and "저장:" in captured.out
