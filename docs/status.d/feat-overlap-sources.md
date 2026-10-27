## [F2] 유사과제 판정 후보 = 과제형 자료원만, 관련 연구 분리 (feat/overlap-sources, 2026-10-28)

- 기준: main 53e5a86(PR #49). 배경: ScienceON·NTIS 적재 뒤 골든셋 precheck 적중 9/10 → 6/10 (논문이 사내 기록을 밀어냄). ADR 0028.
- 규칙 `domain/rules/overlap_candidates.py`(`OverlapCandidateRule`, 순수) + 설정 `config/overlap.yaml candidates`(project: own·alio·ntis
  `rnd_project`·g2b / research: scienceon·openalex·kipris·ntis `report`, k 5 / pool: per_source 7, size 28). 로더 `config_loader.overlap_candidates`,
  조립 `build_precheck`. `RetrievalMix.candidates` 주입으로 생성 단계 판정(`mix.overlap_candidates`)도 같은 집합 — F1 레인 파일은 미수정.
- 포트 `find_similar(text, *, k, sources=None)`: SQLite 는 sqlite-vec KNN 사전 필터(`_vec.search_within`, `chunk_rowid IN (자료원 청크)`), 같은
  질의 임베딩 메모. fake·scoped 저장소 동일. `judge()` 는 차단 먼저 + 입력(reranker) 순서 유지.
- `PrecheckOverlap.run()` → `PrecheckResult(alerts, related_research)`; `__call__` 은 알림만(MCP·Streamlit·CLI·추천·차별화·비교표·측정 호환).
  REST `POST /v1/precheck` 응답에 `related_research[]`(doc_id·title·source·source_label·doc_type·year·similarity·url). 웹 ② 화면
  `features/idea/RelatedResearchList.tsx` — 판정 표 아래 "관련 연구 n건", 배지 "참고", 원문 링크(noopener).
- 측정 `docs/eval-2026-10-28-precheck.md`: 적중 5/10(오늘 코퍼스, 어제 판정) → **9/10**(채택), 지연 on 1.84~2.09s(중앙값 2.06s, reranker 단독
  1.65~2.0s), Gemini 0회, DB 읽기만. 남은 1건(03)은 어제와 같은 주차 안내 차단.
- 테스트: `tests/domain/test_overlap_candidates.py`(4), `test_precheck.py`(+3), `test_overlap.py`(+1 순서), `test_config_loader.py`(+2),
  `tests/contracts`(+1 sources 필터), `test_api.py`(related_research), web `screens.test.tsx`(+1, axe), e2e `related.spec.ts`(가짜 모드 시드
  `scienceon:fake-1` 논문 — 판정 표에 없고 관련 연구에만; 캡처 `docs/screens/25-related-research.png`).
- 검사: pytest 1784 통과·17 skip, lint-imports 8 kept, ruff·format 통과, web lint·vitest 60(15 파일)·build·Playwright(related·ntis·flow) 통과.
- 프론트엔드 영향: `POST /v1/precheck` 응답 키 `related_research` 추가(기존 키 변경 없음). `docs/openapi.json` 은 통합 담당이 `rra api schema` 로.
- 하지 않은 것: reranker `max_length` 축소로 2초 안 맞추기(생성 단계와 공유, 측정 3회 상한), 03 거짓 차단(임계치·키워드 규칙 몫),
  관련 연구를 선행연구 브리핑과 합치기, `rra precheck` CLI·MCP 결과에 관련 연구 싣기(데이터만).
