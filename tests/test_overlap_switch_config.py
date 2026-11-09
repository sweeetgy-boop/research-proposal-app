"""레인 E 설정 — 스위치 로더·idf_weighting·synonyms 절 값·데이터 위치·조립 helper (ADR 0059)."""

from __future__ import annotations

from pathlib import Path

from rra import composition
from rra.config_loader import (
    data_location,
    facets_config,
    idf_weighting_rule,
    load_overlap_switches,
    synonym_config,
    synonym_groups,
)
from rra.domain.rules.overlap_switches import OFF, OverlapSwitches
from rra.settings import Settings

ROOT = Path(__file__).parents[1]


def _settings(tmp_path: Path, overlap: str) -> Settings:
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "overlap.yaml").write_text(overlap, encoding="utf-8")
    return Settings(_env_file=None, config_dir=cfg, data_dir=tmp_path / "data")


def test_repo_config_has_all_switches_off():
    """운영 설정의 스위치는 모두 off — 2026-11-09 밤 방침(평가 보류, 검증 없이 켜지 않음),
    ADR 0059."""
    s = Settings(_env_file=None, config_dir=ROOT / "config")
    assert load_overlap_switches(s) == OFF
    assert idf_weighting_rule(s).min_weight_ratio == 1.0
    assert facets_config(s)["local_stage"] == "clarify"
    assert data_location(s, "idf_cache").name == "idf.json"


def test_switch_loader_defaults_and_values(tmp_path: Path):
    s = _settings(tmp_path, "keywords: {min_hits: 2}\n")
    assert load_overlap_switches(s) == OFF
    assert synonym_groups(s) == [] and synonym_config(s).min_doc_freq == 5
    (tmp_path / "b").mkdir()
    s2 = _settings(
        tmp_path / "b",
        "facets: {enabled: true}\n"
        "idf_weighting: {enabled: true, min_weight_ratio: 0.8, cache: data/x/idf.json}\n"
        "synonyms: {enabled: false, candidates: "
        "[{canonical: 유지보수, terms: [유지보수, 유지관리]}, {canonical: 혼자}]}\n",
    )
    assert load_overlap_switches(s2) == OverlapSwitches(facets=True, idf_weighting=True)
    assert idf_weighting_rule(s2).min_weight_ratio == 0.8
    assert data_location(s2, "idf_cache") == (tmp_path / "b" / "data" / "x" / "idf.json")
    assert synonym_groups(s2) == [["유지보수", "유지관리"]]


class _Pre:
    switches = OFF
    facet_split = None
    idf = None
    idf_rule = None
    same_judge = None


def test_apply_overlap_switches_is_noop_when_off_and_wires_when_on(tmp_path: Path):
    s = _settings(tmp_path, "facets: {enabled: false}\n")
    pre = _Pre()
    assert composition.apply_overlap_switches(pre, s) is pre
    assert pre.switches == OFF and pre.facet_split is None and pre.idf is None
    on = composition.apply_overlap_switches(
        _Pre(), s, switches=OverlapSwitches(facets=True, idf_weighting=True), local_llm=object()
    )
    assert on.switches.facets and on.facet_split is not None and on.facet_split.local is not None
    assert on.idf is None and on.idf_rule is not None  # 캐시 파일 없음 → 가중 없음
