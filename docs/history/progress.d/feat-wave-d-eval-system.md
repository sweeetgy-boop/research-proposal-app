# 진행 메모 — feat/wave-d-eval-system (레인 D)

- 13:40 계약·ADR 0058·기존 측정(evaluate.py·cmd_eval)·precheck·similar_rows·judge_sameness·daily_budget·feedback 읽기 끝. 운영 DB 자료원 건수·본문 길이 확인(읽기 전용): own 1,119(초록 중앙값 141자, 150자 이상 232건) · alio 120 · ntis rnd_project 2,283.
- 14:10 domain(eval_problem 모델, eval_problems·eval_metrics·eval_compare·eval_usage 규칙) · application(ports/eval_store, eval_problems·evaluate_suite·eval_usage 유스케이스) · adapters/eval 4종 작성.
- 14:25 조정 반영: ports/__init__.py·cli.py 불변 → `cli_eval.register(sub, eval_parser)` + 독립 main. 봉인 묶음 = 최종 확인 1회(문서·도움말·경고).
- 14:35 config/eval.yaml·config_loader(eval_config·flags·데이터 위치)·composition build_eval_* ·views_eval·tools/eval_gate·eval_l0_record. 합성 코퍼스 23건 → L0 문제 20건·대본 캐시 20건. L0 0.1초: recall@5 0.90 · false_block 0.00(대본 오라클 수정 전 1.00 → 문제별 정답 집합으로 고침).
- 14:50 테스트 5파일(+53) · plist · CI job · gitignore · 문서(eval-protocol, ADR 0063, 조각 3). lint-imports 8 KEPT.
- 15:05 전체 pytest 2,753 passed(edit_ai 3건은 시운전과 동시 실행 때만 시간 초과, 단독 통과). 가짜 LLM L1 20건×1회 시운전 1,017초 (recall@5 0.833 · false_block 0 · p50 29.99s). llm_calls 는 마른 캐시 미스를 빼도록 고침. compare 예시(캐시 vs 규칙) 확인.
- 다음: 커밋·푸시·PR(병합 안 함).
