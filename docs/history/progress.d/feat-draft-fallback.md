# [F1] feat/draft-fallback 진행 메모 (2026-10-28)

- 01:50 시작. CLAUDE.md·CONTRIBUTING·architecture §4.6·§4.15·eval-2026-10-27 §8.1 읽음. invalid run 15건 + 시범 흐름 01 의 manifest/steps·sections·context 복원 → 원인 표(status.d §1).
- 02:00 PR 1(#55) 빈 초안 금지 — domain/rules/draft_failures, RunState.failed_sections, REST/render·submit-check/웹 버튼/Streamlit. 검사 통과, 02:10 푸시.
- 02:11 재측정 #1(f1_fallback) 시작(heavy lock, mlx 8080 공유). 02:11 #55 CI 전부 pass → 병합, 원격 브랜치 삭제.
- 02:15 PR 2(#57) 코드: 빈 목록 재요청, 청크 500자·기본 집합 10청크, finish_reason=length 집계, compose.fallback: gemini(예산 카운터·검토와 같은 전송 범위·보여 준 청크 기준 근거 검증), manifest fallback_sections, 웹 "대체 작성" 배지, 화면 캡처 2장.
- 02:45 재측정 #1 끝: 유효 10/10, invalid 0, 실패 섹션 1(10 task_type dropped), 대체 작성 1(05 tech_importance), Gemini 11회, 34분.
- 02:50 남은 1건 원인(검증 뒤 전부 폐기는 재요청 조건 밖) → `_validate`/`_bad`/`dropped_hint` 확장, 재측정 #2(f1_fallback2) 시작.
- 03:03 main(#56) 병합 충돌 1건(tests/test_config_loader.py 양쪽 추가) 해결, CI pass → 03:06 #57 병합.
- 03:22 재측정 #2 끝: 유효 10/10, 실패 섹션 0, 대체 작성 5, Gemini 15회(레인 합계 26). 03:25 PR 3(문서) 올림.
