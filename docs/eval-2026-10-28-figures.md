# [G] 제안서 그림 측정 (2026-10-28)

## 1. Nano Banana Pro 실호출 (낮, mlx 미사용 — 2026-10-28 10:2x~10:4x, 개발기)

샘플 명세 6종(`tools/figure_samples.py SAMPLE_SPECS`, 가짜 입력) → 밑그림(resvg, 300dpi) → `gemini-3-pro-image` generateContent(참고 이미지 = 밑그림, 2K,
종류별 비율) 1회. 동시 3(초안 1건과 같은 조건). 응답은 `shrink_image` 로 500KB 이하 JPEG.

| 종류 | 비율 | 성공 | 시간(s) | 저장 크기 | 밑그림 PNG |
|---|---|---|---|---|---|
| concept 개념도 | 16:9 | ✓ | 39.0 | 120 KB | 169 KB |
| process 체계도 | 16:9 | ✓ | 35.7 | 120 KB | 157 KB |
| schedule 일정표 | 21:9 | ✓ | 30.1 | 152 KB | 196 KB |
| stat_chart 수치 그래프 | 16:9 | ✓ | 30.2 | 170 KB | 180 KB |
| comparison 비교 | 16:9 | ✓ | 29.3 | 130 KB | 162 KB |
| roadmap 로드맵 | 16:9 | ✓ | 31.2 | 178 KB | 183 KB |

- **그림 생성 성공률 6/6**(호출 실패 0, 기본 그림 대체 0). **장당 29~39초**(중앙값 31초).
- 눈으로 대조(그림 생성): 6종 모두 배치·순서·화살표·막대 길이·기간 비율이 밑그림과 같고, 이 해상도에서 글자·숫자가 명세와 같았다.
  Nano Banana 는 색을 회색조로 바꾸는 경향(무늬는 유지)이 있다.
- **말로 고치기 1회 26.6~28.3초**(3회). 요청은 반영됐지만 **글자 변형이 생겼다**: 목록 없이 편집하면 "상태→샹태"·"에만→에안"·"대응→대용" 3곳,
  명세 글자 목록을 프롬프트에 함께 넣은 뒤에도 "에만→에안"·"대응→대용" 2곳(+ 상자 테두리 끊김). 이전 그림(JPEG)을 다시 그리는 방식이라
  첫 생성보다 위험이 크다 → 고친 그림은 "확인 전"으로 돌아가고 제출 전 점검·마무리 확인 창이 잡도록 둔다. 글자만 바꿀 때는 [글자 고치기]
  (명세 → 밑그림에서 새로 그림)를 권한다(시범 안내 §5.5).
- 샘플: `docs/history/screens/2026-10-28-figures-<kind>-{baseline.png,nano-banana.jpg,side-by-side.jpg}`, 편집 결과
  `…-concept-edit-1.jpg`·`…-concept-edit-2.jpg`(목록 없음)·`…-concept-edit-2-with-texts.jpg`(목록 포함).

## 2. 초안 1건당 추가 시간·하루 호출 수 (추정 — 골든셋 측정 전)

- 그림 단계 = 명세 3건(로컬 7B, 순차) + Nano Banana 3장(동시 3 → 가장 느린 1장 ≈ 30~40초). 로컬 명세 시간은 골든셋에서 잰다.
- 하루 예상 그림 호출: 시범 3명 × 하루 초안 2~3건 × (생성 3 + 고치기 1~2) ≈ **25~45회**. 상한 150(`figures.daily_image_cap`)이면 초안 30건 안팎까지.

## 3. 골든셋 10건 (18:00 이후, 실행 중·대기 중 run 이 없을 때) — 대기

```
.venv/bin/rra runs active                          # 0건 확인
.venv/bin/python tools/with_heavy_lock.py -- .venv/bin/rra eval --label figures --out data/eval/figures-2026-10-28.json
.venv/bin/rra eval --report data/eval/figures-2026-10-28.json --out docs/eval-2026-10-28-figures.md --append
```

보고서 표의 그림 열: 그림(만든 수)·Nano Banana 채택·기본 그림·그림 건너뜀(명세 실패)·그림 호출·그림 단계(s)·그림 지적(1차 검토).
성공률 = Nano Banana 채택 / 그림, 초안 1건당 추가 시간 = 그림 단계(s) 평균, HWPX 렌더 성공은 마무리 단계 측정(별도).
