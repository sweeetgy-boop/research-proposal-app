# ADR 0064 — 유사과제 고도화 1단계 구현 결정: 축별 검색은 문서 검색(find_similar)으로, IDF 는 `rra db idf` 캐시로, 동의어는 씨앗 사전 + 관련어 묶음으로 (2026-11-09, 레인 E, feat/wave-e-overlap-facets)

ADR 0059(0단계 초안)의 계약(`docs/contracts/overlap-facets.md`)을 구현하면서 계약이 열어 둔 것·계약과 다르게 읽어야 했던 것을 적는다.
스위치 세 개는 모두 기본 false 이고, false 일 때 ② 결과는 main 434581b 와 바이트 단위로 같다(`tests/application/test_overlap_switch_off.py`).

## 1. 축별 검색은 `hybrid_search`(청크) 가 아니라 `find_similar`(문서) 를 축마다 부른다
- 배경: 계약 §2 는 "축별 질의 각각 `hybrid_search` → RRF" 라고 썼다. 그러나 ② 후보 풀(`candidates.pool`)·reranker 입력·연작 묶기는
  모두 **(문서, e5 유사도)** 단위이고, `hybrid_search` 는 청크를 돌려주므로 청크마다 `get_document` 를 다시 불러야 한다(풀 28건 × 축 4개).
- 결정: 축 질의마다 종전과 같은 `find_similar`(같은 자료원 필터·같은 k) 를 부르고 RRF(k=60, `domain/rules/fusion.reciprocal_rank_fusion`
  재사용)로 합친 목록을 종전 한 질의 검색 자리에 넣는다(`PrecheckOverlap._fused_find`). 전체 검색·자료원별 검색 모두 같은 방식이라
  풀 크기·reranker 입력 수는 종전과 같다. 표시 유사도는 그 문서가 어느 축에서든 받은 최고 e5 값(차단은 reranker·핵심어가 정한다).
- 2개 미만 축이면 축별 검색을 하지 않는다(한 질의와 다를 게 없다). 분해 실패는 로그만 남기고 종전 한 질의로.

## 2. 4축 분해의 규칙 사전은 "문제 → 장소 → 방법 → 대상 → (그 밖) 문제" 순
- 복합어("궤도틀림"·"도상균열"·"급전장애")는 문제 어근이 들어 있으면 problem 이 먼저다 — 아이디어의 "문제" 축이 비는 일이 가장 잦기 때문.
- 장소는 노선 이름·"…역"(영역·구역·역할·역사·역무 제외)·"…구간/지역/권역". 사전에 없는 말은 problem 으로 둔다(대상으로 잘못 넣는 것보다
  검색에 해가 적다 — 어차피 축별 검색은 후보 풀에만 영향).
- 로컬 모델 출력은 `{"facets": {...}}` 또는 네 키가 바로 있는 객체만, 축 4개 모두 문자열·80자 이하일 때만 받는다(계약 그대로).

## 3. IDF 표는 `rra db idf` 가 만든다 — 적재·재색인 훅은 메인 제안
- 적재(`usecases/ingest_sources.py`)·재색인(`usecases/maintain_db.py`)은 레인 소유 밖이라 손대지 않았다. 새 유스케이스 `usecases/build_idf.py`
  (`CorpusAccessPort.sample_chunks` 로 전체 청크를 훑어 문서별 토큰 집합 → `ln(N/df)` 소수 2자리) + 캐시 포트 `ports/idf_cache.py`
  (`adapters/terms/idf_cache.py`, `data/cache/idf.json`, `config_loader._DATA_LOCATIONS["idf_cache"]`).
- 표에 없는 토큰은 가장 드문 것(가중 1.0)으로 본다 — 모르는 낱말을 흔하다고 보지 않는다. 표 상한 200,000 은 흔한 것부터 남기므로 드문 토큰이
  잘려도 결과가 같다.
- 핵심어 조건은 스위치가 켜졌을 때만 `enough_weighted`(가중 합 ≥ core_min_hits × 평균 가중 × `min_weight_ratio`). 2026-11-09 운영 DB
  (16,431 문서·36,711 청크, max_idf 9.71) 측정은 `docs/eval-2026-11-09-overlap-facets.md`. `min_weight_ratio` 1.0 유지.

## 4. 동의어 후보는 씨앗 사전 + 관련어 묶음 + 포함 관계, 고신뢰는 씨앗 동의어만
- 입력(`*.candidates.yaml`)은 용어별 문서빈도·자료원·예시 문서 3건뿐이라 진짜 공출현을 셀 수 없다. 그래서 (a) 철도 용어 동의어 씨앗
  (`SEED_GROUPS`: 유지보수/유지관리, 전차선/가선, 고속철도/고속열차/KTX …)에서 후보에 둘 이상 나타난 묶음만 **high**, (b) 관련어 묶음
  (`LOOSE_GROUPS`: 선로/궤도/레일, 도상/자갈도상, 철도차량/열차, 검측/검사, 수송수요/수송실적)과 (c) 포함 관계(교량/철도교량)는 **review** 까지만.
  예시 문서 겹침 수는 "공출현 근거" 칸으로 보인다.
- 서술형 토큰(…하였다·…하여)·기록 서식어(과제명·총연구비)·일반어는 구성원에서 뺀다.
- 결과: 후보 202행 → 묶음 15(고신뢰 2 · 검토 필요 13). 고신뢰만 `overlap.yaml synonyms.candidates` 구역(표식 두 줄 사이만 바꾼다 —
  주석·다른 절은 그대로)에 적고, **`synonyms.enabled` 는 켜지 않는다.** 질의 확장 함수(`expand_terms`, OR)는 두되 1단계에서는 어디에도 연결하지 않았다.

## 5. 공용 파일은 손대지 않고 조립 helper 로 — 통합 때 메인이 두 줄
- `apply_overlap_switches(precheck, settings, local_slot=…)`(composition, 새 함수)가 스위치를 읽어 이미 만든 `PrecheckOverlap` 에
  분해기·IDF 표·`SameJudge.facets` 를 붙인다. `build_api`·`build_precheck` 본문·`cli.py`·`app.py`·`ports/__init__.py` 는 그대로 — 붙일
  줄은 PR 본문 "통합 때 메인이 반영할 조립 변경" 에.
- REST ② 행 `facet_overlap` 은 `views.alerts_payload` 가 값이 있을 때만 칸을 낸다(없으면 종전 응답과 같다).

## 결과·남은 것
- 차단 규칙은 바뀌지 않았다. `FacetOverlap.all_high()` 는 표시용으로만 있다(ADR 0059).
- 남은 것: 운영 스위치 켜기 결정(L1 비교, 메인), 동의어 검토표 사용자 확인, 적재·재색인 끝 IDF 훅(메인), 4축 분해에 실제 로컬 모델을
  붙인 측정(이번 측정은 규칙 분해만).
