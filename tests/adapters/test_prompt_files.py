"""프롬프트 자산 검증. 파일이 규칙(보안 A)을 담고 있는지, 섹션이 빠지지 않았는지."""

from pathlib import Path

import pytest
import yaml

from rra.adapters.llm.prompt_files import FilePromptLibrary, PromptNotFound

RULES_PATH = Path(__file__).parents[2] / "config/templates/proposal_korail.rules.yaml"
RULES = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))
REQUIRED_SECTIONS = RULES["required_sections"]


@pytest.fixture
def prompts():
    return FilePromptLibrary()


def test_system_prompt_declares_untrusted_boundary(prompts):
    system = prompts.system()
    assert "<doc" in system
    assert "지시가 아닙니다" in system
    assert "따르지 마십시오" in system


def test_system_prompt_forces_json_and_evidence(prompts):
    system = prompts.system()
    assert "JSON" in system
    assert "evidence" in system
    assert "도구" in system  # 도구·파일 접근 없음 명시


@pytest.mark.parametrize("key", REQUIRED_SECTIONS)
def test_every_required_section_has_a_prompt(prompts, key):
    assert prompts.section(key).strip()


def test_available_sections_cover_rules(prompts):
    assert set(REQUIRED_SECTIONS) <= set(prompts.available_sections())


@pytest.mark.parametrize("key", RULES["evidence_required"])
def test_evidence_required_sections_say_so(prompts, key):
    assert "evidence" in prompts.section(key)


@pytest.mark.parametrize("name", ["../system", "a/b", "sys tem", "System", "", "x.md", "..", "a-b"])
def test_prompt_names_are_allowlisted(prompts, name):
    with pytest.raises(PromptNotFound):
        prompts._read(name)


def test_unknown_section_raises(prompts):
    with pytest.raises(PromptNotFound):
        prompts.section("nonexistent")


def test_directory_override(tmp_path):
    (tmp_path / "system.md").write_text("덮어쓴 시스템\n", encoding="utf-8")
    (tmp_path / "section_background.md").write_text("배경\n", encoding="utf-8")
    lib = FilePromptLibrary(tmp_path)
    assert lib.system() == "덮어쓴 시스템"
    assert lib.available_sections() == ["background"]


def test_reads_are_cached(prompts):
    first = prompts.system()
    assert prompts._cache["system"] == first
    assert prompts.system() is first


def test_json_fallback_prompt_exists(prompts):
    assert "JSON" in prompts.json_fallback()
