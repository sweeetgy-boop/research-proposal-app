## [4] 실시간 자료 검색 — ScienceON·NTIS·OpenAlex (feat/live-search, 2026-10-28, 레인 C)

- 기준: main. ADR 0031. 설정 `config/live_search.yaml`(로더 `config_loader.live_search_config`, 시범 기본 켬, 가짜 모드는 `fake_mode` 로만).
- 흐름: `POST /v1/precheck` → 키워드(Argon 1회 → 로컬 → 규칙, 입력 개인정보 제거, 국문·영문 3~5) → 세 자료원 동시 검색(자료원 10초·
  전체 15초, 상위 30, ScienceON·NTIS 국문/OpenAlex 영문) → 이름 제거·public·raw.live 로 정리 → 실시간끼리·DB 와 중복 정리 → 새 문서만
  청크·임베딩·upsert → 평소 판정·검색(ADR 0028 후보 규칙·retrieval_mix·reranker·최소 보장·관련도 하한 그대로). 최대 15초 기다리고 DB 만으로 계속.
  같은 입력의 run·선행연구 브리핑은 세션을 이어 쓴다(없으면 시작). 같은 질의·같은 입력의 키워드는 24시간 캐시(`data/cache/live_search`).
- NTIS IP 거부는 그 세션만 건너뛰고 `source_availability` 에 같은 안내(60분 안에는 다시 호출하지 않음, 성공하면 지움).
- 코드: `domain/models/live_search.py`, `domain/rules/live_search.py`, `application/ports/live_search.py`, `application/usecases/live_search.py`,
  `adapters/sources/live.py`, `adapters/fake/live.py`, SQLite `find_identities`(DOI·출원번호·보고서 과제번호·정규화 제목 함수),
  `OpenAlexSource.search_query`, `FileSourceAvailability.recorded_at`, 조립 `build_live_search·build_live_sources·build_live_keywords`,
  `RunManager(live_search=)`·`RunState.live_search/live_doc_ids`, manifest `live_search`(건수·상태, 허용목록 `LIVE_SEARCH_KEYS`).
- 프론트엔드 영향(이미 합쳐진 웹 #69 의 모양과 같음): `POST /v1/precheck` 응답 `live_search{status, keywords{ko,en}, sources[{source,status,count,
  seconds,notice, new, cached}]}`, `alerts[].live`, `related_research[].live`; `GET /v1/runs/{id}` `live_search`(또는 null); draft `citations[].live`;
  `GET /v1/runs/{id}/sentences/{sid}/evidence` `evidence[].live`. `docs/openapi.json` 은 통합 담당이 `rra api schema` 로.
- 실호출(임시 DB): Argon 키워드 약 4초, ScienceON 30건 7.3초(요청 8, 바꾸기 전 질의), OpenAlex 30건 1.2초(요청 1), NTIS ip_blocked(등록 목록의
  IP 인데도 거부, 0.6~0.8초), 같은 입력 두 번째 0.00초(캐시). e5 임베딩 60청크 1.07초.
- 테스트 +43(규칙 16·유스케이스 14·어댑터 5·REST 3·RunManager 2·설정 3). pytest 1945 통과·18 skip, lint-imports 8 kept, ruff 통과.
- 사람 할 일: NTIS 활용신청 IP 반영 확인(ADR 0025 와 같은 증상).
