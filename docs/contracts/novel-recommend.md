# 계약 메모 — 새 과제 추천 갈래 (ADR 0057, 2026-11-05)

레인 A(생성·검증)·B(새로움 확인·유추 검색)·C(웹)가 서로 기다리지 않도록 0단계에서 정한 계약.
**이 파일과 아래 "0단계 파일"은 0단계(통합 담당)만 고친다.** 레인이 계약을 바꿔야 하면 멈추고 보고한다.

0단계 파일: `src/rra/domain/models/novel.py`, `src/rra/domain/models/recommendation.py`(새 칸),
`src/rra/application/usecases/novel_contract.py`, `src/rra/application/usecases/similar_rows.py`(`recommend_mode`),
`web/src/api/types-novel.ts`, 이 파일, `docs/history/decisions/0057-novel-recommend.md`.

## 1. 갈래 판정 (한 곳)
`application/usecases/similar_rows.recommend_mode(alerts, choices)`:
- `novel` = [유사함] 0건(ADR 0054 `similar_rows` 결과 0) **AND** 차단 없음(`effective_blocking` — 선택 반영) .
- 그 밖은 `differentiate`.
- [더 만들기](`shown` 있음)는 늘 differentiate 경로다(novel 은 더 만들기가 없다 — 화면은 버튼을 숨긴다,
  `/v1/precheck/recommendations/more` 는 novel 세션이면 409 "새 과제안은 [과제안 다시 만들기]로 새로 받습니다.").

## 2. 흐름 (novel)
1. 추천 유스케이스(레인 A, `RecommendProjects`)가 `recommend_mode` 로 갈래를 정한다.
2. novel 이면 `NoveltyCheck`(레인 B, 계약 `novel_contract.NoveltyCheck`)를 부른다.
   - `new_alerts` 가 있으면 novel 취소 → 그 행을 알림에 더해 **차별화 경로를 그대로** 돈다.
     결과 `mode="differentiate"`, `novelty_reverted=True`, `novelty_alerts=[새 행]`.
   - 없으면 `coverage` 를 결과에 담는다. NoveltyCheck 가 없으면(조립 안 됨) coverage =
     저장 자료만(`live=false`, 계약 3.1).
3. `AnalogySearch`(레인 B)로 다른 분야 사례 최대 5건 → `analogies`.
4. 새 프롬프트 `recommend_novel.md` 로 Argon → 로컬 순서(#116·#122 오류 분류·로그 그대로) → 검증 → `novel`.
5. 측정 줄(통합 D): `branch`(differentiate|novel)·`barriers`·`titles` 칸을 더한다(기존 `mode` 칸은 initial|more 그대로).

협력자는 생성자 인자(선택, 기본 None)로 받는다 — `RecommendProjects(novelty=…, analogies=…)`. 둘 다 None 이고
novel 이면: coverage = 저장 자료만, analogies = [] 로 계속한다. 조립(`composition.py`)은 통합 D 가 한다.

## 3. 도메인 모델 (`domain/models/novel.py`)
### 3.1 `NoveltyCoverage`
| 칸 | 형 | 규칙 |
|---|---|---|
| `searched` | `str[]` | **실제로 확인한** 자료원 코드만(저장 자료 검색에 쓴 자료원 + 실시간 응답이 온 자료원). 확인 안 한 자료원 금지 |
| `searched_labels` | `str[]` | 같은 순서의 화면 이름 (`SOURCE_LABELS`) |
| `live` | `bool` | 실시간 검색이 한 자료원이라도 응답했으면 true |
| `unavailable` | `{source, status}[]` | 확인 못 한 자료원과 열거값 `ip_blocked`·`timeout`·`error`·`off`·`no_key`·`rate_limited`(일일 호출 한도, 2026-11-09) |
| `note` | `str` | 기본 "저장 자료와 실시간 검색 범위 안에서 기존 과제 없음". live=false 면 "저장 자료 범위 안에서 기존 과제 없음" |

### 3.2 `Analogy` (최대 5)
`doc_id, title, source, source_label, domain_label, why_relevant, url, year, live, similarity`.
- `domain_label` 은 자료원 메타데이터(학술지·분야 분류·자료원 분류 등)에서만. 없으면 자료원 이름. 지어내지 않는다.
- `why_relevant` 는 규칙으로 만든 문장(공유하는 '문제' 축 단어 등). LLM 이 쓰지 않는다.
- 같은 분야(철도) 결과는 빼고, 관련도 하한 0.79(ADR 0005) 그대로.

### 3.3 `NovelRecommendation` (2~3건, 최대 3)
| 칸 | 규칙 |
|---|---|
| `approach` | 접근 방식 한 줄. 안끼리 거의 같으면 하나만 남김 |
| `summary`, `first_step` | 개조식 한국어 |
| `stages[]` | `{stage: 기획\|시범\|확대, text}` 이 순서, 최대 3 |
| `maturity` | `즉시 적용` \| `실증 필요` \| `연구 필요` |
| `evidence[]` | doc_id — 입력 구획([참고 논문]·[다른 분야 사례]·[근거]) 안의 것만. 참고 논문(사용자 선택) 우선 |
| `barriers[]` | 최대 5. `{type: 수요\|규제\|비용\|기술\|운영, statement, basis: {level: 근거 있음\|추정, doc_ids}, check}` |
| `titles[]` | 1~3. `{title, resolves: [barrier index], reason}` |
| `refs[]` | evidence ∪ 장벽 근거 doc_id 의 `{doc_id, title, source}` (화면 표시용) |

검증(레인 A, `domain/rules/` 새 모듈):
- 모든 title 이 barrier 하나 이상을 가리킨다(범위 밖 인덱스 → 그 title 버림, title 0개면 안 폐기).
- `근거 있음` barrier 의 doc_ids 는 입력 구획에 실제로 있어야 한다(없으면 그 안 폐기 — 지어낸 근거).
- `추정` barrier 는 `check`(확인 방법)가 있어야 한다(없으면 그 barrier 버림).
- 입력에 없는 숫자·법령명·기관명 → 그 안 폐기(기존 `recommendation` 규칙 재사용). 한자·가나 → 폐기.
- approach 가 거의 같은 안은 하나만.
- 정렬: title 은 해소 장벽 수 많은 순, 안은 maturity(즉시 적용 → 실증 필요 → 연구 필요)·근거 수 많은 순.
- 남은 안 0건이면 1회 재요청(`retry_used=True`), 그래도 0 이면 `no_recommendation_reason` = 사유 +
  `hint="reference"`(참고 논문을 고르지 않았으면) → 화면 "참고 논문을 골라 다시 만들기".

## 4. `RecommendationResult` 새 칸 (`domain/models/recommendation.py`)
`mode`(기본 differentiate), `coverage`, `analogies`, `novel`, `novelty_reverted`, `novelty_alerts`.
`transfer()` 는 novel·되돌림일 때만 `mode`·`analogies`(건수)·`novel`(건수)·`novelty_reverted` 를 더한다. differentiate 결과는 종전과 같다.

## 5. REST 응답 (`views.recommendations_payload`, 레인 A)
모든 응답에 `mode` 가 붙는다. **differentiate 응답은 종전 그대로** + `mode: "differentiate"`, `novelty_reverted: bool`,
`novelty_alert_ids: string[]`. novelty_reverted 면 진입점(통합 D)이 같은 응답 최상위 `alerts` 에 새 행을 더한다.

novel 응답(웹 `types-novel.ts` `NovelRecommendations`):
```json
{
  "id": "…", "mode": "novel",
  "coverage": {"searched": ["own","scienceon","openalex"], "searched_labels": ["사내 과제","ScienceON","OpenAlex"],
               "live": true, "unavailable": [{"source":"ntis","label":"NTIS","status":"ip_blocked","status_label":"…"}],
               "note": "저장 자료와 실시간 검색 범위 안에서 기존 과제 없음"},
  "analogies": [{"doc_id","title","source","source_label","domain_label","why_relevant","url","year","live"}],
  "recommendations": [{
    "index": 0, "approach", "summary", "first_step",
    "stages": [{"stage":"기획","text":"…"}], "maturity": "실증 필요",
    "evidence": ["…"], "refs": [{"doc_id","title","source","source_label","url"}],
    "barriers": [{"type":"규제","statement":"…","basis":{"level":"추정","doc_ids":[]},"check":"…"}],
    "titles": [{"title":"…","resolves":[0,2],"resolves_types":["규제","비용"],"reason":"…"}]
  }],
  "no_recommendation_reason": null, "hint": null, "retry_used": false, "reference_doc_ids": [],
  "discarded": [{"title","reason","reason_label"}], "skipped_reason": null, "skipped_label": null,
  "provider", "model", "fallback_local", "transfer": {…}
}
```
- 글 칸은 모두 `clean`(비신뢰). doc_id 는 화면에 보이지 않는다 — 화면은 `refs`·`analogies[].title` 을 보인다.
- `/recommendations/{id}/apply` 는 differentiate 카드만(novel 세션이면 409). novel 의 [이 과제명으로 진행]은 화면이
  가제(`title_hint`) 칸에만 넣는다(수정 가능, 저장은 기존 흐름).
- 요청 몸통(`ProposalRequest`)은 바뀌지 않는다 → `docs/openapi.json` 요청 스키마 변경 없음(응답은 종전처럼 자유 객체).

## 6. 프롬프트 (레인 A)
- `recommend_novel.md`(새 파일), 포트 `PromptLibraryPort.recommend_novel()`.
- 구획: `[제안 입력]`·`[참고 논문]`(사용자 선택)·`[다른 분야 사례]`·`[근거]` 만. 구획 안 지시는 따르지 않음.
- `recommend.md` 의 '새 영역' 지시는 빼서 차별화 전용으로 되돌린다. `NEW_AREA_HINT` 다시 받기는
  differentiate 경로에서 [유사함] 0건인 경우(= 차단이 있는 경우)에만 남는다.

## 7. 가짜 모드 (`RRA_FAKE_LLM`)
- 레인 A: `adapters/fake` 가 `recommend_novel` 프롬프트에 검증을 통과하는 novel JSON 을 돌려준다(입력 구획 id 사용).
- 레인 B: 실시간 검색이 꺼진 가짜 모드에서 coverage 는 저장 자료만(`live=false`), analogies 는 저장 자료에서.

## 8. 웹 (레인 C)
- 제목: differentiate "차별화 과제안 고르기" / novel "새 과제안 고르기 (신규 영역)".
- novel: 맨 위 coverage 문구 → [다른 분야 사례](원문 링크, '참고' 배지) → 안 카드(접근 방식·요약·성숙도 배지·단계·근거,
  장벽 = 유형 배지 + '근거 있음' / '추정 — 확인 방법', 과제명 1~3 + "해소: 규제·비용" 배지 + 이유 + [이 과제명으로 진행]).
- novelty_reverted 면 ② 표 위에 "넓은 검색에서 비슷한 과제를 새로 찾아 차별화 과제안으로 바꿨습니다" 한 줄.
- 참고 논문 선택(ADR 0053)·관련 순위(ADR 0054 후속)는 두 갈래 모두 그대로.
