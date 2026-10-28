# ADR 0031 — 실시간 자료 검색: 입력 확인 때 ScienceON·NTIS·OpenAlex 를 바로 조회해 DB 에 넣고 평소 검색으로 함께 본다 (2026-10-28, 레인 C)

## 배경
야간 적재(com.rra.ingest, 02:30)는 `sources.yaml` 의 고정 질의 13개만 돈다. 제안자의 아이디어가 그 질의 밖이면 ② 유사과제·관련 연구,
선행연구 브리핑, ③ 섹션 근거에 그 주제의 국가 R&D 과제·논문이 없다. 시범 운영 중 "새 주제는 근거가 비어 있다"는 지적이 나왔다.
외부 자료원 세 곳(ScienceON·NTIS·OpenAlex)은 이미 키·허용 도메인·어댑터가 있어 새 호출처를 늘리지 않고도 질의만 바꿔 부를 수 있다.

## 선택지
1. 야간 적재 질의를 늘린다 — 제안자 주제를 미리 알 수 없다. 제외.
2. 실시간 결과를 DB 에 넣지 않고 메모리에서 임베딩·병합해 검색 결과에 섞는다 — precheck(find_similar)·hybrid_search·retrieve_sections·
   reranker·자료원별 최소 보장·관련도 하한을 모두 두 갈래로 고쳐야 한다. 중복 제거도 두 번 구현.
3. **입력 확인 직후 백그라운드로 검색 → 정규화·사람 이름 제거 → DB 와 중복 정리 → 새 문서만 청크·임베딩·upsert(public, raw.live=true).
   이후 단계는 평소 검색이 그 문서를 함께 본다.** 세션(소유자+입력 해시)이 실시간 doc_id 를 들고 있어 화면 배지·run 기록에 쓴다.

## 결정
- 3. 규칙 `domain/rules/live_search.py`(키워드 검증·규칙 기반 키워드·질의·캐시 키·세션 키·저장 전 정리·동일성 키·중복 정리, 순수),
  모델 `domain/models/live_search.py`(설정·키워드·자료원별 결과·요약), 포트 `application/ports/live_search.py`(`LiveSourcePort`,
  `IdentityLookupPort`, `TimedAvailabilityPort`), 유스케이스 `application/usecases/live_search.py`(`LiveKeywordMaker`, `LiveSearch`),
  어댑터 `adapters/sources/live.py`(기존 ScienceOn·Ntis 과제/보고서·OpenAlex 어댑터를 감쌈), SQLite `find_identities`, 설정
  `config/live_search.yaml`(로더 `config_loader.live_search_config`), 조립 `build_live_search`·`build_live_sources`·`build_live_keywords`.
- 키워드: Argon(llm.yaml stages.review = gemini, 일일 예산 `BudgetedLLM`·공유 호출 제한기) 1회 → 실패 시 로컬(clarify 단계) → 실패 시
  규칙(keywords.py 토큰). 입력은 `privacy.strip_personal` 을 거쳐 보낸다. 출력은 JSON 만, 문자열 검증(한글/라틴 여부·40자·연산자 제거·
  개인정보 섞이면 버림)만 하고 글자는 바꾸지 않는다(정책명·고유명사 그대로). 같은 입력의 키워드는 24시간 캐시.
- 검색: 세 자료원 동시, 자료원마다 10초·전체 15초, 넘긴 자료원은 timeout 으로 건너뜀. 자료원당 상위 30(ScienceON 은 target 마다 10,
  NTIS 는 과제 15 + 연구보고서 15). 질의는 키워드 하나씩 앞에서부터, 30건이 차면 멈춘다. 세션마다 요청 상한(scienceon 8·ntis 6·
  openalex 3), 자료원별 자물쇠로 동시 세션을 줄 세워 rate_limit 을 지킨다. 같은 (자료원, 정규화 질의, 건수) 는 24시간 캐시
  (`data/cache/live_search`, 값은 정규화·이름 제거된 문서).
- NTIS IP 거부(`SourceIpBlocked`)는 그 세션만 건너뛰고 `source_availability` 에 같은 안내 문구를 남긴다(웹 자료원 상태와 같은 문구).
  기록이 `ip_block_recheck_minutes`(60) 안이면 호출하지 않고 ip_blocked 로 표시, 성공하면 안내를 지운다.
- 저장: visibility public, 자료원 태그 그대로(scienceon·ntis·openalex), ingested_at(저장소), raw.live=true·raw.live_first_seen=세션 해시
  12자, authors 비움(OpenAlex 저자 이름 포함), 초록의 이메일·전화 표식. 중복은 실시간끼리(자료원 순서 ntis → scienceon → openalex 가
  먼저) 그리고 DB 와(같은 doc_id 면 다시 임베딩하지 않음, DOI·출원번호·보고서 과제번호+제목·정규화 제목+연도가 같으면 저장된 문서로 잇는다).
  과제(rnd_project)는 제목으로 합치지 않는다(dedup 규칙 그대로).
- 흐름: REST `POST /v1/precheck` 가 세션을 시작하고 최대 `wait_seconds`(15) 기다린 뒤 판정한다. 같은 입력으로 `POST /v1/runs` 를 하면
  run 이 그 세션을 이어 쓰고(없으면 새로 시작) 검색 전에 최대 15초 기다린다. 선행연구 브리핑도 같다. 못 끝나면 DB 만으로 계속(pending).
  판정 후보 규칙(ADR 0028)·retrieval_mix·reranker·자료원별 최소 보장·관련도 하한은 그대로 — NTIS 과제는 ② 유사과제 후보, 논문·보고서·
  특허는 관련 연구와 섹션 근거 후보가 된다.
- 꺼짐(`enabled: false` 또는 파일 없음)은 종전 동작. 가짜 모드(RRA_FAKE_LLM)는 자료원마다 가짜 문서 2건.

## 이유
- DB 에 넣으면 검색·판정·근거 경로가 하나로 남는다. 다음 사람·다음 run 도 같은 문서를 쓰고(캐시 효과), 야간 적재와 같은 정규화를 거친다.
- 실시간 결과는 공개 API 결과라 public 이 맞다(소유자 결정). 공용 계정 범위(internal 제외)는 그대로이고 실시간 문서는 보인다.
- 2026-10-28 실호출: 키워드 두 개를 AND 로 묶은 첫 질의는 ScienceON 에서 0~2건이라 예산(8회)을 다 썼다 → 키워드 하나씩으로 바꿨다.

## 결과 (2026-10-28 실호출, 임시 DB·결정적 임베딩, 운영 DB 쓰기 없음)
- Argon 키워드 1회 약 4초(국문 5·영문 5, 정책·지명 그대로). ScienceON 30건 7.3초(요청 8회 — 바꾸기 전 질의), OpenAlex 30건 1.2~1.3초(요청 1회),
  NTIS 는 이 기기 공인 IP 가 등록 목록(sources.yaml registered_ips)에 있는데도 "접근 허용 IP가 아닙니다"(0.6~0.8초, 요청 2회) → ip_blocked.
  첫 세션 11.8초(partial), 같은 입력 두 번째는 키워드·검색 캐시로 0.00초. e5 임베딩 60청크 1.07초(MPS).

## 후속
- NTIS IP 등록 반영 확인(활용신청 IP 와 실제 공인 IP — ADR 0025 의 같은 증상). 반영되면 별도 설정 없이 다음 세션부터 호출된다.
- 실시간 문서가 쌓이는 양(세션당 최대 90건)을 보고 보존 기간·정리 규칙(`raw.live` 문서 만료)을 정한다.
- 자료원별 상위 30·질의 수·요청 상한은 시범 표본으로 조정.
