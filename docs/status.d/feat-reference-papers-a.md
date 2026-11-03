# 레인 A — feat/reference-papers-a (2026-11-03, 참고 논문 백엔드, ADR 0053) 전달 사항

계약(`docs/contracts/reference-papers.md`)·도메인 모델 필드·`docs/openapi.json` 은 0단계 그대로다(이 레인은 고치지 않음).

## 전달한 것
- **참고 논문 읽기** `application/usecases/references.load_references`: `reference_ids` → `repo.get_document`(요청 순서, 중복·다른
  구획에 이미 있는 id 제외, 최대 5). 없는 id·권한 밖(공용 계정 `PublicOnlyRepository` 가 internal 을 None 으로)은 조용히 뺀다.
  전송 범위 정책(`include_internal=False`)이면 internal 은 보내지 않고 `excluded_doc_ids` 에 남긴다. 실시간 검색 문서는 precheck
  응답 전에 public·`raw.live` 로 저장되므로(ADR 0031 `_store` → 세션 끝) 같은 길로 읽힌다.
- **도메인 규칙** `domain/rules/reference_papers.py`: `[참고 논문]` 구획(`<doc id kind="reference" source doc_type year>`, 본문
  `escape_untrusted`, 속성 따옴표·꺾쇠 제거), 차단 없는 '참고' 알림(`reference_alert`), `unique_references`.
  `domain/rules/recommendation.py`: `validate_recommendation(reference_doc_ids=…)`(허용 id = 알림 + 근거 + 실제로 넣은 참고 논문),
  `NEW_AREA_HINT`, `recommendation_hint(count, reference_ids)`. `domain/rules/comparison.py`: `reference_column`, `comparison_table(references=…)`.
- **과제안** `recommend_projects`: `[참고 논문]` 구획·`refs`(제목·자료원)·`reference_doc_ids`·전송 기록(public/internal)에 참고 논문.
  **'새 영역' 다시 받기**: [유사함] 0건(similar_only 면 [유사함] 으로 고른 행 없음, 아니면 비교 대상 알림 없음) + 첫 응답이 검증 뒤
  0건 → `NEW_AREA_HINT` 를 붙여 1회만 다시(`retry_used=True`). 첫 응답에 제외 사유가 있으면 종전 "2건 미만 다시 받기" 사유를 **같은
  호출**에 붙인다(`regenerated=True`) — 묶음 받기는 최대 2회, 각 회 Argon → 로컬 순서. [더 만들기](`shown`)에는 쓰지 않는다.
  **hint**: 최종 0건이고 `req.reference_ids` 가 비면 `"reference"`(건너뜀·실패 결과 포함), 아니면 null.
- **활용 제안** `differentiate`: [유사함] 0건이어도 참고 논문이 있으면 실행(`[유사과제]` 는 "(없음)"). 항목은 참고 논문 doc_id 로도
  낼 수 있고(같은 검증 — '참고' 알림), evidence 는 유사과제 + 참고 논문 id 안에서만.
- **비교표** `compare_projects`: 유사과제 열 뒤 `kind="reference"` 열(요청 순서, 칸은 AI 추출 → 규칙 → 제목 기준, 차단 없음,
  similarity null). 참고 논문이 있으면 `empty_reason` null. `views.comparison_payload` 는 모든 열에 `kind`(제안 열은 기본값 similar).
- **REST** `views.recommendations_payload` 에 `retry_used`·`hint`·`reference_doc_ids`. `POST /v1/precheck`(stage=full) 활용 제안은
  `similar_count` 또는 `reference_ids` 가 있을 때. `/recommendations/more` 는 합친 결과의 `hint`·`reference_doc_ids` 를 지금 입력 기준으로
  다시 정한다. `/apply` 는 세션 입력(reference_ids 포함)을 그대로, `POST /v1/runs` 는 request.json 에 reference_ids 를 남긴다.
- **판정 무관 확인**: precheck(규칙·AI 판정)·차단·`default_choices`·선택 기록·precheck 메모 키(search_text 해시)·실시간 검색 세션 키·
  작성 프롬프트(prompt_view, FORM_ONLY)에 reference_ids 가 들어가지 않는다 — 시험으로 고정.
- **프롬프트** `recommend.md`(새 `[참고 논문]` 입력, "겹치는 과제 없음"은 빈 배열 사유 아님 → '새 영역' 1~3건, 빈 배열은 근거 전혀 없음·
  목적 밖일 때만, `[새 영역]` 지시 설명, 지어내기 금지 유지), `differentiate.md`(참고 논문 구획·항목). recommend 프롬프트 변형은 이것 하나뿐.

## 가짜 모드(RRA_FAKE_LLM=1) — e2e 장면 만드는 법
- 관련 연구 참고 논문: 시드 `scienceon:fake-1`("궤도 틀림 진행 속도 추정 논문 (가짜)") — e2e 기본 입력(`fillIdea`)이면 ② 관련 연구 1건.
- **0건 + hint**: `fillIdea(page, " (추천 없음)")`, 참고 논문 고르지 않음 → 과제안 0건, `retry_used: true`, `hint: "reference"`
  (가짜 추천자는 "(추천 없음)" 이면 '새 영역' 다시 받기에도 0건).
- **참고 논문으로 벗어남**: 같은 입력 + 관련 연구 `scienceon:fake-1` [차별화에 참고] → [과제안 다시 만들기] → 과제안 2건(비교 대상 =
  그 논문), `reference_doc_ids: ["scienceon:fake-1"]`, `hint: null`. 비교표에 `kind: "reference"` 열 1개(`empty_reason` null), 활용 제안 1건.
  ("(추천 없음)" 없이 기본 입력 + 참고 논문이어도 2건.)

## 시험
- `tests/application/test_reference_papers.py` 12건(유사함 0 + 참고 1 → 카드, id 허용, 유사함 0 + 참고 0 + 빈 응답 → 정확히 2회·retry·hint,
  제외 사유 + 새 영역 한 호출, [유사함] 있으면 새 영역 없음, 없는/권한 밖 id, 전송 정책, 활용 제안 참고만, 비교표 열 순서·kind,
  판정·차단·메모 키 불변, 골든셋 03 + 참고 논문 차단 0, 실시간 검색 문서 저장 → 참고 논문으로 읽힘(공용 계정 저장소)).
- `tests/entrypoints/test_reference_papers_api.py` 3건(가짜 모드 REST: 판정 불변·선택 기록 없음·6건 422, 0건+hint, 참고 논문 →
  카드·비교표·활용 제안·[적용]·[더 만들기]·생성 요청).
- 합계 2409 → 2424 통과, skip 21. lint-imports 8 유지. `rra api schema` 결과 = docs/openapi.json(변경 없음).

## 남은 것·사람 판단
- 웹(레인 B): [차별화에 참고] 체크·hint 안내·비교표 '선행연구' 칸.
- 참고 논문 열 `similarity` 는 지금 늘 null — 관련 연구 점수를 넘기려면 요청에 점수를 싣거나 precheck 메모에서 찾아야 한다(계약은
  "점수 또는 null" 이라 null 로 둠).
