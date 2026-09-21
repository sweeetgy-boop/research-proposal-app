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

    db_path: Path = Path("data/rra.sqlite")
    runs_dir: Path = Path("runs")
    config_dir: Path = Path("config")

    llm_provider: str = "mlx"
    llm_base_url: str = "http://127.0.0.1:8080/v1"
    llm_api_key: SecretStr = Field(default=SecretStr("none"))

    # ScienceON: client_id + 32자 인증키 + ScienceON 에 등록한 MAC 주소 → 토큰 발급.
    # MAC 은 기기마다 다르다(개발 MacBook·배포 Mac mini 각각 등록, .env 도 기기별로).
    scienceon_client_id: SecretStr | None = None
    scienceon_key: SecretStr | None = None
    scienceon_mac: SecretStr | None = None
    kipris_key: SecretStr | None = None
    ntis_key: SecretStr | None = None  # NTIS rndopen apprvKey (과제검색 활용신청)
    api_token: SecretStr | None = None

    deploy_mode: str = "local"


def _check_env_permissions(path: Path = Path(".env")) -> None:
    if not path.exists() or os.name == "nt":
        return
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise SystemExit(f".env 권한이 {oct(mode)} 입니다. chmod 600 .env 후 다시 실행하세요.")


def load_settings() -> Settings:
    _check_env_permissions()
    return Settings()
