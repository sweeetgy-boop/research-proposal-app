"""실제 Gemini 4 Argon 왕복 — RRA_GEMINI_API_KEY 가 환경에 있을 때만 (CI 에서는 skip).

json_mode=auto 가 어떻게 끝나는지(response_format 수용 여부)를 확인해 llm.yaml 의
providers.gemini.json_mode 기본값을 정한다. 키·응답 본문은 출력하지 않는다.
"""

import json
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("RRA_GEMINI_API_KEY", "").strip(), reason="RRA_GEMINI_API_KEY 없음"
)


async def test_gemini_argon_round_trip_json_mode():
    from rra.composition import build_llm
    from rra.settings import Settings

    llm = build_llm(Settings(_env_file=None), stage="review")
    try:
        raw = await llm.complete(
            '다음을 JSON 배열 하나로만 답하라: [{"text": "안녕", "evidence": []}]', json_mode=True
        )
    finally:
        await llm.aclose()
    data = json.loads(raw)
    assert isinstance(data, list) and data and data[0]["text"]
    assert llm._native_json_supported in (True, False)  # auto 의 결과: 기본값 결정에 쓴다
