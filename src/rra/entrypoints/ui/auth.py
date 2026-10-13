"""보안 G: 화면은 토큰 없이 열리지 않는다.

RRA_API_TOKEN(settings.api_token) 하나를 세션당 한 번 입력한다.
"""

from __future__ import annotations

import secrets

import streamlit as st

INPUT_WIDGET = "token_input"  # 위젯 key (비밀 아님)
AUTHED_KEY = "authed"


def require_token(settings) -> None:
    token = settings.api_token.get_secret_value() if settings.api_token else ""
    if not token:
        st.error(
            "RRA_API_TOKEN 이 설정되지 않아 화면을 열 수 없습니다 (보안 G: 웹 인증 필수). "
            ".env 에 RRA_API_TOKEN=... 을 넣고 다시 실행하십시오."
        )
        st.stop()
    if st.session_state.get(AUTHED_KEY):
        return
    entered = st.sidebar.text_input("접속 토큰", type="password", key=INPUT_WIDGET)
    if entered and secrets.compare_digest(entered, token):
        st.session_state[AUTHED_KEY] = True
        return
    if entered:
        st.sidebar.error("토큰이 일치하지 않습니다.")
    st.info("사이드바에 접속 토큰을 입력하십시오.")
    st.stop()
