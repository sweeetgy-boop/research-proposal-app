# 반영 대기 PR (main 에 합쳤지만 운영 API 에 아직 반영하지 않음)

한 줄 형식: `- #번호 제목 — 종류(기능|오류|문서) — 합친 날짜`. 배포하면 `tools/deploy.sh` 가 이 목록을 그날 기록으로 옮긴다.
보안 수정·로그인/접속 차단 오류 수정은 여기 쌓지 않고 바로 배포한다.
- #133 0단계 계약(ADR 0058·0059 초안, 스위치 3절 false, HealthOut 새 칸) — 문서·모델 — 2026-11-09
- #136 ② novel↔차별화 전환(planKey)·mode_changed 안전망·정책 인용문 문장 경계(ADR 0061) — 기능·오류 — 2026-11-09
- #137 /healthz tunnel·llm.local, rra ops check 5분 점검, llm-check --timeout·첫 요청 타임아웃(ADR 0062) — 운영·오류 — 2026-11-09
- #139 평가 체계 L0·L1·L2, rra eval run|compare|usage|seal, CI eval-l0(ADR 0058·0063) — 기능 — 2026-11-09
- #140 OpenAlex 익명 429 건너뜀·h11 재시도, novel 과제안 동시 실행·SSE /recommendations/stream·단계별 측정(ADR 0060) — 오류·기능 — 2026-11-09
- #138 유사과제 4축·IDF·동의어 — 스위치 모두 off(ADR 0059·0064), rra db idf·terms review — 기능(동작 변화 없음) — 2026-11-09
- #141 평가 짝 비교(McNemar)·--mix/--ids·--discordant-out — 기능 — 2026-11-09
