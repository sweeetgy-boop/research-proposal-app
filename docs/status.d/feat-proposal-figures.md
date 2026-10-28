# [G] 제안서 그림(인포그래픽) 자동 삽입 — feat/proposal-figures (2026-10-28)

## 현황 행 (docs/status.md 용)
| 2026-10-28 | [G] 제안서 그림 | 명세(JSON, 로컬 7B·교정 1회·대체) → 밑그림(SVG 템플릿 6종·번들 Pretendard·resvg 300dpi) → Nano Banana Pro(`gemini-3-pro-image`) 1회 채택, 실패면 기본 그림. 자동 검증 없음 — 카드 "확인 전"→[확인함], [말로 고치기]·[글자 고치기]·[기본 그림으로]·[다시 만들기]·[빼기/넣기]·[다른 그림 추가], 동작마다 새 버전·복원·비교. 1차 검토가 본문·그림 불일치 지적(호출 증가 없음), 제출 전 점검 3항목, 마무리 확인 창, HWPX 섹션 본문 뒤 inline(+별첨 대체), manifest figures, 일일 상한 150·캐시 | ADR 0029, architecture §4.20, `docs/eval-2026-10-28-figures.md` |

## 완료 (2026-10-28 오전, 이 브랜치)
- §5 의 0~6 전부 구현·테스트. 골든셋 측정(§5-6 후반)만 18:00 이후 대기 — 명령은 `docs/eval-2026-10-28-figures.md` §3.
- 실측(낮, Nano Banana 만): 6종 성공 6/6, 장당 29~39초, 말로 고치기 26.6~28.3초(글자 변형 2~3곳 — 확인 절차로 잡는다).
- 테스트: pytest 1,902 통과(+48: 규칙 9·유스케이스 7·RunManager 5·이미지 어댑터 4·HWPX 6·API 3·밑그림 렌더 24 …), vitest 76(+11), e2e 15 통과
  (그림 2 + 기존 흐름이 확인 창을 거치도록 수정, run id 16진수 정규식 수정).
- HWPX: 실물 양식은 섹션 본문이 표 밖 단락 → 표식 단락을 그림으로 바꾸고 바로 뒤에 캡션·출처(inline). 칸 안(표) 양식도 지원, 못 찾으면 별첨.

---
아래는 작업 전 설계 기록(중간 저장본)이다.

## 1. 지시 요약 (세 번에 걸쳐 수정됨 — 최종본)

- 그림은 **Nano Banana Pro**(Gemini API `gemini-3-pro-image`, `generateContent`, 키 `RRA_GEMINI_API_KEY`)로 그린다.
  흐름: ① 초안을 구조화한 **그림 명세(JSON)** 를 로컬 모델이 JSON 스키마로 만들고(교정 재요청 1회, 그래도 실패면 `compose.fallback` 규칙)
  → 규칙으로 명세의 모든 글자·수치가 본문·제안자 입력·검증 근거(table_facts·근거 문단)에 있는지 검사 → ② 템플릿 SVG → PNG(300dpi) **밑그림**
  → ③ Nano Banana Pro 에 밑그림을 참고 이미지로 넣고 "배치·순서·화살표 유지, 글자 목록 그대로, 목록에 없는 글자·숫자·로고·얼굴·상표 금지,
  공공기관 보고서용, 흰 배경, 흑백 인쇄 구분" 프롬프트로 1회 호출 → **그대로 채택**. 호출 실패(오류·응답 없음)일 때만 밑그림을 "기본 그림"으로.
- **자동 검증(OCR 대조·재시도)은 하지 않는다.** 제안자가 직접 확인한다: 그림마다 "확인 전" 배지, [확인함] 누르면 바뀜, 고치면 다시 "확인 전".
  제출 전 점검(U7)에 "확인 전 그림 n개", 확인 전 그림이 있으면 최종 마무리 때 "그림을 확인하지 않았습니다. 그대로 진행할까요?" 확인 창.
  카드에 "AI 가 그린 그림입니다. 숫자와 글자를 원문과 확인하세요" 안내.
- 그림 종류 6: concept(개념도: 현황→문제→해결→기대효과), process(추진 체계도 3~6단계+산출물), schedule(간트, U6 단계별 개월, 연구기간 초과면 안 그리고 알림),
  stat_chart(검증 수치만, 출처 캡션 필수 "출처: 문서명, 연도, 쪽"), comparison(U4 비교표 기존 2~3건 대 제안, 없으면 "정보 없음"), roadmap(성과지표·활용 단계, 목표치 없으면 "목표치 확인 필요").
  비율: 개념도·체계도 16:9, 일정표 21:9, 해상도 2K. 초안 1건당 기본 2~3개(`figures.max_default: 3`), 동시 3.
- 카드 수정 4가지(각각 **새 버전** 저장, 이전 그림으로 되돌리기 가능): [말로 고치기](현재 그림을 입력 이미지로 Nano Banana 편집 호출, 요청 원문은 run 에 저장하되
  개인정보 규칙), [글자 고치기](명세 글자 폼 → 다시 그림), [기본 그림으로], [빼기/넣기]. 카드 배지 "Nano Banana Pro" / "기본 그림".
- 외부 전송은 명세 글자 + 밑그림뿐. 공용 계정이면 internal 근거에서 온 글자·수치는 명세에서 뺀다. manifest 에 그림별 모델·호출 수·채택 방식.
  Gemini 공용 호출 제한기 경유, 그림 호출 일일 상한 `figures.daily_image_cap`(기본 150, 말로 고치기·다시 만들기 포함), 넘으면 기본 그림 + 화면 알림.
  같은 명세·같은 밑그림이면 캐시.
- Argon 1차 검토에 그림 명세를 함께 보내 "본문과 그림이 어긋나는 곳" 지적(호출 수 증가 없음).
- HWPX: 실물 양식 해당 섹션 칸 안 본문 뒤에 그림(칸 너비에 맞춰 축소), 아래 "그림 n. 캡션"·출처 단락. render-check 로 줄 배치가 깨지면 문서 끝 "별첨 그림" 으로 옮기고
  본문에 "(별첨 그림 n 참조)". 방식은 manifest 에. BinData 그림당 500KB 상한.
- 접근성: 대체 텍스트 자동 생성, axe 위반 0. 폰트 번들 Pretendard, 로고·사진 금지, 흑백 구분(명도 차+무늬·선), 색상 토큰은 config 한 곳.
- 측정(골든셋 10건, 18:00 이후 생성 run 없을 때): 그림 생성 성공률, 장당 시간, 초안 1건당 추가 시간, 말로 고치기 1회 소요, 하루 예상 호출 수, HWPX 렌더 성공,
  본문 불일치 지적 수 → docs/eval. 샘플 6종(Nano Banana 결과와 밑그림 나란히)을 docs/history/screens/ 에.
- `figures.enabled` 로 끌 수 있게, 시범 기본값 켬. 낮에는 명세 생성을 가짜 LLM 으로 시험(mlx 금지), Nano Banana 호출 시험은 낮에도 가능. 배포는 "배포해" 지시 때.

## 2. 이 브랜치에 들어 있는 것 (커밋됨)

| 파일 | 내용 |
|---|---|
| `config/figures.yaml` | enabled·max_default·dpi·max_png_bytes·width_px·fonts_dir·template_dir·kinds·spec_stage·hwpx(placement·max_width_hwp·caption_prefix)·**palette**(ink/muted/line/paper, series 4단 명도+무늬 solid/dots/hatch/cross+dash, accent/warn). `daily_image_cap`·`concurrency`·`image_model`·`aspect` 는 아직 없음 → §5-0 |
| `tools/build_figure_fonts.py` | `web/node_modules/pretendard` 원본 OTF → 한글 음절 전체+라틴+구두점+화살표+도형 서브셋 (fonttools) → `config/templates/figures/fonts/` |
| `config/templates/figures/fonts/Pretendard-{Regular,Bold}.otf` + LICENSE | 각 1.9MB(OFL). resvg 에 `font_files` 로 넘긴다(시스템 폰트 미사용 → 운영기·CI 동일) |
| `docs/history/screens/2026-10-28-figures-baseline-concept-sample.png` | 밑그림 실험 결과(resvg, 2000×625, 17KB) |
| `docs/history/screens/2026-10-28-figures-nano-banana-concept-sample.jpg` | Nano Banana Pro 실호출 결과(축소본). 글자 5개가 한 글자도 바뀌지 않고 배치 유지됨 |

## 3. 확정 설계 (탐색 보고 2건 + 실험으로 확인한 사실 포함)

### 3.1 렌더·호출 기반 (실험으로 확인)
- SVG→PNG: **`resvg-py==0.5.0`** (macOS arm64·manylinux x86_64 휠 있음, cairo 불필요). `resvg_py.svg_to_bytes(svg_string=, font_files=[Regular, Bold], skip_system_fonts=True, dpi=300, zoom=300/96)`.
  한글 렌더 0.02초. **pyproject `render` 또는 새 `figures` extra 에 추가해야 한다**(현재 .venv 에만 설치됨). CI(backend job)도 설치 필요.
- Nano Banana Pro 실호출(2026-10-28 09:4x, 개발기): `POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image:generateContent`,
  헤더 `x-goog-api-key`, 본문 `{"contents":[{"parts":[{"text": 프롬프트},{"inline_data":{"mime_type":"image/png","data": base64 밑그림}}]}],
  "generationConfig":{"responseModalities":["IMAGE","TEXT"],"imageConfig":{"aspectRatio":"16:9","imageSize":"2K"}}}` → 200, **27.7초**,
  응답 `candidates[0].content.parts[].inlineData{mimeType:"image/jpeg", data}` → 2752×1536 JPEG 1.05MB, usage promptTokens 457·candidates 1333·thoughts 360.
  → 500KB 상한을 넘으므로 **채택 뒤 Pillow 로 JPEG 품질 조정/축소(긴 변 2000px)** 가 필요. 호스트는 `security.yaml allowed_domains` 에 이미 있음.
  모델 id 는 공식 문서상 `gemini-3-pro-image`(이미지 생성 문서) / `gemini-3-pro-image-preview`(Gemini 3 가이드) 둘 다 보임 → `llm.yaml` 에 설정값으로 두고 기본 `gemini-3-pro-image`(실호출 성공).
- 기존 Gemini 어댑터(`adapters/llm/openai_compat.py`)는 OpenAI 호환 경로라 이미지 생성 불가 → **새 어댑터 `adapters/llm/image_gen.py`**(httpx 직접, `_endpoint.guard_base_url` 로 보안 C·H,
  `rate_limiter.limiter_for("gemini")` 공유, 키는 Settings SecretStr, 429/5xx 재시도는 `RetryPolicy` 재사용). 일일 상한은 `FileDailyBudget` 을 `data/cache/figure_budget.json` 으로 하나 더.
  말로 고치기 = 같은 엔드포인트에 현재 그림을 inline_data 로 + 지시 텍스트.
- HWPX 삽입: `python-hwpx 6.8` 에 `HwpxDocument.open(bytes)`, `doc.add_image(png,"png")`(BinData/BIN0001.png 쓰기 + content.hpf manifest `isEmbeded="1"` + header binDataList 등록),
  `paragraph.add_picture(item_id, width=, height=)`(HWPUNIT), `doc.to_bytes()` 가 있다. 표 셀은 `paragraph.tables[i].cell(r, c)` → `cell.text`/`cell.paragraphs`/`add_paragraph`(마지막 실험은 중단됨 — **셀 안 단락 추가·그림 삽입이 되는지 첫 실험으로 확인할 것**).
  `adapters/rendering/hwpx.py:358` 의 "zip 파일 목록이 템플릿과 같아야 한다" 검사는 BinData 추가를 허용하도록 완화(추가 항목이 `BinData/*` 뿐인지 검사로 대체).
  삽입 순서: 기존 문자열 치환(`_fill_template`) → `HwpxDocument.open` → 섹션 칸 찾기(치환 전에 섹션 마지막 줄로 넣어 둔 표식 `​[fig:<key>]` 단락을 찾아 그림+캡션으로 교체) → to_bytes → `verify_hwpx`.
  inline/appendix 판정: 칸에 `line_limits` 가 있거나(한 줄 칸) 그림 높이(HWPUNIT) + 본문 줄수 추정이 칸 상한을 넘으면 appendix. 실물 양식 본문 칸은 페이지가 늘어나므로 기본 inline.

### 3.2 계층별 설계
- **domain** `models/figure.py`: `FigureKind`, 종류별 Spec(pydantic: ConceptSpec 4상자{label, lines≤2}, ProcessSpec stages 3~6{name, outputs}, ScheduleSpec{stages{name,start,end}, total_months},
  StatChartSpec{chart bar|line, categories, series{name, values}, unit, source{doc_id,title,year,page}}, ComparisonSpec{aspects, projects≤3{title, cells}, proposal{cells}},
  RoadmapSpec{metrics{name,target|"목표치 확인 필요"}, stages{name, desc}}), `Figure{id "f:<section>:<n>", kind, section, caption, alt, spec, renderer nano_banana|baseline,
  model, calls, included, confirmed, source_caption, internal(bool), image_sha, baseline_sha, edit_requests[{text, at}], created_at}`.
  `DraftVersion.figures: list[Figure]` 추가(버전 저장·복원·비교에 포함). `rules/figures.py`: `text_pool(draft, request, snapshot, facts)`, `validate_spec`(본문·입력·근거에 없는 글자/수치 거부,
  stat_chart 는 table_facts 만), `choose_default(draft, request, max_default)`(섹션→종류 우선순위: tech_importance→stat_chart(수치 있을 때)·comparison, objective→concept,
  method→process·schedule(U6 기간 있을 때), expected_*→roadmap), `texts_of(spec)`, `alt_text(spec)`, `image_prompt(kind, spec)`, `aspect_of(kind)`, `figure_diff(a, b)`.
  스키마 JSON 은 `config/templates/figures/<kind>.schema.json`(명세 프롬프트에 그대로 넣는다).
- **application** ports: `ImageGeneratorPort.generate(prompt, reference_png, *, aspect, size) -> ImageResult(bytes, mime, model)`, `.edit(prompt, image)`,
  `FigureRendererPort.svg(spec, palette) -> str`, `.png(svg) -> bytes`; `RunStorePort` 에 `save_figure_image/load_figure_image(user, run_id, figure_id, variant)`
  (파일 저장소 `figures/<id>.{png|baseline.png|svg}`, fake 저장소 3곳 + `test_port_conformance`). `PromptLibraryPort.figures()`(명세 프롬프트 `prompts/figures.md`) + fakes.
  usecase `usecases/figures.py` `MakeFigures`: `plan` → `make_spec`(로컬 JSON, 교정 1회, fallback) → `draw`(밑그림 → NB 1회 → 채택/기본) with `asyncio.Semaphore(3)`;
  `edit_by_words`, `edit_texts`, `use_baseline`, `toggle`, `confirm`. RunManager: v1 저장 직후(검토 전) `_figures_step`(step 이름 `figures`, `figures.enabled` 일 때),
  ReviewContext 에 `figures` → `[그림 명세 — 본문과 어긋나는 곳만 figures 에 {figure_id, comment}]` 블록 + 출력 `figures` 파싱 → `ReviewComment(section=<섹션>, kind="figure", figure_id)`;
  그림 편집 API 마다 `_store_version`(origin "edit", note "그림 …", `figures` 갱신, confirmed=False). `submit_check` 항목 `figures_unconfirmed`(count, target `section:`)·
  `figures_source`(stat_chart 출처 캡션 없음)·`figures_mismatch`(열린 figure 의견). `render_check` notes 에 배치 방식. manifest `figures: [{id, kind, section, renderer, model, calls, placement, included, confirmed}]`
  + `file_run_log.MANIFEST_KEYS/FIGURE_KEYS`. `evaluate.EvalIdea` 에 figures_total/figures_nano/figures_baseline/figure_seconds/figures_extra_seconds/verbal_edit_seconds.
- **adapters** `adapters/figures/{render.py(종류별 SVG 템플릿, 한글 줄바꿈·넘침 처리, 팔레트), png.py(resvg, 500KB 상한)}`, `adapters/llm/image_gen.py`, `adapters/fake/figures.py`
  (가짜 명세 응답은 `ScriptedComposeLLM` 에 `[그림 명세` 머리 분기, 가짜 ImageGenerator 는 밑그림을 그대로 돌려준다 → e2e 는 NB 없이 돈다).
- **entrypoints** REST: `GET /v1/runs/{id}/figures`, `GET /v1/runs/{id}/figures/{fid}/image?variant=adopted|baseline`(PNG, 소유자 검사), `POST /v1/runs/{id}/figures`{kind, section, base_version},
  `POST /v1/runs/{id}/figures/{fid}`{action: words|texts|baseline|include|exclude|confirm|regenerate, request?, texts?, base_version}. `views.draft_payload`·`version_payload` 에 `figures`,
  `diff_payload` 에 `figures_changed`. CLI `rra runs figures <id>`(목록·상태만). OpenAPI 재생성 + `npm run gen:api`.
- **web** `features/figures/FigureCard.tsx`(미리보기 `<img src="/v1/runs/{id}/figures/{fid}/image">` — CSP `img-src 'self'` 라 같은 출처 OK, 배지 Nano Banana Pro/기본 그림/확인 전,
  안내 문구, 버튼 [확인함]·[말로 고치기](textarea Dialog)·[글자 고치기](명세 폼 Dialog)·[기본 그림으로]·[빼기/넣기]), `AddFigureDialog`(6종 선택), Edit.tsx `sectionTools` 아래와 Draft.tsx 섹션 머리에 카드,
  Versions diff 에 "그림 변경" 행, Finalize 에 확인 전 그림 경고 Dialog, SubmitCheck 는 백엔드 항목으로 자동 표시. 훅 키 `["run", id, "figures"]`.

## 4. 참고한 코드 지점 (탐색 보고 요약)
- 초안 모델 `domain/models/draft.py`(Section/Sentence/Draft), 버전 `domain/models/review.py` `DraftVersion`, 저장 `adapters/runs/file_run_store.py`(`versions/draft_vN.json`).
- 생성 흐름 `application/services/run_manager.py` `_execute`(v1 저장 → `finally` 에서 `review()` 자동), `_execute_review`(ReviewContext), `_apply_draft_review`(v2), `_store_version`, `apply_edits`, `revert`, `finalize`, `render_check`, `manifest()`.
- 검토 입력 `usecases/review_draft.py` `_input`(블록 "[초안]"·"[근거]"…), 출력 키 sentences/sections/additions/resolved/checklist/candidates/support/scores.
- 제출 점검 `usecases/submit_check.py`(CheckItem key/label/ok/detail/count/target/extra). 렌더 점검 `usecases/render_check.py`.
- 직렬화 `entrypoints/views.py` `draft_payload`·`version_payload`·`diff_payload`·`submit_check_payload`. API `entrypoints/api/app.py`(`_own`·`_svc`·`_save`, finalize 는 Response bytes + X-RRA-Check).
- 가짜 모드 `composition.build_fake_parts`·`adapters/fake/llm.py`(`[섹션: key]` 분기). 테스트 fake `tests/fakes.py`, RunManager 조립 예 `tests/application/test_draft_fallback.py:170`, API 테스트 `tests/entrypoints/ui/fake_app.py make_assistant`.
- 설정 `config_loader.pipeline_config/usability_config`(모르는 키 거부 — 새 설정은 `figures_config` 함수로 따로), `llm_config(stage)`(stages 에 없는 단계는 KeyError → `stages.figures` 추가), `data_location` 표.
- 웹: `features/draft/DraftEditor.tsx`(`sectionTools` render prop), `routes/run/Edit.tsx`, `routes/run/Draft.tsx` `SectionHeader`, `features/submit/SubmitCheckList.tsx`, `routes/run/Finalize.tsx`, `src/test/utils.tsx`(mockFetch·axe), e2e `web/e2e/helpers.ts`(login·createRun·subnav), fake 포트 8010.
- U4 비교표 `domain/models/comparison.py`(ASPECTS objective/method/scope/outcome/differentiation, ComparisonTable), U6 `domain/rules/schedule.py`(`research_period_months`, `schedule_months`), table_facts `domain/models/table_fact.py`(`as_text`, 판독 미확인은 적재 단계에서 이미 제외).

## 5. 다음 단계 (순서)
0. `config/figures.yaml` 에 `daily_image_cap: 150`, `concurrency: 3`, `aspect: {concept: "16:9", process: "16:9", schedule: "21:9", stat_chart: "16:9", comparison: "16:9", roadmap: "16:9"}`, `image_size: "2K"`,
   `budget_counter: data/cache/figure_budget.json`, `cache_dir: data/cache/figures` 추가. `config/llm.yaml` 에 `stages.figures: {max_tokens: 1500}`(명세, 로컬) 과 `providers.gemini.image_model: gemini-3-pro-image`.
   `pyproject` extra 에 `resvg-py>=0.5`. CI backend job 설치 확인.
1. HWPX 셀 삽입 실험 마무리(§3.1 마지막 항목) → `adapters/rendering/hwpx.py` 에 `figures` 인자·BinData 허용·표식 교체·appendix 경로. 테스트: `tests/fixtures/hwpx/proposal_template_min.hwpx` 로 열기·BinData·`hp:pic` 존재.
2. domain(모델·규칙·스키마 6종) + 렌더러(SVG 6종 + resvg) + 단위 테스트(스냅샷 글자 포함·줄바꿈·흑백 무늬·500KB).
3. ports·usecase·RunManager 단계·버전·검토 입력·제출 점검·manifest·평가 지표 + fakes 3곳 + 테스트.
4. image_gen 어댑터(실호출 1회 테스트는 낮에 가능, fixture 는 응답 구조만 저장·이미지 바이트는 짧게) + 예산·캐시·제한기.
5. REST·views·CLI·OpenAPI 재생성 → web 카드·다이얼로그·버전 diff·Finalize 경고·vitest(axe)·e2e(가짜 모드: 넣기·빼기·글자 고치기·확인함·버전 복원).
6. 샘플 6종(가짜 입력) 생성 → `docs/history/screens/2026-10-28-figures-<kind>-{baseline,nano-banana}.png`. 측정은 18:00 이후 `rra eval --label figures ...`(생성 run 없을 때) → `docs/eval-2026-10-28-figures.md`.
7. 문서: architecture §4.16, ADR(그림 생성 방식: 이미지 AI 는 Nano Banana Pro + 밑그림 참고·사람 확인), pilot-guide(그림 확인 절차), status.md 행, timeline·metrics, CLAUDE.md 한 줄.
   병합 뒤 `docs/history/deploys/pending.md` 에 한 줄 — 배포는 "배포해" 지시 때.

## 6. 주의
- `npm run build` 는 운영기 `web/dist` 를 바로 바꾼다(배포 전 금지, 메모리 pilot-deploy-rule). 낮에는 mlx 호출 금지(명세 생성은 가짜 LLM 으로).
- Nano Banana 응답은 JPEG·1MB 급 → 저장 전 축소. 응답·프롬프트에 개인정보·사번이 들어가지 않게 명세 글자 목록만 보낸다.
- `.venv` 에 설치한 `resvg-py` 는 pyproject 반영 전까지 다른 환경에 없다.
