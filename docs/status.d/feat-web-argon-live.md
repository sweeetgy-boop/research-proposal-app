# 레인 D — feat/web-argon-live (2026-10-28, [3]·[4] 화면) 전달 사항

## 전달한 것
- **[3] 로컬 작성 배지** 초안 보기 섹션 머리(모든 버전 탭)·직접 수정 섹션 제목 옆에 `local_sections` 섹션만 "로컬 작성"
  (title·sr-only: "Argon 작성 실패(오류|호출 한도|일일 상한|형식 오류) 뒤 로컬 모델이 작성", `writers[key].reason`). 옛 run 의
  "대체 작성"(fallback_sections)은 그대로(`features/draft/WriterBadges.tsx` 로 공용화, 직접 수정에도 표시).
  알림 영역에 `local_check.enabled` 면 "근거 대조(로컬) 불일치 N건"(mismatches 와 `local_evidence_mismatch` 알림 수 중 큰 값)·
  대조 건너뛴 섹션, 알림 항목 중 `local_evidence_mismatch` 에 같은 라벨. run 머리 칩(outline): `writer` gemini → "Argon 작성(· 로컬 N개 섹션)",
  local → "로컬 작성".
- **[4] 실시간 검색** ② 유사과제 표·관련 연구·초안 인용 문서·근거 패널의 `live: true` 항목에 "실시간 검색" 배지. ② 에
  `features/live/LiveSearchPanel.tsx`(전체 상태 완료/일부 완료/검색 중/꺼짐, 표 "자료원별 상태": ScienceON·NTIS·OpenAlex 결과 수·
  상태 완료/시간 초과/IP 차단/오류/꺼짐·걸린 시간, 자료원 `notice` 는 UntrustedText, 검색어 ko/en 은 `<details>` 접힘,
  pending 이면 polite 상태 줄 "실시간 검색 중…").
- **타입** `api/types.ts` 에 SectionWriter·LocalCheck·LiveSearch·LiveSearchSource, 기존 응답에 선택 필드(`writers`·`local_sections`·
  `local_check`·`writer`·`live_search`·`live`). 라벨은 `lib/writer.ts`·`lib/live.ts`.
- **테스트** vitest 3파일 10건(LiveSearchPanel 상태 라벨 전부·notice·검색어·pending/off, Precheck 배지 있음/없음, Draft·Edit 로컬 작성
  사유 4종·대체 작성·대조 건수·칩·인용·근거 패널, axe 0) — 전체 86 통과. e2e `e2e/argon-live.spec.ts` 2건(page.route 로 필드 주입,
  ip_blocked+notice·timeout 포함 / 필드 없는 옛 흐름) — 전체 17 통과·2 skip. 캡처 `docs/history/screens/2026-10-28-argon-live-0{1,2}-*.png`.

## 자동 결정
- 문장 origin 배지(llm → "로컬 작성")와 섹션 배지 문구가 같다(지시대로). 섹션 배지는 제목 안(h3), 문장 배지는 문장 아래라 구분된다.
- `local_check.enabled=false` 면 아무것도 표시하지 않는다. 자료원 상태 off 는 결과 수·시간을 "—".
- run 화면(진행 등)에는 live_search 요약을 그리지 않았다(타입만). 필요하면 LiveSearchPanel 재사용.

## 남은 것
- 백엔드 레인 B(feat/argon-first)·C(feat/live-search) 응답이 확정되면 fixture 를 실응답으로 바꾸고 e2e 의 page.route 주입을 걷어낸다.
