# ADR 0019 — 공사 홈페이지·정부 정책 자료 수집: 스냅샷 방식과 쓰임 범위 (2026-10-27)

## 배경
정책적 중요도(2-가-(1))·경영전략 정합성(2-가-(3))의 근거가 제안자 입력뿐이었고 전략체계 목록(`korail_strategy.yaml`)은
비어 있었다. 공사 홈페이지와 국토교통부 정책자료에 근거가 공개돼 있다.

## 선택지
1. `www.korail.com` 을 Playwright 로 렌더해 수집 — JS 번들 SPA, 헤드리스에서 본문이 뜨지 않고 봇 보호층이 있다.
2. 회사소개 사이트 `info.korail.com/info/`(서버 렌더 HTML)만 수집 — robots 빈 파일, 저작권정책 공공저작물 자유이용, 본문 공공누리 제4유형.
3. 예약(launchd) 수집 vs 사람이 돌리는 스냅샷.
4. 정책·보도자료를 다른 자료와 같이 유사과제 판정·기술 근거에 쓰기 vs 용도 제한.

## 결정
- 2: `info.korail.com` 만 `allowed_domains` 에 넣고 GuardedClient(2초 간격·동시 1·robots)로 받는다. 봇 보호층은 우회하지 않는다.
- 3: 예약 없음. `rra crawl korail --explore|--download [--incremental]` 스냅샷(`data/korail_web/snapshots/<날짜>/`), 사라진
  항목은 "원본 삭제됨" 표시만. 보도자료는 최근 5년, 사진 첨부는 이름만(용량 10GB 초과 추정).
- 4: `policy`(경영·전략·ESG·정책·현황)는 정책적 중요도·경영전략 정합성·정책 근거 추천에만, `korail_news` 는 특이사항·현황
  보조에만. 둘 다 유사과제 판정(`find_similar`)과 기술적 중요도 근거에서 뺀다(`domain/rules/retrieval_scope.py`,
  `NON_OVERLAP_SOURCES`). 섹션별 혼합 비율은 retrieval_mix.yaml(통합 세션).
- 전략체계는 "중장기 경영목표" 표에서 뽑은 초안(`korail_strategy.draft.yaml`, basis text, 항목마다 출처)을
  `strategy.yaml source: draft` 로 쓰고 화면·API 에 "전략체계 초안(확인 전)" 을 붙인다. 확정은 사람이 `rra strategy promote`.
- 정책 근거 추천은 LLM 없이 키워드 겹침 문장을 고르고, 제안자가 고른 것만 `policy_basis` 에 들어간다(자동 삽입 없음).
  정책적 중요도의 근거 규칙(입력만)은 그대로다.
- 국토교통부 정책자료는 같은 원칙으로 `molit` 어댑터(판 추적: 제N차 최신만 현행, 구판 `valid_until`).

## 이유
공개·서버 렌더 자료만, 봇 보호 우회 없음, 사람이 통제하는 스냅샷, 정책 문서가 유사과제 판정을 오염하지 않게.

## 결과
`adapters/sources/korail_web/`·`molit/`, `rra crawl korail`, `rra strategy draft/promote`, `rra policy-suggest`,
`POST /v1/ideas/policy-suggestions`, `GET /v1/sources/status` 스냅샷 표시, 테스트 1,300 통과. 경과는 `docs/korail-web-crawl.md`.
