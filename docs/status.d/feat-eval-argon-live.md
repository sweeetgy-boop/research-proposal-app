## [5] 통합 측정 도구 — `rra eval` 확장 (feat/eval-argon-live, 2026-10-28)

- 목적: Argon 먼저 작성(ADR 0032)·실시간 검색(레인 C)·그림을 켠 구성 B/C 와 동시 3건을 골든셋 10건으로 재고, 아침
  로컬 작성 측정(`data/eval/f1_fallback2.json`, docs/eval-2026-10-28.md)과 한 표로 비교한다. 이 레인은 도구·테스트만(실측 없음).
- `usecases/evaluate.py`
  - 시간: `precheck_seconds`(②), `draft_seconds`(제출 → 생성 실행 작업 종료 — 그림 포함, 자동 1차 검토 제외), `seconds`(전체).
  - ⑤ `final_review=True`: `final_review_status`·`final_scores`(기준별)·`final_score_avg`·`final_review_seconds`. 거부·예산 소진은
    `error:<예외 이름>`.
  - ⑥ `finalize=True`: 선택형은 제안값, `ProposerInfo(department=철도연구원)` 렌더 인자로만 → `finalized`·`hwpx_bytes`·`hwpx_ok`
    (`adapters/rendering/hwpx.hwpx_ok` = zip + 섹션 XML defusedxml 재파싱)·`figure_placements`·`finalize_error`.
  - 품질(측정 끝 상태): `valid`(drafted 이후 상태), `empty_draft`·`empty_required_sections`, `number_alerts`(`unsupported_number`),
    `review_mismatch`(검토 support "불일치", 1차 검토에만 있음), `local_evidence_mismatch`, `local_check_mismatches`·`local_check_skipped`.
  - 실시간(레인 C 필드를 방어적으로 읽음 — 없으면 0·빈 값): `live_citations()` 인용 문서 단위 (citation `live` 또는 문서
    `raw.live`), `live_sources()` ← `state.live_search.sources`, 합계 `source_stats()` = 자료원별 runs·failures·failure_rate(status≠ok)·
    seconds_avg·count_sum.
  - 동시: `concurrent=N` — N건씩 precheck 는 차례로, 제출은 한꺼번에(같은 RunManager, runs.max_concurrent·max_queued_runs 그대로),
    `batches[{ideas, draft_seconds(묶음 첫 제출 → 마지막 생성 완료), seconds}]`. 본보기 제외는 묶음 정답의 합집합.
  - 결과 `config`(writer·local_check·figures·first_pass·final_review·finalize·concurrent·max_concurrent), `mode`.
- CLI: `--final-review`, `--finalize`(⑤ 포함), `--concurrent N`, `--local-check on|off`(llm.yaml 덮어쓰기, 설정 파일은 그대로),
  `--department`. 조립 `build_eval(final_review, finalize, concurrent, local_check, department)`.
- 비교표 `views.eval_markdown`: "### [5] 통합 비교"(구성마다 한 줄 — 실행 방식, ②·생성·전체 시간, 유효율, 빈 초안, 최종 점수,
  수치 알림, 근거 불일치 검토/로컬, 실시간 비율, 유사과제 적중, 자료원별 응답·실패율, 그림 성공률, Gemini 작성·검토·그림, HWPX) +
  기준별 최종 점수 + "### 아이디어별 [5] 통합 측정". 예전 JSON 은 없는 칸 "-", 유효율은 ideas − invalid, Gemini 는 아이디어별
  fallback_calls·gemini_calls 로 맞춘다. 기존 표는 그대로.
- 측정 명령(통합 담당):
  ```bash
  tools/with_heavy_lock.py -- .venv/bin/rra eval --label argon_b --local-check off --finalize
  tools/with_heavy_lock.py -- .venv/bin/rra eval --label argon_c --local-check on --finalize
  tools/with_heavy_lock.py -- .venv/bin/rra eval --label argon_b_c3 --local-check off --finalize --concurrent 3
  .venv/bin/rra eval --report data/eval/f1_fallback2.json data/eval/argon_b.json data/eval/argon_c.json \
      data/eval/argon_b_c3.json --out docs/eval-2026-10-28.md --append
  ```
  실시간 검색·그림 켜기는 각 설정 파일(레인 C 설정·`config/figures.yaml enabled`)로. Gemini 예산: 한 건에 작성 섹션 수 + 최종 검토 1 +
  그림 호출 — 10건 × 3구성이면 일일 600 안인지 먼저 확인.
- 테스트: `tests/application/test_evaluate_integrated.py`(10건), `test_cli.py` 플래그 전달 1건, `test_hwpx_renderer.py` hwpx_ok 1건.
