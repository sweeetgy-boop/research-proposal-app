# feat/recommend-metrics (2026-11-04, ADR 0055 덧붙임) 전달 사항

## 전달한 것
- **측정 파일** `<data_dir>/cache/recommend_metrics.jsonl`(데이터 위치 `recommend_metrics`). 추천 호출 한 번 = 한 줄, 건너뜀(no_alerts_or_evidence·
  no_documents)·해석/호출 실패도 한 줄. 예외로 끝난 호출(일일 상한 BudgetExhausted·취소)은 결과가 없어 줄이 없다.
- **줄 모양** `{"ts": "2026-11-04T14:46:17+09:00", "provider": "gemini", "fallback_local": false, "calls": 2, "cards": 0, "discarded": 0,
  "retry_used": true, "regenerated": false, "skipped_reason": null, "references": 0, "similar": 0, "mode": "initial", "seconds": 41.24}`.
  문자열은 열거 칸 셋(provider·skipped_reason·mode)뿐, 짧은 영문 식별자가 아니면 null. 가제·본문·doc_id·사용자/소유자 id·아이디어 해시 없음.
  `seconds` 는 호출 전체(검색·다시 받기·카드 겹침 재판정 포함), `mode` 는 이미 보인 카드(`shown`)가 있으면 more.
- **구조** 규칙 `domain/rules/recommend_metrics`(`FIELDS`·`metrics_row`·`enum_value`), 포트 `application/ports/recommend_metrics.RecommendMetricsPort`
  (runtime_checkable), 어댑터 `adapters/logging/recommend_metrics.JsonlRecommendMetrics`, 유스케이스 `RecommendProjects.metrics`(None 이면 기록 없음 —
  `__call__` 이 시간을 재고 본문은 `_recommend`), 조립 `composition.build_recommend_metrics`(가짜 모드 None) → `build_recommender` 가 넘긴다.
  REST(일반·공용 계정)·CLI(`rra recommend`·`rra precheck` 자동)·MCP `rra_recommend`·Streamlit(build_assistant) 모두 `build_recommender` 를 거친다.
- **파일 규칙** 폴더 700·파일 600(O_APPEND·O_NOFOLLOW), 프로세스 안 잠금. 쓰기 전에 5 MB 이상이면 `.jsonl.1` 로 옮기고(옛 `.1` 덮어씀) 새 파일 —
  많아야 두 파일. 쓰기 실패(OSError)는 어댑터가, 그 밖 예외는 유스케이스가 삼키고 `recommend.metrics_failed kind=<예외 클래스>` debug 한 줄.
- **변하지 않은 것** `recommend.done` 로그 단계(로컬 대체·실패 WARNING, 그 밖 INFO)·응답 필드·화면.
- **문서** architecture §4.14 "측정 파일", ADR 0055 덧붙임 한 줄.

## 시험
- pytest 2526 → 2543(+17): 유스케이스 10(한 줄·정확한 칸, '새 영역' 다시 받기 retry_used·calls 2, [유사함] 수, more, 건너뜀, 실패 기록기 2종,
  None, 본문·id 없음·값 형식, 규칙 정리) + 조립 1(데이터 폴더 경로·가짜 모드 None) + 어댑터 6(줄 모양·ts, 600/700, 회전, 쓰기 실패, 심볼릭 링크, 허용 칸 밖 거절).
  `tests/test_data_dir.py` 통과(새 위치도 데이터 폴더 아래). 전체 실행 뒤 원 저장소 `data/cache` 에 측정 파일이 생기지 않음을 확인.

## 남은 것
- 집계 도구는 없다(필요하면 `jq`/pandas 로 읽는다). 회전 잠금은 프로세스 안에서만이다 — API·CLI 가 같은 순간에 5 MB 를 넘기면 회전이 두 번 일어나 옛 `.1` 의 줄을 잃을 수 있다(측정용이라 허용).
