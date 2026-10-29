# feat/ui-studio-tokens — Research Studio 디자인 토큰 + 공용 조각 + ①~⑥ 안쪽 화면 스타일 (2026-10-29, [UI] 레인 4)

## 바뀐 것
- **디자인 토큰**(`web/src/index.css` 한 곳): 옅은 회색 바탕(#F7F7FB)·흰 카드·옅은 테두리(#ECECF3)·남보라 주 색(#4F46E5)·
  본문 #1F2330·보조 글자 #5B6070(캡처 #6B7280 보다 진하게). 새 변수 `--primary-soft`(연보라)·`--apricot`(살구)·`--mint`(민트)·
  `--link-green`·`--destructive-soft`·`--primary-hover`, 그림자 `shadow-card`·`shadow-pop`, 모서리 sm 6·md 10·lg 14·xl 16px,
  여백 `p-card`(1.25rem)·`gap-section`(1.5rem)·`p-page`(2rem), 영어 작은 대문자 라벨 유틸리티 `eyebrow`. 다크 값은
  `prefers-color-scheme` 와 `[data-theme="dark"]` 두 경로 모두 같은 값. 기존 변수 이름은 그대로(값만 바뀜).
- **공용 조각**(`web/src/components/ui/`): `Eyebrow`(장식, aria-hidden), `StatusChip`(writing 작성 중 연보라 · reviewing 검토 중 살구 ·
  done 마무리 완료 민트), `ProgressBar`(role=progressbar, 이름 기본 "진행률", 0~100 자름), `Tabs` 에 선택 건수 `count`.
- **공용 부품 겉모습**: 버튼(굵게, 주 색 hover 진하게, outline 은 흰 카드+옅은 테두리, secondary 는 연보라), 카드(16px·그림자 거의 없음),
  배지(채운 남보라 → 옅은 색조 칩, 모서리 6px), 알림(색조 바탕), 입력·선택·여러 줄 입력(흰 바탕·3:1 테두리·포커스 남보라),
  팝업(16px·부드러운 그림자·바탕 남회색 반투명), 토스트, 체크박스, 밑줄형 탭(선택 탭 남보라 글자+밑줄).
- **①~⑥ 안쪽 화면**(두 번째 PR, 브랜치 feat/ui-studio-inner — 스타일만, 배치·기능·문구·test id 그대로):
  - 단계 표시(Stepper): 지난 단계 민트 칩 · 지금 단계 남보라 채움 · 남은 단계 흰 칩, hover 연보라. 못 여는 단계 안내 말풍선은 둥근 팝업.
  - 아래 이동 막대(StepNavBar): 흰 카드 바탕 반투명. 제안서 화면 메뉴: 밑줄형(선택 남보라 굵게).
  - 회색 바탕 위 테두리 상자(섹션·카드·표 상자·목록 칸 47곳) → 흰 카드 바탕(`bg-card`), 경고 상자 → 살구 색조, 오류 상자 → 옅은 빨강 색조,
    표 머리글 작은 회색 글자(`text-xs`, muted 바탕), ③ 진행 막대·브리핑 연도 막대 → 연보라 바탕 + 남보라 둥근 막대.
  - 영어 작은 대문자 라벨(장식): ① `Step 01 · Idea`, ② `Step 02 · Similar projects`, 브리핑 `Step 02 · Literature`, 보강 질문 `Step 03 · Questions`,
    제안서 안쪽 머리 `Proposal`. 한국어 제목은 그대로.
  - 실제 화면 명암 점검(axe-core 를 화면에 넣어 color-contrast 포함 WCAG 2.1 AA, 밝은·어두운 테마, ①·②·브리핑·보강 질문·초안·진행·직접 수정·
    버전·최종 검토·제출 전 점검·마무리 11 화면): main 은 밝은 4종·어두운 1종 위반 → 이 브랜치 0. 고친 것 — 근거 칩의 자료원 글자
    (`DocRef`, 11.2px·opacity 80% 3.7:1 → 12px 보조색 5.6:1), ③ 진행 막대 이름 없음(`aria-label="초안 생성 진행률"`), 버전 비교
    추가·삭제 표시 글자(4.1~4.3:1 → 본문색). 점검 스크립트는 임시(커밋 안 함, `bypassCSP` 로 axe 주입).
  - Lighthouse(`npm run lighthouse`, 기준 0.95·CLS 0.05): main 성능 100 · 접근성 100 · 권장 100 · CLS 0.001 → 이 브랜치 같음(100·100·100·0.001).
- 캡처: `docs/history/screens/2026-10-29-ui-studio-step{1-idea,2-precheck,3-draft,4-edit,5-final-review,6-finalize}-{before,after}.png`,
  다크 `2026-10-29-ui-studio-step3-draft-dark-after.png`. before 는 origin/main(546f244) 빌드, 1280 폭 전체 페이지.
  기존 `e2e/screens.spec.ts` 는 main 에서도 360 폭 가로 넘침 검사에서 실패한다(틀 교체 레인 1 범위) — 그래서 다크 before 는 없음.

## 명암비(WCAG AA, 글자 4.5:1 · 입력 테두리 3:1)
| 짝 | 밝은 모드 | 다크 모드 |
|---|---|---|
| 본문 / 바탕 | #1F2330 / #F7F7FB 14.65 | #E9EAF2 / #0F1118 15.73 |
| 본문 / 카드 | #1F2330 / #FFFFFF 15.66 | #E9EAF2 / #171A24 14.48 |
| 보조 글자 / 바탕 | #5B6070 / #F7F7FB 5.86 | #A6ABBD / #0F1118 8.24 |
| 보조 글자 / 카드 | #5B6070 / #FFFFFF 6.27 | #A6ABBD / #171A24 7.59 |
| 보조 글자 / muted | #5B6070 / #F1F1F7 5.57 | #A6ABBD / #1F2330 6.84 |
| 보조 글자 / 연보라 | #5B6070 / #EFEDFC 5.43 | #A6ABBD / #25224A 6.53 |
| 주 색 글자 / 카드 | #4F46E5 / #FFFFFF 6.29 | #9C97FF / #171A24 6.85 |
| 주 색 버튼 글자 | #FFFFFF / #4F46E5 6.29 (hover #4338CA 7.90) | #0F1118 / #9C97FF 7.44 (hover 9.42) |
| 연보라 칩·라벨 | #3F37C9 / #EFEDFC 6.99 | #C4C1FF / #25224A 8.83 |
| 살구 칩 | #9A4A12 / #FDF1E6 5.62 | #F3B27A / #2F2218 8.41 |
| 민트 칩 | #1D6B45 / #EEF6F1 5.89 | #7FD3A6 / #15281F 8.69 |
| 초록 링크 / 민트 | #1D7A4C / #EEF6F1 4.84 | #6FD19C / #15281F 8.32 |
| 성공 / 카드 | #18794E / #FFFFFF 5.41 | #6FD19C / #171A24 9.32 |
| 경고 / 카드 | #A04F05 / #FFFFFF 5.81 | #F5B451 / #171A24 9.53 |
| 오류 / 카드 | #C2261D / #FFFFFF 5.85 | #FF8A80 / #171A24 7.60 |
| 오류 칩 | #B42318 / #FDEDEC 5.79 | #FFB3AC / #3A1A1C 9.15 |
| Argon 배지 / 카드 | #6D3FC8 / #FFFFFF 6.57 | #C4A4FF / #171A24 8.35 |
| 입력 테두리 / 카드 | #8F93A8 / #FFFFFF 3.04 | #6E748A / #171A24 3.74 |
- 장식 테두리(#ECECF3)는 구분선일 뿐이라 3:1 대상 아님. 영어 라벨은 12px 굵게 연보라 글자색(6.99/5.45 이상).

## 판단
| 항목 | 판단 | 이유 |
|---|---|---|
| 보조 글자 색 | 캡처 #6B7280 대신 #5B6070 | 바탕 #F7F7FB 위 #6B7280 은 4.52 로 경계. 연보라·muted 위에서도 5.4 이상 되게 |
| 입력 칸 테두리 | 캡처보다 진한 #8F93A8 | WCAG 1.4.11 입력 경계 3:1. 카드 테두리는 옅게 유지 |
| 기존 변수 이름 | 유지, 값만 바꿈 + 새 변수 추가 | 화면 수십 곳이 `text-primary`·`bg-muted` 를 쓴다. 이름 바꾸면 충돌 |
| 배지 default | 채운 남보라 → 연보라 칩 | 캡처의 상태 칩 모양. 채운 색은 버튼에만 |
| 모서리 | 카드 16·알림 14·버튼/입력 10·칩 6px | 캡처 카드 12~16px, 버튼은 그보다 작게 |
| 영어 라벨 | `aria-hidden` 장식 | 화면 읽기에는 한국어 제목만. 화면 글자는 대비 기준 만족 |
| 그림자 변수 | `--elev-card`·`--elev-pop`(:root) → `shadow-card`·`shadow-pop` | `@theme inline` 의 `--shadow-*` 와 이름이 같으면 순환 참조 |

## ADR 초안 (레인 5 가 번호 붙여 기록)
- 제목: Research Studio 디자인 토큰 — 색·모서리·여백을 index.css 한 곳에
- 맥락: 동료 UI("Research Studio") 겉모습으로 바꾸되 기능·흐름은 그대로. 화면마다 색을 직접 쓰면 다크 모드·대비가 깨진다.
- 결정: HSL 변수(:root, 다크 두 경로)에 바탕·카드·테두리·주 색·색조(연보라·살구·민트)·상태 색을 두고 Tailwind `@theme inline` 으로
  유틸리티를 만든다. 기존 변수 이름은 유지. 공용 조각 `Eyebrow`·`StatusChip`·`ProgressBar` 는 components/ui 에.
  캡처의 흐린 회색은 AA 를 넘게 진하게 한다.
- 결과: 새 화면은 토큰만 쓴다(색 직접 지정 금지). 색을 바꿀 때는 이 문서 표의 명암비를 다시 잰다. 캡처와 눈으로 같은 정도가 목표이며
  일부 회색은 캡처보다 진하다.

## 기록 한 줄
- timeline: `2026-10-29 | [UI] 레인 4 | Research Studio 디자인 토큰·공용 조각(Eyebrow·StatusChip·ProgressBar)·공용 부품·①~⑥ 안쪽 화면 겉모습 | PR #101 · #?`
- metrics.csv: `2026-10-29,<commit>,ui-studio-tokens,,,,,,,,,,,,,,,,,,"디자인 토큰·공용 조각·①~⑥ 안쪽 화면 스타일, 웹 vitest 163"`
