# 비교 평가 — 유사과제 고도화 1단계 스위치 (2026-11-09, ADR 0058·0059, 연습용 묶음)

E 스위치(`facets`·`idf_weighting`)를 운영에서 켤지 정하기 위한 L1 짝 비교. **연습용 묶음** seed 1109048, 40문제 = 역방향 20·함정 12·
새 영역 8(`--mix 0.5,0.3,0.2`), 판정만(`--no-recommend`), Argon 판정 포함. 봉인 묶음(119건)은 만들어 두기만 했고 열지 않았다 —
보고서용 최종 확인 1회에 쓴다. 결과 JSON: `eval/results/2026-11-09-l1-*.json`(수치·문제 id 해시만).

| 열 | 구성 | 문제 | 반복 |
|---|---|---|---|
| 가 ga-main | main(E 병합, 스위치 모두 off = 종전 동작) | 40 | 1 |
| 다 da-e-on | `facets.enabled`·`idf_weighting.enabled` = true (`synonyms` off) | 40 | 1 |
| 재측정 *-disc | 가·다 결과가 갈린 7문제 | 7 | 3 (두 구성 모두) |
| 라 ra-idf-on | `idf_weighting` 만 true | 함정 12·새 영역 8 | 1 |

## 결론
- **(가)·(다) 는 차이 없음.** 1차에서 함정 5건이 "(가)만 맞힘" 으로 보였으나(false_block 0.50 vs 0.92) 갈린 7문제를 순차로 3회씩 재측정하니
  두 구성 모두 같은 결과(함정 5건 3/3 차단, 새 영역 1건 3/3 맞힘·1건 0/3) — 1차의 차이는 아래 "주의" 의 동시 실행 부하 때문이다.
  보정한 (가) false_block ≈ 0.917(11/12), recall@5 1.000(20/20), novel 0.875(7/8) = (다) 와 같다.
- **idf 만 켠 (라)** 는 보정한 (가) 대비 함정 1건만 다르다(라가 차단 안 함 — 덜 차단, 개선 방향), 새 영역 동일, 역방향은 idf 가 순위를 바꾸지 않아
  영향 없음(핵심어 조건만 가중). 레인 E 골든셋(`docs/eval-2026-11-09-overlap-facets.md`)의 "idf on 12/12·규칙 차단 행 60→35" 와 방향이 같다.
- **facets** 는 이 묶음에서 득실 없음, 골든셋에서는 1건 손실(분해가 한 축에 몰림) → 로컬 모델 분해 재측정 전에는 켤 근거 없음.
- **권고**: 운영은 세 스위치 모두 off 로 배포(합의한 기본). 켬 후보는 `idf_weighting` 하나 — 조건(recall@5 하락 없음·false_block 증가 없음)은
  충족, 사용자의 `docs/review/terms-review.md` 확인(동의어는 그 뒤에도 별도)과 함께 결정 요청. `facets` 는 보류, `synonyms` 는 검토 전 금지.
- 함정 문제의 차단율이 두 구성 모두 0.9 안팎으로 높은 것은 함정 생성 방식(A 의 대상·문제 문장을 그대로 씀 → A 와 '같다' 판정)의 성질이다.
  스위치 효과가 아니라 **문제 생성기의 보정 과제**(레인 D 후속: 대상 문장을 바꿔 쓰기)로 적는다.

## 주의 (측정 결함, 사람이 알아야 할 것)
- (가)는 고정 worktree 에서, (다)는 원 저장소에서 돌려 `tools/with_heavy_lock.py` 의 잠금 파일(cwd 상대)이 달라 **두 실행이 16분 겹쳤다**
  (15:38:56 / 15:39:10 시작). 1차 지연 수치(p50·p90)는 쓰지 않는다. 재측정·(라)는 순차. 잠금 경로는 #143 에서 원 저장소 기준으로 고쳤다.
- 평가용 Gemini 카운터(`data/cache/eval_llm_budget.json`)는 두 프로세스가 같은 파일을 동시에 써 과소 집계됐다(파일 102, 실제 ≈ 142/150).
  결과 JSON 의 `llm_calls` 도 (가)=0 으로 잘못 세었다(집계 버그, 레인 D 후속). 오늘 LLM 평가는 여기서 멈췄다.
- 새 영역 1문제(`0532…`)는 두 구성 모두 novel 이 아님(차단은 아님) — AI 기본 선택 [유사함] 이 생긴 것으로, 문제 재료(주제)의 문제인지 판정의
  문제인지 봉인 묶음 확인 때 함께 본다.

## 다음
1. 사용자: `docs/review/terms-review.md` 15묶음 확인 → `idf_weighting` 켬 여부 결정(권고 켬). 켜면 `config/overlap.yaml` 한 줄 + 배포.
2. 봉인 묶음 최종 확인 1회(`rra eval run --suite l1 --sealed --label 최종`) — 판단이 끝난 뒤, 예산이 새로 생기는 날.
3. 레인 D 후속: 함정 생성 보정, `llm_calls` 집계, 카운터 파일 잠금. 야간 L1(`com.rra.eval`)은 배포 뒤 등록.

---

## 표 1 — (가) vs (다), 40문제 1회 (1차, 동시 실행 부하 있음)
| 지표 | ga-main | da-e-on | 차이(da-e-on) | 판정(da-e-on) |
|---|---|---|---|---|
| 역방향 정답 상위 5 적중률 (recall_at5) | 1.000 | 1.000 | +0.000 | 구간 없음 |
| 함정 차단율 (false_block, 낮을수록 좋음) | 0.500 | 0.917 | +0.417 | 구간 없음 |
| 새 영역 novel 판정률 (novel_rate) | 0.875 | 0.875 | +0.000 | 구간 없음 |
| novel 장벽 '추정' 비율 (낮을수록 좋음) | — | — | — | — |
| ② 지연 중앙값 초 (latency_p50) | 24.200 | 22.540 | -1.660 | 구간 없음 |
| ② 지연 p90 초 (latency_p90) | 27.630 | 34.670 | +7.040 | 구간 없음 |
| 과제안 0건 비율 (rec_zero_rate, 낮을수록 좋음) | — | — | — | — |

## 실행 정보

| 열 | suite | seed | n | repeats | 봉인 | 커밋 | LLM 호출 | 캐시 적중 | 초 | 스위치 |
|---|---|---|---|---|---|---|---|---|---|---|
| ga-main | l1 | 1109048 | 40 | 1 | 아니오 | aeebccf | 0 | 0 | 988 | facets.enabled=False, idf_weighting.enabled=False, judgment.enabled=True, keywords=rule, llm=none, rerank.enabled=True, rerank.threshold=0.5, series.enabled=True, synonyms.enabled=False, with_recommend=False |
| da-e-on | l1 | 1109048 | 40 | 1 | 아니오 | a0531b4 | 40 | 0 | 1038.3 | facets.enabled=True, idf_weighting.enabled=True, judgment.enabled=True, keywords=rule, llm=gemini, rerank.enabled=True, rerank.threshold=0.5, series.enabled=True, synonyms.enabled=False, with_recommend=False |

## 짝 비교 (같은 문제, 문제별 맞힘 대조)

기준 열과 같은 문제 id 를 가진 열만. '기준만'·'비교만' 은 두 구성의 결과가 갈린 문제 수, McNemar p 는 그 둘의 정확 이항 검정(양측). p < 0.05 면 갈린 쪽이 많은 구성을 개선/악화로, 아니면 '차이 없음'. 갈린 문제만 3회 반복해 다시 재는 것이 다음 단계다.

### ga-main vs da-e-on

| 종류 | 공통 | 둘 다 맞힘 | 기준만 | 비교만 | 둘 다 틀림 | McNemar p | 판정 |
|---|---|---|---|---|---|---|---|
| 전체 | 40 | 27 | 6 | 1 | 6 | 0.1250 | 차이 없음 |
| 새 영역 | 8 | 6 | 1 | 1 | 0 | — |  |
| 역방향 | 20 | 20 | 0 | 0 | 0 | — |  |
| 함정 | 12 | 1 | 5 | 0 | 6 | — |  |

갈린 문제 7건 (id 는 `--discordant-out` 으로 저장)


## 메모

- ga-main: 새 영역 문제 차단 1/8건 (false_block 분모 밖)
- ga-main: 문제 종류: novel 8, reverse 20, trap 12
- da-e-on: 새 영역 문제 차단 0/8건 (false_block 분모 밖)
- da-e-on: 문제 종류: novel 8, reverse 20, trap 12

## 표 2 — 갈린 7문제 재측정, 두 구성 3회 (순차)
| 지표 | ga-main-disc | da-e-on-disc | 차이(da-e-on-disc) | 판정(da-e-on-disc) |
|---|---|---|---|---|
| 역방향 정답 상위 5 적중률 (recall_at5) | — | — | — | — |
| 함정 차단율 (false_block, 낮을수록 좋음) | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 | 차이 없음 |
| 새 영역 novel 판정률 (novel_rate) | 0.500 [0.000, 1.000] | 0.500 [0.000, 1.000] | +0.000 | 차이 없음 |
| novel 장벽 '추정' 비율 (낮을수록 좋음) | — | — | — | — |
| ② 지연 중앙값 초 (latency_p50) | 23.340 | 20.650 | -2.690 | 구간 없음 |
| ② 지연 p90 초 (latency_p90) | 32.300 | 34.770 | +2.470 | 구간 없음 |
| 과제안 0건 비율 (rec_zero_rate, 낮을수록 좋음) | — | — | — | — |

## 실행 정보

| 열 | suite | seed | n | repeats | 봉인 | 커밋 | LLM 호출 | 캐시 적중 | 초 | 스위치 |
|---|---|---|---|---|---|---|---|---|---|---|
| ga-main-disc | l1 | 1109048 | 7 | 3 | 아니오 | 561ad78 | 21 | 0 | 531.6 | facets.enabled=False, idf_weighting.enabled=False, judgment.enabled=True, keywords=rule, llm=gemini, rerank.enabled=True, rerank.threshold=0.5, series.enabled=True, synonyms.enabled=False, with_recommend=False |
| da-e-on-disc | l1 | 1109048 | 7 | 3 | 아니오 | 561ad78 | 21 | 0 | 551.5 | facets.enabled=True, idf_weighting.enabled=True, judgment.enabled=True, keywords=rule, llm=gemini, rerank.enabled=True, rerank.threshold=0.5, series.enabled=True, synonyms.enabled=False, with_recommend=False |

## 짝 비교 (같은 문제, 문제별 맞힘 대조)

기준 열과 같은 문제 id 를 가진 열만. '기준만'·'비교만' 은 두 구성의 결과가 갈린 문제 수, McNemar p 는 그 둘의 정확 이항 검정(양측). p < 0.05 면 갈린 쪽이 많은 구성을 개선/악화로, 아니면 '차이 없음'. 갈린 문제만 3회 반복해 다시 재는 것이 다음 단계다.

### ga-main-disc vs da-e-on-disc

| 종류 | 공통 | 둘 다 맞힘 | 기준만 | 비교만 | 둘 다 틀림 | McNemar p | 판정 |
|---|---|---|---|---|---|---|---|
| 전체 | 7 | 1 | 0 | 0 | 6 | — | 차이 없음 |
| 새 영역 | 2 | 1 | 0 | 0 | 1 | — |  |
| 함정 | 5 | 0 | 0 | 0 | 5 | — |  |

갈린 문제 0건 (id 는 `--discordant-out` 으로 저장)


## 메모

- ga-main-disc: 새 영역 문제 차단 0/2건 (false_block 분모 밖)
- ga-main-disc: ci95: 문제별 반복 평균의 부트스트랩 2000회 (2.5·97.5 백분위)
- ga-main-disc: 문제 종류: novel 2, trap 5
- da-e-on-disc: 새 영역 문제 차단 0/2건 (false_block 분모 밖)
- da-e-on-disc: ci95: 문제별 반복 평균의 부트스트랩 2000회 (2.5·97.5 백분위)
- da-e-on-disc: 문제 종류: novel 2, trap 5

## 표 3 — (가 1차) vs (라) idf 만, 함정·새 영역 20문제 (보정 전 기준이라 "기준만" 6 중 5 는 1차 부하 영향 — 본문 결론 참고)
| 지표 | ga-main | ra-idf-on | 차이(ra-idf-on) | 판정(ra-idf-on) |
|---|---|---|---|---|
| 역방향 정답 상위 5 적중률 (recall_at5) | 1.000 | — | — | — |
| 함정 차단율 (false_block, 낮을수록 좋음) | 0.500 | 0.833 | +0.333 | 구간 없음 |
| 새 영역 novel 판정률 (novel_rate) | 0.875 | 0.875 | +0.000 | 구간 없음 |
| novel 장벽 '추정' 비율 (낮을수록 좋음) | — | — | — | — |
| ② 지연 중앙값 초 (latency_p50) | 24.200 | 30.500 | +6.300 | 구간 없음 |
| ② 지연 p90 초 (latency_p90) | 27.630 | 82.590 | +54.960 | 구간 없음 |
| 과제안 0건 비율 (rec_zero_rate, 낮을수록 좋음) | — | — | — | — |

## 실행 정보

| 열 | suite | seed | n | repeats | 봉인 | 커밋 | LLM 호출 | 캐시 적중 | 초 | 스위치 |
|---|---|---|---|---|---|---|---|---|---|---|
| ga-main | l1 | 1109048 | 40 | 1 | 아니오 | aeebccf | 0 | 0 | 988 | facets.enabled=False, idf_weighting.enabled=False, judgment.enabled=True, keywords=rule, llm=none, rerank.enabled=True, rerank.threshold=0.5, series.enabled=True, synonyms.enabled=False, with_recommend=False |
| ra-idf-on | l1 | 1109048 | 20 | 1 | 아니오 | 3854659 | 20 | 0 | 931.9 | facets.enabled=False, idf_weighting.enabled=True, judgment.enabled=True, keywords=rule, llm=gemini, rerank.enabled=True, rerank.threshold=0.5, series.enabled=True, synonyms.enabled=False, with_recommend=False |

## 짝 비교 (같은 문제, 문제별 맞힘 대조)

기준 열과 같은 문제 id 를 가진 열만. '기준만'·'비교만' 은 두 구성의 결과가 갈린 문제 수, McNemar p 는 그 둘의 정확 이항 검정(양측). p < 0.05 면 갈린 쪽이 많은 구성을 개선/악화로, 아니면 '차이 없음'. 갈린 문제만 3회 반복해 다시 재는 것이 다음 단계다.

### ga-main vs ra-idf-on

| 종류 | 공통 | 둘 다 맞힘 | 기준만 | 비교만 | 둘 다 틀림 | McNemar p | 판정 |
|---|---|---|---|---|---|---|---|
| 전체 | 20 | 7 | 6 | 2 | 5 | 0.2891 | 차이 없음 |
| 새 영역 | 8 | 6 | 1 | 1 | 0 | — |  |
| 함정 | 12 | 1 | 5 | 1 | 5 | — |  |

갈린 문제 8건 (id 는 `--discordant-out` 으로 저장)


## 메모

- ga-main: 새 영역 문제 차단 1/8건 (false_block 분모 밖)
- ga-main: 문제 종류: novel 8, reverse 20, trap 12
- ra-idf-on: 새 영역 문제 차단 0/8건 (false_block 분모 밖)
- ra-idf-on: 문제 종류: novel 8, trap 12
