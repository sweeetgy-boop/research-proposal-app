# [B] feat/figure-phrases 진행 메모 (2026-10-29, 시범 의견 3차 — 그림 칸 글자)

- 시작. COMMON·B 지시서, figures 유스케이스·규칙·figure_fit·render·figures.yaml·eval 문서(figures-wide·pilot2) 읽음.
  잘라 줄이는 경로 3곳 확인: `figure_fit.shorten_spec`(밑그림 맞춤·OCR 다시 그림), `figures.normalize_spec_data`(clip_text, 명세 받을 때),
  `techniques._box`(clip_text).
- 완료: `domain/rules/figure_phrases.py`(칸별 상한·완결 검사·낱말 묶음 대체), 유스케이스(명세·기법·말로 고치기 프롬프트 상한, 교정 재요청 → 대체,
  `rewrite_texts` 다시 쓰기, `max_image_redraws` 1), 잘라 줄이는 코드 삭제, 가짜 모드 답 상한 맞춤, 테스트(도메인 34·유스케이스 6+5·어댑터 10).
- (자리 이동으로 잠시 멈춤 → 재개) pytest 2326 passed·21 skipped, e2e 27 passed, vitest 151.
- 실측: 시범 run 5건 사본 그림 13장 — 9pt 13/13, 미완 0, 다시 그림 1. 로컬 모델은 쓰지 않음(가짜 자리), runs active 0건 확인.
  균열 As-Is/To-Be 1장이 명사형 바꿔 쓰기('남음·못함·미추적')로 출처 검사에 걸려 빠짐 → 명사형 인정·출처 밖 칸 대체·프롬프트 보강 뒤 다시 돌려 통과.
- 문서: ADR 0044, docs/eval-2026-10-29-figure-phrases.md, 화면 9장(screens/2026-10-29-figure-phrases-*), status·timeline·metrics 조각. PR 올림.
