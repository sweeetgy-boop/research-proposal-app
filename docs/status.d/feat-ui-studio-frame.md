# [UI] 레인 1 — feat/ui-studio-login(#102) · feat/ui-studio-frame (2026-10-29) 전달 사항

## 바뀐 것 (화면·메뉴·문구)
- **로그인 페이지 없앰 → 화면 안 로그인** (#102): `features/auth/LoginCard`(홈 오른쪽 열용)·`LoginDialog`/`LoginDialogProvider`(앱 전체 창 하나)·
  `useRequireLogin()`·`loginContext.useLoginDialog()`. 로그인 전 보호 화면(`/new`·`/runs`·제안서 주소·자료 검색·자료 현황)은 **주소를 그대로 두고**
  그 자리에 로그인 창 → 로그인하면 같은 화면. 창을 닫으면 "로그인이 필요한 화면입니다" + [로그인 창 열기]. 옛 `/login` → 홈 + 창.
  로그아웃 → 같은 홈의 로그인 전 상태. 탭·입력 id 는 `useId` 접두어(카드와 창이 한 화면에 있어도 겹치지 않음).
- **화면 틀**: 위쪽 메뉴 → 왼쪽 사이드바(`components/frame/Sidebar`, 폭 13rem, 흰 배경). "R" 글자 타일 + "Research Studio", WORKSPACE 작은 대문자 라벨,
  메뉴 연구 작업실(`/`)·새 제안서(`/new`)·내 제안서(`/runs`, 건수 = runs API 50건 목록 길이, 로그인 뒤에만 부름)·작성 가이드(`/guide`, 화면은 레인 2),
  선택 메뉴는 연보라 배경 + 남보라 글자 + `aria-current="page"`. 아래쪽: 자료 현황(작은 메뉴), "제안서는 연구원 서버에 저장됩니다.",
  공용 계정이면 "공용 계정의 제안서는 함께 쓰는 사람에게 보입니다.", 사용자 칸(로그인 종류 직원/공용 계정/관리자 · 로그아웃 또는 로그인 전 · 로그인), 해/달 테마 단추.
- **위쪽 막대**(`components/frame/TopBar`): 좁은 화면 메뉴 단추, 집 아이콘 + 경로 표시 `Research Studio › 연구 작업실 › …`(`frame/crumbs.ts` 순수 함수 —
  새 제안서는 단계 이름, 제안서 안은 제목 › ①~⑥ 화면 이름; 제목은 RunLayout 과 같은 캐시), 통합 검색 자리(`SearchSlot` — 레인 3 GlobalSearch 전까지
  자료 검색으로 보냄, 로그인 전이면 창), 물음표 → 작성 가이드. 좁은 화면에서는 경로의 마지막 칸만.
- **좁은 화면(< 1024px)**: 사이드바 대신 접는 메뉴(`frame/MobileMenu`, 네이티브 `<dialog>` — 포커스 가두기·Esc 닫기·바깥 클릭·메뉴 누르면 닫힘).
- 아래 이동 막대(StepNavBar)는 넓은 화면에서 사이드바 오른쪽부터(`lg:left-52`), `--stepnav-h` 그대로. ①~③ 단계 표시는 위쪽 막대 아래.
- 앱 이름: 브라우저 탭 제목(index.html)·사이드바·경로 첫 칸 "Research Studio". 예전 "자료 검색"·"자료원 상태" 위쪽 메뉴는 없앰(자료 검색은 통합 검색 → 전체 결과, 자료 현황은 사이드바 아래 작은 메뉴).
- 임시 홈 `App.tsx TempHome`(로그인 전 카드, 로그인 뒤 `/new`) — 레인 2 Home 이 대체.

## 판단
| 항목 | 판단 | 이유 |
|---|---|---|
| 로그인 뒤 이어 가기 | 주소를 바꾸지 않고 그 자리에서 창 | 로그인 뒤 같은 주소를 그리기만 하면 원래 가려던 곳이 맞는다. 리다이렉트·state 전달이 없어 새로고침에도 안전 |
| 옛 /login 주소 | 홈 + 창 | 동료 북마크가 깨지지 않게 |
| 로그아웃 중 창 | 띄우지 않음(`isLoggingOut`) | 보호 화면이 창을 띄웠다가 홈으로 가는 깜빡임 방지 |
| 내 제안서 건수 | 기존 `GET /v1/runs?limit=50` 길이 | 새 API 없이. 50건 넘는 사용자는 아직 없음(시범 3명) — 넘으면 total 필드 검토 |
| 자료 현황 | 사이드바 아래 작은 메뉴, 이름 "자료 현황" | 소유자 지시 3번. 화면 제목(자료원 상태)은 레인 3·4 몫이라 그대로 |
| 접는 메뉴 기준 | 1024px(lg) | 사이드바 13rem + 본문 최소 폭. 태블릿 세로도 접는 메뉴 |
| 접는 메뉴 구현 | 네이티브 `<dialog>` | 기존 Dialog 와 같은 이유(CSP style-src 'self', 포커스 가두기·Esc 를 브라우저가 처리) |
| 경로 표시 좁은 화면 | 마지막 칸만 | 390px 에서 가로 넘침 없이 |
| "WORKSPACE" 라벨 | `aria-hidden` | 장식용 영어 라벨 — 화면 읽기에서는 "주 메뉴" 이름으로 충분 |

## ADR 초안 (레인 5 가 번호 매겨 등록)
**제목**: 화면 안 로그인과 왼쪽 사이드바 화면 틀 (Research Studio)
- **맥락**: 시범 의견 — 로그인 페이지가 따로 있어 처음 화면이 빈 로그인 카드였고, 위쪽 메뉴는 6단계 흐름·제안서 목록과 함께 보기 어려웠다. 동료 UI 캡처("Research Studio")의 틀을 따르기로 함.
- **결정**: 로그인 페이지를 없애고, 보호 화면은 주소를 유지한 채 그 자리에 로그인 창(LoginDialogProvider 하나)을 띄운다. 로그인 뒤 같은 화면이 그려진다. 홈은 로그인 밖. 화면 틀은 왼쪽 사이드바(연구 작업실·새 제안서·내 제안서·작성 가이드, 아래 자료 현황·사용자 칸·테마) + 위쪽 막대(경로 표시·통합 검색·작성 가이드), 1024px 미만은 접는 메뉴(native dialog).
- **결과**: 로그인 전에도 앱 틀과 홈이 보이고, 개인 데이터·API 호출은 로그인 뒤에만. 세션 쿠키·CSRF·잠금 규칙 불변. e2e 로그인 도우미는 `/new` 를 열어 창에서 로그인. 옛 /login 북마크는 홈 + 창으로. 새 메뉴 항목은 `components/frame/Sidebar.tsx`, 경로 이름은 `frame/crumbs.ts` 한 곳.

## timeline 한 줄
`| 2026-10-29 | [UI] 레인 1 화면 틀·화면 안 로그인 | #102, #(frame) | 로그인 페이지 → 창, 위쪽 메뉴 → 사이드바·경로 표시·접는 메뉴, 앱 이름 Research Studio |`

## metrics 한 줄 (metrics.csv 머리글 순서)
`2026-10-29,<merge commit>,ui-studio-frame,,,,,,,,,,,,,,,,,,"web vitest 34→36 files; e2e +5 (frame.spec)"`

## 통합 세션이 할 것
- 레인 2 Home 이 들어오면 `App.tsx` 의 `<Route index element={<TempHome />} />` 를 Home 으로 바꾸고 TempHome 삭제. `/guide` 라우트(레인 2) 추가 확인.
- 레인 3 GlobalSearch 가 들어오면 `components/frame/TopBar.tsx` 의 `{search ?? <SearchSlot />}` 자리(Layout 에서 `search={<GlobalSearch />}`)로 바꾸고 SearchSlot 삭제.
- 레인 2 홈이 들어온 뒤 `e2e/frame.spec.ts` 첫 테스트에 "로그인 카드 → 연구 한눈에 보기" 확인 추가(지금은 사이드바 사용자 칸·건수로 확인).
- 레인 4 토큰이 들어오면 사이드바 선택 색(`bg-primary/10 text-primary`)·라벨(`Eyebrow`)을 토큰으로.
