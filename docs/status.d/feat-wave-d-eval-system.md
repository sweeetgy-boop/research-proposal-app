# feat/wave-d-eval-system (2026-11-09, 레인 D, ADR 0058·0063) 전달 사항

## 전달한 것
- **계층별 모듈** — domain: `models/eval_problem.py`(EvalProblem·NovelTopic·ProblemMix·EvalSuiteConfig), `rules/eval_problems.py`(역방향·함정·새 영역 만들기, 제목 토큰 제거),
  `rules/eval_metrics.py`(평균·p50·p90·부트스트랩 ci95·종류별 지표), `rules/eval_compare.py`(비교 행·판정·게이트), `rules/eval_usage.py`(실사용 지표).
  application: `ports/eval_store.py`(결과·문제 저장·CacheMiss·재생 카운트 — `ports/__init__.py` 미반영), `usecases/eval_problems.py`(ProblemGenerator, CorpusAccessPort 로 DB 읽기),
  `usecases/evaluate_suite.py`(EvaluateSuite, `l2_from_quality`), `usecases/eval_usage.py`. adapters: `adapters/eval/{results,problem_store,llm_cache,l0_repo}.py`.
  entrypoints: `cli_eval.py`(`register(sub, eval_parser)` + 독립 `main`), `views_eval.py`(한국어 비교표). composition: `build_eval_stores`·`build_eval_llm`·`build_eval_precheck`·
  `build_problem_generator`·`build_eval_suite`·`build_eval_usage`. config_loader: `eval_config`·`eval_config_flags`, 데이터 위치 `eval_sealed`·`eval_practice`·`eval_llm_budget`.
- **설정** `config/eval.yaml`(sealed_seed 20261109, daily_llm_calls 150, l0·l1·l2, novel_topics 18). **문서** `docs/eval-protocol.md`, ADR 0063.
- **CI** `eval-l0` job(`python -m rra.entrypoints.cli_eval run --suite l0` → `tools/eval_gate.py`), 기준 `eval/results/latest-l0.json`(이 PR 에서 처음), `ci-l0.json` 은 .gitignore.
- **launchd** `deploy/launchd/com.rra.eval.plist`(04:30, heavy lock 경유, 원 저장소 경로), 검사 `tests/deploy/test_eval_plist.py`, `deploy/README.md` §2 한 절.
- **L0 fixture** `tests/eval/l0_corpus.jsonl`(합성 23건)·`l0_problems.jsonl`(20건)·`l0_cache/`(정답표 대본 20건), 도구 `tools/eval_l0_record.py`.

## 공용 파일 — 통합 때 메인이 반영
- `src/rra/entrypoints/cli.py`: import 한 줄 + `register_eval(sub, ev)` 한 줄 (PR 설명의 코드 조각).
- `src/rra/application/ports/__init__.py`: `EvalResultStorePort`·`ProblemStorePort`·`CacheMiss`·`ReplayCountsPort` export (선택).
- `rra eval seal --suite l1`(봉인 묶음), `com.rra.eval.plist` 설치, `latest-l0.json` 은 main 병합 뒤 갱신.

## 수치
- L0 20건(역방향 10·함정 6·새 영역 4) 0.1초: recall@5 0.90 · false_block 0.00 · novel 1.00 · 캐시 적중 20/20.
- 가짜 LLM(RRA_FAKE_LLM=1) L1 20건 × 1회 시운전(운영 DB·e5·reranker, heavy lock): 벽시계 1,017초(문제 생성 포함, 실행 964.5초), recall@5 0.833 · false_block 0.000 · 지연 p50 29.99s · p90 63.65s(과제안 포함). novel_rate 0 은 가짜 판정 대본 탓(가짜 모드 한정).
- pytest +53 (domain 15 · application 8 · adapters 4 · entrypoints 8 · deploy 2 … ), lint-imports 8 KEPT.

## 남은 것
- 실제 Gemini 로 L1 100건 × 3회(메인 2차), 임계치 ±0.05 는 2주 뒤 조정, L0 캐시를 실응답으로 교체(`--record`), 봉인 묶음 생성.
