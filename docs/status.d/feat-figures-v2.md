# 그림 v2 — 기본 그림 정리·As-Is/To-Be·디자인 개선·분석 기법 추천 — feat/figures-v2 (2026-10-28, 레인 C)

## 현황 행 (docs/status.md 용)
| 2026-10-28 | [G] 그림 v2 (10·3·4·11) | 기본 그림 = As-Is/To-Be 1(+ 검증 수치 그래프·일정표) + 분석 기법 추천 0~2, 최대 4장. 개념도·체계도·로드맵은 [다른 그림 추가]에서만. 기법 20종(`config/figures/techniques.yaml`)을 Argon(실패면 로컬)이 고르고 제안 내용으로 분석 → Nano Banana. 추천 배지·이유, [넣기 확정]·[필요 없음](접힘·다시 넣기)·[다른 기법으로 바꾸기], 빈 결과도 사유 + [다시 시도], 제출 전 점검 "결정 전 추천 그림". 그림 프롬프트 "새로 디자인"·비율 자동 | ADR 0033, architecture §4.20 v2, `docs/eval-2026-10-28-figures-v2.md` |

## 완료
- 도메인: `AsIsToBeSpec`·`TechniqueSpec`·`FigureRecommendation`·`TechniqueOutcome`, `RunState.figure_techniques`, `MAX_BOX` 30;
  규칙 `rules/techniques.py`(목록·고르기·종류별 분석 규칙·출처), `rules/figures`(choose_default v2·technique_slots·choose_aspect·인포그래픽
  image_prompt·As-Is/To-Be 검사·다듬기·추천 결정 diff·undecided).
- 유스케이스 `figure_techniques.TechniqueSteps`(MakeFigures 가 물려받음), RunManager `_figures_step`(기본 + 추천 동시)·`retry_techniques`·
  `figure_action` accept·dismiss·restore·swap·`add_figure(technique=)`, 제출 전 점검 `figures_undecided`.
- 어댑터: 밑그림 SVG 2종(As-Is/To-Be 점선·빗금 / 실선·점, 기법 묶음 카드·평가 표·금액 배지), 렌더러 `svg(aspect=)`, 프롬프트
  `figure_techniques.md`, `figures.md` 상자 30자·As-Is/To-Be 규칙, 가짜 모드 답(As-Is/To-Be·SWOT·비용-편익·퓨).
- REST: 그림 목록 `techniques`·`technique_catalog`, 그림 필드 `technique`·`family_label`·`prelim_note`·`provenance`·`recommendation`,
  `POST /v1/runs/{id}/figures/techniques`, `FigureActionIn.action` accept·dismiss·restore·swap + `technique`, `FigureAddIn.kind`
  as_is_to_be·technique + `technique`.
- 웹: `features/figures/TechniqueCard.tsx`(추천 패널·항목 출처·바꾸기 대화상자·접힌 추천·추천 결과), `api.ts`, `api/types-figures.ts`,
  [다른 그림 추가] 8종·기법 선택, 버전 비교 라벨 4개.
- 실호출: 이미지 15·텍스트 3 — 기존/v2 나란히 6종 + Argon 추천 1회(퓨·SWOT), 장당 27~35초.

## 남은 일
- 골든셋에서 기법 추천률·해당 없음 비율·제안자 결정 비율 측정(`rra eval` 열 추가).
- Nano Banana 큰 글씨 글자 뭉개짐(2회차 As-Is/To-Be 2곳) — 확인 전·제출 전 점검으로 잡는다.
- 통합 담당: `rra api schema` → openapi.json, `npm run gen:api` 뒤 `types-figures.ts` 와 겹치는 타입 정리, CLAUDE.md [G] 줄에 v2 한 줄.
