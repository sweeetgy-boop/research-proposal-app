"""설정 로더 — config/*.yaml 읽기·병합·환경변수 우선순위. 조립(composition)은 이 결과만 받는다.

I/O 라이브러리 객체(httpx·sqlite·모델)는 만들지 않는다. 돌려주는 것은 dict 와 domain 값 객체다.
비밀은 Settings(SecretStr) 에만 있고, 이 모듈은 값의 유무만 본다 (보안 D).
"""

from __future__ import annotations

import logging
import shutil
import subprocess  # nosec B404 - git rev-parse 만, 인자 고정·shell 없음
from collections.abc import Callable, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from rra.domain.models import StrategyCatalog
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.lint import LintRules
from rra.domain.rules.overlap import OwnUnit
from rra.domain.rules.relevance import RelevanceFloor
from rra.domain.rules.source_ip import IpPolicy
from rra.settings import Settings

DEFAULT_STAGE = "compose"
TEMPLATE = "proposal_korail"
STRATEGY_FILE = "templates/korail_strategy.yaml"
STRATEGY_DRAFT_FILE = "templates/korail_strategy.draft.yaml"
STRATEGY_SOURCES = ("draft", "confirmed")
SLOTS_FILE = f"templates/{TEMPLATE}.slots.yaml"
FORM_FILE = f"templates/{TEMPLATE}.hwpx"


logger = logging.getLogger(__name__)


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


def auth_config(settings: Settings) -> dict[str, Any]:
    """config/auth.yaml (비밀 아님) — 공용 계정 자료 범위·일일 상한·잠금 정책·저장소 경로."""
    raw = read_config("auth.yaml", settings)
    guest = raw.get("guest") or {}
    limits = raw.get("limits") or {}
    lockout = raw.get("lockout") or {}
    return {
        "store_dir": data_location(settings, "auth", cfg=raw),
        "include_internal": bool(guest.get("include_internal", False)),
        "min_password_length": int(guest.get("min_password_length", 8)),
        "limits": {
            "guest_runs_per_day": int(limits.get("guest_runs_per_day", 10)),
            "staff_runs_per_day": int(limits.get("staff_runs_per_day", 20)),
        },
        "lockout": {k: v for k, v in lockout.items() if isinstance(v, int | float)},
        "trust_cf_connecting_ip": api_config(settings)["trust_cf_connecting_ip"],
    }


def llm_budget(settings: Settings) -> dict[str, Any]:
    """외부(gemini) LLM 일일 전체 호출 상한 — llm.yaml budget. limit 0 이면 상한 없음."""
    raw = read_config("llm.yaml", settings).get("budget") or {}
    return {
        "limit": int(raw.get("gemini_daily_calls", 300)),
        "path": data_location(settings, "llm_budget", cfg=raw),
    }


API_CONFIG_FILE = "api.yaml"
API_CONFIG_KEYS = ("public_origin", "trust_cf_connecting_ip")


def api_config(settings: Settings) -> dict[str, Any]:
    """config/api.yaml → {"public_origin": str, "trust_cf_connecting_ip": bool} (보안 G).

    파일이 없으면 public_origin "" · trust_cf_connecting_ip False. 모르는 키는 오류.
    public_origin 은 `https://host[:port]` 만(경로·쿼리 없음, 끝 슬래시 제거) — 공개 주소는
    항상 TLS 종단(역프록시) 뒤에 있어야 한다.
    """
    from urllib.parse import urlsplit

    raw = read_config(API_CONFIG_FILE, settings) or {}
    unknown = set(raw) - set(API_CONFIG_KEYS)
    if unknown:
        raise ValueError(f"config/{API_CONFIG_FILE} 에 모르는 키: {sorted(unknown)}")
    origin = str(raw.get("public_origin") or "").strip().rstrip("/")
    if origin:
        parts = urlsplit(origin)
        extra = parts.path or parts.query or parts.fragment
        if parts.scheme != "https" or not parts.netloc or extra:
            raise ValueError(
                f"config/{API_CONFIG_FILE} public_origin 은 https://호스트 형식이어야 합니다: "
                f"{origin!r}"
            )
        origin = f"https://{parts.netloc.lower()}"
    trust = raw.get("trust_cf_connecting_ip", False)
    if not isinstance(trust, bool):
        raise ValueError(
            f"config/{API_CONFIG_FILE} trust_cf_connecting_ip 는 true/false 여야 합니다."
        )
    return {"public_origin": origin, "trust_cf_connecting_ip": trust}


def retention_days(settings: Settings, default: int = 180) -> int:
    """I. runs/ 보존 기간 (security.yaml retention_days). 0 이하는 거부."""
    days = int(security_config(settings).get("retention_days", default))
    if days <= 0:
        raise ValueError("security.yaml retention_days 는 1 이상이어야 합니다.")
    return days


def source_config(settings: Settings, name: str) -> dict[str, Any]:
    """sources.yaml 의 항목. 없으면 config/<name>.yaml (molit·bai·mofe·datago·g2b 처럼 파일을 따로
    둔
    자료원)."""
    return read_config("sources.yaml", settings).get(name) or read_config(f"{name}.yaml", settings)


def public_ip_config(settings: Settings) -> dict[str, Any]:
    """sources.yaml `public_ip` — 현재 공인 IP 조회 URL·자료원 가용 상태 파일 (레인 I)."""
    return read_config("sources.yaml", settings).get("public_ip") or {}


def source_ip_policy(settings: Settings, name: str, *, label: str = "") -> IpPolicy:
    """자료원의 IP 제한 (sources.yaml `<source>.ip_restricted`·`registered_ips`). 항목이 없으면 제한
    없음."""
    return IpPolicy.from_mapping(source_config(settings, name) or {}, label=label or name)


def molit_config(settings: Settings) -> dict[str, Any]:
    """국토교통부 정책자료 수집 설정 (config/molit.yaml)."""
    return read_config("molit.yaml", settings)


def rnd_notice_config(settings: Settings) -> dict[str, Any]:
    """정부 R&D 공고(KAIA·IRIS) 스냅샷 수집 설정 (config/rnd_notice.yaml). 없으면 빈 dict."""
    return read_config("rnd_notice.yaml", settings)


def korail_web_config(settings: Settings) -> dict[str, Any]:
    """공사 홈페이지 스냅샷 수집 설정 (config/korail_web.yaml). 없으면 빈 dict."""
    return read_config("korail_web.yaml", settings)


# ── 데이터 폴더 (RRA_DATA_DIR) ───────────────────────────────
# 모든 실행 데이터(DB·크롤 스냅샷·캐시·vision_cache·inbox)는 레인 worktree 가 아니라 원 저장소의
# data/ 절대 경로에 둔다. worktree 를 지우면 그 안의 미커밋 데이터가 같이 사라지기 때문이다.
DATA_DIR_NAME = "data"
_GIT_TIMEOUT_SEC = 5
_announced: set[Path] = set()


@lru_cache(maxsize=16)
def _git_repo_root(cwd: str) -> Path | None:
    """`git rev-parse --git-common-dir` → 원 저장소 루트. 연결 worktree 에서도 본 체크아웃의
    `.git` 을 돌려주므로 그 부모가 원 저장소다. git 이 없거나 저장소 밖이면 None."""
    git = shutil.which("git")
    if git is None:
        return None
    try:
        proc = subprocess.run(  # nosec B603 - 절대 경로 실행 파일, 고정 인자, shell 없음  # noqa: S603
            [git, "rev-parse", "--git-common-dir"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    common = Path(proc.stdout.strip())
    if not common.is_absolute():
        common = Path(cwd) / common
    common = common.resolve()
    if common.name != ".git":  # bare 저장소·서브모듈 — 어디가 루트인지 단정하지 않는다
        return None
    return common.parent


def resolve_data_dir(settings: Settings | None = None, *, cwd: Path | None = None) -> Path:
    """데이터 폴더 절대 경로. RRA_DATA_DIR(settings.data_dir) > 원 저장소/data > cwd/data.
    처음 정해질 때 경로 한 줄만 로그에 남긴다(값·비밀 없음)."""
    base = Path(cwd or Path.cwd()).resolve()
    override = settings.data_dir if settings is not None else None
    if override is not None:
        path = Path(override).expanduser()
        if not path.is_absolute():
            path = base / path
        path = path.resolve()
    else:
        root = _git_repo_root(str(base))
        path = (root if root is not None else base) / DATA_DIR_NAME
    if path not in _announced:
        _announced.add(path)
        logger.info("데이터 폴더: %s", path)
    return path


def data_path(settings: Settings | None, rel: str | Path, *, only_prefixed: bool = False) -> Path:
    """데이터 경로를 데이터 폴더 기준 절대 경로로. 절대 경로는 그대로.
    상대 경로는 앞의 `data/` 를 떼고 데이터 폴더 아래로 옮긴다
    (`data/korail_web` → <data_dir>/korail_web).
    only_prefixed=True 면 `data/` 로 시작하는 상대 경로만 옮기고 나머지 상대 경로(runs 등)는
    그대로 둔다."""
    path = Path(rel).expanduser()
    if path.is_absolute():
        return path
    parts = path.parts
    if parts and parts[0] == DATA_DIR_NAME:
        return resolve_data_dir(settings).joinpath(*parts[1:])
    if only_prefixed:
        return path
    return resolve_data_dir(settings) / path


# 데이터 위치 표 — 키: (설정을 읽는 함수, yaml 키, 기본값). composition 의 build_* 와 worktree 보호
# 테스트가 같은 표를 쓴다. 새 데이터 경로는 여기에 더한다 — 소스에 "data/…" 리터럴을 두지 않는다.
_DATA_LOCATIONS: dict[str, tuple[Callable[[Settings], Mapping[str, Any]], str, str]] = {
    "alio_catalog": (lambda s: source_config(s, "alio"), "catalog_dir", "data/catalog"),
    "alio_inbox": (lambda s: source_config(s, "alio"), "inbox_dir", "data/inbox/alio"),
    "alio_summary_inbox": (
        lambda s: source_config(s, "alio").get("summary") or {},
        "inbox_dir",
        "data/inbox/alio_summary",
    ),
    "own_projects_inbox": (lambda s: source_config(s, "own"), "projects_inbox", "data/inbox/own"),
    "own_docs_inbox": (lambda s: source_config(s, "own"), "docs_inbox", "data/inbox/own_docs"),
    "ntis_cache": (
        lambda s: source_config(s, "ntis").get("insights") or {},
        "cache_dir",
        "data/cache/ntis",
    ),
    "korail_web": (korail_web_config, "snapshot_dir", "data/korail_web"),
    "rnd_notice": (rnd_notice_config, "snapshot_dir", "data/rnd_notice"),
    "bai": (lambda s: read_config("bai.yaml", s), "snapshot_dir", "data/bai"),
    "molit": (molit_config, "store_dir", "data/molit"),
    "mofe": (lambda s: read_config("mofe.yaml", s), "store_dir", "data/mofe"),
    "datago": (lambda s: read_config("datago.yaml", s), "store_dir", "data/datago"),
    "vision_store": (
        lambda s: read_config(VISION_FILE, s).get("paths") or {},
        "store",
        "data/korail_web",
    ),
    "vision_snapshots": (
        lambda s: read_config(VISION_FILE, s).get("paths") or {},
        "snapshots",
        "data/korail_web/snapshots",
    ),
    "eval": (lambda s: {}, "", "data/eval"),
    "bench": (lambda s: {}, "", "data/bench"),
    # 로그인 저장소(secret·staff.json·guest.json, 레인 A)·외부 LLM 일일 예산 카운터
    "auth": (lambda s: read_config("auth.yaml", s), "store_dir", "data/auth"),
    "llm_budget": (
        lambda s: read_config("llm.yaml", s).get("budget") or {},
        "counter",
        "data/cache/llm_budget.json",
    ),
    "source_availability": (
        public_ip_config,
        "availability_file",
        "data/cache/source_availability.json",
    ),
}
DATA_LOCATION_KEYS = ("db", *_DATA_LOCATIONS)


def data_location(settings: Settings, key: str, *, cfg: Mapping[str, Any] | None = None) -> Path:
    """표의 한 항목을 데이터 폴더 기준 절대 경로로. cfg 를 주면 그 매핑에서 읽는다(이미 읽은
    yaml)."""
    if key == "db":
        return data_path(settings, settings.db_path)
    loader, field, default = _DATA_LOCATIONS[key]
    table = cfg if cfg is not None else (loader(settings) or {})
    value = table.get(field) if field else None
    return data_path(settings, value or default)


def data_locations(settings: Settings) -> dict[str, Path]:
    """composition 이 쓰는 모든 데이터 경로 {키: 절대 경로}. 진단·보호 테스트용."""
    return {key: data_location(settings, key) for key in DATA_LOCATION_KEYS}


# ── LLM ────────────────────────────────────────────────────
# provider → .env 키 필드 (settings). mlx 는 키가 없다.
LLM_KEY_FIELDS: dict[str, str] = {"openai": "llm_api_key", "gemini": "gemini_api_key"}
REASONING_EFFORTS = ("low", "medium", "high")


def llm_config(
    settings: Settings, stage: str = DEFAULT_STAGE, *, provider: str | None = None
) -> dict[str, Any]:
    """llm.yaml + 환경변수를 합쳐 단계별 LLM 설정을 만든다. 순수 딕셔너리 계산.

    provider 해석 순서: 인자 provider → stages[stage].provider → 환경변수 RRA_LLM_PROVIDER →
    yaml provider. 접속 정보(base_url·model·served_model·json_mode·reasoning_effort)는
    providers[provider] 에서, 없으면 예전 방식의 최상위 키에서. RRA_LLM_BASE_URL 은 기본 provider 를
    쓸 때만 base_url 을 덮는다.
    키 값은 돌려주지 않는다 — 어떤 settings 필드를 쓸지(api_key_field)만.
    """
    cfg = read_config("llm.yaml", settings)
    stages = cfg.get("stages") or {}
    if stage not in stages:
        raise KeyError(f"config/llm.yaml 의 stages 에 {stage!r} 가 없습니다: {sorted(stages)}")
    stage_cfg = stages[stage] or {}
    limits = cfg.get("limits") or {}
    timeout = cfg.get("timeout") or {}
    retries = cfg.get("retries") or {}
    default_provider = str(env_first(settings, "llm_provider", cfg.get("provider")) or "mlx")
    chosen = str(provider or stage_cfg.get("provider") or default_provider)
    table = dict((cfg.get("providers") or {}).get(chosen) or {})
    profile_name, profile = _model_profile(settings, cfg, table)
    table = {**table, **profile}  # 프로필 값이 provider 표의 같은 키를 덮는다
    base_url = table.get("base_url") or cfg.get("base_url")
    if chosen == default_provider and not stage_cfg.get("provider") and provider is None:
        base_url = env_first(settings, "llm_base_url", base_url)
    effort = table.get("reasoning_effort")
    if effort is not None and str(effort) not in REASONING_EFFORTS:
        raise ValueError(
            f"providers.{chosen}.reasoning_effort 는 {'|'.join(REASONING_EFFORTS)} 중 하나입니다 "
            f"(none 금지): {effort!r}"
        )
    if "thinking_level" in table:
        raise ValueError(
            "thinking_level 은 reasoning_effort 와 함께 보낼 수 없습니다 — 설정에서 지우세요."
        )
    system_role = table.get("system_role", True)
    stop = [str(x) for x in (table.get("stop") or []) if str(x)]
    rate = _rate_config(chosen, table.get("rate"))
    return {
        "stage": stage,
        "provider": chosen,
        "profile": profile_name,
        "system_role": bool(system_role),
        "stop": stop,
        "context_length": int(table["context_length"]) if table.get("context_length") else None,
        "base_url": str(base_url),
        "model": stage_cfg.get("model") or table.get("model") or cfg.get("model") or "local",
        "served_model": str(table.get("served_model") or cfg.get("served_model") or "").strip()
        or None,
        "api_key_field": LLM_KEY_FIELDS.get(chosen),
        "reasoning_effort": str(effort) if effort is not None else None,
        "max_tokens": int(stage_cfg.get("max_tokens", 1024)),
        "max_tokens_cap": int(limits.get("max_tokens_cap", 4096)),
        "prompt_max_chars": int(limits.get("prompt_max_chars", 60_000)),
        "temperature": float(stage_cfg.get("temperature", cfg.get("temperature", 0.2))),
        "json_mode": str(table.get("json_mode") or cfg.get("json_mode", "auto")),
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
        # 원격 provider 의 공유 호출 제한기 설정. None 이면 제한기 없음 (로컬 mlx)
        "rate": rate,
    }


RATE_DEFAULT_PROVIDERS = ("gemini", "openai")
RATE_DEFAULTS = {"concurrency": 4, "per_minute": 60}


def _rate_config(provider: str, raw: Any) -> dict[str, int] | None:
    if raw is None and provider not in RATE_DEFAULT_PROVIDERS:
        return None
    table = raw if isinstance(raw, dict) else {}
    return {
        "concurrency": max(1, int(table.get("concurrency", RATE_DEFAULTS["concurrency"]))),
        "per_minute": max(0, int(table.get("per_minute", RATE_DEFAULTS["per_minute"]))),
    }


# ── 이미지 판독 (P3, config/vision.yaml) ───────────────────
VISION_FILE = "vision.yaml"


def vision_config(settings: Settings) -> dict[str, Any]:
    """config/vision.yaml → 거르기·상한·경로·순서. 값 객체(ImageFilterConfig)는 domain 에서
    만든다."""
    cfg = read_config(VISION_FILE, settings)
    paths = cfg.get("paths") or {}
    order = cfg.get("order") or {}
    ocr = cfg.get("ocr") or {}
    return {
        "filter": dict(cfg.get("filter") or {}),
        "photo": dict(cfg.get("photo") or {}),
        "cap": int(cfg.get("cap", 2000)),
        "concurrency": int(cfg.get("concurrency", 1)),
        "snapshots_dir": str(data_location(settings, "vision_snapshots", cfg=paths)),
        "store_dir": str(data_location(settings, "vision_store", cfg=paths)),
        "sample_dir": str(paths.get("sample", "docs/ocr-sample")),
        "order_keywords": {k: list(v) for k, v in order.items() if isinstance(v, list)},
        "attachments": {
            "formats": [
                str(x)
                for x in (
                    (cfg.get("attachments") or {}).get("formats")
                    or ["hwpx", "hwp", "pdf", "pptx", "xlsx"]
                )
            ],
            "max_images_per_file": int(
                (cfg.get("attachments") or {}).get("max_images_per_file", 200)
            ),
            "max_image_bytes": int(
                (cfg.get("attachments") or {}).get("max_image_bytes", 8 * 1024 * 1024)
            ),
            "min_pixels": int((cfg.get("attachments") or {}).get("min_pixels", 20_000)),
        },
        "ocr": {
            "languages": [str(x) for x in (ocr.get("languages") or ["ko-KR", "en-US"])],
            "max_bytes": int(ocr.get("max_bytes", 15 * 1024 * 1024)),
            "max_pixels": int(ocr.get("max_pixels", 40_000_000)),
            "timeout_sec": float(ocr.get("timeout_sec", 90)),
        },
        "image_max_bytes": int(cfg.get("image_max_bytes", 8 * 1024 * 1024)),
        "sample_per_type": int(cfg.get("sample_per_type", 30)),
    }


def _model_profile(
    settings: Settings, cfg: dict[str, Any], table: dict[str, Any]
) -> tuple[str | None, dict[str, Any]]:
    """provider 표의 model_profile(또는 RRA_LLM_PROFILE) → model_profiles[name]. 없으면 빈 값."""
    name = settings.llm_profile or table.get("model_profile")
    if not name:
        return None, {}
    profiles = cfg.get("model_profiles") or {}
    if name not in profiles:
        raise KeyError(
            f"config/llm.yaml 의 model_profiles 에 {name!r} 가 없습니다: {sorted(profiles)}"
        )
    profile = dict(profiles[name] or {})
    if "served_model" in profile and isinstance(profile["served_model"], str):
        profile["served_model"] = str(Path(profile["served_model"]).expanduser())
    return str(name), profile


def model_profiles(settings: Settings) -> dict[str, dict[str, Any]]:
    """llm.yaml model_profiles 전체 (벤치 보고용)."""
    return dict(read_config("llm.yaml", settings).get("model_profiles") or {})


def llm_key_present(settings: Settings, cfg: dict[str, Any]) -> bool:
    """이 provider 의 키가 .env 에 있는지 (값은 돌려주지 않는다). 키가 없는 provider 는 True."""
    field = cfg.get("api_key_field")
    if not field:
        return True
    secret = getattr(settings, field, None)
    return bool(
        secret is not None and secret.get_secret_value().strip().lower() not in ("", "none")
    )


def review_policy(settings: Settings) -> dict[str, Any]:
    """llm.yaml 의 review·external_llm 정책 (기본: auto=true, include_internal=true)."""
    cfg = read_config("llm.yaml", settings)
    review = cfg.get("review") or {}
    external = cfg.get("external_llm") or {}
    return {
        "auto": bool(review.get("auto", True)),
        "include_internal": bool(external.get("include_internal", True)),
    }


def pipeline_config(settings: Settings):
    """config/pipeline.yaml → PipelineConfig (파일이 없으면 기본값). 모르는 키는 오류."""
    from rra.domain.models import PipelineConfig

    try:
        cfg = read_config("pipeline.yaml", settings)
    except FileNotFoundError:
        return PipelineConfig()
    known = set(PipelineConfig.model_fields)
    unknown = set(cfg or {}) - known
    if unknown:
        raise ValueError(f"config/pipeline.yaml 에 모르는 키: {sorted(unknown)}")
    return PipelineConfig(**(cfg or {}))


def usability_config(settings: Settings):
    """config/usability.yaml → UsabilityConfig (파일이 없으면 기본값 = 전부 켬). 모르는 키 오류."""
    from rra.domain.models import UsabilityConfig

    cfg = read_config("usability.yaml", settings) or {}
    known = set(UsabilityConfig.model_fields)
    unknown = set(cfg) - known
    if unknown:
        raise ValueError(f"config/usability.yaml 에 모르는 키: {sorted(unknown)}")
    return UsabilityConfig(**cfg)


def section_checklists(settings: Settings) -> dict[str, list[dict[str, Any]]]:
    """config/templates/section_checklists.yaml → {섹션: [{element, question, keywords[]}]}.
    파일이 없으면 빈 dict (U3 보완 질문 없음)."""
    data = read_config("templates/section_checklists.yaml", settings) or {}
    out: dict[str, list[dict[str, Any]]] = {}
    for key, items in (data.get("sections") or {}).items():
        rows = []
        for item in items or []:
            if not isinstance(item, dict) or not item.get("element"):
                continue
            rows.append(
                {
                    "element": str(item["element"]),
                    "question": str(
                        item.get("question") or f"{item['element']} 을(를) 적어 주십시오."
                    ),
                    "keywords": [str(k) for k in (item.get("keywords") or []) if str(k)],
                }
            )
        out[str(key)] = rows
    return out


def recommend_policy(settings: Settings) -> dict[str, Any]:
    """llm.yaml 의 recommend 정책 (기본: auto=true — precheck 뒤 자동 1회)."""
    cfg = read_config("llm.yaml", settings)
    rec = cfg.get("recommend") or {}
    mode = str(rec.get("self_overlap", "warn"))
    if mode not in ("warn", "exclude"):
        raise ValueError(f"llm.yaml recommend.self_overlap 은 warn|exclude 중 하나: {mode!r}")
    return {"auto": bool(rec.get("auto", True)), "self_overlap": mode}


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


def relevance_floor(settings: Settings) -> RelevanceFloor:
    """생성 근거의 관련도 하한 (config/overlap.yaml `evidence_floor`). 없으면 도메인 기본값.
    출처별 최소 보장(min_per_source)은 config/retrieval_mix.yaml 이 있으면 그 값이 우선한다."""
    cfg = read_config("overlap.yaml", settings).get("evidence_floor") or {}
    if not isinstance(cfg, dict):
        raise ValueError("overlap.yaml evidence_floor 는 매핑이어야 합니다.")
    keys = ("min_similarity", "min_keyword_hits", "min_per_source", "search_multiplier")
    values = {k: cfg[k] for k in keys if k in cfg}
    mix = _retrieval_mix_raw(settings)
    if mix is not None and "min_per_source" in mix:
        values["min_per_source"] = mix["min_per_source"]
    return RelevanceFloor.model_validate(values)


def overlap_candidates(settings: Settings):
    """config/overlap.yaml `candidates` → OverlapCandidateRule (ADR 0028). 절이 없으면 제한 없음."""
    from rra.domain.rules.overlap_candidates import OverlapCandidateRule, SourceMember

    cfg = read_config("overlap.yaml", settings).get("candidates") or {}
    if not isinstance(cfg, dict):
        raise ValueError("overlap.yaml candidates 는 매핑이어야 합니다.")

    def members(items: Any, where: str) -> tuple[SourceMember, ...]:
        if items is None:
            return ()
        if not isinstance(items, list):
            raise ValueError(f"overlap.yaml candidates.{where} 는 목록이어야 합니다.")
        out = []
        for item in items:
            if not isinstance(item, dict) or not item.get("source"):
                raise ValueError(f"overlap.yaml candidates.{where} 항목에는 source 가 필요합니다.")
            out.append(
                SourceMember(
                    source=str(item["source"]),
                    doc_types=tuple(str(x) for x in (item.get("doc_types") or [])),
                )
            )
        return tuple(out)

    research = cfg.get("research") or {}
    if not isinstance(research, dict):
        raise ValueError("overlap.yaml candidates.research 는 매핑이어야 합니다.")
    pool = cfg.get("pool") or {}
    if not isinstance(pool, dict):
        raise ValueError("overlap.yaml candidates.pool 은 매핑이어야 합니다.")
    return OverlapCandidateRule(
        project=members(cfg.get("project"), "project"),
        research=members(research.get("members"), "research.members"),
        research_k=int(research.get("k", 5)),
        per_source=int(pool.get("per_source", 0)),
        pool_size=int(pool.get("size", 30)),
    )


def _retrieval_mix_raw(settings: Settings) -> dict[str, Any] | None:
    if not (Path(settings.config_dir) / "retrieval_mix.yaml").is_file():
        return None
    cfg = read_config("retrieval_mix.yaml", settings)
    if not isinstance(cfg, dict):
        raise ValueError("retrieval_mix.yaml 은 매핑이어야 합니다.")
    return cfg


def retrieval_mix(settings: Settings):
    """config/retrieval_mix.yaml → RetrievalMix (파일이 없으면 None = 규칙 없음)."""
    from rra.domain.rules.retrieval_mix import RetrievalMix, SectionMix

    cfg = _retrieval_mix_raw(settings)
    if cfg is None:
        return None
    sections = {}
    for key, item in (cfg.get("sections") or {}).items():
        if not isinstance(item, dict):
            raise ValueError(f"retrieval_mix.yaml sections.{key} 는 매핑이어야 합니다.")
        sections[str(key)] = SectionMix(
            allow=tuple(str(x) for x in (item.get("allow") or [])),
            min_scholarly=int(item.get("min_scholarly", 0)),
        )
    return RetrievalMix(
        min_per_source=int(cfg.get("min_per_source", 6)),
        section_min_per_source=int(cfg.get("section_min_per_source", 2)),
        scholarly=tuple(str(x) for x in (cfg.get("scholarly") or ["paper", "report", "patent"])),
        sections=sections,
        overlap_exclude=tuple(str(x) for x in (cfg.get("overlap_exclude") or [])),
        candidates=overlap_candidates(settings),  # generate 의 판정도 같은 후보 집합(ADR 0028)
    )


# ── 양식 ───────────────────────────────────────────────────
def lint_rules(settings: Settings) -> LintRules:
    """config/templates/<TEMPLATE>.rules.yaml → LintRules. 섹션 순서 = sections."""
    data = read_config(f"templates/{TEMPLATE}.rules.yaml", settings)
    if not data.get("required_sections"):
        raise KeyError(f"templates/{TEMPLATE}.rules.yaml 에 required_sections 가 없습니다.")
    return LintRules.model_validate(data)


def strategy_source(settings: Settings) -> str:
    """config/strategy.yaml `source`: draft(초안 파일 사용) | confirmed(확정 파일, 기본)."""
    value = str(read_config("strategy.yaml", settings).get("source") or "confirmed")
    if value not in STRATEGY_SOURCES:
        raise ValueError(f"config/strategy.yaml source 는 draft|confirmed 중 하나: {value!r}")
    return value


def strategy_catalog(settings: Settings) -> StrategyCatalog:
    """코레일 전략체계. strategy.yaml source 가 draft 면 korail_strategy.draft.yaml(status=draft),
    confirmed 면 korail_strategy.yaml. 파일이 없거나 비면 빈 목록."""
    status = strategy_source(settings)
    data = read_config(STRATEGY_DRAFT_FILE if status == "draft" else STRATEGY_FILE, settings)
    return StrategyCatalog.model_validate(
        {
            "source": data.get("source") or "",
            "status": status,
            "directions": data.get("directions") or [],
        }
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
    "kipris": {"RRA_KIPRIS_KEY": "kipris_key"},
    "g2b": {"RRA_DATA_GO_KR_KEY": "data_go_kr_key"},  # 나라장터 입찰공고정보서비스 (공공데이터포털)
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
