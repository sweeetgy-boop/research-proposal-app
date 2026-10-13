"""Streamlit 화면 — 기획서 Ⅱ 활용 시나리오. 유스케이스·composition 만 호출하고 로직은 두지 않는다.

실행: `rra ui` 또는 `python -m rra.entrypoints.ui` (127.0.0.1:8501, .streamlit/config.toml).
보안 G: 토큰 게이트(RRA_API_TOKEN) 필수, 생성 동시성 1 은 RunManager 의 파일 락 그대로.
"""
