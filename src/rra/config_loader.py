"""설정 로더 — config/*.yaml 읽기·병합·환경변수 우선순위. 조립(composition)은 이 결과만 받는다.

I/O 라이브러리 객체(httpx·sqlite·모델)는 만들지 않는다. 돌려주는 것은 dict 와 domain 값 객체다.
비밀은 Settings(SecretStr) 에만 있고, 이 모듈은 값의 유무만 본다 (보안 D).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from rra.domain.models import StrategyCatalog
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.lint import LintRules
from rra.domain.rules.overlap import OwnUnit
from rra.settings import Settings

DEFAULT_STAGE = "compose"
TEMPLATE = "proposal_korail"
STRATEGY_FILE = "templates/korail_strategy.yaml"
SLOTS_FILE = f"templates/{TEMPLATE}.slots.yaml"
FORM_FILE = f"templates/{TEMPLATE}.hwpx"


# ── 원시 읽기 ──────────────────────────────────────────────
def read_config(name: str, settings: Settings) -> dict[str, Any]:
    path = Path(settings.config_dir) / name
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def env_first(settings: Settings, field: str, fallback: Any) -> Any:
    """환경변수가 실제로 설정되었으면 그 값을, 아니면 yaml 값을 쓴다."""
    if field in settings.model_fields_set:
        return getattr(settings, field)
    return fallback if fallback is not None else getattr(settings, field)


def security_config(settings: Settings) -> dict[str, Any]:
    return read_config("security.yaml", settings)


def allowed_domains(settings: Settings) -> list[str]:
    return list(security_config(settings).get("allowed_domains") or [])


def input_limits(settings: Settings) -> dict[str, Any]:
    return security_config(settings).get("input_limits") or {}


def source_config(settings: Settings, name: str) -> dict[str, Any]:
    return read_config("sources.yaml", settings).get(name) or {}


# ── LLM ────────────────────────────────────────────────────
def llm_config(settings: Settings, stage: str = DEFAULT_STAGE) -> dict[str, Any]:
    """llm.yaml + 환경변수를 합쳐 단계별 LLM 설정을 만든다. 순수 딕셔너리 계산."""
    cfg = read_config("llm.yaml", settings)
    stages = cfg.get("stages") or {}
    if stage not in stages:
        raise KeyError(f"config/llm.yaml 의 stages 에 {stage!r} 가 없습니다: {sorted(stages)}")
    stage_cfg = stages[stage] or {}
    limits = cfg.get("limits") or {}
    timeout = cfg.get("timeout") or {}
    retries = cfg.get("retries") or {}
    return {
        "provider": env_first(settings, "llm_provider", cfg.get("provider")),
        "base_url": env_first(settings, "llm_base_url", cfg.get("base_url")),
        "model": stage_cfg.get("model") or "local",
        "served_model": str(cfg.get("served_model") or "").strip() or None,
        "max_tokens": int(stage_cfg.get("max_tokens", 1024)),
        "max_tokens_cap": int(limits.get("max_tokens_cap", 4096)),
        "prompt_max_chars": int(limits.get("prompt_max_chars", 60_000)),
        "temperature": float(cfg.get("temperature", 0.2)),
        "json_mode": str(cfg.get("json_mode", "auto")),
        "timeout": {
            "connect": float(timeout.get("connect", 5)),
            "read": float(timeout.get("read", 180)),
            "write": float(timeout.get("write", 10)),
            "pool": float(timeout.get("pool", 5)),
        },
        "retry": {
            "attempts": int(retries.get("attempts", 3)),
            "backoff_sec": float(retries.get("backoff_sec", 0.5)),
            "max_backoff_sec": float(retries.get("max_backoff_sec", 8)),
        },
    }


def served_model_aliases(served: str | None) -> frozenset[str]:
    """선언한 모델 이름과 같은 것으로 볼 문자열. 로컬 경로로 띄웠으면 서버는 절대경로를 싣는다."""
    if not served:
        return frozenset()
    names = {served}
    path = Path(served).expanduser()
    if path.exists():
        names.add(str(path.resolve()))
    return frozenset(names)


# ── 자료원·기관 ─────────────────────────────────────────────
def institutions(settings: Settings) -> list[dict[str, Any]]:
    """대상 기관 목록 (sources.yaml 최상위). 예전 위치(alio.institutions)도 읽는다."""
    cfg = read_config("sources.yaml", settings)
    return list(cfg.get("institutions") or (cfg.get("alio") or {}).get("institutions") or [])


def own_unit(settings: Settings) -> OwnUnit | None:
    """own 티어 기준 (sources.yaml own_unit). 설정이 없으면 None → own 티어 없음."""
    cfg = read_config("sources.yaml", settings).get("own_unit")
    if not cfg:
        return None
    return OwnUnit(
        org=str(cfg.get("org") or "korail"),
        departments=frozenset(str(d).strip() for d in cfg.get("departments") or [] if d),
    )


def keyword_rule(settings: Settings) -> KeywordRule:
    """유사과제 차단의 키워드 조건 (config/overlap.yaml `keywords`). 파일이 없으면 도메인 기본값."""
    cfg = read_config("overlap.yaml", settings).get("keywords") or {}
    rule = KeywordRule(min_hits=int(cfg.get("min_hits") or 2))
    extra = cfg.get("generic_terms") or []
    if not isinstance(extra, list):
        raise ValueError("overlap.yaml keywords.generic_terms 는 목록이어야 합니다.")
    return rule.with_extra_generic([str(t) for t in extra])


# ── 양식 ───────────────────────────────────────────────────
def lint_rules(settings: Settings) -> LintRules:
    """config/templates/<TEMPLATE>.rules.yaml → LintRules. 섹션 순서 = sections."""
    data = read_config(f"templates/{TEMPLATE}.rules.yaml", settings)
    if not data.get("required_sections"):
        raise KeyError(f"templates/{TEMPLATE}.rules.yaml 에 required_sections 가 없습니다.")
    return LintRules.model_validate(data)


def strategy_catalog(settings: Settings) -> StrategyCatalog:
    """코레일 전략체계 (config/templates/korail_strategy.yaml). 파일이 없거나 비면 빈 목록."""
    data = read_config(STRATEGY_FILE, settings)
    return StrategyCatalog.model_validate(
        {"source": data.get("source") or "", "directions": data.get("directions") or []}
    )


def render_slots(settings: Settings) -> dict[str, Any]:
    """HWPX 자리표시자 선언 (config/templates/<TEMPLATE>.slots.yaml). 비어 있으면 KeyError."""
    data = read_config(SLOTS_FILE, settings)
    if not data.get("text"):
        raise KeyError(f"{SLOTS_FILE} 에 text 슬롯이 없습니다.")
    return data


def render_template_path(settings: Settings) -> Path | None:
    """실물 양식 HWPX 가 있으면 그 경로 (템플릿 모드), 없으면 None (생성 모드)."""
    path = Path(settings.config_dir) / FORM_FILE
    return path if path.is_file() else None


# ── 키 유무 (값은 절대 돌려주지 않는다) ─────────────────────
class MissingCredential(ValueError):
    """요청한 소스의 키가 .env 에 없다. 메시지에는 변수 이름만 (값 없음)."""


# 소스별 필요한 .env 변수 → Settings 필드
CREDENTIALS: dict[str, dict[str, str]] = {
    "scienceon": {
        "RRA_SCIENCEON_CLIENT_ID": "scienceon_client_id",
        "RRA_SCIENCEON_KEY": "scienceon_key",
        "RRA_SCIENCEON_MAC": "scienceon_mac",
    },
    "ntis": {"RRA_NTIS_KEY": "ntis_key"},
}
KEYED_SOURCES = tuple(CREDENTIALS)


def credential_status(settings: Settings, source: str) -> dict[str, bool]:
    """{변수 이름: 값이 있는지}. 값 자체는 돌려주지 않는다."""
    out = {}
    for env, field in CREDENTIALS.get(source, {}).items():
        secret = getattr(settings, field)
        out[env] = bool(secret is not None and secret.get_secret_value().strip())
    return out


def require_credentials(settings: Settings, source: str) -> None:
    missing = [env for env, ok in credential_status(settings, source).items() if not ok]
    if missing:
        raise MissingCredential(
            f"{source} 수집에 필요한 키가 .env 에 없습니다: {', '.join(missing)} "
            "(README 발급 절차 참고)"
        )
