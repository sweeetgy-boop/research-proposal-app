"""진단 유스케이스 — `rra llm-check`·`rra sources check` 가 쓴다. 외부 접근은 포트로만.

결과에는 비밀 값·문서 본문이 들어가지 않는다 (보안 D·I). 실패는 예외 클래스명과 짧은 메시지만.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from rra.application.ports import ProbingSource, PublicIpPort, SourceAvailabilityPort
from rra.domain.rules.source_ip import (
    IpPolicy,
    SourceIpBlocked,
    ip_notice,
    ip_registered,
    lookup_needed,
)

MAX_LISTED = 5
MAX_ERROR_CHARS = 300


# ── served_model (manifest 표시용 모델명) ─────────────────
MODEL_ID_PREFIX = "models/"  # Gemini OpenAI 호환 /v1/models 는 id 를 "models/gemini-…" 로 준다


def _model_id(name: str) -> str:
    """비교용 이름: 공백 제거, "models/" 접두어 1개 제거. 대소문자는 그대로 (정확 일치)."""
    name = name.strip()
    return name.removeprefix(MODEL_ID_PREFIX) if name.startswith(MODEL_ID_PREFIX) else name


def served_model_listed(candidates: Iterable[str], listed: Iterable[str]) -> bool:
    """/v1/models 목록에 선언한 모델 이름이 있는지. 오타·엉뚱한 이름만 거른다 (정확 일치).

    양쪽 모두 "models/" 접두어를 떼고 비교한다 — llm.yaml 의 served_model "gemini-4-argon" 과
    Gemini 목록의 "models/gemini-4-argon" 은 같은 모델이다.
    """
    wanted = {name for c in candidates if (name := _model_id(c))}
    return bool(wanted & {name for m in listed if (name := _model_id(m))})


async def check_served_model(
    llm: object, served: str | None, aliases: Iterable[str] = ()
) -> str | None:
    """served_model 이 서버 목록에 없으면 경고 문구, 괜찮으면 None. 기동을 막지 않는다.

    llm 이 ModelListingPort(list_models) 를 구현하지 않으면 확인하지 않는다 (None).
    aliases: served 와 같은 것으로 볼 이름들 (로컬 경로의 절대경로 등) — 조립이 넘긴다.
    """
    if not served:
        return "llm.yaml 에 served_model 이 없습니다 — manifest 에 요청용 모델 이름이 남습니다."
    lister = getattr(llm, "list_models", None)
    if lister is None:
        return None
    try:
        listed = list(await lister())
    except Exception as exc:  # 진단일 뿐 — 실패해도 왕복 확인은 계속한다
        return f"/v1/models 조회 실패 ({type(exc).__name__}) — served_model 을 확인하지 못했습니다."
    if served_model_listed({served, *aliases}, listed):
        return None
    shown = (
        ", ".join(listed[:MAX_LISTED]) + (" …" if len(listed) > MAX_LISTED else "")
        if listed
        else "(비어 있음)"
    )
    return (
        f"served_model {served!r} 이 서버 /v1/models 목록에 없습니다 — 오타이거나 다른 모델입니다. "
        f"목록: {shown}"
    )


# ── 자료원 연결 확인 ──────────────────────────────────────
@dataclass(frozen=True)
class SourceTarget:
    """점검 대상 하나. 조립이 설정에서 만든다 — 유스케이스는 값의 유무만 본다."""

    name: str
    host: str
    host_allowed: bool
    credentials: dict[str, bool] = field(default_factory=dict)
    # 키·허용목록이 갖춰졌을 때만 조립이 넘긴다. None 이면 왕복을 건너뛴다.
    connect: Callable[[], ProbingSource] | None = None
    # 자료원 IP 제한 (sources.yaml ip_restricted·registered_ips). None 이면 IP 항목을 내지 않는다.
    ip_policy: IpPolicy | None = None

    @property
    def ready(self) -> bool:
        return self.connect is not None and all(self.credentials.values()) and self.host_allowed


class CheckSources:
    """소스별 키 유무(값 없음)·허용목록·왕복 1회. 한 소스가 실패해도 다음 소스를 확인한다.

    IP 제한 자료원이 있으면 현재 공인 IP 를 한 번 조회해(PublicIpPort) 등록 목록과 대조한다 — 조회
    실패는 `ip_lookup_error` 진단만 남기고 계속. 안내 문구(`ip_notice`)는 domain/rules/source_ip 가
    정하고, availability 가 있으면 자료원별로 기록·해제해 웹 자료원 상태가 같은 문구를 보인다.
    """

    def __init__(
        self,
        targets: list[SourceTarget],
        *,
        public_ip: PublicIpPort | None = None,
        availability: SourceAvailabilityPort | None = None,
    ):
        self.targets = list(targets)
        self.public_ip = public_ip
        self.availability = availability

    async def __call__(self) -> list[dict[str, Any]]:
        ip, lookup_error = await self._current_ip()
        return [await self._check(t, ip, lookup_error) for t in self.targets]

    async def _current_ip(self) -> tuple[str | None, str | None]:
        """IP 제한 자료원 중 왕복할 수 있는 것이 있을 때만 조회한다 (키 없으면 조회도 없음)."""
        policies = [t.ip_policy for t in self.targets if t.ip_policy is not None and t.ready]
        if self.public_ip is None or not lookup_needed(policies):
            return None, None
        try:
            return await self.public_ip.current_ip(), None
        except Exception as exc:  # 진단일 뿐 — 왕복은 계속한다
            return None, type(exc).__name__
        finally:
            await self.public_ip.aclose()

    async def _check(
        self, target: SourceTarget, ip: str | None, lookup_error: str | None
    ) -> dict[str, Any]:
        row: dict[str, Any] = {
            "source": target.name,
            "credentials": dict(target.credentials),
            "host": target.host,
            "host_allowed": target.host_allowed,
            "roundtrip": "skipped",
        }
        blocked = False
        if target.ready:
            source = target.connect()  # type: ignore[misc]
            try:
                row["result"] = await source.probe()
                row["roundtrip"] = "ok"
            except Exception as exc:  # 진단 — 메시지는 어댑터가 비밀을 제거한 것만 올린다
                row["roundtrip"] = type(exc).__name__
                row["error"] = str(exc)[:MAX_ERROR_CHARS]
                blocked = isinstance(exc, SourceIpBlocked)
            finally:
                await source.aclose()
        policy = target.ip_policy
        if policy is None:
            return row
        row["ip_restricted"] = policy.restricted
        row["registered_ips"] = list(policy.registered_ips)
        row["current_ip"] = ip if policy.restricted else None
        if policy.restricted and lookup_error:
            row["ip_lookup_error"] = lookup_error
        row["ip_registered"] = ip_registered(ip, policy) if policy.restricted else None
        notice = ip_notice(ip, policy, blocked=blocked)
        row["ip_notice"] = notice
        if self.availability is not None and (notice or row["roundtrip"] == "ok"):
            self.availability.record(target.name, notice)
        return row
