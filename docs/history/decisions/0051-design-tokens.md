# ADR 0051 — Research Studio 디자인 토큰: 색·모서리·여백을 index.css 한 곳에 (2026-10-29, [UI] 레인 4, #101·#107)

## 맥락
동료 UI("Research Studio")의 겉모습으로 바꾸되 기능과 흐름은 그대로 둔다. 화면마다 색을 직접 쓰면 다크 모드와 명암 대비가 깨진다.

## 결정
- `web/src/index.css` 의 HSL 변수에 바탕·카드·테두리·주 색(남보라)·색조(연보라·살구·민트)·상태 색을 둔다.
  변수는 :root 와 다크 두 경로에 두고, Tailwind `@theme inline` 으로 유틸리티를 만든다. 기존 변수 이름은 그대로 두고 값만 바꾼다.
- 공용 조각 `Eyebrow`(장식용 영어 라벨, aria-hidden)·`StatusChip`·`ProgressBar` 는 `components/ui/` 에 둔다.
- 캡처의 흐린 회색은 WCAG AA 를 넘게 진하게 한다(보조 글자 #5B6070, 입력 테두리 3:1).
- ①~⑥ 안쪽 화면은 스타일만 바꾼다. 배치·기능·문구·test id 는 그대로다.

## 결과
- 새 화면은 토큰만 쓴다(색 직접 지정 금지). 색을 바꿀 때는 `docs/status.d/feat-ui-studio-tokens.md` 의 명암비 표를 다시 잰다.
- 실제 화면 axe 점검(11개 화면, 밝은·어두운 테마): 위반이 main 5건 → 0건.
- Lighthouse 100·100·100, CLS 0.001 — 바꾸기 전과 같다.
