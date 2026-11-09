# 계약 — 유사과제 4축 분해·IDF·동의어 스위치 (ADR 0059, 2026-11-09, 레인 E)

모델: `src/rra/domain/models/facets.py`(`Facets`·`FacetOverlap`, `FACET_KEYS`). 스위치: `config/overlap.yaml` 세 절.

## 1. 기능 스위치 (`config/overlap.yaml`, 기본 모두 false)
```yaml
facets:        {enabled: false}   # 4축 분해 → 축별 질의 검색 → RRF 합침 + 판정 출력 facet_overlap
idf_weighting: {enabled: false}   # 핵심어 겹침 점수에 말뭉치 IDF 가중 (적재 때 계산·캐시)
synonyms:      {enabled: false}   # 동의어 확장 (사람 검토를 거친 항목만)
```
- 절 이름과 `enabled` 키는 계약. 절 **안의** 다른 값(가중치·상한·캐시 경로 등)은 레인 E 가 더한다.
- **false 일 때 결과는 지금과 같아야 한다** — 회귀 시험(`tests/application/test_overlap_switch_off.py`): 골든셋 10건 + 시범 사례로
  ② 표(순서·blocking·keywords)·판정 입력이 스위치 전후 동일.
- 운영에서 켜는 조건(ADR 0058·0059): L1 비교에서 `recall_at5` 가 떨어지지 않고 `false_block` 이 늘지 않음 + 동의어는 사용자가
  `docs/review/terms-review.md` 를 확인한 뒤. 조건 전에는 off 로 배포만.
- 읽기: `config_loader.load_overlap_switches(settings) -> OverlapSwitches`(새, pydantic, frozen) — 세 불리언. 레인 E 가 만든다.

## 2. 4축 분해 형식
```json
{"facets": {"target": "철도역사 승강장 캐노피", "problem": "비둘기 침입·배설물 오염", "method": "비살상 퇴치 장치", "place": "수도권 지상역"},
 "facet_overlap": {"target": 2, "problem": 2, "method": 1, "place": 0}}
```
- `facets` 네 축 각 문자열(≤80자, 한 줄), 비어도 됨. `Facets.source` = local(로컬 모델) | rule(규칙 대체) | none.
- 분해는 **로컬 모델 우선**(clarify 단계 슬롯 안, Argon 금지 — 판정 전 단계라 외부 전송 늘리지 않음), 실패·비정상(JSON 아님·축 4개 아님·
  80자 초과) 이면 규칙(핵심어를 `domain/rules/facets.py` 의 사전으로 축에 배정, 못 배정하면 problem).
- 검색: 축별 질의(비어 있지 않은 축만, 2~4개) 각각 `hybrid_search` → RRF(k=60) 합침 → 기존 풀 규칙(`candidates.pool`)로 이어 준다.
  축별 검색은 e5 후보 풀에만 영향, reranker 입력 수는 종전과 같다.
- 판정: Argon·로컬 같음 판정 프롬프트 출력 항목에 `facet_overlap` {축: 0|1|2} 를 더한다(선택 — 없으면 빈 모델). 파싱은 `FacetOverlap.from_mapping`
  (비신뢰 — 범위 밖은 0). `OverlapAlert.facet_overlap: FacetOverlap | None`(새 칸, 기본 None) 에 담고 REST ② 행에 `facet_overlap` 으로 내보낸다.
- **차단은 지금 규칙 유지.** 4축 모두 높을 때만 차단으로 바꾸는 것은 평가(가·나·다) 결과 보고 결정 — 코드에는 `FacetOverlap.all_high()` 만 둔다.

## 3. IDF 가중
- 말뭉치 IDF 는 적재(`rra ingest`)·재색인(`rra reindex`) 끝에 계산해 `data/cache/idf.json`(토큰 → idf, 정수 소수 2자리) 에 캐시. 토큰은
  `domain/rules/keywords.tokenize` + `stem` 과 같은 것. 파일 없으면 가중 없음(=지금).
- 겹침 점수: 핵심어 `h` 의 가중 = `idf(h) / max_idf`(0~1). `keyword_overlap` 은 그대로 두고 새 함수 `weighted_overlap(...)` 를 `domain/rules/idf.py` 에.
  `core_min_hits` 판정은 스위치 on 일 때 "가중 합 ≥ core_min_hits × 평균 가중" 으로 — 값은 골든셋으로 확정하고 `overlap.yaml idf_weighting` 안에 적는다.

## 4. 동의어 확장
- 입력: `config/generic_terms.candidates.yaml`·`config/rail_terms.candidates.yaml`(`rra terms candidates` 결과, 미커밋 — 레인 E 가 읽고 커밋하지 않는다).
- 자동 선별(빈도·공출현) → `docs/review/terms-review.md` 검토표(항목·근거 수·추천 여부·체크 칸) + 고신뢰 항목만
  `config/overlap.yaml synonyms.candidates:` 구역(주석 "검토 전 — 운영 반영 안 함"). **사람 검토 전에는 `synonyms.enabled` 를 켜지 않는다.**
- 검색 질의에 동의어를 더할 때는 OR 확장(FTS5 토큰별 인용 유지, 보안 E). 차단 키워드 겹침에는 쓰지 않는다(1단계).

## 5. 평가 연결 (레인 D 와)
`EvalResult.config_flags` 에 `facets.enabled`·`idf_weighting.enabled`·`synonyms.enabled` 를 적는다. 2차 비교는 (가) main off,
(나) 레인 A 적용 off, (다) E 스위치 on — 같은 seed.
