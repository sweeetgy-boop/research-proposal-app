# LLM 실응답 fixture

`rra generate` 가 실제 모델에서 받은 응답 원문. 파서(domain/rules/llm_output.py)가 어떤 형태를 받아들이고
어떤 형태를 거부하는지 고정하는 데 쓴다. 비신뢰 텍스트이므로 내용은 그대로 두고 파싱 결과만 검증한다.

- `qwen7b_tech_importance_tag_fragment_{1,2}.txt` — Qwen2.5-7B-Instruct-4bit, 2026-10-13,
  run 20261013051151-c502d474 의 tech_importance 재현 응답. `text` 안에 자료 구획 태그 조각
  (`(basis="summary" id="…")`, `\<doc id="…" basis="summary">`)을 그대로 베껴 넣어 따옴표가
  이스케이프되지 않은 채 JSON 이 깨진 사례.

- `gemini_errors/*.json` — Gemini OpenAI 호환 엔드포인트 오류 응답 모양(2026-11-04, ADR 0055). 400 키 무효는
  2026-11-03 사고 때 받은 본문 모양(message·status·reason)을 옮기고 키·요청 정보는 넣지 않았다. 401·403·
  429(할당량 소진 RESOURCE_EXHAUSTED / 일반 호출 한도)·503 은 같은 형식의 녹화형 표본. 실제 키 없음,
  네트워크 없음 — `tests/adapters/test_llm_error_classes.py` 가 분류·로그·상태 기록을 검사한다.
