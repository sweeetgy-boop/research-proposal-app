# ADR 0007 — 로컬 작성 + Gemini Argon 검토 2중화 (2026-10-26)

**배경** 로컬 7B 만으로는 근거 불일치·논리·서식 문제를 스스로 잡지 못한다. 외부 모델에 사내 자료를 그대로 보낼 수는 없다.
**선택지** (a) 외부 모델로 작성, (b) 로컬 작성만, (c) 로컬 작성 + 외부 검토(수정안·점수), 전송 범위 제한.
**결정** (c). 단계별 provider(`llm.yaml stages`: compose=mlx, review·differentiate=gemini), `include_internal` 규칙과 manifest 에 외부 전송 doc_id·문장 수 기록, 키가 없으면 검토 건너뜀(review_skipped).
**이유** 작성은 사내 장비에서, 검토는 강한 모델에서. 전송 범위가 매니페스트에 남아 감사 가능.
**결과** P5 채점(4개 기준), 2026-10-27 흐름에서 1차(자동)·최종(요청 시 1회)로 정리(ADR 0011). 근거 `9cb311f`, `b979fd0`, architecture §4.6·§4.11.
