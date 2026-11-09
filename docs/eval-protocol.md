# 평가 절차 — L0·L1·L2 와 봉인 묶음 (ADR 0058, 2026-11-09)

계약: `docs/contracts/eval-results.md`(결과 형식·지표·suite·명령), 모델 `src/rra/domain/models/eval_result.py`.
구현(레인 D): 문제 생성 `application/usecases/eval_problems.py`(규칙 `domain/rules/eval_problems.py`), 실행
`application/usecases/evaluate_suite.py`(지표 `domain/rules/eval_metrics.py`), 비교 `domain/rules/eval_compare.py`,
어댑터 `adapters/eval/`(결과 JSON·문제 JSONL·LLM 캐시·L0 메모리 저장소), 명령 `entrypoints/cli_eval.py`,
설정 `config/eval.yaml`.

## 1. 세 단계

| suite | 언제 | 문제 | LLM | 명령 |
|---|---|---|---|---|
| **L0** | PR 마다 (CI job `eval-l0`, 1~2분) | 고정 20건 `tests/eval/l0_problems.jsonl` — 합성 코퍼스 `tests/eval/l0_corpus.jsonl` 23건(가상 철도 과제, own·alio·ntis) | 없음. 판정 응답은 캐시 재생(`tests/eval/l0_cache/`, 프롬프트 sha256 키) — 미스면 규칙 판정 | `rra eval run --suite l0` |
| **L1** | 매일 04:30 (`deploy/launchd/com.rra.eval.plist`, heavy lock 경유) | 운영 DB 과제형 자료원(own·alio·ntis rnd_project, internal 제외)에서 seed 로 자동 생성 120건(역방향 60% · 함정 25% · 새 영역 15%), 같은 문제 3회 | Gemini 는 `config/eval.yaml daily_llm_calls`(150) 안에서만 — 카운터는 운영 예산(600)과 **다른 파일** `data/cache/eval_llm_budget.json`. 넘으면 로컬(judgment.local_stage) → 규칙 | `rra eval run --suite l1 [--seed N] [--repeats 3]` |
| **L2** | 배포 전·주 1회 (사람) | 골든셋 10건(`tests/golden`) + 초안 — 기존 `rra eval --label …` 을 그대로 감싼다 | 기존 예산 | `rra eval run --suite l2` → 사람 확인 표본 10%(run id) 출력 |

통합 전(cli.py 에 `register` 두 줄이 들어가기 전)에는 `python -m rra.entrypoints.cli_eval run …` 이 같은 명령이다.
CI 와 launchd 는 이 형태를 쓴다.

## 2. 문제 종류와 정답 (계약 §2)

- **역방향(reverse)** — 실제 과제의 초록(없으면 본문)에서 **제목의 명사 토큰**(`keywords.query_keywords`: 조사 제거·일반어·숫자·
  한 글자 제외, 접두 일치로 "자산개발을"도 뺀다)을 뺀 글을 문장 단위로 현황·원인·한계·목표 네 칸에 나눈다. 가제는 비운다.
  정답 = 원래 과제 doc_id(연작·같은 제목 판은 `merged_ids` 로 같은 행). 지표 `recall_at5`.
- **함정(trap)** — 과제 A 의 앞 절반(대상·문제) + 과제 B 의 뒤 절반(방법·목표). 두 과제의 토큰 자카드가 0.15 이상(같은 주제)이면
  버린다. 두 과제 모두 제목 토큰을 뺀다. 차단되면 오답 → `false_block`.
- **새 영역(novel)** — `config/eval.yaml novel_topics`(철도 밖 합성 주제 18개)에서 뽑되, 생성기가 **규칙 판정**(LLM 없음)으로
  유사 과제가 없는지 미리 확인해 차단되는 주제는 뺀다. 정답 = `recommend_mode == novel` → `novel_rate`; 과제안을 돌리면
  `rec_zero_rate`·`novel_estimated_barrier_ratio`. 새 영역 문제가 차단되면 `false_block` 분모에 넣지 않고 `notes` 에 따로 센다.
- 모든 문제: `latency_p50`·`p90`(② 검색+판정, L1 은 과제안 포함 — `config_flags.with_recommend`).
- 생성기는 문서의 제목·초록·본문만 읽는다 — 이름·연락처·사번 칸은 쓰지 않는다. 문제 id 는 doc_id 를 노출하지 않는 해시.

## 3. 반복·신뢰구간

L1 은 같은 문제를 `repeats`(기본 3)회 돌려 문제별 평균을 내고, 지표는 그 평균의 평균이다. `ci95` 는 문제별 평균 벡터를
복원 추출 2,000회 부트스트랩한 평균의 2.5·97.5 백분위(seed 고정 → 재현). 반복 1회(L0·L2)에는 구간이 없다.
`rra eval compare` 는 구간이 겹치면 **"차이 없음"**, 겹치지 않으면 방향에 따라 "개선"/"악화", 구간이 없으면 "구간 없음"(차이 값만).

## 4. 봉인 묶음 — 열람 금지, 최종 확인 1회

- `rra eval seal --suite l1` 이 `config/eval.yaml sealed_seed` 로 묶음을 만들어 `data/eval/sealed/l1.jsonl`(폴더 700·파일 600,
  `.gitignore` 의 `/data/` 아래)에 둔다. 이미 있으면 덮어쓰지 않는다(`--force` 만).
- **개선 작업(레인 E·A 등) 중에는 봉인 묶음을 열지 않는다.** 파일을 cat·편집기로 보지 않고, 문제 본문을 로그·PR·이슈에 옮기지
  않는다. 결과 파일에는 수치만(`sealed: true`), 문제 본문·doc_id 는 없다.
- **쓰임(2026-11-09 사용자 지시)**: 스위치를 켤지 판단하는 (가) main off · (나) 레인 A 적용 off · (다) E 스위치 on 비교는
  **연습용 묶음**(`data/eval/practice/l1-<seed>.jsonl`, `--seed` 를 같게)으로 한다. 봉인 묶음(`--sealed`)은 판단이 끝난 뒤
  **보고서용 최종 확인 한 번만** 쓴다. `--sealed` 실행은 "봉인 묶음 — 보고서용 최종 확인 1회" 경고 한 줄을 낸다.
- 연습용 묶음은 자유롭게 본다. 같은 seed 면 같은 묶음(재사용), 야간 L1 은 그날 날짜 seed 로 새 묶음을 만든다.

## 5. 비교 절차 (가·나·다)

```bash
# 같은 seed 의 연습용 묶음으로, 구성마다 한 번씩 (각 ≈10~20분, Gemini ≤150회/일 → 하루 한 구성이 안전)
rra eval run --suite l1 --seed 20261110 --label 가-main        # main, 스위치 off
rra eval run --suite l1 --seed 20261110 --label 나-laneA        # 레인 A 적용, 스위치 off
rra eval run --suite l1 --seed 20261110 --label 다-switch-on    # overlap.yaml facets·idf_weighting·synonyms on
rra eval compare eval/results/2026-11-10-l1-가-main.json eval/results/2026-11-10-l1-나-laneA.json \
                 eval/results/2026-11-10-l1-다-switch-on.json --out docs/eval-2026-11-10-compare.md
# 판단이 끝난 뒤 보고서용 최종 확인 한 번
rra eval run --suite l1 --sealed --label 최종
```
`config_flags` 에 `facets.enabled`·`idf_weighting.enabled`·`synonyms.enabled`·`judgment.enabled`·`series.enabled`·`rerank.threshold`·
`rerank.enabled`·`llm`·`with_recommend`·`keywords` 가 적힌다(열거값·불리언·숫자만).

## 6. L0 게이트 (CI)

`eval-l0` job: `python -m rra.entrypoints.cli_eval run --suite l0 --out eval/results/ci-l0.json` 뒤 `tools/eval_gate.py` 가
`eval/results/latest-l0.json`(직전 main) 대비 `recall_at5` −0.05 초과 하락 또는 `false_block` +0.05 초과 상승이면 실패.
`latest-l0.json` 은 main 병합 뒤 통합 담당이 `rra eval run --suite l0 --out eval/results/latest-l0.json` 으로 갱신해 커밋한다
(기준 파일이 없으면 게이트는 안내만 하고 통과). 임계치는 첫 2주 분포를 보고 조정(ADR 0058).

L0 캐시는 판정 프롬프트 전체의 해시가 키라 **프롬프트·후보 선정이 바뀌면 미스**가 난다 — 그때 결과 `notes` 의 "미스 n건"이
늘고 판정이 규칙으로 바뀐다. 합성 코퍼스는 보정 유사도가 높아 규칙만으로는 함정이 모두 차단된다(2026-11-09 측정: 캐시 재생
false_block 0.00 → 캐시 없음 1.00, novel_rate 1.00 → 0.75) — 즉 **미스가 나면 게이트가 떨어지도록** 되어 있다.
의도한 변경이면 `tools/eval_l0_record.py --oracle`(정답표 대본) 또는
`rra eval run --suite l0 --record`(평가 예산 Gemini)로 캐시를 다시 녹화해 함께 커밋한다. 현재 캐시는 **정답표 대본**이다
(실제 Gemini 응답이 아님 — 합성 코퍼스에서 정답 과제만 same).

## 7. 실사용 기록 지표

`rra eval usage [--since YYYY-MM-DD] [--include-test]` → `eval/results/<날짜>-usage.json`. 선택 기록은 `source=user`·시험 줄 아님만
(AI 기본 선택과의 일치율), 과제안 측정은 시험 줄 아님만(갈래별 건수·0건 비율·중앙값·로컬 대체 비율). 결과에 doc_id·해시·시각 없음.

## 8. 하지 않는 것

- 평가는 실시간 검색을 쓰지 않는다(네트워크 변동 배제). 운영 DB 는 읽기만. 평가 과제안 호출은 운영 측정 줄
  (`recommend_metrics.jsonl`)에 남기지 않는다.
- 문제 묶음·캐시에 사내 본문이 들어가는 것은 L1 연습·봉인 묶음(데이터 폴더, 600)뿐이다. `tests/eval/` 의 L0 자료는 모두 합성.
