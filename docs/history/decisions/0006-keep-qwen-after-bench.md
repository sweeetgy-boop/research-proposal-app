# ADR 0006 — 로컬 모델 비교 뒤 Qwen 유지 (2026-10-26, PR #1)

> 상태(2026-10-29 문서 최신화): 로컬 모델 선택(Qwen 유지)은 유효. 다만 2026-10-28 ADR 0032 부터 로컬 모델은 주 작성자가 아니다(대체·L2 검토).

**배경** 한국어 특화 모델(Mi:dm 2.0 Base, A.X 4.0 Light)이 더 나은지 확인.
**선택지** Qwen2.5-7B-Instruct-4bit 유지 / Mi:dm 2.0 Base 4bit / A.X 4.0 Light 4bit. EXAONE 4.5 는 비상업 라이선스·메모리, Solar Open 은 메모리로 후보 제외(대화 기록 기준, 미검증).
**결정** Qwen 유지. 결정 규칙: JSON (b) ≥ 95%, 근거 폐기 ≤ Qwen×2.
**이유** 2차 비교 JSON (b) Qwen 96.5% / A.X 79.3%(선택형 sentences 가 문자열 배열) / Mi:dm 3.5%, 근거 폐기 Qwen 0 / A.X 7.
**결과** `llm.yaml model_profiles` 로 교체 준비는 남김. 근거 `docs/llm-bench-2026-10-26.md`.
