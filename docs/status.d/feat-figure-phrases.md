# [B] 그림 칸 글자 — feat/figure-phrases (2026-10-29, 시범 의견 3차 항목 2, 레인 B)

## 현황 행 (docs/status.md 용)
| 2026-10-29 | 그림 칸 글자: 잘라 줄이지 않고 완결 구절로 | 명세·기법·말로 고치기 프롬프트에 칸별 글자 수 상한(`domain/rules/figure_phrases.FIELD_LIMITS`: As-Is 칸 20·해결 방안 14·기법 항목 16 …)과 완결 구절 규칙, 끊긴 구절(조사·연결어미·말줄임·낱말 중간·상한 초과) 거절 → 교정 재요청 1회 → 온전한 낱말 묶음(`salvage`), 9pt 미달이면 Argon 이 상한 −25% 로 칸 글자를 다시 써서(`rewrite_texts`) 밑그림부터 1회 다시 그림(`max_image_redraws` 2 → 1), `shorten_spec`·`clip_text`·`max_shorten` 삭제, 근거 동사의 명사형(…함·…됨·…음)은 출처로 인정 | ADR 0044 |

## 완료
- domain: `rules/figure_phrases.py`(새 — 칸 경로·상한·`TIGHTEN` 0.75, `incomplete_reason`·`phrase_problem`·`problems`·`limits_prompt`·`RULES_PROMPT`·
  `correction_hint`·`complete_window`·`salvage(also=)`·`schema_overlong`), `rules/figures.py`(`normalize_spec_data` 는 자르지 않음, `clip_text` 삭제,
  `TextPool.has_text` 명사형 인정), `rules/figure_fit.py`(`shorten_spec`·`clip_words`·`SHORTEN_LEVELS` 삭제, `shorten_tags` 만), `rules/techniques.py`
  (`_box`·금액·열·묶음 이름 자르지 않음).
- application: `usecases/figures.py` — 명세 프롬프트 `[칸 글자 수 상한]`, `_parse_and_check(final=)`(칸 글자 검사 → 교정 → 대체, 출처 밖 칸 대체),
  `_ask(final_check=)`, `layout()` 글자 줄이기 없음, `draw(pool=, protect=, local_held=)` → 밑그림·그림 9pt 미달이면 `rewrite_texts`(Argon → 오류면 로컬,
  `[그림 글자 다시 쓰기: 종류]`, 답 `{"texts":[{path,value}]}`, 이미 줄인 상한 안이면 부르지 않음) + 이름표 두 글자, `change_spec` 제안자 요청·현재 명세
  글자 제외(`exempt`), `FigureConfig.max_image_redraws` 1·`max_shorten` 삭제. `usecases/figure_techniques.py` — 기법 분석 프롬프트 상한·완결 규칙, 검사·
  교정·대체, `draw(pool=)`. `services/run_manager.py` — [말로 고치기] 거절 안내 2줄(`figure_phrase_incomplete`·`figure_phrase_too_long`)만.
- adapters: 프롬프트 `figures.md`("핵심 구절만 그대로 잘라 쓴다" 삭제 → 상한 안 완결 구절, `[그림 글자 다시 쓰기]` 절), `figure_techniques.md`,
  가짜 모드 그림 답(`adapters/fake/llm.py`) 상한 안으로.
- config: `figures.yaml fit.max_image_redraws: 1`, `max_shorten` 삭제(config_loader·composition 함께).
- 도구: `tools/eval_figure_phrases.py`(시범 run 사본 → Argon 명세 → Nano Banana → OCR → 다시 쓰기·다시 그림 → 실물 양식 HWPX·쪽 미리보기·이전/이번 나란히).

## 측정·테스트
- 실측(골든 run 5건 사본, 그림 13장): 글자 9pt 이상 13/13(최소 9.0·중앙 10.1pt), 본문 폭·높이 상한 13/13, 최종 미완 구절 0(같은 run 이전 그림 9장은 14개),
  다시 그린 그림 1/13, 장당 42~103초(중앙 54초), Gemini 텍스트 25회·그림 14회(레인 카운터). `docs/eval-2026-10-29-figure-phrases.md`.
- pytest 2329 passed·21 skipped(새 테스트: 도메인 36·유스케이스 7+5·어댑터 10, 기존 잘라 줄이기 테스트 4건 삭제·갱신), lint-imports 8 kept, ruff 통과,
  vitest 151, e2e(가짜 모드, 포트 8032) 27 passed.

## 판단
| 항목 | 판단 | 이유 |
|---|---|---|
| 칸별 상한 값 | As-Is 칸 20·해결 방안 14·기법 항목 16·평가 기준 16·일정 단계 14·개념도 줄 20·체계도 12/16·로드맵 12/16/12/18·비교 18 | 밑그림 10pt 로 1~2줄 + pilot2 에서 9pt 밑으로 떨어진 길이(SWOT 24~29자, As-Is 30자)보다 짧게. 상한까지 채워도 밑그림 9.7~10.1pt(테스트로 고정) |
| 다시 그릴 때 상한 | × 0.75 (As-Is 15·해결 방안 10·기법 12) | 지시 예 "−25%". 이미 그 안이면 Argon 을 부르지 않고 "글자를 더 크게" 만 |
| 교정 뒤에도 끊기면 | 그 칸 안의 연속한 온전한 낱말 묶음(끝 낱말 조사·어미만 덜 수 있음), 끝 낱말을 지키는 묶음 먼저, 없으면 빼도 되는 칸만 빼고 아니면 명세 거절 | "규칙으로, 완결될 때만, 낱말은 자르지 않는다" |
| 다시 쓰기 실패 칸 | 원래 글자의 상한 안 낱말 묶음, 없으면 원래 글자 그대로 | 다시 쓰기는 글자 키우기용 — 실패가 그림을 없애면 안 된다 |
| 명사형(…함·…됨·…음) 출처 인정 | 근거에 그 동사 꼴(못하…·남는…·확보되…)이 있을 때만 | "명사형으로 끝내라" 와 출처 낱말 검사가 부딪혀 그림 1장이 빠졌다(실측). 새 낱말('잔존·미추적')은 여전히 거절 |
| 미완 판정의 모호한 끝 글자(의·과·로·이·가·도·만) | 명사 목록(회의·효과·선로…) + 근거에서 같은 줄기가 다른 조사로도 쓰였을 때만 조사로 | '효과·결과·선로·평가' 같은 명사를 끊김으로 보지 않게 |
| 낱말 중간 끊김 | 끝 낱말이 근거에 그대로·조사 붙은 꼴로 없고 더 긴 낱말의 앞부분으로만 있을 때 | 근거 대조로만 알 수 있다. '철도 수송'(근거엔 '수송수요'만)도 끊김으로 본다 — 교정 재요청 |
| 그림 자동 검증 | 하지 않음(ADR 0029 유지) | "반영 SARIMA 기법" 같은 어색한 구절은 규칙으로 못 잡는다 — 제안자 확인 |
| 제안자 글자 | [글자 고치기]는 다시 쓰지 않고, [말로 고치기]는 요청·현재 명세 글자를 규칙에서 빼고 다시 그릴 때도 요청 글자 칸은 그대로 | 제안자가 정한 글자를 AI 가 바꾸지 않는다 |
| `Figure.fit.shortened` | 이름 그대로, 뜻은 "다시 쓴 칸 수" | API·화면 스키마를 바꾸지 않으려고(openapi 공유 파일) |
| run_manager [다시 만들기](regenerate) | pool 없이 draw — 다시 쓰기 출처는 현재 그림 글자만 | run_manager 는 레인 C 영역 — 건드리지 않음 |
| 로컬 모델 | 측정에서 부르지 않음(가짜 자리) | 시범 운영 중. 코드의 순서는 Argon → 오류면 로컬 그대로 |

## 프론트엔드 영향
- 없음. API 필드 변경 없음(`fit.shortened` 의 뜻만 "다시 쓴 칸 수"). 새 [말로 고치기] 거절 사유 코드 2개는 안내 문장(run_manager `_EDIT_REJECT_HINTS`)으로만 나간다.

## 통합 담당 할 일
- docs/status.md 에 위 행, timeline 조각(`docs/history/timeline.d/2026-10-29-feat-figure-phrases.md`)·metrics 조각 옮기기, PR #98.
- 레인 C(그림 백그라운드 단계)와 합칠 때: `MakeFigures.draw` 에 `pool=`·`local_held=` 인자가 생겼다 — `build_all`·기법 경로는 이미 넘긴다.
  run_manager 의 [다시 만들기](`figures.draw(fig)`)도 `pool=self.figures.pool(...)` 을 넘기면 다시 쓰기가 초안 낱말까지 쓸 수 있다(선택).
- 6번 측정(골든 10건)에서 그림 글자 9pt·다시 그림 수·미완 구절 0 을 함께 보면 된다(`tools/eval_figure_phrases.py` 의 `phrases.problems` 판정 재사용 가능).
