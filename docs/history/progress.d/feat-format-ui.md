# feat/format-ui 진행 메모 (레인 D — HWPX 서식과 화면 편의)

- 17:10 시작. 실물 템플릿·원본 단락 속성 덤프(장·항목·세부 제목이 공백 들여쓰기, 3장 가. 만 내어쓰기,
  특이사항 본문은 제목 복제로 13pt 굵게, 실용화 계획 칸 10pt, 활용계획 목록 칸은 단락 모양 3종, 그림 캡션은
  문서 끝 단락 서식(17pt)을 물려받음) 확인.
- 17:40 `adapters/rendering/hwpx_format.py`(단계별 단락 모양·글자 크기·앞 공백·표 칸·캡션 점검+고침) 연결,
  골든 10건 실물 템플릿 렌더 remaining 0. 실물 닮은 fixture `tests/fixtures/hwpx/proposal_form_like.hwpx`
  (`tests/tools/make_form_like_template.py`) + 테스트 12건.

## 일시 정지 (운영자가 기기 이동) — 현재 상태

완료(백엔드, 테스트 2070 통과·lint·lint-imports 통과):
- 항목 12: hwpx_format(렌더마다 점검·고침, manifest `hwpx_format`), 측정 도구 `tools/hwpx_format_report.py`,
  `docs/eval-2026-10-28-hwpx-format.md`(골든 10/10, 시범 run 19/19), ADR 0033.
- 항목 2: `domain/rules/run_title.py`, run 응답 `title`, 내려받기 `<제목>_v<n>.hwpx`(RFC 5987) — REST·MCP·Streamlit.
- 항목 16: `domain/rules/problem_labels.py` + `web/src/lib/labels.ts`(같은 표, 테스트가 대조), 응답 `label`·`severity_label`·
  `draft_review_skipped_label`, 근거 "확인 필요"(불일치·부분·이미지 판독) + `POST …/evidence-decisions/bulk-approve`,
  선택형 제안값(`choices_confirmed.choices`), usage 섹션 작성 벽시계 + `sections_sum`·`steps`·`total_label`.
- 항목 17: `domain/rules/request_change.py`, `RunManager.request_change_preview/regenerate/run_inputs`,
  `GET …/request`·`POST …/request/preview`·`POST …/regenerate`(routes_format.py), ADR 0034.
- 덤: decide_evidence·apply_rewrite 새 버전에서 그림이 빠지던 것 수정.

반쯤 된 것:
- 웹(web/) — 하위 작업으로 진행 중이었다(제목 머리·run 목록·단계 표시 이동·/runs/:id/idea·precheck·변경 대화 상자·
  제출 전 점검 화면·영문 코드 라벨·vitest·e2e). 이 WIP 커밋에 든 web/ 변경은 미완성일 수 있다 — 재개 때 lint·typecheck·
  vitest·playwright 부터 다시 돌려 확인.

다음:
- 웹 마무리·검사 통과, e2e(단계 이동 → 제출 전 점검 → 마무리, 파일 이름), 캡처.
- 조각 파일: status.d·timeline.d·metrics.d, PR(본문 요약/측정/테스트/프론트엔드 영향/판단).
