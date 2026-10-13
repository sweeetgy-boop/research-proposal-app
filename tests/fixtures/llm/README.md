# LLM 실응답 fixture

`rra generate` 가 실제 모델에서 받은 응답 원문. 파서(domain/rules/llm_output.py)가 어떤 형태를 받아들이고
어떤 형태를 거부하는지 고정하는 데 쓴다. 비신뢰 텍스트이므로 내용은 그대로 두고 파싱 결과만 검증한다.

- `qwen7b_tech_importance_tag_fragment_{1,2}.txt` — Qwen2.5-7B-Instruct-4bit, 2026-10-13,
  run 20261013051151-c502d474 의 tech_importance 재현 응답. `text` 안에 자료 구획 태그 조각
  (`(basis="summary" id="…")`, `\<doc id="…" basis="summary">`)을 그대로 베껴 넣어 따옴표가
  이스케이프되지 않은 채 JSON 이 깨진 사례.
