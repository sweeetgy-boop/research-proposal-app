"""C. 아웃바운드 허용목록 + 7. 원본 캐시. Step 2에서 httpx 연결."""

from __future__ import annotations

import hashlib
import ipaddress
import socket
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SECRET_PARAMS = {"key", "apikey", "api_key", "servicekey", "accesskey", "token"}
PRIVATE_NETS = [
    ipaddress.ip_network(n)
    for n in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "::1/128",
        "fc00::/7",
    )
]


def strip_secrets(url: str) -> str:
    p = urlsplit(url)
    q = [
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=True)
        if k.lower() not in SECRET_PARAMS
    ]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ""))


def cache_key(url: str) -> str:
    return hashlib.sha256(strip_secrets(url).encode()).hexdigest()


def host_allowed(url: str, allowed: set[str]) -> bool:
    host = urlsplit(url).hostname or ""
    return host in allowed


def resolves_private(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if any(ip in n for n in PRIVATE_NETS):
            return True
    return False
