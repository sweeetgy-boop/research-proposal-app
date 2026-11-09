# feat/wave-e-overlap-facets (2026-11-09, 레인 E, ADR 0059·0064) 전달 사항 — 유사과제 고도화 1단계

## 전달한 것 (모두 스위치 뒤, 기본 끔 — false 면 ② 결과는 main 434581b 와 바이트 단위로 같다)
- **회귀 시험** `tests/application/test_overlap_switch_off.py` + 하네스 `overlap_switch_harness.py` + 스냅샷
  `tests/fixtures/overlap_switch_off_snapshot.json`(main 코드로 생성, 골든셋 12건 + 비둘기 합성 13 사례 — 저장소 호출·REST 행·관련 연구·판정 프롬프트).
- **스위치** `config_loader.load_overlap_switches` → `domain/rules/overlap_switches.OverlapSwitches`(frozen, facets·idf_weighting·synonyms).
- **4축 분해** `domain/rules/facets.py`(규칙 사전·로컬 출력 파서·`facet_queries`), `usecases/facet_split.py`(로컬 clarify 단계 → 규칙, Argon 금지),
  `PrecheckOverlap(switches, facet_split, idf, idf_rule)` — 축별 `find_similar` → RRF(k=60) → 기존 풀(크기·reranker 입력 수 같음).
- **facet_overlap** `same_judgment.parse_facet_overlaps`·`apply_verdicts(..., facet_overlaps)`, `SameJudge(facets=True)` 면 프롬프트에 요구,
  `OverlapAlert.facet_overlap: FacetOverlap | None`, `PrecheckResult.facets`, REST 행 `facet_overlap`(값 있을 때만 — `views.facet_overlap_view`). 차단 규칙 불변.
- **IDF** `domain/rules/idf.py`(`IdfWeights`·`compute_idf`·`weighted_overlap`·`enough_weighted`), `overlap.judge(idf=, idf_rule=)`, `usecases/build_idf.py`,
  포트 `ports/idf_cache.py`, 어댑터 `adapters/terms/idf_cache.py`, 데이터 위치 `idf_cache`(data/cache/idf.json), CLI `rra db idf`(`entrypoints/cli_overlap.register_db`).
  운영 DB 측정: 문서 16,431 / 청크 36,711 → 토큰 200,000, max_idf 9.71. `overlap.yaml idf_weighting` 값: cache·min_weight_ratio 1.0·min_doc_freq 1·max_terms 200000.
- **동의어** `domain/rules/synonyms.py`(씨앗 동의어·관련어 묶음·포함 관계, `expand_terms` OR), `usecases/terms_review.py`, 포트 `ports/terms_review.py`,
  어댑터 `adapters/terms/review.py`(후보 yaml 읽기·검토표·overlap.yaml 표식 구역만 교체), CLI `rra terms review [--candidates-dir]`.
  결과 `docs/review/terms-review.md`(후보 202행 → 묶음 15: 고신뢰 2 · 검토 필요 13), `overlap.yaml synonyms.candidates` 고신뢰 2. **`synonyms.enabled` 는 켜지 않았다.**
- **조립** `composition.apply_overlap_switches`·`build_facet_splitter`·`build_idf`·`build_idf_weights`·`build_terms_review`(새 함수만; `build_api`·`build_precheck`·
  `cli.py`·`app.py`·`ports/__init__.py` 미수정 — 붙일 줄은 PR 본문).
- **측정** `tools/eval_overlap_facets.py`, `docs/eval-2026-11-09-overlap-facets.md`(off / facets on / idf on, e5+reranker, LLM 없음).

## 시험
- pytest +42(회귀 17 · 스위치 on 5 · 규칙 11 · 어댑터 4 · 설정 3 + 기존 수정 2), lint-imports 8 kept, ruff 통과.

## 남은 것 (메인·사용자)
- `build_api` 에 `precheck = apply_overlap_switches(precheck, settings, local_slot=slot)` 한 줄(공용 계정 `build_scoped_services` 도), `cli.py` 에 `register_db(db_sub)`·`register_terms(terms_sub)`.
- 적재·재색인 끝 IDF 훅 제안: `cmd_ingest`·`cmd_reindex` 끝에 `build_idf(settings, repo=repo)[0]()` 한 줄(또는 launchd ingest 뒤 `rra db idf`).
- 사용자: `docs/review/terms-review.md` 체크 → 그 뒤에만 `synonyms.enabled`. 스위치 켜기는 L1 비교(연습용 묶음) 뒤 메인 결정.
