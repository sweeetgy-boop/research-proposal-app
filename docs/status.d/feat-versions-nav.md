# [D] 상태 표시·아래 이동 막대·"run" 표기 — feat/versions-nav (2026-10-28 밤, 레인 D)

## 현황 행 (docs/status.md 용)
| 2026-10-28 | [D] 상태 표시는 버전 없음·아래 이동 막대·쉬운 말 | 21 그림 확인·추천 그림 결정·근거 승인/제외·선택형 확정은 현재 버전의 표시 파일(`versions/marks_vN.json`)에 — 버전 수 그대로, 읽을 때 합침(화면·점검·마무리), "변경 n건"과 "확인 n건" 분리, 예전 상태만 바뀐 버전은 "확인 기록"으로 접기, 실제로 바뀐 섹션만·그림 이름·v1 실제 작성자 배지 · 22 단계 화면 아래 이동 막대(이전·다음·남은 일, `--stepnav-h`), 초안 보기 [수정 없이 최종 검토로], ⑤ 최종 검토·브리핑 대기 경과 초+[취소] · 25 화면 "run" → 제안서·작성 번호·내 제안서 | ADR 0042 |

## 완료
- 백엔드: `domain/models/marks.py`(VersionMarks·StatusMark·FigureMark), `domain/rules/status_marks.py`, `domain/rules/version_history.py`
  (version_rows·figure_name·note_label·writer_label), `change_count` STATUS_TYPES·`confirmations`·`confirm_items`, 포트
  `RunStorePort.save_marks/load_marks`(파일·가짜 2곳), `services/status_marks_mixin.py`(_version·_save_figure_mark·_save_evidence_marks·
  _log_mark·record_mark·version_history·cancel_final_review), RunManager 연결(읽기 합치기·figure_action/decide_evidence/bulk_approve/
  confirm/revert, 새 그림 메모 "그림 다시 그리기 — 이름", 최종 검토 CancelledError → 검토 전 상태), REST `GET …/versions`(status_only·
  changed_figures·marks·confirmations·description·v1 origin_label), `GET …/changes`(confirmations·confirm_items),
  `POST …/final-review/cancel`, `POST /v1/precheck/brief` 를 `cancel_on_disconnect` 로.
- 웹: `components/StepNavBar.tsx`, `features/stepnav/RunStepBar.tsx`, `lib/runSteps.ts`(FLOW_STEPS 한 표·runStepNeighbors·remainingWork),
  RunLayout(막대·작성 번호·작성 상태·"Argon 작성(일부 로컬)"), Layout("내 제안서", 본문 아래 여백 `--stepnav-h`), Idea·Precheck(게이트만)·
  Brief·Clarify 에 막대, Draft [수정 없이 최종 검토로](`features/versions/SkipEditButton.tsx`), Versions(확인 기록 접기·설명·바뀐 그림·
  확인 n건, `features/versions/fold.ts`), ChangeCount "변경 n건 · 확인 n건", FinalReview·Brief 대기(AiWaiting·[취소]), Edit 저장 막대
  `bottom: var(--stepnav-h)`, 확인 toast "확인 표시를 저장했습니다 (새 버전 없음)", 화면 "run" 문구 교체.
- 테스트: pytest 새 13건(`tests/application/test_status_marks.py` 7, `tests/entrypoints/test_versions_nav_api.py` 3, 기존 8건 갱신),
  vitest 새 6건(`features/stepnav/StepNav.test.tsx`), e2e `web/e2e/versions-nav.spec.ts` 2건 + `helpers.expectNoRunWord`.

## 판단
| 항목 | 판단 |
|---|---|
| 저장 방식 | 버전 파일을 고치지 않고 버전마다 표시 파일(marks_vN)에 쌓아 읽을 때 합친다. 버전 파일은 만든 뒤 그대로(알림 수 갱신만 예전대로). |
| 상태 표시 뒤 run 상태 | drafted·final_reviewed 를 editing 으로 바꾸지 않는다 — 최종 검토 뒤 그림 확인은 "최종 검토 이후 수정" 이 아니다. |
| 추천 그림 [다시 넣기] | [필요 없음]의 되돌림이라 상태 표시로 본다. 추천이 아닌 그림의 [빼기]·[넣기] 는 제안서에 들어갈 그림이 바뀌므로 새 버전(그대로). |
| 근거 판단 | 승인·제외만 상태 표시, 교체는 본문 근거 id 가 바뀌므로 새 버전. |
| 그림이 바뀐 뒤 표시 | 표시한 그림 해시와 지금 그림이 다르면 그 표시는 적용하지 않는다(다시 확인). |
| 복원 | 되돌린 버전의 그림 중 지금과 같은 그림(id·해시·명세)은 지금 표시를 이어받는다. |
| 선택형 확정 | 예전처럼 confirmed.json 에 저장 + 현재 버전 확인 기록에 한 줄. "확인 n건" 에 들어간다. |
| "변경 n건" 기준 | 기준 버전은 표시 없는 버전 파일, 현재는 합친 것 — 기준 버전 위에서 한 확인도 "확인 n건" 으로 센다. |
| 그림 이름 | 레인 C `display_name` 이 있으면 그것, 없으면 종류 이름(As-Is/To-Be 는 "현재·개선 비교 그림")·"분석 기법 그림 – <기법 이름>". 기법 이름 중 영어가 섞인 "퓨 매트릭스(Pugh)" 는 레인 C 카탈로그 몫. |
| v1 배지 | writer 기록이 없는 예전 run 은 "로컬 생성" 그대로(그때는 로컬 작성). |
| 이전 단계 단추 문구 | "[← 이전 단계: ○○]" — 어느 단계로 가는지 보이게 이름을 붙였다. |
| 남은 일 | 제출 전 점검의 실패 항목(최대 3개 + "외 n건"), ③ 이후만. 막지 않고, 다음으로 갈 때 (작성 번호·단계별) 한 번 toast. |
| ① 다음 단추 | 상세 입력에서는 막대 [다음: 유사과제 확인] 이 폼을 제출(폼 안 단추는 숨김, IdeaForm `hideSubmit`). 간편 입력은 네 칸으로 나눈 뒤(또는 이미 유사과제 결과가 있으면 이동). |
| ③ 보강 질문 | 막대 [다음: 초안 생성] = 폼 제출(답하고 생성). [건너뛰고 생성] 은 화면 안에 그대로. |
| 최종 검토 [취소] | 백그라운드 작업을 취소하고 끝날 때까지 기다린 뒤 상태를 돌려준다. 다른 프로세스가 돌리는 검토는 409. |
| "run" 표기 | 화면 글자만 바꿨다(내부 코드·API·주석은 그대로). 서버 오류 문구 "run 을 찾을 수 없습니다" 는 정상 흐름에 보이지 않아 두었다. |

## 남은 일
- 레인 C 병합 뒤 `figure_name` 이 `display_name` 을 쓰는지 한 번 확인(getattr 로 이미 우선).
- 레인 B 로컬 검토 [무시] 는 `RunManager.record_mark(user, run_id, "suggestion_ignore", label=…)` 로 기록하면 버전 목록 확인 기록에 나온다.
