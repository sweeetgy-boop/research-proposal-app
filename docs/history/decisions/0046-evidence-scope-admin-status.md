# ADR 0046 — 근거 범위: 행정 공시·사업 현황·통계는 정책 분류에서 빼기 (2026-10-29, 레인 D)

## 배경
- ADR 0040 은 공사 홈페이지 자료를 다시 분류하면서 행정 공시(270)·사업 현황(70)을 **doc_type policy 그대로** 두고 `raw.doc_class`
  로만 갈랐다. 정책 근거 추천·작성안은 `is_policy_basis` 로 빠졌지만, 섹션 근거 구성(`config/retrieval_mix.yaml`)은 doc_type 만 보므로
  `policy` 를 허용하는 2-가-(3) 경영전략 정합성·3-다 대외위상에는 그대로 들어갔다(측정: 02 자산개발의 2-가-(3) 에 「자산개발 규정」).
- 사용자 지시(2026-10-29): 행정 공시·현황·통계는 정책 분류에서 빼서 2-가-(3)·정책 근거 추천·작성안에는 쓰지 않고, **필요성·현황 섹션
  근거로만** 쓴다. 2-가-(3) 근거는 정책·전략 문서만.
- 측정 중 다른 길도 찾았다: 섹션 필터가 유사과제 보탬 청크(`#overlap`)를 항상 남겨, 2-가-(3) 에 연구용역(「광역철도 수송수요 예측」
  등)이 6건 중 2건에 섞였다.

## 결정
1. **doc_type 을 분류에 맞춘다** (`domain/rules/doc_category.classify_korail`, 적재·`rra db reclassify` 공용, 멱등):
   행정 공시·규정 → `admin_notice`(doc_class admin_record), 사업 현황·소개 → `status_report`(doc_class status),
   통계 → `statistics`(이미 그랬다). 분류 키 이름(admin_record·status)은 그대로 — 저장된 행과 화면 구분 이름이 바뀌지 않는다.
   `DocType` 에 두 값 추가. DB 의 doc_type 열에는 CHECK 가 없어 migration 은 필요 없다(이주는 `rra db reclassify --apply`).
2. **섹션 범위 규칙 두 가지** (`domain/rules/retrieval_mix`, `config/retrieval_mix.yaml`):
   - `only_in`: doc_type → 쓸 수 있는 섹션. 여기 없는 섹션에는 0건 되돌리기(전부)에서도 주지 않는다.
     `admin_notice`·`status_report` → 2-가-(2) 기술적 중요도·2-나 연구목적. `statistics` → 같은 둘 + 3-가 경영혁신.
   - `strict` 섹션: 걸러서 0건이어도 전부로 되돌리지 않고, 유사과제 보탬 청크도 허용 종류일 때만 남긴다. 2-가-(3) 이 `strict`, 허용 `policy` 만.
   - 기술적 중요도·연구목적의 `allow` 에 세 종류 추가. `overlap_exclude`·`retrieval_scope.OVERLAP_EXCLUDED_DOC_TYPES` 에 새 두 종류.
3. **정책 근거 추천·작성안**은 바꾸지 않는다 — `is_policy_basis` 가 doc_type(policy·rnd_notice·audit)과 분류(policy·audit·notice) 둘 다
   보므로 새 doc_type 은 분류 키가 없어도 빠진다. 테스트로 고정.
4. **유사과제 판정**은 그대로 — 후보는 `overlap.yaml candidates` 의 korail_web `procurement`(연구용역)만.

### 필요성·현황 섹션을 이렇게 정한 이유
- 양식(별지 제2호서식)에 "현황" 칸은 따로 없다. 2. 연구의 필요성 아래 2-가-(2) 기술적 중요도가 국내외 동향·기존 기술(현황)의 한계를,
  2-나 연구목적이 적용 대상·범위를 쓴다(`section_checklists.yaml`). 2-가-(1) 정책적 중요도는 제안자 입력 전용(자료 없음), 2-가-(3) 은 정책만.
- 통계는 datago 철도 안전·수송 통계와 같은 doc_type 이고 처음부터 "현황·필요성·기대효과 수치" 용이라 3-가 경영혁신(현황 기준값)을 남겼다.

## 결과
- 운영 DB 사본 점검: korail_web 340행만 바뀜(policy→admin_notice 270, policy→status_report 70), 통계 23행·다른 자료원 0행. 다시 점검 0건.
- 골든셋 6건: 2-가-(3) 의 정책·전략 아닌 청크 5건(3/6) → 0건. 작성안·추천 출처는 6건 모두 전후 같다. 세 종류가 기술적 중요도(3/6)·
  연구목적(1/6)에 근거로 들어감, 논문 최소 2건 유지. 자세히 `docs/eval-2026-10-29-evidence-scope.md`.

## 남은 일
- 운영 DB 적용은 통합 담당: `rra db backup --out data/backups` → `rra db reclassify`(점검 340건 확인) → `rra db reclassify --apply`.
  **새 코드 배포(API 재시작) 뒤에** 적용한다 — 옛 코드의 `DocType` Literal 은 새 값을 몰라 이주된 행을 읽을 때 검증 오류가 난다.
- 이미 만든 run 의 스냅샷 `doc_types` 는 옛 값(policy)이라, 옛 run 을 다시 쓰면 그 run 의 2-가-(3) 은 종전 규칙대로다(새 run 부터 적용).
- 2-가-(3) 섹션 질의(전략 목록 + 아이디어)·`hybrid_search` doc_type 필터는 후속.
