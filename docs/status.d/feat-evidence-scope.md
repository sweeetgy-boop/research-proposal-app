## 근거 범위 — 행정 공시·사업 현황·통계는 정책 분류에서 빼기 (feat/evidence-scope, 2026-10-29, 레인 D, ADR 0046)

- 분류: `domain/rules/doc_category.classify_korail` 이 행정 공시 → `admin_notice`, 사업 현황 → `status_report`, 통계 → `statistics`
  로 doc_type 을 바꾼다(적재 normalize·`rra db reclassify` 공용, 멱등). `DocType` 에 두 값. 분류 키(raw.doc_class admin_record·status)는 그대로.
  `rra db reclassify` 집계에 `transitions`("policy→admin_notice" 행 수) — CLI "자료 종류 변경" 줄.
- 범위: `RetrievalMix.only_in`(doc_type → 쓸 수 있는 섹션, 0건 되돌리기에서도 적용)·`SectionMix.strict`(되돌리기 없음, 유사과제 보탬
  청크도 허용 종류만). `config/retrieval_mix.yaml`: 2-가-(3) `strategy_alignment` = `{allow: [policy], strict: true}`, 세 종류는
  `tech_importance`·`objective`(통계는 `expected_management` 도)에서만, `overlap_exclude` 에 새 두 종류. 정책 근거 추천·작성안
  (`is_policy_basis`)·유사과제 후보(`overlap.yaml candidates`)는 코드 변경 없이 새 종류를 뺀다(테스트로 고정).
- 측정 `docs/eval-2026-10-29-evidence-scope.md`(운영 DB 사본, 골든셋 6건, LLM 0회): 2-가-(3) 의 정책·전략 아닌 청크 5건(3/6) → 0건,
  작성안·추천 출처 6/6 전후 같음, 기술적 중요도 논문 최소 2 유지.
- **통합 담당이 할 일(운영 DB, 측정 전)**: 아래 순서. 점검 340건(policy→admin_notice 270, policy→status_report 70)이 아니면 멈춘다.
  ```
  cd /Users/chan/projects/research-proposal-app
  PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli db backup --out data/backups
  PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli db reclassify            # 점검: 바뀔 행 340건
  PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli db reclassify --apply    # 적용 → 다시 점검하면 0건
  ```
  재색인 불필요(검색 때마다 DB 에서 doc_type 을 읽는다). **순서 주의: 새 코드로 API 를 재시작(배포)한 뒤에 적용한다** — 옛 코드의
  `DocType`(Literal)은 `admin_notice`·`status_report` 를 모르므로, 이주된 행을 읽는 순간 `Document` 검증 오류가 난다. 반대(새 코드 +
  이주 전 DB)는 안전하다(분류는 그 자리에서 판정, 다만 2-가-(3) 에는 이주 전까지 행정 공시가 policy 로 들어갈 수 있다).
  측정 API(RRA_DATA_DIR 이 운영 DB 인 것)도 새 코드로 띄운다.
- 프론트엔드 영향: 없음(API 필드·스키마 변경 없음, docs/openapi.json 그대로). 새 알림 코드 없음.

### 판단
| 항목 | 판단 | 이유 |
|---|---|---|
| doc_type 이름 | `admin_notice`·`status_report`(통계는 기존 `statistics`) | 지시 예시와 같음. 분류 키(admin_record·status)는 저장된 행·화면 이름 호환을 위해 그대로 |
| 필요성·현황 섹션 | 2-가-(2) 기술적 중요도, 2-나 연구목적 | 양식에 "현황" 칸이 없고, 2. 필요성 아래 기술적 중요도가 동향·기존 기술 한계(현황), 연구목적이 대상·범위를 쓴다. 2-가-(1) 은 입력 전용 |
| 통계의 3-가 경영혁신 | 남김 | datago 통계와 같은 doc_type, 처음부터 "현황·필요성·기대효과 수치" 용(기대효과의 현황 기준값). 지시의 "필요성·현황만" 보다 한 칸 넓음 — 빼려면 `only_in.statistics` 에서 지우면 된다 |
| 2-가-(3) 되돌리기 | 없음(strict) | 0건이면 전부로 되돌리던 규칙 때문에 정책 아닌 자료가 들어갈 수 있었다. 2-가-(3) 은 선택형이고 근거 필수 섹션이 아니라 빈 [자료] 도 안전 |
| 유사과제 보탬 청크 | strict 섹션에서는 허용 종류만 | 측정에서 2-가-(3) 에 연구용역이 섞인 실제 경로(6건 중 2건). 다른 섹션은 종전대로 항상 남김 |
| 기술적 중요도에 세 종류 허용 | 허용(지시대로) | 측정 3/6 건에서 1~2청크가 들어와 논문이 4~5 → 3 으로 줄었다(최소 2 보장 유지). 근거 필수 섹션이라 무관한 규정은 관련도 하한·reranker 가 거른다. 줄어든 논문 인용은 통합 측정에서 확인 필요 |
| 옛 run 스냅샷 | 손대지 않음 | 스냅샷 `doc_types` 는 생성 때 값 — 옛 run 을 다시 쓰면 그 run 은 종전 규칙. 새 run 부터 적용 |
| 정책 작성안 검색 상한 | 이번 범위 밖 | korail_web 묶음은 방향당 12청크 안에서 보도·이미지 판독·연구용역과 자리를 다퉈 공사 정책 구간이 0~3건. `hybrid_search` doc_type 필터(포트 변경)는 후속 |
