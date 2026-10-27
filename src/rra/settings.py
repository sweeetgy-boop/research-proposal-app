"""D. 비밀 관리 — 유일한 환경 로딩 지점.

- SecretStr 로 키 보관 (repr/log 미출력)
- .env 권한 600 아니면 기동 거부
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RRA_", env_file=".env", extra="ignore")

    # 모든 실행 데이터(DB·스냅샷·캐시·inbox)의 뿌리. 비우면 config_loader.resolve_data_dir 가
    # 원 저장소(git common dir 의 부모)/data 를 쓴다 — 레인 worktree 안에 데이터를 남기지 않는다.
    data_dir: Path | None = None
    db_path: Path = Path("data/rra.sqlite")  # 상대 경로는 data_dir 기준으로 다시 맞춘다
    runs_dir: Path = Path("runs")
    config_dir: Path = Path("config")

    llm_provider: str = "mlx"
    llm_profile: str | None = (
        None  # llm.yaml model_profiles 키. 있으면 provider 표의 model_profile 을 덮는다
    )
    llm_base_url: str = "http://127.0.0.1:8080/v1"
    llm_api_key: SecretStr = Field(default=SecretStr("none"))
    gemini_api_key: SecretStr | None = None  # provider=gemini (검토 단계). 없으면 검토 건너뜀

    # ScienceON: client_id + 32자 인증키 + ScienceON 에 등록한 MAC 주소 → 토큰 발급.
    # MAC 은 기기마다 다르다(개발 MacBook·배포 Mac mini 각각 등록, .env 도 기기별로).
    scienceon_client_id: SecretStr | None = None
    scienceon_key: SecretStr | None = None
    scienceon_mac: SecretStr | None = None
    kipris_key: SecretStr | None = None
    openalex_mailto: str | None = (
        None  # OpenAlex polite pool 연락 이메일 (요청 URL 에 실린다, 비밀 아님)
    )
    openalex_api_key: SecretStr | None = None  # 선택 — 없어도 page 페이징으로 수집된다
    ntis_key: SecretStr | None = None  # NTIS rndopen apprvKey (과제검색 활용신청)
    # 공공데이터포털 일반 인증키(서비스별 활용신청, 같은 키) — 나라장터 입찰공고 API (g2b, P2-6).
    # 파일데이터는
    # 키
    # 불필요
    data_go_kr_key: SecretStr | None = None
    api_token: SecretStr | None = None
    # REST API 바인딩 (G). 기본 루프백. 외부 공개는 HTTPS 역프록시(Tailscale·Cloudflare) 뒤에서만.
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    deploy_mode: str = "local"
    # e2e·스키마 추출용 가짜 모드 (RRA_FAKE_LLM=1): 가짜 LLM(작성·검토)·메모리 저장소. 운영 금지
    fake_llm: bool = False
    static_dir: Path = Path("web/dist")  # 프론트엔드 빌드 산출물. 없으면 "/" 는 404


def _check_env_permissions(path: Path = Path(".env")) -> None:
    if not path.exists() or os.name == "nt":
        return
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise SystemExit(f".env 권한이 {oct(mode)} 입니다. chmod 600 .env 후 다시 실행하세요.")


def load_settings() -> Settings:
    _check_env_permissions()
    return Settings()
