# ADR 0021 — [P2] 보류 자료원의 수집 경로와 쓰임 범위 (2026-10-27, 레인 E)

## 배경
레인 A(ADR 0019)가 보류한 자료원: 발주 연구용역 공고(ebid.korail.com, POST 폼), 감사원 감사결과(JS 렌더·robots `/api/` 금지),
철도 안전 통계(railsafety 시간 초과·KOSIS 키), 운영·수송 통계(API 키), 경영평가 개선 권고. 사람에게 묻지 않고 자동 판단 규칙으로 처리해야 했다.

## 선택지
1. ebid.korail.com 목록 POST 를 흉내 내 수집 vs 나라장터 공개 API(키).
2. 감사원 내부 `/api/` 를 직접 호출 vs Playwright 로 공개 화면만 조작 vs 보류 유지.
3. 통계: KOSIS·공공데이터포털 API(키) vs 공공데이터포털 파일데이터(키 없음).
4. 경영평가: 알리오 기관별 평가보고서 vs 기재부 보도자료(총괄 결과).
5. 발주 용역 공고를 유사과제 판정에 넣을지, 어떤 티어·상태로 보일지.

## 결정
- 1: ebid 는 GET 목록 "총 0 건", POST 1회도 행 없음(JS 적재), 상세 로그인 전용, 약관 확인 불가 → "불명확" → **나라장터 API(`g2b`)**.
  키 `RRA_DATA_GO_KR_KEY` 는 scienceon·ntis·kipris 와 같은 MissingCredential 경로. 과업 개요(공고서 첨부)는 호스트 미정이라 보류.
- 2: **Playwright 공개 화면 조작**. 검색어 입력·제목 클릭·파일 클릭만 하고 `/api/` URL 은 만들지 않는다(페이지 자체 XHR 은 브라우저 동작).
  srno 는 페이지가 받은 목록 JSON 에서 읽는다. 2초 간격·동시 1·백오프·보류 규칙은 korail_web 과 같다. 공공누리 4유형을 `raw.terms` 에 기록.
  국정감사 지적사항은 감사원 밖(국회)이라 보류 — "공개 보고서 파일만" 규칙.
- 3: **파일데이터(키 없음)** 를 1차 경로로. 상세 페이지의 "로그인 없이 다운로드"·"이용허락범위 제한 없음" 표기와 2단계 내려받기 확인. 표는 앞 400행만 본문에.
- 4: **기재부 보도자료(총괄 결과·등급표)**. 공사별 개선 권고 본문(평가보고서)은 알리오 항목이라 보류. 담당자 정보는 strip_pii.
- 5: `procurement` 는 **판정에 포함**(통합 세션 retrieval_mix 의도대로). 새 Tier `procurement`("발주 용역"), 임계치 0.80(own 과 동일, 표본 뒤 조정),
  알림 상태 `procuring` → "용역으로 진행 중/예정"(공고일 540일 이내), 그 밖은 `procured`. `audit`·`statistics` 는 판정 제외(근거 전용).
- P2-10: `mark_editions` 는 최신 판 등록일을 모르면 이전 판도 현행으로 두고 `ambiguous`·`superseded_by` 를 기록한다(이전엔 "구판" 표시만).
  연도별 기록(경영평가·통계)은 판이 아니므로 적용하지 않는다.

## 이유
봇 보호·로그인 우회 없음, robots 가 막은 경로 직접 호출 없음, 키가 필요한 것은 어댑터·테스트까지 만들고 런타임만 건너뛰어 키 투입 즉시 켜지게,
키 없는 공개 파일이 있으면 그쪽을 우선.

## 결과
`adapters/sources/{procurement,audit,datago}/`, `config/{g2b,bai,mofe,datago}.yaml`, `rra crawl bai`, `rra ingest --source g2b|bai|mofe|datago`,
감사원 스냅샷 55항목(pdf 20·hwp 20, 82.5MB), 테스트 1,519 통과. 기록: docs/korail-web-crawl.md §5, docs/status.d/feat-policy-sources.md.
