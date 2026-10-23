"""조립 지점 — 화면이 유스케이스에 닿는 유일한 통로.

테스트는 build_assistant·get_settings 를 바꿔 끼운다 (monkeypatch).
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from rra import composition
from rra.domain.models import OverlapAlert, ProposerInfo
from rra.domain.models.proposer import Person
from rra.entrypoints.ui.labels import BASIS, TIER, clean
from rra.entrypoints.ui.worker import Worker
from rra.entrypoints.views import draft_payload


class ConfigError(RuntimeError):
    """설정을 읽을 수 없다 (.env 권한 등). 화면은 이것을 st.error 로 보이고 멈춘다."""


def get_settings():
    """load_settings 는 거부 사유를 SystemExit 로 올린다(CLI 용).

    Streamlit 은 SystemExit 를 잡지 않아 스크립트 스레드가 조용히 죽고 화면이 빈 채로 남는다.
    그래서 여기서 보이는 예외로 바꾼다.
    """
    try:
        return composition.load_settings()
    except SystemExit as exc:
        raise ConfigError(str(exc)) from exc


def build_assistant():
    return composition.build_assistant(get_settings())


@st.cache_resource(show_spinner="앱을 준비하는 중…")
def get_worker() -> Worker:
    """프로세스에 하나. 세션·재실행을 넘어 살아 있다. 생성 동시성 1 은 RunManager 의 파일 락."""
    return Worker(build_assistant)


def alert_rows(alerts: list[OverlapAlert]) -> list[dict[str, Any]]:
    """유사과제 표 행. 제목은 비신뢰 텍스트 — 표 셀은 마크다운을 해석하지 않아 제어문자만 뗀다."""
    return [
        {
            "차단": "예" if a.blocking else "",
            "구분": TIER.get(a.tier, a.tier),
            "유사도": round(a.similarity, 2),
            "겹친 키워드": ", ".join(a.keywords) or "-",
            "근거": BASIS.get(a.basis or "", a.basis or "-"),
            "문서 id": a.doc_id,
            "제목": clean(a.title, 120),
        }
        for a in alerts
    ]


def download_payload(view, request) -> dict[str, Any]:
    """결과 JSON — draft_payload + 제안자 입력 + 확정값. request 에 성명·연락처는 없다."""
    payload = draft_payload(view)
    payload["request"] = request.model_dump(mode="json") if request is not None else None
    payload["confirmed"] = view.confirmation.model_dump(mode="json") if view.confirmation else None
    return payload


def proposer_info(
    proposed_on: str, proposer: tuple[str, str, str], head: tuple[str, str, str]
) -> ProposerInfo:
    """화면 입력 → ProposerInfo (직급, 성명, 연락처 순). 세션 밖으로 저장되지 않는다."""
    return ProposerInfo(
        proposed_on=(proposed_on or "").strip(),
        proposer=Person(rank=proposer[0] or "", name=proposer[1] or "", phone=proposer[2] or ""),
        head=Person(rank=head[0] or "", name=head[1] or "", phone=head[2] or ""),
    )


def download_bytes(view, request) -> bytes:
    return json.dumps(download_payload(view, request), ensure_ascii=False, indent=2).encode("utf-8")
