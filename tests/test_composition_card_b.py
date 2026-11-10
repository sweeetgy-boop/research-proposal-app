"""문제 정의 카드 레인 B 조립 (ADR 0065) — 설정이 꺼져 있으면(저장소 값) 종전, 설정 사본에서 켜면
유추 검색·키워드가 같은 설정을 본다. KIPRIS 분류 건수는 키가 없으면 None."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import httpx
from pydantic import SecretStr

from rra import composition
from rra.application.usecases.problem_card_contract import PatentClassCount
from rra.settings import Settings
from tests.fakes import FakeLLM, InMemoryRepository

ROOT_CONFIG = Path(__file__).parents[1] / "config"


class _Live:
    keywords = None

    async def keywords_for(self, req):  # pragma: no cover - 호출되지 않는다
        raise AssertionError


class _Precheck:
    async def rule_stage(self, req, **kw):  # pragma: no cover
        raise AssertionError


def _settings(config_dir: Path, tmp_path: Path, **kw) -> Settings:
    return Settings(
        _env_file=None, config_dir=config_dir, data_dir=tmp_path / "data", fake_llm=True, **kw
    )


def _copy(tmp_path: Path, *, enabled: bool) -> Path:
    """설정 사본 — 맨 위 스위치만 원하는 값으로(저장소 값이 무엇이든)."""
    target = tmp_path / ("config_on" if enabled else "config_off")
    shutil.copytree(ROOT_CONFIG, target)
    path = target / "problem_card.yaml"
    text = path.read_text(encoding="utf-8")
    new, n = re.subn(
        r"(?m)^enabled: (true|false)$", f"enabled: {str(enabled).lower()}", text, count=1
    )
    assert n == 1
    path.write_text(new, encoding="utf-8")
    return target


def _enabled_copy(tmp_path: Path) -> Path:
    return _copy(tmp_path, enabled=True)


def test_switched_off_config_keeps_everything_off(tmp_path):
    """스위치를 끄면(끄는 PR 한 줄) 유추·보완 질문이 카드를 쓰지 않는다."""
    settings = _settings(_copy(tmp_path, enabled=False), tmp_path)
    _, analogies = composition.build_novelty(
        settings, repo=InMemoryRepository(), precheck=_Precheck(), live=_Live()
    )
    assert analogies.card_config.enabled is False and analogies.scorer is None
    assert analogies.card_config.uses("analogy_queries") is False
    clarifier = composition.build_clarifier(settings, llm=FakeLLM())
    assert clarifier.card_config.uses("clarify") is False


def test_enabled_copy_wires_card_config_into_analogy_search_and_keywords(tmp_path):
    settings = _settings(_enabled_copy(tmp_path), tmp_path)
    _, analogies = composition.build_novelty(
        settings, repo=InMemoryRepository(), precheck=_Precheck(), live=_Live()
    )
    assert analogies.card_config.uses("analogy_queries") and analogies.card_config.uses(
        "analogy_rank"
    )
    assert analogies.problem_keywords.card_config is analogies.card_config
    assert analogies.scorer is None  # 가짜 모드는 재순위 모델을 올리지 않는다
    assert composition.build_clarifier(settings, llm=FakeLLM()).card_config.uses("clarify")


def test_patent_class_count_needs_a_key(tmp_path):
    assert composition.build_patent_class_count(_settings(ROOT_CONFIG, tmp_path)) is None
    no_key = Settings(_env_file=None, config_dir=ROOT_CONFIG, data_dir=tmp_path / "data")
    assert composition.build_patent_class_count(no_key) is None
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    keyed = Settings(
        _env_file=None,
        config_dir=ROOT_CONFIG,
        data_dir=tmp_path / "data",
        kipris_key=SecretStr("KIPRIS-SECRET-KEY"),
    )
    counter = composition.build_patent_class_count(
        keyed, transport=transport, resolver=lambda host: False
    )
    assert isinstance(counter, PatentClassCount) and "SECRET" not in repr(counter)
