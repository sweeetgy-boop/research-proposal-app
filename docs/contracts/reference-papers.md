# 계약 메모 — 참고 논문(reference) (ADR 0053, 2026-11-03)

레인 A(백엔드)와 레인 B(웹)가 서로 기다리지 않도록 0단계에서 정한 계약. 이 파일, `src/rra/domain/models/{request,comparison,recommendation}.py`
의 새 필드, `docs/openapi.json`, `web/src/api/schema.d.ts`, `web/src/api/types.ts`·`types-precheck.ts` 의 새 필드는 0단계에서만 고친다.

## 요청 (ProposalRequest — precheck·judgment·comparison·differentiate·recommendations·runs 모두 같은 몸통)
| 필드 | 형 | 규칙 |
|---|---|---|
| `reference_ids` | `string[]` | ② 관련 연구 doc_id. 최대 5(넘으면 422). 공백·빈 값 제외, 중복 제거. 실시간 검색(live) 항목도 허용. **판정·차단·similar_choices 에 쓰지 않음**. 작성 프롬프트(prompt_view)에도 안 들어감 |

## 응답
### 비교표 `comparison.projects[]` (ComparisonColumn)
- `kind`: `"similar"`(기본, [유사함] 유사과제) | `"reference"`(참고 논문). 화면 구분 칸에는 `"선행연구"` 를 보인다.
- reference 열 순서: similar 열 뒤, `reference_ids` 순서. `blocking` false, `similarity` 는 관련 연구 점수 또는 null.
- (2026-11-04 변경, feat/reference-rank — 소유자 결정) `relevance_rank: int | null`·`relevance_total: int | null` 이 모든 열에
  붙는다. reference 열에서만 값이 있고, 제안자가 본 ② 관련 연구 목록(`related_research`, 점수 내림차순 — 화면 순서) 안에서
  그 문서의 자리(1부터)와 목록 길이다. 같은 점수는 목록 순서를 그대로 둔다(`domain/rules/reference_rank`). 목록 출처는 같은
  입력의 precheck 메모이고, 메모가 없으면 같은 관련 연구 검색(`PrecheckOverlap.search_research`)을 다시 한다. 관련 연구 목록
  밖이면 둘 다 null 이다. similar 열·제안 열은 늘 null 이다. 화면은 선행연구 열 제목 아래 "관련 순위 n/총수"(예: "관련 순위
  2/5")로만 보이고 점수 숫자는 보이지 않는다(ADR 0039). `similarity`(점수)는 그대로 남지만 화면에 쓰지 않는다.
  - 없앤 것: 같은 날 feat/reference-relevance 가 더한 `relevance: "high" | "mid" | "low" | null`(고정 경계값 0.895·0.885,
    `config/overlap.yaml candidates.research.relevance`). 경계값 재측정은 시범 사례가 쌓인 뒤
    (`docs/eval-2026-11-04-reference-relevance.md` 맨 위).
- [유사함] 0건이어도 reference 가 있으면 `empty_reason` 은 null 이고 reference 열만 나온다.

### 과제안 `recommendations` (RecommendationResult payload)
- 형식은 그대로다. `compared_with`·`evidence`·`refs` 에 reference doc_id 가 들어올 수 있다.
- 더한 필드:
  - `retry_used: boolean`: 유사함 0건 + 추천 0건이라 '새 영역' 지시로 1회 다시 받았는지.
  - `hint: "reference" | null`: 추천 0건이고 `reference_ids` 가 비었을 때 `"reference"`. 그 밖에는 null.
  - `reference_doc_ids: string[]`: 입력으로 쓴 참고 논문(검증을 통과해 실제로 구획에 넣은 것).

### 차별화 활용 제안 `differentiation`
- 형식은 그대로다. 유사함 0건이어도 reference 가 있으면 실행하고, 항목 `evidence` 에 reference doc_id 를 쓸 수 있다.

## 화면 규칙 (레인 B)
- ② 관련 연구 행마다 [차별화에 참고] 체크를 둔다(기본 해제). 다섯 건이 넘으면 체크를 막고 "참고 논문은 5건까지" 를 안내한다.
- idea store `referenceIds` 를 [선택 적용]·과제안 다시 만들기·비교표·생성 요청에 넣는다. ③ 이후 다시 열어도 남는다.
  바뀌면 '선택이 바뀌었습니다' 를 보인다.
- 추천 0건이고 `hint === "reference"` 면 사유 아래에 "관련 연구에서 참고 논문을 골라 [과제안 다시 만들기]" 와 [원래 아이디어로 진행] 을 둔다.
