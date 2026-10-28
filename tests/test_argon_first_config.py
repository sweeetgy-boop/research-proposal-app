"""[3] Argon 먼저 작성 (ADR 0032) — 설정 읽기·조립.

네트워크·모델 없음 (키는 가짜 값, 호출하지 않는다).
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from rra.config_loader import compose_policy, llm_budget, review_policy, runs_config
from rra.domain.rules.writer import on_off, parse_writer
from rra.settings import Settings
from tests.fakes import FakeLLM, InMemoryRepository

FAKE_GEMINI = SecretStr("gemini-test-not-a-real-key")


def shipped(**kw):
    kw.setdefault("gemini_api_key", None)
    return Settings(_env_file=None, **kw)


def with_llm_yaml(tmp_path, text, **kw):
    import shutil
    from pathlib import Path

    dst = tmp_path / "config"
    shutil.copytree(Path(__file__).resolve().parents[1] / "config", dst)
    (dst / "llm.yaml").write_text(text, encoding="utf-8")
    return Settings(_env_file=None, config_dir=dst, **kw)


def test_shipped_config_writes_with_argon_and_turns_off_the_self_review():
    s = shipped()
    assert compose_policy(s) == {
        "writer": "gemini",
        "concurrency": 4,
        "local_check": False,
        "local_check_timeout_sec": 20.0,
    }
    assert review_policy(s)["first_pass"] is False
    assert runs_config(s) == {"max_concurrent": 3}
    assert llm_budget(s)["limit"] == 600


def test_missing_keys_keep_the_old_behaviour(tmp_path):
    s = with_llm_yaml(tmp_path, "provider: mlx\nstages: {compose: {}}\n")
    assert compose_policy(s)["writer"] == "local" and review_policy(s)["first_pass"] is True
    (tmp_path / "config" / "runs.yaml").unlink()
    assert runs_config(s) == {"max_concurrent": 1}


def test_setting_values_are_checked():
    assert parse_writer("local") == "local" and parse_writer("mlx") == "local"
    assert parse_writer("Gemini") == "gemini" and parse_writer(None) == "gemini"
    with pytest.raises(ValueError):
        parse_writer("openai")
    assert on_off(False) is False and on_off("on") is True and on_off(None, True) is True
    with pytest.raises(ValueError):
        on_off("maybe")


def test_writer_needs_the_key_and_falls_back_to_local_without_it(tmp_path):
    from rra.composition import build_compose_writer, build_generate

    repo, llm = InMemoryRepository(), FakeLLM()
    assert build_compose_writer(shipped()) is None  # 키 없음 → 로컬 작성
    gen = build_generate(shipped(), repo=repo, llm=llm, reranker=object())
    assert not gen.writes_remotely and gen.fallback_llm is None
    keyed = shipped(gemini_api_key=FAKE_GEMINI)
    writer = build_compose_writer(keyed)
    assert writer["provider"] == "gemini" and writer["model"] == "gemini-4-argon"
    gen = build_generate(keyed, repo=repo, llm=llm, reranker=object())
    assert gen.writes_remotely and gen.writer_include_internal is True
    assert gen.fallback_llm is None  # 역할이 뒤집혀 ADR 0027 대체 작성은 쓰지 않는다
    assert gen.local_provider == "mlx" and gen.compose_concurrency == 4
    public = build_generate(keyed, repo=repo, llm=llm, reranker=object(), public=True)
    assert public.writer_include_internal is False
    # writer: local 이면 키가 있어도 로컬 먼저 + 대체 작성(ADR 0027)
    text = _shipped_text().replace("writer: gemini", "writer: local")
    local = with_llm_yaml(tmp_path, text, gemini_api_key=FAKE_GEMINI)
    assert build_compose_writer(local) is None
    gen = build_generate(local, repo=repo, llm=llm, reranker=object())
    assert not gen.writes_remotely and gen.fallback_llm is not None


def test_fake_mode_puts_the_fake_llm_in_the_argon_seat():
    from rra.composition import build_compose_writer

    fake = FakeLLM()
    writer = build_compose_writer(shipped(fake_llm=True), fake_llm=fake)
    assert writer == {"llm": fake, "provider": "gemini", "model": "fake/argon"}


def test_run_manager_uses_a_run_pool_only_when_argon_writes(tmp_path):
    from rra.adapters.runs import FlockPool, FlockSlot
    from rra.composition import build_run_manager

    keyed = shipped(gemini_api_key=FAKE_GEMINI, runs_dir=tmp_path / "runs")
    mgr = build_run_manager(keyed, repo=InMemoryRepository(), llm=FakeLLM())
    assert isinstance(mgr.run_slot, FlockPool) and mgr.run_slot.size == 3
    assert isinstance(mgr.slot, FlockSlot) and mgr.generate.local_slot is mgr.slot
    assert mgr.first_pass is False
    plain = shipped(runs_dir=tmp_path / "runs2")  # 키 없음 → 로컬 작성, 예전처럼 슬롯 하나
    mgr = build_run_manager(plain, repo=InMemoryRepository(), llm=FakeLLM())
    assert mgr.run_slot is None and not mgr.generate.writes_remotely


def _shipped_text() -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parents[1] / "config" / "llm.yaml").read_text(encoding="utf-8")
