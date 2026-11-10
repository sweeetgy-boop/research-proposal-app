# feat/card-reuse-pin-zero-hint (2026-11-10, 계약 problem-card.md 4.4절) 전달 사항

## 전달한 것
- **카드 재사용** `POST /v1/ideas/diagnose` 는 고정한 카드 → 공용 캐시 → AI 순으로 본다. 응답 `reused`(pinned·cached·null), 요청 `refresh`(웹 [다시 정리]).
  규칙 `domain/rules/card_reuse`, 유스케이스 `usecases/card_reuse.CardReuse`, 저장소 `adapters/persistence/card_store`, 조립 `build_card_reuse`.
- **고정** 카드를 실은 과제안·생성 요청과 `diagnose/edit` 가 그 사용자 몫으로 카드를 고정한다. 공용 계정은 고정하지 않는다.
- **카드 방식만 0건** `AnalogyReport.legacy_count` → 응답 `analogy_report.card_hint` → 웹 0건 구획의 안내와 [카드 확인하러 가기].
- **변하지 않은 것** `config/problem_card.yaml enabled: false` 면 저장소를 만들지 않고 모든 응답·화면이 종전과 같다. 유추 세션·메모 키(계약 4.1절)는 그대로.

## 남은 것
- 고정 카드를 푸는 화면·명령은 없다([다시 정리] 뒤 그 카드로 진행하면 갈아 끼워진다. 지우려면 `data/cache/problem_cards/pinned/` 의 파일을 지운다 — 파일 이름이 해시라 사용자별로 고를 수 없다).
- 본인 수정 예시가 지시문에 들어간 진단·사용자 항목이 있던 진단은 공용 캐시에 넣지 않는다 — 그 사용자는 확인(고정)하기 전까지 부를 때마다 AI 를 부른다.
