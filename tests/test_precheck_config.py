"""② 판정 설정 (2026-10-28 레인 A) — overlap.yaml rerank·judgment·core_min_hits·일반어, 선택 기록
위치."""

from pathlib import Path

from rra.config_loader import (
    data_location,
    keyword_rule,
    rerank_rule,
    same_judgment_config,
)
from rra.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


def _settings(tmp_path):
    return Settings(_env_file=None, config_dir=ROOT / "config", data_dir=tmp_path / "data")


def test_repo_config_sets_reranker_threshold_judgment_and_pilot_generic_terms(tmp_path):
    s = _settings(tmp_path)
    assert rerank_rule(s).threshold == 0.5
    cfg = same_judgment_config(s)
    assert cfg["enabled"] and cfg["stage"] == "review" and cfg["max_candidates"] == 10
    rule = keyword_rule(s)
    assert rule.core_min_hits == 1 and rule.min_hits == 2
    for term in ("부족", "정책", "상황", "인식", "필요한", "응용연구"):
        assert term in rule.generic_terms
    assert "공간" not in rule.generic_terms and "역사" not in rule.generic_terms


def test_choice_log_lives_under_the_data_folder(tmp_path):
    path = data_location(_settings(tmp_path), "similar_choices")
    assert path == (tmp_path / "data" / "feedback" / "similar_choices.jsonl").resolve()


def test_jsonl_choice_log_appends_allowed_keys_only(tmp_path):
    import json

    import pytest

    from rra.adapters.logging.choice_log import JsonlChoiceLog

    log = JsonlChoiceLog(tmp_path / "fb" / "c.jsonl")
    log.append([{"doc_id": "own:1", "choice": "similar", "idea": "abc"}])
    log.append([{"doc_id": "own:2", "choice": "unrelated", "idea": "abc"}])
    lines = (tmp_path / "fb" / "c.jsonl").read_text().splitlines()
    assert [json.loads(x)["doc_id"] for x in lines] == ["own:1", "own:2"]
    assert oct((tmp_path / "fb" / "c.jsonl").stat().st_mode & 0o777) == "0o600"
    with pytest.raises(ValueError):
        log.append([{"doc_id": "own:3", "title": "원문 제목"}])
