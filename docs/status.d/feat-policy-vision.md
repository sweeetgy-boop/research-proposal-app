## [P3] 웹 이미지 판독 (feat/policy-vision, 2026-10-27, ADR 0018, architecture §4.17)

- 코드만·fixture 테스트만 (실제 스냅샷 OCR·Argon 호출·DB 적재는 통합 세션이 아래 순서로). 새 테스트 83, 전체 1322 통과·18 skip, 계약 8 유지.
- 모듈: `domain/models/vision.py`(ImageItem·OcrResult·VisionReading·ImageReadResult), `domain/rules/image_filter.py`(거르기),
  `vision_plan.py`(순서·예산), `vision_trust.py`(JSON 만·수치 대조·"[판독 확인 필요]"), `privacy.py`(개인정보 제거);
  `application/ports/vision.py`(OcrPort·VisionReaderPort·VisionStorePort·ImageSnapshotPort·OcrUnavailable),
  `usecases/read_images.py`(파이프라인·dry-run·cap), `link_image_readings.py`(적재 준비), `ingest_image_readings.py`(캐시→DB),
  `vision_sample.py`(측정 harness); `adapters/vision/`(manifest·store·ocr_mac·_ocr_worker), `adapters/llm/vision_reader.py`(이미지 입력),
  `adapters/llm/rate_limiter.py`(공용 제한기, `openai_compat` 에 배선), `prompts/vision.md`; `composition.build_vision_reader/
  build_vision_ocr/build_vision_store/build_vision_snapshot/build_read_images/build_ingest_image_readings`.
- `_sandbox.run_parser` 변경: 자식을 `python -I -c <bootstrap>` 로 띄워 부모의 패키지 루트를 sys.path 에 넣는다(워크트리·편집 설치에서
  자식이 같은 코드를 쓰도록). `SandboxLimits.extra` 추가, `_worker.PARSERS["ocr_image"]`.
- 설정 키: `config/vision.yaml` — `cap`(2000) · `image_max_bytes` · `sample_per_type` · `paths.{snapshots,store,sample}` ·
  `filter.{min_width,min_height,min_pixels,max_aspect,max_repeat_pages,max_bytes,name_patterns,alt_patterns,skip_mime,skip_ext}` ·
  `order.{strategy,esg_policy,statistics,press}` · `ocr.{languages,max_bytes,max_pixels,timeout_sec}`.
  `config/llm.yaml` — `stages.vision: {provider: gemini, max_tokens: 3000}`, `providers.gemini.rate: {concurrency: 4, per_minute: 60}`
  (`config_loader.llm_config()["rate"]`, 없으면 gemini·openai 는 기본 4/60, mlx 는 None). pyproject extra `vision = [ocrmac, pillow]`, dev 에 pillow.
- CLI: `rra vision read [--snapshot <date>] [--dry-run] [--limit N] [--cap N] [--ocr-only] [--json]`,
  `rra vision sample [--snapshot] [--out docs/ocr-sample/] [--limit] [--per-type 30] [--cached-only]`,
  `rra vision ingest [--snapshot] [--dry-run] [--limit] [--json]`.
- 데이터 경로(미커밋): 입력 `data/korail_web/snapshots/<date>/manifest.jsonl`(+이미지, 형식 `docs/vision-manifest.md`),
  출력 `data/korail_web/ocr/<sha>.json`·`vision_cache/<sha>.json`(실패 포함 캐시)·`vision_log.jsonl`(hash·url·time·status — 키·본문 없음),
  표본 `docs/ocr-sample/`.
- 통합 세션 실행 순서 (크롤 완료 뒤, 모두 저장소 루트에서):
  1. `uv pip install --python .venv/bin/python -e ".[vision]"` (macOS; 리눅스면 OCR 없음 경로로 간다)
  2. `rra vision read --dry-run` → 유지/제외 건수(이유별), 계획 건수, 예상 호출 수 = min(cap, 유지 − 캐시) 확인. manifest 필드가
     다르면 `docs/vision-manifest.md` 별칭 표로 맞춘다.
  3. `rra vision read --ocr-only` → OCR 캐시만 먼저 채운다 (Argon 0건, 장당 ≈1초).
  4. `rra vision read --cap 2000` (큐 안에서, RRA_GEMINI_API_KEY 필요) → 호출 = 캐시에 없는 유지 이미지 수, 상한 초과분은 OCR 만 + 목록.
     남으면 같은 명령 반복(캐시 적중은 호출 0). 실패 해시를 다시 부르려면 `data/korail_web/vision_cache/<sha>.json` 삭제.
  5. `rra vision sample --cached-only --out docs/ocr-sample/` → 종류별 30건 나란히 + `summary.md`(구조화 성공률·숫자 대조 통과율·장당 시간·호출 수).
  6. `rra vision ingest --dry-run` → 문서·청크 수·건너뜀(`body_wins`·`no_text`·`unknown_source`) 확인 후 `rra vision ingest`.
     `unknown_source` 가 나오면 크롤 레인의 SourceType(`korail_web`) 추가가 먼저다 (페이지 문서의 `page_doc_id` 가 있으면 그 source 를 따른다).
- 프론트엔드 영향: `Chunk.basis`·`Document.text_basis` 에 새 값 `"image_vision"` — 라벨 `ui/labels.BASIS["image_vision"]="이미지 판독"`
  (Streamlit). 웹(web/)·REST `chunks_payload` 는 `basis` 를 그대로 내보내므로 화면은 `basis === "image_vision"` 이면 "이미지 판독" 배지를 붙이고
  원본 링크는 문서 `raw.image.url`(이미지)·`url`(페이지)에서 가져온다. `raw.image` 필드: `sha256, url, path, page_url, page_doc_id, image_type,
  status(argon|ocr_only|failed), ocr(bool), uncertain, confirmed_numbers, unconfirmed_numbers, width, height`. 본문 안 `[판독 확인 필요]`
  표식이 붙은 문장은 수치가 OCR 로 확인되지 않은 것 — 경고 색으로 보여 주면 된다. 검색 응답에 문서 raw 를 싣는 API 는 아직 없다(필요하면
  `views.chunks_payload` 에 `image` 필드 추가 — 통합 세션 결정).
- 남은 일: 실측(지표·임계치), 크롤 레인 source 추가 뒤 `unknown_source` 해소, OCR 리눅스 대안(없음 — 설계상 macOS 전용),
  `rra sources check` 에 vision 진단 추가(선택).
