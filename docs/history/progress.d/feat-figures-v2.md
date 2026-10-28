# feat/figures-v2 진행 메모 (레인 C — 그림 v2)

- 2026-10-28 시작. origin/main 1d1dc17 기준 worktree. 범위: [10] 기본 그림 정리, [3] As-Is/To-Be, [4] 그림 디자인 개선, [11] 분석 기법 추천.
- 계획: domain(명세 2종 `as_is_to_be`·`technique`, 기법 규칙) → usecase(기본 세트·기법 추천 Argon → 로컬) → RunManager 동작
  (accept·dismiss·restore·swap) → 어댑터(SVG 2종·자동 비율) → REST → 웹(추천 카드·기법 바꾸기) → 실호출 샘플 → 문서 조각.
- 판단: "연구배경 및 필요성" 칸은 양식에 없다 → As-Is/To-Be 는 `objective`(2-나 연구목적), 목적이 비면 `tech_importance`(2-가-(2)).
  기법 목록은 `config/figures/techniques.yaml`(같은 이름의 파일 `config/figures.yaml` 과 경로 충돌 없음).
