"""ScienceON API Gateway 인증 — accounts 암호화(순수) + TokenManager(발급·갱신·만료).

흐름 (공개 서드파티 가이드 기준, 첫 실응답으로 확인할 것):
  GET /tokenrequest.do?client_id=<ID>&accounts=<enc>   → access(2시간) · refresh(2주)
  GET /tokenrequest.do?refreshToken=<RT>&client_id=<ID> → access 재발급
  enc = urlsafe_b64(AES-256-CBC(PKCS7({"datetime":"YYYYMMDDHHMMSS","mac_address":"AA-BB-.."}),
                                key=인증키 32바이트, iv=고정 16바이트))

보안 D:
- 키·MAC·토큰은 SecretStr 로 받아 요청 파라미터를 만드는 순간에만 꺼낸다. 로그·예외 메시지에 없음.
- 토큰은 메모리에만 둔다 (디스크 캐시 없음). ingest 한 번에 발급 1회가 기본.
- client_id·accounts·refreshToken·token 은 _base.SECRET_PARAMS 로 오류 메시지에서 제거된다.
"""

from __future__ import annotations

import base64
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import SecretStr

from rra.adapters.sources._base import FetchError, GuardedClient

FIXED_IV = b"jvHJ1EFA0IXBrxxz"
ACCESS_TTL_SEC = 2 * 3600
REFRESH_TTL_SEC = 14 * 24 * 3600
EXPIRY_MARGIN_SEC = 120  # 만료 직전 토큰으로 긴 페이지 요청을 보내지 않도록
TOKEN_TYPES = frozenset({"application/json", "text/json", "text/plain", "text/html"})
_MAC = re.compile(r"^([0-9A-F]{2})([:-]?)([0-9A-F]{2})(?:\2[0-9A-F]{2}){4}$")


class ScienceOnAuthError(FetchError):
    """토큰 발급·갱신 실패. 메시지에는 오류 코드만 (키·MAC·토큰 없음)."""


def normalize_mac(mac: str) -> str:
    """AA:BB:CC:DD:EE:FF / aa-bb-… / AABBCCDDEEFF → AA-BB-CC-DD-EE-FF."""
    raw = mac.strip().upper()
    if not _MAC.match(raw):
        raise ValueError("MAC 주소 형식이 올바르지 않습니다 (예: AA-BB-CC-DD-EE-FF).")
    hexes = re.sub(r"[^0-9A-F]", "", raw)
    return "-".join(hexes[i : i + 2] for i in range(0, 12, 2))


def encrypt_accounts(auth_key: str, mac: str, now: datetime) -> str:
    """순수 함수. 같은 입력이면 같은 출력 (IV 고정)."""
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    key = auth_key.encode("utf-8")
    if len(key) != 32:
        raise ValueError("ScienceON 인증키는 32바이트여야 합니다.")
    plain = json.dumps(
        {"datetime": now.strftime("%Y%m%d%H%M%S"), "mac_address": normalize_mac(mac)},
        separators=(",", ":"),
    ).encode("utf-8")
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plain) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(FIXED_IV)).encryptor()
    return base64.urlsafe_b64encode(encryptor.update(padded) + encryptor.finalize()).decode()


@dataclass
class _Token:
    access: str
    access_until: float
    refresh: str | None
    refresh_until: float


def parse_token_response(data: Any, now: float) -> _Token:
    """토큰 응답(JSON) → _Token. 만료 시각 필드가 없으면 문서화된 수명(2시간·2주)을 쓴다."""
    if not isinstance(data, dict):
        raise ScienceOnAuthError("토큰 응답이 JSON 객체가 아닙니다.")
    access = data.get("access_token") or data.get("accessToken")
    if not isinstance(access, str) or not access:
        code = data.get("errorCode") or data.get("error_code") or data.get("code") or "unknown"
        raise ScienceOnAuthError(f"토큰 발급 실패 (code={str(code)[:20]})")
    refresh = data.get("refresh_token") or data.get("refreshToken")
    return _Token(
        access=access,
        access_until=now + ACCESS_TTL_SEC,
        refresh=refresh if isinstance(refresh, str) and refresh else None,
        refresh_until=now + REFRESH_TTL_SEC,
    )


class TokenManager:
    def __init__(
        self,
        client: GuardedClient,
        base_url: str,
        *,
        client_id: SecretStr,
        auth_key: SecretStr,
        mac: SecretStr,
        clock: Callable[[], float] = time.time,
        now: Callable[[], datetime] = datetime.now,
    ):
        self._client = client
        self._url = f"{base_url.rstrip('/')}/tokenrequest.do"
        self._client_id = client_id
        self._auth_key = auth_key
        self._mac = mac
        self._clock = clock
        self._now = now
        self._token: _Token | None = None
        self.issued = 0  # 테스트·진단용 (발급 횟수)
        self.refreshed = 0

    def __repr__(self) -> str:
        return "TokenManager()"

    @property
    def client_id(self) -> str:
        return self._client_id.get_secret_value()

    async def token(self) -> str:
        t, now = self._token, self._clock()
        if t and now < t.access_until - EXPIRY_MARGIN_SEC:
            return t.access
        if t and t.refresh and now < t.refresh_until - EXPIRY_MARGIN_SEC:
            try:
                return await self._refresh(t.refresh)
            except ScienceOnAuthError:
                pass  # refresh 가 거부되면 새로 발급
        return await self._issue()

    def invalidate(self) -> None:
        """서버가 토큰 만료(E4103)를 알렸을 때. 다음 token() 은 refresh → 재발급 순으로 시도."""
        if self._token:
            self._token.access_until = 0.0

    async def _issue(self) -> str:
        accounts = encrypt_accounts(
            self._auth_key.get_secret_value(), self._mac.get_secret_value(), self._now()
        )
        data = await self._get({"client_id": self.client_id, "accounts": accounts})
        self._token = parse_token_response(data, self._clock())
        self.issued += 1
        return self._token.access

    async def _refresh(self, refresh: str) -> str:
        data = await self._get({"refreshToken": refresh, "client_id": self.client_id})
        fresh = parse_token_response(data, self._clock())
        if fresh.refresh is None and self._token:  # refresh 응답이 refresh 토큰을 안 줄 수 있다
            fresh.refresh, fresh.refresh_until = self._token.refresh, self._token.refresh_until
        self._token = fresh
        self.refreshed += 1
        return fresh.access

    async def _get(self, params: dict[str, str]) -> Any:
        body = await self._client.get_bytes(self._url, params, accept_types=TOKEN_TYPES)
        try:
            return json.loads(body)
        except ValueError:
            raise ScienceOnAuthError("토큰 응답이 JSON 이 아닙니다.") from None
