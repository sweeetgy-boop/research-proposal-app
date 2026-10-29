# 레인 B — feat/policy-l2 (2026-10-28 밤, 시범 의견 반영 2차) 전달 사항

> 이후 변경(2026-10-29 오후): ① [추천 받기] 버튼은 정책 근거 추천 팝업(자동 호출·1순위 미리 체크·[적용])으로 바뀜 — ADR 0052. 아래는 2026-10-28 레인 기록.

ADR 0040. 측정 `docs/eval-2026-10-28-policy-reclass.md`. PR #90.

## 측정 요약
- 이주: korail_web 702건(연구용역 287·행정 공시 270·현황 70·통계 23·정책 52), 다른 자료원 0건. 정책 근거 후보 702 → 52.
- 정책 근거 추천(골든셋 4건): 전 19건 중 16건이 연구용역·행정 자료 → 후 연구용역 0건.
- L2(실제 Argon + 로컬 7B, 그림 끔): 로컬 판정 20~46초 + Argon 제안 5~18초. 01 단독 생성 183~278초, 동시 3건 261~355초(전체 371초).
  최종 규칙 02: 지지 23·불일치 1 / 24문장. Gemini 레인 B 82회(55 → 137).

## 전달한 것
- **18. 정책 근거 추천 — 자료 분류**
  - 규칙 `domain/rules/doc_category` — 공사 사전정보공표 연구용역(infoRelNo 55 등) = **연구용역(사내 발주)**: `doc_type procurement`
    + `raw.doc_class research_service`. 행정 공시·사업 현황·규정 = `raw.doc_class admin_record|status`(doc_type 그대로).
    통계자료 게시판 옛 행 = statistics. 적재(`korail_web` normalize)와 이주가 같은 규칙.
  - 운영 DB 이주 `rra db reclassify [--apply] [--json]`(기본은 점검만): 백업 `data/backups/rra-20261028-214727.sqlite` 뒤 적용 —
    korail_web 702건 바뀜(연구용역 287·행정 공시 270·현황 70·통계 23·정책 52), 다른 자료원 0건. 재색인 없음.
  - 연구용역은 유사과제 판정 후보(`overlap.yaml candidates.project` + korail_web procurement)·선행연구에 남고, 알림 구분은
    "연구용역(사내 발주)".
  - ① 정책 근거 추천 = ③ 정책적 중요도 작성안과 같은 범위·관련도(`policy_cards.policy_passage`, `doc_category.is_policy_basis`):
    국토부·R&D 공고·공사 정책·감사원·기재부. 인용은 URL·앞 글머리 없이 통문장, 원문 링크는 아래 "원문". 정책 근거 칸 문구에도
    URL 없음. [추천 받기]·작성안·[AI로 다듬기] 는 시간 제한 없이 "응답 기다리는 중 · 경과 n초" + [취소](경로 `cancel_on_disconnect`).
- **내부 번호 정리 — 공용 도우미**
  - 서버: `domain/rules/doc_refs`(SOURCE_NAMES·doc_ref·replace_internal_ids)·`entrypoints/views_refs`. draft `citations[]` 에
    `source`·`source_label`·`url`, 검토 의견 `comment`·`revised_text`·점수 이유의 번호를 「제목」·"<섹션> 그림 n"·"<섹션> 문장 n" 으로,
    의견마다 `evidence_refs[]`, 정책 추천 `source`·`source_label`, 근거 패널 title 없으면 "제목 없는 자료", 알림·제출 전 점검 문구 번호 제거,
    유사과제 알림 `source_label`.
  - 화면: `web/src/lib/docRefs.ts`(docRef·replaceDocIds·hasInternalId·SOURCE_NAMES)·`web/src/components/DocRef.tsx`(DocRef·DocRefList·
    DocRefPanel). 적용: 근거 패널(번호·문장 id 없음, 원문 링크), 초안 근거 칩·인용 문서 목록, 알림 목록, 검토 의견(1차·최종), 정책 추천,
    정책 작성안, 직접 수정의 수정안·메모, 제출 전 점검 상세, 설계도.
  - e2e 도우미 `web/e2e/helpers-text.ts` `expectNoInternalIds(page, scope?)`.
- **L2 로컬 2차 검토** — `compose.local_check: on`, 시간 상한 제거, 2-가-(1)·(2)·수치·고유명 문장 먼저, 판정 지지/부분/불일치(문장 옆
  "로컬 검토: …"), 규칙 불일치(근거에 없는 수치·이름·핵심어 0), 불일치만 Argon "근거 안에서 다시 쓰기 또는 빼기" 제안 → [반영](새 버전)·
  [무시](결정 기록, 새 버전 없음, 레인 D `record_mark("suggestion_ignore")`), 실패면 사유 + [다시 시도]. 제출 전 점검 "근거 확인" 에
  결정 전 불일치 수. manifest `local_check.counts`.

## 판단
| 항목 | 판단 | 이유 |
|---|---|---|
| 연구용역 표현 | doc_type procurement + raw.doc_class | procurement 는 이미 유사과제 판정 "용역" 티어·정책 근거 밖. 새 doc_type 은 retrieval_mix 등 여러 곳을 바꿔야 함 |
| raw 키 이름 | `doc_class` (category 아님) | 이주 점검에서 국토부·사내 과제가 raw.category 를 다른 뜻으로 쓰는 것을 발견 |
| 행정 공시·현황 | doc_type 그대로 + doc_class | 섹션 근거 구성(retrieval_mix, 공유 파일)을 바꾸지 않으려고. 2-가-(3) 근거에는 남을 수 있음(후속) |
| 신사업자료실 | 검토·구상·자문용역 = 연구용역, 규정 = 행정 | 공사 자체 검토 보고서는 정책 방침이 아니라 과제형 자료 |
| 경영실적 평가·안전관리등급 심사·업무보고·부서별 주요계획 | 정책 | 공사 경영목표·전략·평가 지적 |
| 감사계획·공직기강 감찰·청렴 | 행정 공시 | 정책 지적이 아니라 내부 행정 |
| 인용 300자 초과 문장 | 자르지 않고 후보에서 뺌 | "문장 중간에서 끊지 않는다". 청크 끝에서 잘린 조각도 고르지 않음 |
| 정책 근거 칸 문구 URL | 넣지 않음 | 원문 링크는 화면 "원문" 으로만 |
| 로컬 판정 | 규칙이 겹친다(근거·입력·제목에 없는 수치, 낫표·제N차·법령 이름, 핵심어 0 → 불일치) | 실측에서 7B 가 바꾼 수치를 "지지", 무관 주장을 "부분". 7B 스스로의 불일치는 실측 0건 |
| 규칙의 범위 | 일정 표기·문장 속 번호·5. 특이사항 제외, 이름은 분명한 것만 | 첫 규칙이 실측 거짓 불일치 16건 — 다듬은 뒤 같은 문장 122개에 0건 |
| Argon 제안 | 동시 4건 | 차례로 7건 69초 → 동시 4건 5~18초 |
| 로컬 판정 응답 | 배열도 받음 | 7B 는 배열만 냈고 파서가 전부 버렸다(불일치 0건의 원인) |
| 제출 전 점검 | 결정 전 로컬 불일치는 "근거 확인" 의 확인 필요 | [무시] 도 결정이므로 빠진다 |
| [반영] 중 임시 편집 | 막음(먼저 저장) | apply_edits 가 임시 사본을 지운다 |
| 측정 구성 | 그림 끔(figures.enabled false) | Gemini 상한 안에서 L2 시간만 보려고 — 생성 시간 비교는 이 점을 감안 |
| 가짜 모드 | 2-가-(2) 첫 문장 불일치·둘째 부분·연구용역 시드 1건 | e2e 가 [반영]·[무시]·추천 제외를 본다 |

## 남은 일
- 행정 공시·현황(policy + doc_class)을 2-가-(3) 전략 정합성 근거에서 뺄지 — `config/retrieval_mix.yaml`(통합 담당).
- 7B 판정의 거짓 불일치(실측 6문장 중 1건) — 자동 반영이 없으니 제안자가 [무시]. 표본이 쌓이면 판정 모델·규칙 재검토.
- `docs/openapi.json`·`schema.d.ts` 재생성(새 경로 4개, 요청 본문 `LocalApplyIn`).
