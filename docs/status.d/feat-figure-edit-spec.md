# [2] 그림 [말로 고치기] = 명세 변경 → 밑그림 → 새로 그림 — feat/figure-edit-spec (2026-10-28)

## 현황 행 (docs/status.md 용)
| 2026-10-28 | [2] 그림 말로 고치기·명세 Argon | 요청 → Argon(실패면 로컬) 명세 변경 `{spec, style, summary}` → 생성과 같은 검사(pool + 현재 명세 + 요청 글자) → 새 밑그림 → Nano Banana `generate`. 현재 그림·편집 호출 안 씀. 모양만이면 명세 그대로 + 모양 요청. 위반·변경 없음 409(사유 + 안내), 버전 없음. 카드 "바뀐 내용"(`Figure.last_change`), 초안 명세도 Argon 먼저(`Figure.spec_model`) | ADR 0030, architecture §4.20, `docs/eval-2026-10-28-figure-edit.md` |

## 완료
- 유스케이스 `MakeFigures._ask`(Argon → 로컬 → 대체, 모델마다 교정 1회), `edit_by_words`·`change_spec`, `draw(style=)`; 규칙 `with_texts`·
  `spec_change_summary`·`image_prompt(style=)`(편집 프롬프트 `edit_prompt` 삭제); 모델 `FigureChange`·`Figure.spec_model/last_change`; 프롬프트
  `figure_edit.md`(포트 `figure_edit()`); RunManager words·texts 가 `last_change` 기록, 거절 사유 안내; 조립 `build_figures(argon=)`; 가짜 모드 `[그림 수정:` 분기.
- 웹 카드 "바뀐 내용"(목록, UntrustedText, kind=style 이면 "(모양만)"), [말로 고치기] 안내문 변경. axe 0.
- 실측: 6회 한글 글자 변형 합계 1(오전 편집 1회 3·2), 31~41초. OCR 같은 잣대 오전 4·3 → 새 경로 0~1.

## 남은 일
- mlx 를 띄운 상태에서 로컬 대체 명세 변경 품질 측정, 골든셋 그림 단계(Argon 명세)의 그림 수·시간.
- [글자 고치기]로 바꾼 개념도 상자 이름은 다음 [말로 고치기]에서 템플릿 라벨로 돌아간다(`repair_spec` 규칙).
