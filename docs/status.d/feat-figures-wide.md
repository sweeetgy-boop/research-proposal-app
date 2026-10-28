# [23] 그림 모양 — feat/figures-wide (2026-10-28 밤, 레인 C)

## 현황 행 (docs/status.md 용)
| 2026-10-28 | [23] 그림 가로·본문 폭·글자 9pt | 모든 그림 가로 비율(16:9·21:9, 일정표·로드맵 21:9·4:1 — 4:1 은 21:9 생성 + 흰 여백 맞춤), 가로 배치(As-Is/To-Be 좌우 두 단, SWOT 한 줄, 기법별 arrange), HWPX 그림 폭 = 양식 본문 안쪽 폭(153.8mm, 양식에서 읽음)·높이 상한 쪽 1/3 → 넓은 비율로, 글자 ≥ 9pt(밑그림 SVG 계산, Nano Banana OCR 상대 어림) → 덜 넓은 비율·글자 줄이기·"글자를 더 크게" 다시 그림, manifest `figure_fit`, 카드 가로 비율·한국어 `display_name`·오류 문구, 그림 AI 버튼 대기·[취소] | ADR 0041 |

## 완료
- domain: `rules/figure_fit.py`(WIDE_ASPECTS·choose_aspect·api_aspect·wider/narrower·BodyFrame·fit_aspect_for_frame·font_pt·min_font_units·svg_metrics·
  svg_text_pts·estimate_relative_pt·estimate_ocr_pt·make_fit·shorten_spec·clip_words·pixel_ratio_label·BIGGER_TEXT), `models/figure.py`
  (FigureFit, Figure.fit·display_name 속성, FigurePlacement.fit, DISPLAY_NAME·display_name()), `rules/figures.py`(choose_aspect 위임, 프롬프트
  "가로로 넓게 배치, 좌우 여백 최소"·배치별 구조·글자 높이 2%·일정표 눈금, `technique_arrangement`, 그림 안 글자에서 수치 그래프 출처 제외),
  `rules/techniques.py`(Technique.arrange·arrangement), `config/figures/techniques.yaml`(arrange 20개, 기법 이름 영어 병기 정리).
- application: `usecases/figures.py` — `layout()`(비율·높이 상한·글자 하한·넘침 → 덜 넓은 비율 → 글자 줄이기), `draw(shorten=)`(4:1 패딩 참고 이미지,
  reframe, 실제 픽셀 맞춤, OCR 상대 어림, 작으면 "글자를 더 크게" 1회), `FigureConfig.frame·min_text_pt·max_shorten·max_image_redraws·ocr_box_em·arrangements`,
  캡션 기본값 한국어 이름. `run_manager` — [글자 고치기]는 줄이지 않음(shorten=False), manifest `figure_fit`(생성 때 + 마무리 때 HWPX 실측).
- adapters: `figures/render.py`(가로 배치·글자 하한 33.1·data-overflow·폭 기준 줄바꿈 `wrap_width`), `figures/png.py`(`fit_aspect`·`pad_to_aspect`),
  `rendering/hwpx_geometry.py`(양식 본문 폭), `rendering/hwpx.py`(그림 폭 = 표식 자리 폭, 높이 상한, placement.fit), `logging/file_run_log.py`
  (FIGURE_FIT_KEYS), composition(`build_figure_frame`, OCR·reframe·image_size·arrangements 연결, 가짜 모드는 OCR 끔), `config/figures.yaml fit:`.
- entrypoints: views `display_name`·`error_label`·`fit`(aspect_css·note), REST 그림 3경로 `cancel_on_disconnect`.
- web: `features/figures` — 카드 그림 `fit.aspect_css` 비율·높이 제한 없음·본문 폭 안내 한 줄, 제목 `display_name`, 오류는 `error_label`,
  [다시 만들기]·[말로 고치기]·[다른 기법으로 바꾸기]·[다른 그림 추가]·[다시 시도] 를 `useAiCall`+`AiWaiting`(경과 초·[취소]),
  `types-figures.ts`(FigureFitView·display_name·error_label·fit). e2e 선택자 한국어 이름 + 카드 그림 가로 확인.
- 도구: `tools/eval_figures_wide.py`(샘플 → 밑그림·Nano Banana·맞춤·실물 양식 HWPX·한/글 Quick Look 쪽 미리보기), `tools/figure_samples.py WIDE_SAMPLES`.

## 측정·테스트
- 실물 양식 HWPX(한/글 Quick Look 쪽 미리보기) 9/9 본문 폭 153.8mm·높이 ≤ 99mm, 글자 9pt 이상 8/9(As-Is/To-Be 이름표 8.7pt), 다시 그림 2/9,
  장당 35~43초. 이미지 32회(레인 카운터, 상한 40), 텍스트 0회. `docs/eval-2026-10-28-figures-wide.md`.
- pytest 2234 passed·21 skipped(새 테스트 함수 48: figure_fit 23·wide 유스케이스 12·wide 어댑터 25 케이스·REST 1, 기존 갱신), lint-imports 8 kept,
  vitest 139(새 2), e2e 전체 24 passed·3 skipped(figures.spec 가로 그림 확인 추가, 선택자 한국어 이름).

## 통합 담당 할 일
- docs/openapi.json·schema.d.ts 다시 만들기: 그림 응답에 `display_name`·`error_label`·`fit{ratio,aspect_css,width_mm,height_mm,fits,min_text_pt,text_ok,shortened,note}`
  (손으로 쓴 타입은 `web/src/api/types-figures.ts`).
- 시범 배포 때 운영기 config 에 `figures.yaml fit:` 이 들어가는지(기본값이 있어 없어도 돈다). 실물 양식이 있으면 본문 폭은 양식에서 읽는다.
- 저장된 예전 그림은 `fit` 이 없다(카드 16:9 로 보임, manifest figure_fit null) — [다시 만들기]·[기본 그림으로] 하면 생긴다. HWPX 에는 넣을 때
  본문 폭·높이 상한이 그대로 적용된다(예전 4:3 은 높이에 맞춰 줄고 fits=false).

## 판단
| 항목 | 판단 |
|---|---|
| 4:1 만들기 | Nano Banana 는 4:1 을 받지 않는다 → 21:9 로 생성, 밑그림을 21:9 흰 캔버스 가운데에 넣어 보내고 "가운데 4:1 띠 안에만" 지시, 결과 흰 여백을 잘라 맞춤. 자르기만 하고 글자를 자르는 크롭은 하지 않는다. |
| 흰 여백 맞춤 | 잘라 낸 내용이 목표보다 넓으면 위아래만 채우고, 그 종류의 가장 덜 넓은 허용 비율보다 좁으면 좌우를 채우고, 그 사이면 그대로(좌우 여백을 늘리지 않는다). 그래서 실제 비율이 "2.62:1" 처럼 될 수 있고 맞춤 기록은 실제 픽셀로. |
| 본문 폭 | 렌더 결과에서 표식 단락 자리 폭을 읽는다(쪽 − 좌우 여백 − 단락 오른쪽 여백; 표 칸이면 칸 − 칸 여백). 그림 단락은 서식 점검이 왼쪽 0·가운데로 바꾸므로 왼쪽 여백은 빼지 않는다. 양식이 없으면 figures.yaml fit.body_width_mm(153.8). |
| 높이 상한 넘침 | 그림 단계가 넓은 비율로 다시 그린다. HWPX 에서 넘는 것(예전 4:3·세로 그림)은 높이에 맞춰 줄이고 `fits=false` — 다시 그리지는 않는다(렌더러는 AI 를 부르지 않는다). |
| 글자 하한 9pt | 브리프 "9~10pt" 중 하한 9pt 를 막는 기준으로, 본문 글자는 37단위(10.1pt)로 그린다. 반올림(33.0 단위 = 8.99pt) 때문에 0.05pt 허용. |
| 글자가 작을 때 순서 | ① 같은 종류의 덜 넓은 가로 비율(높이 상한 안) → ② 글자 줄이기 2단계. 글자를 지키는 쪽을 먼저. |
| 글자 줄이기 | 띄어쓰기 자리에서만 자르고(숫자·낱말 중간 안 자름) 항목 수를 줄인다 — 원래 글자의 앞부분이라 출처 검사를 그대로 통과. 수치 그래프·일정 기간은 손대지 않는다. 줄인 칸 수는 카드 안내에 "n곳을 줄였습니다". |
| 제안자 글자 | [글자 고치기]로 쓴 글자는 줄이지 않는다(기록만, `text_ok=false` 가능). [말로 고치기]는 AI 가 명세를 바꾸는 것이라 줄이기 대상. |
| Nano Banana 글자 크기 | OCR 상대 어림(같은 글자의 밑그림/그림 높이 비 × 밑그림 pt). 처음 쓴 절대 어림(상자 높이 ÷ 1.2)은 밑그림(실제 9.3pt)에서 6.3~8.5pt 로 낮게 나와 버렸다 — 짧은 한글·숫자는 상자가 낮다. 절대 어림은 함께 찾은 글자가 없을 때만. |
| 다시 그리기 상한 | OCR 로 작다고 나오면 1회만 더(그림 호출 +1) — 내용은 두고 "글자를 더 크게: 직전 약 n pt" 만 붙인다. 글자 줄이기는 밑그림 단계(layout)에서만. 그 뒤에도 작으면 그대로 넣고 기록(`text_ok=false`). |
| OCR 실행 | 운영(맥 미니)은 macOS Vision OCR(격리 자식) — 그림 1장에 2회(밑그림·그림, 각 1~3초). 리눅스·CI·가짜 모드는 OCR 없음 → 밑그림 값(`text_method=baseline`). |
| 수치 그래프 출처 | 그림 안에서 뺐다 — HWPX 캡션 아래 12pt 출처 줄과 카드 출처 줄이 이미 있다(글자 자리 확보). |
| 이름 | `display_name`: As-Is/To-Be = "현재·연구 후 비교 그림", 기법 = "분석 기법 그림 – <기법 이름>", 나머지 종류 이름(비교 = "차별성 비교표"). 새 그림 캡션 기본값도 이 이름(저장된 캡션은 그대로). 레인 D 버전 목록은 `Figure.display_name` 속성을 먼저 쓴다. |
| 기법 이름 영어 | 영어 단어 병기를 뺐다: 퓨 매트릭스(Pugh)→퓨 매트릭스, 역장분석(Force Field)→역장분석, AHP(계층분석)→계층분석(AHP), FMEA·LCC·DEA 도 한국어 먼저. 공공 문서에 흔한 약칭(SWOT·TOWS·PEST(EL)·PMI·TOPSIS)은 그대로. 그림 안 묶음 이름(Plus(장점) 등)은 명세 검사 고정 글자와 묶여 그대로(후속). |
| 쪽 미리보기 | 한/글 Quick Look 확장으로 실제 쪽(첫 쪽)을 그렸다 — 그림이 1쪽 2-가-(1) 에 오는 미리보기용 HWPX(본문은 짧은 가짜 문장). 이전(v2) 미리보기는 v2 측정 때 그림을 이전 크기 규칙(폭 42000·상한 없음)으로 넣은 것. |
| 카드 그림 | 높이 제한(max-h-64)을 없애고 그림 비율 그대로 카드 폭에 꽉 — 가로 그림이 작게 보이지 않게. |
