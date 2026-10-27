"""자료원 IP 제한 판정 — 순수 함수 (레인 I, 2026-10-27).

NTIS 같은 자료원은 활용신청에 등록한 서버 IP 에서만 호출을 받는다(다르면 HTTP 200 +
`<error>접근 허용 IP가 아닙니다.</error>`). 여기서는 세 가지만 판단한다:

- 현재 공인 IP 가 자료원 등록 IP 목록에 있는가 (`ip_registered`),
- API 오류 문구가 IP 거부인가 (`is_ip_error`) — 어댑터는 이때 `SourceIpBlocked`(의 하위 예외)를
  올린다,
- 사람에게 보일 안내 문구 (`unregistered_notice`) — CLI·로그·웹 자료원 상태가 같은 문구를 쓴다.

IP 조회·설정 읽기·네트워크는 밖(어댑터·조립)의 일이다.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

# API 오류 본문에서 IP 거부로 보는 문구 (대소문자 무시).
# NTIS 실문구 "접근 허용 IP가 아닙니다." (2026-10-27 실호출).
IP_ERROR_PHRASES: tuple[str, ...] = (
    "접근 허용 ip",
    "허용 ip가 아닙니다",
    "허용된 ip",
    "등록된 ip",
    "ip 제한",
    "not allowed ip",
    "ip not allowed",
    "unauthorized ip",
    "ip address is not",
)
NOTICE = "현재 IP {ip} 가 {source} 등록 IP 에 없습니다. 활용신청에 추가하세요"
UNKNOWN_IP = "(확인 실패)"
MAX_REGISTERED = 50


class SourceIpBlocked(RuntimeError):
    """자료원 API 가 호출 IP 를 거부했다. 어댑터가 IP 오류 응답을 이 종류(또는 하위 종류)로 올리면
    유스케이스는 그 자료원만 건너뛴다. 메시지에는 짧은 문구만 (키·URL 없음)."""


@dataclass(frozen=True)
class IpPolicy:
    """자료원 하나의 IP 제한. restricted=False 면 등록 목록을 보지 않는다."""

    restricted: bool = False
    registered_ips: tuple[str, ...] = ()
    source_label: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None, *, label: str = "") -> IpPolicy:
        """sources.yaml 항목(`ip_restricted`·`registered_ips`) → IpPolicy. 잘못된 IP 는 뺀다."""
        raw = raw or {}
        ips = raw.get("registered_ips") or []
        if not isinstance(ips, list | tuple):
            ips = []
        cleaned = tuple(
            normalize_ip(str(ip)) for ip in ips[:MAX_REGISTERED] if normalize_ip(str(ip))
        )
        return cls(
            restricted=bool(raw.get("ip_restricted", bool(cleaned))),
            registered_ips=cleaned,
            source_label=label,
        )


def normalize_ip(text: str) -> str:
    """IPv4/IPv6 문자열을 정규형으로. 아니면 빈 문자열."""
    try:
        return str(ipaddress.ip_address(text.strip()))
    except ValueError:
        return ""


def is_ip_error(message: str | None) -> bool:
    """API 오류 문구가 IP 거부인가."""
    if not message:
        return False
    lowered = " ".join(message.lower().split())
    return any(p in lowered for p in IP_ERROR_PHRASES)


def ip_registered(ip: str | None, policy: IpPolicy) -> bool | None:
    """현재 IP 가 등록 목록에 있는가. 제한 없는 자료원은 True, IP 를 모르면 None."""
    if not policy.restricted:
        return True
    normalized = normalize_ip(ip or "")
    if not normalized:
        return None
    return normalized in policy.registered_ips


def unregistered_notice(ip: str | None, source: str) -> str:
    """"현재 IP <값> 가 <자료원> 등록 IP 에 없습니다. 활용신청에 추가하세요".

    IP 를 모르면 (확인 실패)."""
    return NOTICE.format(ip=normalize_ip(ip or "") or UNKNOWN_IP, source=source)


def ip_notice(ip: str | None, policy: IpPolicy, *, blocked: bool = False) -> str | None:
    """안내가 필요하면 문구, 아니면 None.

    - 제한 자료원인데 현재 IP 가 등록 목록에 없다 → 안내.
    - API 가 IP 거부를 돌려줬다(blocked) → 등록 여부와 무관하게 안내 (등록 반영 전·IP 변동).
    - IP 조회에 실패했고 거부도 없었다 → None (진단만 남기고 계속).
    """
    if not policy.restricted and not blocked:
        return None
    if blocked or ip_registered(ip, policy) is False:
        return unregistered_notice(ip, policy.source_label or "자료원")
    return None


def restricted_sources(policies: Mapping[str, IpPolicy]) -> list[str]:
    return [name for name, p in policies.items() if p.restricted]


def lookup_needed(policies: Iterable[IpPolicy]) -> bool:
    """등록 목록 대조가 필요한 자료원이 하나라도 있는가."""
    return any(p.restricted for p in policies)
