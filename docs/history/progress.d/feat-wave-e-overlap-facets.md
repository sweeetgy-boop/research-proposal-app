# feat/wave-e-overlap-facets 진행 메모 (레인 E — 유사과제 고도화 1단계)

- 2026-11-09 시작. main 434581b 기준 worktree. 계약 `docs/contracts/overlap-facets.md`·ADR 0059 읽음.
- 순서: ① 회귀 하네스(가짜 저장소·결정적 reranker·FakeLLM, 골든셋 12건 + 비둘기 합성)로 **main 코드 스냅샷**을 먼저 뽑아 고정 →
  ② 스위치 로더·4축 규칙·IDF·동의어 → ③ precheck 검색(RRF)·판정 facet_overlap → ④ `rra db idf`·`rra terms review` → ⑤ 측정.
- 14:00 회귀 하네스(`tests/application/overlap_switch_harness.py`)·스냅샷 13 사례 고정(main 코드) → 스위치 로더·`domain/rules/{overlap_switches,facets,idf,synonyms}.py`
  → precheck RRF 검색·judge idf·SameJudge facet_overlap → 유스케이스 `facet_split`·`build_idf`·`terms_review` → 어댑터 `adapters/terms/{idf_cache,review}.py`
  → `cli_overlap.py`(cli.py 미수정, 메인 지시) → views `facet_overlap`. 스위치 off 결과 = 스냅샷 바이트 동일 확인.
- 14:37 `rra db idf`(heavy lock): 문서 16,431 / 청크 36,711 → 토큰 200,000, max_idf 9.71 → data/cache/idf.json(4.2MB).
- 14:45 `rra terms review`: 후보 202행 → 묶음 15(고신뢰 2 · 검토 필요 13). 서술형 토큰·관련어 묶음 분리(ADR 0064 §4).
- 14:50 골든셋 측정(off/facets/idf, e5+reranker, LLM 없음) heavy lock 안에서 실행 중.
- 15:10 측정 끝: off 11/12 · facets 10/12(10 분산에너지 풀 이탈, +0.43s) · idf 12/12(규칙 차단 행 60→35), 거짓 차단 0. docs/eval-2026-11-09-overlap-facets.md. 전체 pytest 2703 통과·lint-imports 8·ruff 통과 → 커밋·푸시·PR.
