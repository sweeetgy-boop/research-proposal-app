# ADR 0037 — 작성·편집 AI 버튼: Argon 먼저·빈 결과 금지·정책적 중요도 작성안 (2026-10-28, 레인 B)

> 상태(2026-10-29 오후 문서 2차 최신화): 유효. ③ 정책적 중요도 작성안은 정책 근거가 비면 처음부터 펼쳐지고, ④ 의 [정책 근거 고르기] 는 [정책 근거 넣기·바꾸기](늘 보임·직접 입력)로 바뀌었다 — ADR 0052.

> 번호는 통합 담당이 정한다(0033 C, 0034·0035 D 사용 중 → 0037).

## 배경
시범 운영 하루 동안 다음이 보고되었다.
- **AI 다시 쓰기 "후보 0문장"** — 시범 runs 의 `rewrites/rewrite_*.json` 4건(사용자 2명)이 모두 `policy_importance`·후보 0·
  폐기 0이었다. 원인: 2-가-(1) 정책적 중요도는 입력 전용(`requires_input: policy_basis`)이다. 정책 근거가 비면
  `GenerateProposal.rewrite_section` 이 LLM 을 부르지 않고 **사유 없이** 빈 후보를 돌려줬다(`mode="skipped"`). 화면에는
  현재 문장 옆에 "(후보 없음)" 만 보였다. 같은 run 의 다른 섹션 다시 쓰기는 정상 반영(v3·v5·v6)되어 있었고, 복사한 실 run
  으로 Argon 다시 쓰기를 돌리면 후보가 1~8문장 나왔다. `overlap_review` 는 409 였다.
- **정책적 중요도 빈칸** — 정책 근거를 모르는 제안자가 많다. 빈칸 + `input_missing` 경고만 남았다.
- **보강 질문 없음** — `pipeline.clarify: false`. 화면은 "꺼져 있거나 입력 충분" 을 구분하지 못했다.
- **보완 질문은 늘 "빠진 요소가 없습니다"** — 체크리스트가 6개 섹션에만 있었고 키워드가 본문에 하나만 있어도 "있음".
- **"변경 0건"이라 [새 버전으로 저장]이 꺼짐** — 그림 확인·근거 승인 같은 동작은 바로 버전이 되므로 세지 않았다.
- (별도) 근거 판단을 다시 저장하면 `decide_evidence` 가 `sorted(dict…)` TypeError 로 500 을 냈다(API 오류 로그).

## 결정
1. **AI 버튼 공통 규칙** (`application/usecases/argon_first.ArgonFirst`)
   - Argon(review 단계 provider, `BudgetedLLM`·공유 호출 제한기) 먼저. 호출 예외(error·rate_limit·budget)나 교정 재요청 뒤에도
     형식 오류(invalid)면 로컬 모델(전역 슬롯 안에서). 모델이 "없음" 이라고 답하면(empty) 다시 묻지 않는다.
   - **빈 결과로 조용히 끝내지 않는다**: 값이 없으면 사유 코드 + 한국어 라벨(`REASON_LABELS`: 호출 실패 / 해당 없음 /
     규칙에 걸러짐 / 꺼져 있음)을 돌려주고 화면은 [다시 시도] 를 보인다. 내부 코드는 화면에 보이지 않는다.
   - 공용 계정은 internal 을 프롬프트에 넣지 않는다(기존 규칙). 제안자 수정 문장·선택값은 AI 가 바꾸지 않는다.
   - 레인 A 의 precheck 카드 [AI로 다듬기] 와 레인 C 의 그림 [말로 고치기] 도 같은 규칙을 따른다(구현은 각 레인).
2. **AI 다시 쓰기** — 작성자가 로컬(compose.writer: local)이어도 다시 쓰기는 Argon 먼저(`GenerateProposal.rewrite_llm`).
   후보가 0이면 `reason`(policy_basis_needed·no_relevant_evidence·app_section·error·invalid·filtered·empty). 빈 섹션은
   "새로 쓰기"(mode new). 2-가-(1) 은 정책 근거가 없으면 작성안으로 연결한다. 원격·로컬 모두 실패해도 500 이 아니라 사유.
3. **정책적 중요도 작성안 최대 4개** (`domain/rules/policy_cards`, `usecases/policy_cards`)
   - 정책 자료원(국토부·정부 R&D 공고 / 공사 중장기 전략 / 감사원·경영평가 / 남은 구간 중 지역·사회 정책 어휘)을 방향별로
     검색하고 원문 문장을 그대로 인용한다. **한 문서는 한 안에만**(근거 겹침 없음), 근거가 받쳐 주는 방향만큼만 안을 보인다.
   - 안의 본문(2~3 "○" 문장)은 Argon 이 쓰고, 문장마다 그 안의 구간 id 를 인용해야 하며 정책·계획명·연도(grounding)와
     수치(numbers)는 인용 구간(+제안자 입력)에 있어야 한다 — 어기면 그 문장을 버린다(정책명 규칙).
   - 동작: [이 안으로] · 두 안 합치기 · 고른 뒤 직접 수정 + [AI로 다듬기] · [직접 작성] · [정책 근거 없음으로 진행] ·
     [다른 안 보기](본 문서 제외). 결과는 자동으로 들어가지 않는다.
   - 고른 안은 `ProposalRequest.policy_choice` 로 run 에 들어간다. 생성 때 인용 구간을 **저장소 원문과 다시 대조**해(보안 A,
     클라이언트가 보낸 인용은 비신뢰) 통과한 구간만 스냅샷 `policy_ids` 에 고정하고, 2-가-(1) 은 고른 문장을 그대로
     (origin proposer_input) 근거와 함께 쓴다. 근거 금지 섹션 규칙은 이 구간에 한해 허용한다. policy_basis 가 비었으면 요지로 채운다.
   - "정책 근거 없음" → 빈칸 대신 `policy_basis_needed`("정책 근거 확인 필요") 알림, 제출 전 점검 `policy_basis` 항목에서 다시 표시.
   - ④ 편집에서도 같은 작성안으로 고를 수 있다(`POST /v1/runs/{id}/policy-choice`, 새 버전 "정책 근거 선택").
4. **보강 질문 켬** (`pipeline.clarify: true`) — 앱 점검(정책 근거·소요예산·연구기간·적용 대상·정량 목표치) + 섹션 체크리스트를
   Argon 에게 주고 2~4개 질문. 정책 근거 질문은 앱이 내고 그 자리에 작성안. 상태 off/enough/failed 로 "질문 없음" 사유를
   가르고, 모델이 모두 실패하면 앱 점검 질문 + 사유.
5. **보완 질문** — Argon 이 섹션 본문·근거·양식 작성 지침(섹션 프롬프트)을 읽고 2~4개. 실패하면 로컬, 그다음 체크리스트.
   **모든 섹션에 체크리스트**(테스트가 rules.yaml 섹션과 대조). 결과는 버전별로 보관(같은 버전은 다시 부르지 않음).
   [답 반영해 다시 쓰기] = 답 저장 → 그 섹션 AI 다시 쓰기.
6. **변경 n건** (`domain/rules/change_count`) — 기준 = 마지막 최종 검토 버전(없으면 초안 v1·v2 중 최신). 문장 수정·삭제·추가,
   선택값, 그림 추가·변경·확인·빼기·다시 넣기·추천 그림 결정(그림 v2), 근거 승인·교체·제외, 선택형 확정, 정책 근거 선택,
   보완 메모. 화면은 + 저장하지 않은 편집. 버튼은 항상 켜짐: 변경 없음 → "변경된 내용이 없습니다. 최종 검토로 넘어갈까요?",
   있음 → 저장 뒤 "최종 검토로 넘어갈까요?".

## 결과
- REST: `POST /v1/ideas/policy-cards(/polish)`, `POST /v1/runs/{id}/policy-cards(/polish)`, `POST /v1/runs/{id}/policy-choice`,
  `GET /v1/runs/{id}/changes`, `GET …/questions?refresh=true`, `POST /v1/precheck/clarify` 응답 확장, rewrite 응답 확장.
- 비용: 보강 질문 1회, 작성안 1회, 다시 쓰기·보완 질문 섹션당 1회(+교정 1회) — 모두 Gemini 일일 예산 카운터를 거친다.
- 되돌리기: `pipeline.clarify: false`, review 키가 없으면 자동으로 로컬만.
