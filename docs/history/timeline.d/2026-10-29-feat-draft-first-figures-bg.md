- 2026-10-29 레인 C (feat/draft-first-figures-bg, ADR 0045): 초안 글 먼저 — v1 저장 즉시 drafted, 그림은 백그라운드 작업
  (figures_job.json·.figures.lock, 읽을 때 합치기·끝나면 버전 파일에 채우기). 그리는 동안 편집 가능·그림 때문에 새 버전 없음,
  자리 카드 "그림 준비 중"·실패 사유 + [다시 그리기], 최종 검토·마무리는 "그림 준비 중 — 끝나면 진행할 수 있습니다", 재시작 →
  failed, `rra runs active` 가 그리는 run 도 셈. 진행 화면에 다 쓴 섹션 먼저 보기(GET /v1/runs/{id}/sections-progress).
  시간 draft_visible_seconds·figures_done_seconds(상태·usage·manifest timing). 실측 docs/eval-2026-10-29-draft-first.md.
