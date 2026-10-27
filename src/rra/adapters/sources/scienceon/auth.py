"""ScienceON API Gateway 인증 — accounts 암호화(순수) + TokenManager(발급·갱신·만료).

흐름 (API Gateway 공식 가이드 "API 인증 안내" + 2026-10-27 실응답으로 확인):
  GET /tokenrequest.do?client_id=<ID>&accounts=<enc>
    → JSON {access_token, access_token_expire, refresh_token, refresh_token_expire, issued_at}
  GET /tokenrequest.do?refresh_token=<RT>&client_id=<ID>  → access 재발급 (이름이 refresh_token)
  enc = urlsafe_b64(AES-256-CBC(PKCS7({"mac_address":"AA-BB-..","datetime":"YYYYMMDDHHMMSS"}),
                                key=인증키 32자, iv=고정 16바이트))   — 표준 base64 도 서버가 받는다
  client_id 는 64자, 인증키는 32자 (둘이 바뀌면 복호화 실패 → XML E5001 내부 서버 오류).
  토큰 오류는 JSON(E4005~E4108) 또는 XML(MetaData/errorDetail/errorCode) 로 온다.

보안 D:
- 키·MAC·토큰은 SecretStr 로 받아 요청 파라미터를 만드는 순간에만 꺼낸다. 로그·예외 메시지에 없음.
- 토큰은 메모리에만 둔다 (디스크 캐시 없음). ingest 한 번에 발급 1회가 기본.
- client_id·accounts·refresh_token·token 은 _base.SECRET_PARAMS 로 오류 메시지에서 제거된다.
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
TOKEN_TYPES = frozenset(
    {"application/json", "text/json", "text/plain", "text/html", "text/xml", "application/xml"}
)
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
        raise ValueError(
            f"ScienceON 인증키는 32자여야 합니다 (지금 {len(key)}바이트). client_id 는 64자 — "
            ".env 의 RRA_SCIENCEON_CLIENT_ID 와 RRA_SCIENCEON_KEY 가 서로 바뀌지 않았는지 확인."
        )
    plain = json.dumps(
        {"mac_address": normalize_mac(mac), "datetime": now.strftime("%Y%m%d%H%M%S")},
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
    """토큰 응답(JSON) → _Token. 만료는 문서화된 수명(2시간·2주)을 쓴다 (서버 만료 문자열은 KST
      벽시계라
    로컬 시계와 비교하지 않는다)."""
    if not isinstance(data, dict):
        raise ScienceOnAuthError("토큰 응답이 JSON 객체가 아닙니다.")
    access = data.get("access_token") or data.get("accessToken")
    if not isinstance(access, str) or not access:
        code = data.get("errorCode") or data.get("error_code") or data.get("code") or "unknown"
        raise ScienceOnAuthError(f"토큰 발급 실패 (code={_safe_code(code)})")
    refresh = data.get("refresh_token") or data.get("refreshToken")
    return _Token(
        access=access,
        access_until=now + ACCESS_TTL_SEC,
        refresh=refresh if isinstance(refresh, str) and refresh else None,
        refresh_until=now + REFRESH_TTL_SEC,
    )


def _safe_code(code: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "", str(code))[:20] or "unknown"


def _xml_error_code(body: bytes) -> str:
    """XML 오류 본문(MetaData/errorDetail/errorCode) 에서 코드만 꺼낸다. 본문은 메시지에 넣지
    않는다.
    """
    from rra.adapters.sources import _xml

    try:
        root = _xml.parse(body)
    except _xml.XmlResponseError:
        return "unknown"
    # errorDetail/errorCode 가 resultSummary/statusCode 보다 뒤에 오므로 따로 찾는다
    return _safe_code(_xml.first_text(root, "errorCode") or _xml.first_text(root, "statusCode"))


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
        data = await self._get({"refresh_token": refresh, "client_id": self.client_id})
        fresh = parse_token_response(data, self._clock())
        if fresh.refresh is None and self._token:  # refresh 응답이 refresh 토큰을 안 줄 수 있다
            fresh.refresh, fresh.refresh_until = self._token.refresh, self._token.refresh_until
        self._token = fresh
        self.refreshed += 1
        return fresh.access

    async def _get(self, params: dict[str, str]) -> Any:
        body = await self._client.get_bytes(self._url, params, accept_types=TOKEN_TYPES)
        if body.lstrip().startswith(b"<"):  # 게이트웨이는 복호화 실패 등을 XML 오류로 돌려준다
            raise ScienceOnAuthError(f"토큰 발급 실패 (code={_xml_error_code(body)})")
        try:
            return json.loads(body)
        except ValueError:
            raise ScienceOnAuthError("토큰 응답이 JSON 이 아닙니다.") from None
