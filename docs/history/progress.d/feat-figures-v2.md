# feat/figures-v2 진행 메모 (레인 C — 그림 v2)

- 2026-10-28 시작. origin/main 1d1dc17 기준 worktree. 범위: [10] 기본 그림 정리, [3] As-Is/To-Be, [4] 그림 디자인 개선, [11] 분석 기법 추천.
- 계획: domain(명세 2종 `as_is_to_be`·`technique`, 기법 규칙) → usecase(기본 세트·기법 추천 Argon → 로컬) → RunManager 동작
  (accept·dismiss·restore·swap) → 어댑터(SVG 2종·자동 비율) → REST → 웹(추천 카드·기법 바꾸기) → 실호출 샘플 → 문서 조각.
- 판단: "연구배경 및 필요성" 칸은 양식에 없다 → As-Is/To-Be 는 `objective`(2-나 연구목적), 목적이 비면 `tech_importance`(2-가-(2)).
  기법 목록은 `config/figures/techniques.yaml`(같은 이름의 파일 `config/figures.yaml` 과 경로 충돌 없음).
- 17:40 일시 정지(장비 이동). 완료: 백엔드 전부(명세 as_is_to_be·technique, techniques.yaml 20종, 기법 고르기·분석 Argon→로컬,
  카드 동작 accept·dismiss·restore·swap, REST `/figures/techniques`, 제출 전 점검 figures_undecided, 가짜 모드 답, 밑그림 2종,
  인포그래픽 프롬프트·자동 비율), 백엔드 테스트 +34(전체 통과), 웹 카드 TechniqueCard·api·types-figures·AddFigureDialog(8종·기법 선택·추천 결과).
  실호출 샘플 before/after 6종 + Argon 추천 1회(pugh·swot) → docs/history/screens/2026-10-28-figures-v2-*.jpg.
- 실호출 누계: 이미지 14/30(장당 27~35초), Gemini 텍스트 3/80 (laneC 카운터).
- 다음: 웹 vitest 3건 실패 수정(onApplied 대기 — mock 응답 모양), e2e figures.spec 갱신(As-Is/To-Be·추천 넣기/빼기), as_is_to_be
  제목 규칙 반영 뒤 샘플 1장 다시(+1 이미지), ruff E501 2건, ADR 0033·status·timeline·metrics 조각, PR.
- 재개 뒤: vitest 3건(그림 id 가 인코딩된 주소) 고침, e2e figures.spec 갱신·추가(전체 18 통과·2 건너뜀), 제목 규칙 반영 뒤
  As-Is/To-Be 1장 다시(제목 없음, 글자 뭉개짐 2곳 — eval 에 기록), ADR 0033·eval 문서·architecture §4.20 v2·조각 파일, PR.
  실호출 최종: 이미지 15/30, 텍스트 3/80.
