# precheck 적중 재측정 — 유사과제 판정 후보를 과제형 자료원으로 제한 (2026-10-28, 레인 F2, ADR 0028)

> 보관(2026-10-29): 유사과제 판정 후보 제한 [F2] 측정. 판정 규칙은 이후 reranker + 핵심 키워드 + Argon 같음 판정(ADR 0036)·표 먼저(0039)·연작(0043)으로 바뀜. 최근은 `docs/eval-2026-10-29-precheck-series.md`.

## 1. 배경과 측정 방법
- 어제 저녁 ScienceON 2,045건·NTIS 연구보고서 1,084건·NTIS 과제 2,000건 적재 뒤 골든셋 precheck 적중 9/10 → 6/10(`docs/eval-2026-10-27.md` §8.1).
- 측정 방법은 어제 10:40 의 `data/eval/precheck_hits_k4.json` 과 같다: 골든셋 10건(`tests/golden/*.yaml`)의 입력으로 `build_precheck` 유스케이스를
  직접 호출해 알림 상위 5 안에 `expected_similar` 가 하나라도 있으면 적중(정답이 비면 차단 알림 0 이 적중 — `usecases/evaluate.py` 와 같은 기준),
  지연은 유스케이스 호출 벽시계(검색 + reranker, 2회 중 최소). 어제의 측정 스크립트는 저장소에 없어 같은 형식으로 다시 썼다
  (`rows[].{before,off,on}.{top,blocking,alerts,hit,seconds,rank}`; 원본 JSON 은 작업 세션 임시 폴더, 표는 아래).
- 코퍼스: 원 저장소 `data/rra.sqlite`(읽기만, 11,003 문서·32,933 청크; own 1,119 · alio 120 · ntis 과제 2,000/보고서 1,084 · scienceon 2,045 ·
  openalex 2,482 · korail_web 5,098 …). reranker `~/models/bge-reranker-v2-m3`(MPS). **Gemini·LLM 호출 0회.** DB 수정 없음.
- REST `POST /v1/precheck` 는 자동 추천(Gemini)이 붙어 약 38초이므로 지연은 유스케이스 경로로 쟀다(화면의 체감 지연은 추천을 뺀 값이 아니다).
- 모드: **before** = 후보 제한 없음(어제 코드와 같은 판정, reranker k×3=30), **off** = 과제형 자료원만 + reranker 없음, **on** = 과제형 자료원만 +
  자료원별 풀 + reranker(기본 설정).

## 2. 결과 요약

| 구성 | 적중 | 지연(on, 초) | 비고 |
|---|---|---|---|
| 어제 10:40 (코퍼스 ≈5,800, reranker k×3) | 9/10 | 1.5~1.95 | `docs/eval-2026-10-27.md` §5 |
| 어제 18:44 `rra eval` (코퍼스 11,008) | 6/10 | — | §8.1 |
| **before** 오늘 코퍼스, 후보 제한 없음 (1차) | 5/10 | 1.65~2.0 (첫 호출 14s 는 모델 적재) | 01·08·10 상위가 논문·NTIS |
| 1차: 자료원 제한만 (off / on) | 7/10 / 7/10 | 2.03~2.11 | 01·10 은 NTIS 과제 2,000건이 사내 기록을 상위 80 밖으로 밀어냄 |
| **2차: + 자료원별 풀 7/28 + reranker 순서 유지 (off / on)** | 7/10 / **9/10** | **1.84~2.09 (중앙값 2.06)** | **채택** — 03 만 남음 |
| 3차: 풀 6/24 (off / on) | 7/10 / 8/10 | 1.86~2.12 | 10번 놓침, 지연 차이 없음 → 폐기 |

## 3. 골든셋 10건 — 전후 비교 (before = 1차 기준, after = 2차 on 채택 구성)

| 골든셋 | 정답 수 | before 적중(정답 순위) | before 지연 | after off | after on 적중(순위) | after on 지연 | after 상위 3 자료원 | 관련 연구 |
|---|---|---|---|---|---|---|---|---|
| 01_track_irregularity | 6 | 놓침 | 14.15s | 놓침 | 적중(3위) | 2.06s | ntis·ntis·own | 5건 |
| 02_asset_development | 1 | 적중(1위) | 1.83s | 적중(1위) | 적중(1위) | 1.94s | alio·own·ntis | 5건 |
| 03_unrelated_library | 0 | 놓침 | 1.05s | 놓침 | 놓침 | 1.84s | alio·ntis·own | 5건 |
| 04_catenary_arc | 1 | 적중(1위) | 1.93s | 적중(1위) | 적중(1위) | 2.06s | alio·own·ntis | 5건 |
| 05_axle_bearing | 4 | 적중(1위) | 1.77s | 적중(1위) | 적중(2위) | 2.07s | alio·own·own | 5건 |
| 06_slab_track_crack | 2 | 놓침(7위) | 1.95s | 적중(5위) | 적중(1위) | 2.09s | alio·own·alio | 5건 |
| 07_train_protection_lte | 2 | 적중(1위) | 1.95s | 적중(1위) | 적중(1위) | 2.07s | alio·alio·own | 5건 |
| 08_demand_forecast | 8 | 놓침 | 1.7s | 적중(4위) | 적중(3위) | 1.94s | alio·alio·alio | 5건 |
| 09_station_parking | 2 | 적중(1위) | 1.68s | 적중(1위) | 적중(3위) | 2.06s | own·alio·alio | 5건 |
| 10_distributed_energy | 4 | 놓침 | 1.65s | 놓침 | 적중(1위) | 2.08s | alio·ntis·ntis | 5건 |

- 01 궤도 틀림: before 상위 5 가 전부 ScienceON 논문(0.886~0.903). 자료원 제한만으로는 NTIS 과제(0.877~0.888)가 상위를 메워 여전히 놓침 →
  자료원별 풀(own·alio 각 7건 보장)로 정답 own 기록이 풀에 들어가고 reranker 가 3위로 올림.
- 10 분산 에너지: 정답 alio 요약(0.854)이 NTIS 과제(0.866~0.877) 아래 27위 → 풀 보장 + reranker 1위. 풀 6/24 에서는 다시 놓침(reranker 입력에서
  빠짐) → 7/28 유지.
- 06·08: 자료원 제한만으로 적중(before 는 논문·NTIS 보고서가 밀어냄). 03 도서관(정답 없음): 세 모드 모두 "역 주차 안내" alio 요약(0.854)이
  차단 — 어제와 같은 임계치·키워드 특성, 이 변경의 대상이 아님.
- before 1차의 01 지연 14.15s 는 첫 호출의 모델 적재(임베딩·reranker)이고 2차 이후 2.0s.

## 4. 지연 분석
- reranker 단독(before, 30건) 1.65~2.0s — 어제 기록(1.5~1.95s)보다 약간 높다(같은 시각 다른 레인이 LLM·웹 검사를 돌림).
- 채택 구성 on 1.84~2.09s(중앙값 2.06s): 질의 임베딩 1회(저장소 메모) + 전체 1 + 자료원별 4 + 관련 연구 1 검색(sqlite-vec KNN 사전 필터
  각 0.05~0.09s) + reranker 28건. 관련 연구 검색은 reranker 와 겹쳐 돈다. **상한 2초를 0.06s 안팎 넘는다** — reranker 자체가 상한에 붙어 있어
  풀을 줄여도(24건) 지연이 줄지 않았고 적중만 잃었다. 더 줄이려면 reranker `max_length`(512) 축소나 문서 텍스트 절단을 측정해야 하는데
  생성 단계 reranker 와 공유하는 설정이라 오늘(측정 3회 상한) 안 했다.
- off(reranker 없음) 0.11~0.17s, 7/10.

## 5. 채택 설정 (`config/overlap.yaml candidates`)
```yaml
candidates:
  project: [{source: own}, {source: alio}, {source: ntis, doc_types: [rnd_project]}, {source: g2b}]
  pool: {per_source: 7, size: 28}
  research: {k: 5, members: [{source: scienceon}, {source: openalex}, {source: kipris_kr}, {source: kipris_intl}, {source: ntis, doc_types: [report]}]}
```
판정 순서 규칙: `judge()` 는 차단 먼저, 그 안에서는 입력(reranker) 순서 유지 — 유사도 재정렬을 버렸다(2차에서 10번이 1위가 된 이유).
