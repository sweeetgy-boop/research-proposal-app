# [D] HWPX 서식과 화면 편의 — feat/format-ui (2026-10-28)

## 현황 행 (docs/status.md 용)
| 2026-10-28 | [D] HWPX 서식·제목·제출 전 점검·단계 이동 | 12 HWPX 단계별 서식 점검·고침(`adapters/rendering/hwpx_format.py`, manifest `hwpx_format`) · 2 과제 제목 머리·목록·`<제목>_v<n>.hwpx`(RFC 5987) · 16 알림 한국어 설명 표(`domain/rules/problem_labels.py` = `web/src/lib/labels.ts`), 근거 확인 필요(불일치·부분·이미지 판독)+일괄 승인, 선택형 제안값 확정, 섹션 작성 벽시계 · 17 단계 표시 이동, `/runs/:id/idea`·`/precheck`, 입력 변경 → 관련 섹션만/전체 다시 쓰기(새 버전) | ADR 0033·0034, `docs/eval-2026-10-28-hwpx-format.md` |

## 완료
- 백엔드: `hwpx_format.py`(단계 표 LEVELS, header 모양 복제·재사용, 점검 → 고침 → 재점검, 멱등), `expand_paragraphs` 앞 공백 제거,
  `domain/rules/run_title.py`·`problem_labels.py`·`request_change.py`, `evidence.evidence_attention/bulk_approvals`,
  `usage.step_durations`(sections = 벽시계, sections_sum = 합), `RunManager.run_title/run_inputs/request_change_preview/regenerate/
  bulk_approve_evidence`, 포트 `RunStorePort.save_request`, REST `entrypoints/api/routes_format.py`(+ `schemas_format.py`),
  run 응답 `title`, problems `label`·`severity_label`, flow `draft_review_skipped_label`, usage `steps`·`total_label`,
  내려받기 파일 이름(REST·MCP·Streamlit), manifest 허용 키 `hwpx_format`.
- 덤: 근거 판단·AI 다시 쓰기 새 버전에서 그림이 빠지던 것 수정(`figures=list(current.figures)`).
- 측정: 골든 10/10, 시범 run 19/19 남은 서식 불일치 0 (`tools/hwpx_format_report.py`).
- 웹: run 머리 과제 제목(두 줄 말줄임·전체는 title/초점)·run 번호 복사, run 목록 제목·만든 때, 단계 표시(run 안에서는
  RunLayout 이 그림) 눌러 이동·닿지 않은 단계 이유(툴팁·aria-describedby), `/runs/:id/idea`·`/runs/:id/precheck`
  (`RunIdea`·`RunPrecheck`), 변경 대화 상자 `features/regenerate/ChangeDialog` + `useRunChangeSave`, 제출 전 점검 한국어 설명·
  [근거 일괄 승인]·`ChoiceConfirm`([제안값 그대로 확정]/[직접 고르기])·사용 기록 줄바꿈·섹션 벽시계, 내려받기 filename* 이름,
  영문 코드 화면 문구 교체(ReviewPanel·WriterBadges·DifferentiationPanel·RecommendationCards·Draft·ComparisonTable 각 1줄).
  vitest 99, e2e 17(+3 캡처 skip), 캡처 `docs/history/screens/2026-10-28-format-ui-*.png`.

## 판단 (기록)
- 서식은 템플릿을 다시 만들지 않고 렌더 결과에서 맞춘다(운영기 템플릿 그대로 적용). 내어쓰기 폭은 어림값 — 한/글에서 1건 확인 필요.
- 활용계획 목록 칸은 "칸의 원래 모양 중 가장 많이 쓴 것"(-1300)으로 통일, 실용화 계획 칸은 칸 첫 단락 모양 + ○ 내어쓰기(줄 간격 110% 유지).
- 안내(※) 줄도 공백 대신 여백으로(글자 크기는 양식 그대로). 제안자 표·서식 머리·맺음말은 점검 밖.
- 입력 변경 다시 쓰기는 근거를 다시 검색하지 않는다(보안 A 대조 집합 유지), 설계도도 다시 만들지 않는다. 동기 호출(섹션 많으면 1분 안팎).
- 제목은 현재 버전 1-가 문장 → 없으면 가제 → 없으면 "제목 미정"(화면)/"연구과제제안서"(파일).
- 화면 "확인 필요"에서 판단이 끝난 문장(모든 근거에 판단)은 뺀다.

## 남은 일
- 운영기 한컴오피스에서 HWPX 1건 열어 둘째 줄 정렬 확인(어긋나면 `LEVELS` hang 값만).
- 실제 Argon 으로 관련 섹션 다시 쓰기 시간 측정.
