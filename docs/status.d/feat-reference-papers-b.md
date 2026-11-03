## 참고 논문 — ② 관련 연구에서 골라 차별화·과제안에 쓰기 (feat/reference-papers-b, 2026-11-03, 레인 B 웹, ADR 0053)

- ② `features/idea/RelatedResearchList.tsx`: 행마다 [차별화에 참고] 체크(`data-testid=reference-checkbox`, 접근 이름 "차별화에 참고 — 제목"), 기본 해제,
  실시간 검색 항목 포함. 다섯 건이면 나머지 체크를 막고 `reference-limit-note`(aria-live polite)에 "참고 논문은 5건까지 고를 수 있습니다…".
  `onToggle` 없이 `selected` 만 주면 읽기 전용 배지(run 안 ② `RunPrecheck` 는 저장된 `reference_ids` 를 배지로).
- idea store: `referenceIds`(고른 순서)·`appliedReferenceIds`([선택 적용] 한 것)·`planRefSig`(과제안을 만든 때의 서명). 새 유사과제 확인이면 비운다.
  요청: 비교표·활용 제안 = 적용한 선택 + 적용한 참고 논문, 과제안 다시 만들기·더 만들기 = 적용한 [유사함] 선택 + **지금** 참고 논문
  ("참고 논문을 골라 [과제안 다시 만들기]" 안내를 그대로 따르게), [선택 적용]·③ 생성(`Clarify` 본문 `reference_ids`) = 지금 선택.
  유사함 0건이어도 참고 논문이 있으면 [선택 적용] 이 활용 제안을 부른다. 참고 논문이 바뀌면 요약 막대 '선택이 바뀌었습니다'·과제안 칸 "참고 논문 선택이 바뀌었습니다".
- 비교표 `ComparisonView`: `kind === "reference"` 열에 구분 배지 '선행연구'(`lib/labels.ts COMPARISON_KIND_LABELS`, 없으면 유사과제).
  선행연구 열이 섞일 때만 열마다 구분 배지(`data-testid=comparison-kind`)를 보인다.
- 과제안 0건(`PlanCards`): `hint === "reference"` 면 사유 아래 `plan-reference-hint`("관련 연구에서 참고 논문을 골라 [과제안 다시 만들기]…", 지금 고른 수,
  [관련 연구로 이동] → 관련 연구 제목에 포커스), `plan-empty-actions` 안에 [과제안 다시 만들기](고른 것이 없으면 꺼짐)·[원래 아이디어로 진행]·[직접 작성].
  `retry_used` 면 `plan-retry-note` "겹치는 기존 과제가 없어 '새 영역' 기준으로 한 번 더 받았습니다."
- 작성 가이드 `features/guide/content.tsx` ② 유사과제 확인에 한 문장 추가 — **통합 담당: `docs/pilot-guide.md` 같은 자리에 옮길 것.**
- 시험: vitest 214 → 223(`features/precheck/ReferencePapers.test.tsx` 9건, axe 0). e2e 는 통합 담당.
