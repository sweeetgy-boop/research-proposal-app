# ADR 0063 — 평가 체계 구현 결정 (레인 D, 2026-11-09, feat/wave-d-eval-system)

ADR 0058(초안)의 세 단계·봉인 묶음·신뢰구간을 구현하면서 정한 세부 결정. 계약(`docs/contracts/eval-results.md`)은 바꾸지 않았다.

## 배경
ADR 0058 은 지표·suite·명령을 정했지만 (1) L0 가 CI 에서 모델·DB 없이 무엇을 재는지, (2) 평가용 Gemini 호출이 운영 예산을 어떻게
피하는지, (3) 신뢰구간 방법, (4) 봉인 묶음의 쓰임(2026-11-09 사용자 지시로 바뀜), (5) 공용 파일을 건드리지 않는 조립 방식은 레인이 정해야 했다.

## 결정
1. **L0 = 합성 코퍼스 + 보정 유사도 + 캐시 재생.** `tests/eval/l0_corpus.jsonl`(가상 철도 과제 23건)을 메모리 저장소
   (`adapters/eval/l0_repo.py`)에 올리고, 유사도는 어절 해시 백오브워즈 코사인을 `0.78 + 0.22 × cos` 로 보정한다 — e5 의
   압축된 분포(무관 문서도 0.79 근처)처럼 own 임계치 0.80·키워드 조건이 뜻을 갖게. 재는 것은 검색 규칙·풀·판정 규칙·캐시 재생
   판정의 **회귀**이지 e5 품질이 아니다(그건 `--real`). 캐시는 정답표 대본(`tools/eval_l0_record.py --oracle`)으로 녹화했다 —
   실제 Gemini 응답은 `--record` 로 바꿀 수 있다.
2. **평가 예산 분리.** `composition.build_eval_llm` 은 운영 `build_llm` 의 `BudgetedLLM`(일일 600, `llm_budget.json`)을 거치지 않고
   `_build_openai_compat` 로 원 어댑터를 만든 뒤 **별도 카운터** `data/cache/eval_llm_budget.json`(`eval.yaml daily_llm_calls` 150)으로
   감싼다. 소진되면 `BudgetExhausted` → SameJudge 가 로컬(judgment.local_stage) → 규칙으로 내려가고 결과 `notes` 에 적는다.
   과제안 호출도 같은 LLM 을 쓰며 `recommender.metrics = None` 으로 운영 측정 줄을 오염시키지 않는다.
3. **ci95 = 문제별 반복 평균의 부트스트랩**(복원 추출 2,000회, seed 고정, 2.5·97.5 백분위). 반복 ≥ 2 일 때만. 비교는 구간
   겹침이면 "차이 없음".
4. **봉인 묶음은 보고서용 최종 확인 1회.** 스위치 판단(가·나·다)은 연습용 묶음(같은 seed)으로 — `docs/eval-protocol.md` §4,
   `rra eval run` 도움말, `--sealed` 실행 경고 한 줄.
5. **공용 파일 불변.** `cli.py`·`ports/__init__.py`·`api/app.py` 를 고치지 않는다. 명령은 `entrypoints/cli_eval.py` 의
   `register(sub, eval_parser)` + 독립 `main()`(`python -m rra.entrypoints.cli_eval`) — CI·launchd 는 이 형태. 통합 때 메인이
   cli.py 에 두 줄을 넣는다.
6. **핵심어는 규칙만.** 평가 ② 는 Argon 키워드를 부르지 않고 `LiveKeywordMaker(primary=None, local=None)`(운영의 규칙 대체
   경로와 같은 결과)을 쓴다 — 예산을 판정·과제안에 남기고 네트워크 변동을 뺀다(`config_flags.keywords = rule`).
7. **문제 재료에서 internal 문서 제외.** 공개 요약만 있는 알리오 5건의 internal 문서는 원격 판정에 보내지 않기 위해 뺀다.
8. **실시간 검색 미사용.** 평가는 저장 자료만 본다(novel 갈래의 새로움 확인·유추 검색도 저장 자료만).

## 이유
- CI 는 모델·DB·키가 없다. 규칙 회귀만이라도 PR 마다 잡는 쪽이 아무것도 안 재는 것보다 낫다(ADR 0058 "LLM 캐시 재생").
- 운영 예산 600 은 시범 사용자용이다. 야간 평가가 그것을 깎으면 아침 Argon 이 막힌다.
- 봉인 묶음을 비교에 반복해서 쓰면 그 자체가 과적합 통로가 된다(사용자 지시).

## 결과
- 좋은 점: PR 마다 L0 20건 0.1초, 야간 L1 자동, 비교표 한 명령. 운영 예산·측정 줄·DB 에 영향 없음.
- 비용: L0 캐시는 판정 프롬프트가 바뀌면 다시 녹화해야 한다(미스는 notes 에 보인다). 합성 유사도는 실물과 다르다.
- 남은 것: 실제 Gemini 로 L1 100건(메인 2차), 임계치(±0.05) 2주 뒤 조정, 봉인 묶음 생성(`rra eval seal`), L0 캐시를 실응답으로 교체.
- 상태: 구현 완료(PR 대기), ADR 0058 확정은 메인.
