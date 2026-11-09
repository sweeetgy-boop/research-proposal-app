# 진행 메모 — feat/wave-b-branch-switch-policy-quote (레인 B, 2026-11-09)

- 14:00 문서(계약 wave-1109·novel-recommend, ADR 0057·0052·0054)·코드 읽기 끝. 기준선: pytest 2665 passed/21 skipped, vitest 264.
- 14:20 분석: (a)(b) 전환은 [선택 적용]→`runCards`(새 `/recommendations`)라 409 를 거치지 않지만, 차단 행만 [관련 없음]으로 바꿔
  (유사함 집합은 그대로) 갈래가 바뀌는 경우 `planSignature` 가 같아 과제안을 다시 받지 않는 틈이 있음 → 서명에 갈래를 넣고
  서버 `/more`·`/apply` 는 `mode_changed` 409 로 보강하기로 함. 정책 인용문: 운영 DB 정책 자료 청크 22,643건 중 각주형 2,054·
  조사로 시작 539·문장 끝 없음 18,507 (건수만).
- 14:25 규칙 조정 반영 — app.py(공용)는 되돌리고 서버 판정은 새 모듈 `entrypoints/api/recommend_switch.py` 로; 핸들러 연결은 PR 설명.
  cli.py 도 공용(변경 없음). 웹 `planKey`·`modeMismatch`·`isModeChanged`, 정책 인용 `normalize_pdf`·`widen_to_sentences`·`Passage`.
- 14:30 e2e branch-switch 2건·novel·policy-popup 통과(가짜 모드). (a)(b) 는 409 를 거치지 않고 [선택 적용] 한 번으로 전환됨을 확인.
  되돌림(novelty_reverted) 세션은 전환으로 보지 않도록 웹·서버 모두 예외. pytest 2675/21 skip, vitest 270, ruff·lint-imports 통과.
- 14:35 ADR 0061·timeline.d·status.d 작성, e2e 전체 돌리는 중 → 커밋·푸시·PR.
