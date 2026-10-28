# 레인 D 진행 기록 — feat/evidence-scope (2026-10-29, 근거 범위)

## 경과
- 07:50 탐색. 운영 DB 사본(scratch, backup API) 조사: korail_web policy/admin_record 270 · policy/status 70 ·
  statistics/statistics 23(이미 statistics) · policy/policy 52 · procurement/research_service 287.
- 07:55 분류 규칙(`doc_category.classify_korail`) — 행정 공시 → `admin_notice`, 사업 현황 → `status_report`, 통계 → `statistics`.
  `RetrievalMix.only_in`(doc_type 별 쓸 수 있는 섹션)·`SectionMix.strict`(0건 되돌리기 없음) 추가, `retrieval_mix.yaml` 갱신.
- 07:57 이전 측정(4건) — 2-가-(3) 근거에 행정 공시·현황은 없었고, 대신 **유사과제 보탬 청크(연구용역)** 가 2/4 건에 섞여 있었다
  (#overlap 은 항상 남기는 규칙). strict 섹션은 보탬 청크도 허용 doc_type 일 때만 남기도록 고침.
- 08:05 사본 이주 적용(340행) · 다시 점검 0건(멱등). 전후 측정 6건 진행 중.
