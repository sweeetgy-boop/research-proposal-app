# feat/usability 진행 메모 (레인 C)

- 2026-10-27 시작. main 1102b72 기준 worktree. 기준선: `pytest -q` 전부 통과(마지막 줄 참조), lint-imports 8 kept.
- 계획: config/usability.yaml(UsabilityConfig) → U8 저장소 포트(usage) → U1 근거 보기·적합성·판단 →
  U6 일정·성과지표 → U7 제출 전 점검 → U3 섹션 다시 쓰기·보완 질문 → U2 간편 입력 → U4 비교표 → U5 브리핑 → CLI·문서.
- 골격 커밋 9bc40ab(구현)·이어 테스트 커밋. 전체 `pytest -q` 1,292 통과·18 skip, lint-imports 8 kept, ruff 통과.
  설계 선택: 근거 제외(exclude)는 문장의 근거 id 를 지우지 않고 판단만 남김(근거 필수 섹션의 error 가 아니라 warning 유지);
  replace 는 검색 집합 id 로만. 다시 쓰기 후보는 rewrites/rewrite_<key>.json 에 두고 apply 때 버전 생성.
  제안자 보완 답·우선 근거 id 는 proposer_notes.json(제안자 입력 보관). U5 brief 는 llm.yaml stages.brief(gemini) 추가.
- 남은 일: Streamlit 패널(웹 레인과 겹쳐 생략), MCP 도구(선택, 생략), 문서 조각(status.d·timeline.d·ADR 0017).
- 문서 조각 작성: status.d·timeline.d·metrics.d·ADR 0017. 마무리 검사 재실행 뒤 커밋.
