- 2026-11-09 — [레인 B] ② 과제안 갈래 전환(novel ↔ 차별화)은 [선택 적용] 한 번으로: 웹 서명에 갈래를 넣고(`planKey`) 더/적용 전
  갈래 비교(`modeMismatch`), 서버 안전망 `entrypoints/api/recommend_switch.py`(409 `code=mode_changed`, app.py 연결은 통합 때).
  정책 근거 인용은 각주·줄 끝 하이픈 제거 + 본문에서 문장 경계까지 넓힘 + 불완전하면 후순위(`policy_phrases.pick_passage`,
  `PolicySuggestion.complete`). ADR 0061. e2e 51→53(새 spec `branch-switch` 2건), vitest 264→270, pytest 2665→2675(+skip 21). PR #(미정).
