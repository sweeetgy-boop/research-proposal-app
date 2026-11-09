# 계약 — 평가 결과 형식·suite·명령 (ADR 0058, 2026-11-09, 레인 D)

모델: `src/rra/domain/models/eval_result.py`(`EvalResult`·`EvalMetrics`·`CI95`, `METRIC_KEYS`·`SUITES`). 바꾸려면 이 파일부터.

## 1. 결과 파일
`eval/results/<YYYY-MM-DD>-<suite>[-<label>].json` — `EvalResult.model_dump()` 하나. 예:
```json
{
  "suite": "l1", "seed": 20261109, "n": 120, "repeats": 3,
  "metrics": {"recall_at5": 0.87, "false_block": 0.05, "novel_rate": 0.92,
              "novel_estimated_barrier_ratio": 0.45, "latency_p50": 41.2, "latency_p90": 78.0, "rec_zero_rate": 0.03},
  "ci95": {"recall_at5": {"low": 0.81, "high": 0.92}, "false_block": {"low": 0.02, "high": 0.09}},
  "config_flags": {"facets.enabled": false, "idf_weighting.enabled": false, "synonyms.enabled": false,
                   "judgment.enabled": true, "rerank.threshold": 0.5},
  "label": "가-main", "commit": "3f31de6", "started_at": "2026-11-09T22:30:00+09:00", "seconds": 912.4,
  "sealed": false, "llm_calls": 240, "cache_hits": 0, "notes": []
}
```
- 지표는 숫자만. 문제 본문·과제명·doc_id·사용자/소유자 식별자·아이디어 해시는 결과 파일에 쓰지 않는다(보안 D).
- `eval/results/` 는 git 에 커밋한다(수치만이라 공개 가능). 문제 묶음은 커밋하지 않는다(아래 3).
- `ci95` 는 지표 이름 키. `repeats` ≥ 2 인 지표만 구간이 있다. 못 구하면 키를 빼거나 `{low: null, high: null}`.

## 2. 지표 정의 (문제 종류 → 지표)
| 문제 종류 | 정답 | 지표 |
|---|---|---|
| 역방향(reverse) — DB 의 실제 과제(사내·NTIS 과제·알리오)를 제목 단어 없이 아이디어로 바꿔 씀 | 원래 과제 doc_id 가 ② 상위 5행 | `recall_at5`, `reverse_block`(차단된 비율 — 정답을 유사과제로 잡았는가, 높을수록 좋음; 2026-11-09 사용자 요청, idf 켬 판단 기준) |
| 함정(trap) — 과제 A 의 대상 × 과제 B 의 방법 | 차단되지 않음 | `false_block`(차단된 비율) |
| 새 영역(novel) — 유사 과제가 없을 아이디어 | `recommend_mode == novel` | `novel_rate`, `novel_estimated_barrier_ratio`, `rec_zero_rate` |
| 모두 | — | `latency_p50`·`latency_p90`(② 표+판정, L1 은 과제안 포함 여부를 `config_flags.with_recommend` 로 적는다) |

- 역방향 문제의 "제목 단어 없이": 과제 제목의 명사 토큰(`domain/rules/keywords.tokenize` 기준)을 아이디어 본문에서 뺀다.
  정답 과제 자체가 후보에 있으므로 `recall_at5` 는 검색·판정 품질을 잰다. 개인정보 칸(이름·연락처)은 읽지 않는다.
- `false_block` 은 함정 문제에서 `effective_blocking` 참인 비율. 새 영역 문제가 차단되면 그것도 센다(둘을 `notes` 에 나눠 적어도 된다).
- AI 흔들림: L1 은 같은 문제를 `repeats`(기본 3)회 돌려 평균, `ci95` 는 문제별 평균의 부트스트랩 또는 정규 근사(방법은 레인 D 가 정하고 `notes` 에 한 줄).

## 3. 문제 묶음 (레인 D)
- 생성기: `usecases/eval_problems.py`(새) — seed 로 DB 에서 뽑는다. 매 실행 새 seed(기본 오늘 날짜 숫자).
- **시험용 봉인 묶음**: seed 고정(`config/eval.yaml sealed_seed`), 파일 `data/eval/sealed/<suite>.jsonl` 권한 600, `.gitignore`.
  개선 작업(레인 E·A) 중에는 열지 않는다 — `rra eval run --sealed` 만 읽고, 결과에는 수치만(`sealed: true`). 문서 `docs/eval-protocol.md` 에 명시.
- **연습용 묶음**: `data/eval/practice/<suite>-<seed>.jsonl`, 자유롭게 본다. **스위치를 켤지 판단하는 비교(가·나·다)는 연습용 묶음으로 한다**
  (2026-11-09 사용자 조정). 봉인 묶음은 판단이 끝난 뒤 최종 확인(보고서용 수치)에 **한 번만** 쓴다.
- `test: true` 줄(시험 계정)은 실사용 기록 지표에서 뺀다. 실사용 기록 지표(`similar_choices.jsonl` source=user 의 AI 판정 일치율,
  `recommend_metrics.jsonl` 의 채택률·갈래별)는 `rra eval usage` 로 따로 내고 `EvalResult.notes` 가 아닌 별도 JSON(`eval/results/<날짜>-usage.json`)에 쓴다.

## 4. suite
| suite | 언제 | 범위 | 시간 목표 | LLM |
|---|---|---|---|---|
| l0 | PR 마다(CI job `eval-l0`) | 검색·판정만(과제안·초안 없음), 고정 문제 20건 안팎(`tests/eval/l0_problems.jsonl` — 합성·공개 자료만) | 1~2분 | 없음 — LLM 응답은 캐시 재생(프롬프트 해시 키 `tests/eval/l0_cache/`), 캐시 없으면 규칙 판정 |
| l1 | 매일 밤(launchd `com.rra.eval.plist`, 04:30 — 백업 03:30 뒤) | 자동 생성 ≥100건, 3회 평균, 과제안 포함 | 10~20분 | Gemini 는 `config/eval.yaml daily_llm_calls`(기본 150) 안에서만 — 넘으면 남은 문제는 로컬·규칙, `notes` 에 적음 |
| l2 | 배포 전·주 1회(사람이 돌림) | 골든셋 10건(`tests/golden`) + 초안까지(기존 `rra eval` 재사용), 사람 확인 표본 10% 목록 출력 | — | 기존 예산 |

## 4.1 짝 비교 (2026-11-09 사용자 보완)
- 결과 파일에 `problems: [{id, kind, correct, runs, correct_runs, blocked, seconds}]`(모델 `ProblemRecord`) — `id` 는 문제 id 의
  sha256 앞 16자(본문·doc_id 없음), `correct` 는 종류별 정답 기준(역방향 = 상위 5 적중, 함정 = 차단 안 됨, 새 영역 = novel 갈래)·반복이면 과반.
- `rra eval compare` 는 기준 열과 같은 문제 id 를 가진 열에 대해 **문제별 맞힘 대조**(둘 다·기준만·비교만·둘 다 틀림, 종류별)와
  **McNemar 정확 검정(양측)** p 를 표에 더한다(`domain/rules/eval_compare.paired`). p < 0.05 면 갈린 쪽이 많은 구성을 개선/악화, 아니면 차이 없음.
- 비교 묶음 구성(스위치 판단용 40문제): 역방향 ≥ 20·함정 ≥ 12·새 영역 ≥ 8 → `rra eval run --n 40 --mix 0.5,0.3,0.2`(새 묶음을 만들 때만).
- 3회 반복은 두 구성의 결과가 **갈린 문제만**: `compare --discordant-out ids.txt` → `run --ids @ids.txt --repeats 3`(두 구성 모두). 예산 150 안에서.

## 5. 명령
- `rra eval run --suite l0|l1|l2 [--seed N] [--sealed] [--repeats N] [--label 이름] [--out 경로]` → 결과 JSON 경로 출력.
- `rra eval compare <a.json> <b.json> [<c.json> …] [--out docs/eval-<날짜>-compare.md]` → 지표별 열 비교표(값·ci95·차이), 한국어.
- `rra eval usage [--since 날짜] [--include-test]` → 실사용 기록 지표.
- 기존 `rra eval [--label …]`(초안 품질 측정)은 그대로 둔다 — 서브명령이 없으면 종전 동작.

## 6. CI
`eval-l0` job: backend 와 같은 venv, `rra eval run --suite l0 --out eval/results/ci-l0.json`(커밋 안 함) 뒤 `tools/eval_gate.py`
가 직전 main 결과(`eval/results/latest-l0.json`)와 비교해 `recall_at5` 가 0.05 넘게 떨어지거나 `false_block` 이 0.05 넘게 오르면 실패.
`latest-l0.json` 은 main 병합 뒤 통합 담당이 갱신한다.
