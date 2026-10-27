# 외부 자료원 전수 점검 (2026-10-26, P4)

키 값은 `.env`(권한 600)에만 둔다. 여기에는 신청처·필요 정보·검증 명령만 적는다. 키 유무는 `rra sources check` 가
값 없이 보여 준다.

## 1. 전수 점검 표

| 자료원 | source 이름 | 용도(기획서) | 신청처 | 필요 정보 (.env) | 비용·한도 | 어댑터 | 상태 |
|---|---|---|---|---|---|---|---|
| OpenAlex | `openalex` | 해외 논문 근거 (기능 3·4) | 없음 (키 불필요). 선택: `RRA_OPENALEX_MAILTO`(polite pool), `RRA_OPENALEX_API_KEY`(무료, openalex.org/settings/api — cursor 페이징용, 없어도 page 페이징) | — | 무료, 초당 10회 | `adapters/sources/openalex.py` — 분야별 질의 13개(`sources.yaml openalex.queries`), 10년·초록 조건 | 적재 (architecture §4.13) |
| 알리오 공시 원문 | `alio` | 사내·국내 철도기관 유사과제 (기능 1·2·4) | 수동 다운로드 → `data/inbox/alio` | — | 무료 | `alio/filedrop.py` | 원문 파일 대기 |
| 알리오 공개 요약 (.txt) | `alio_summary` | 원문 비공개 보고서 | 상세 페이지 복사 → `data/inbox/alio_summary` | — | 무료 | `alio/summary.py` | 1건 |
| 사내 과제 현황·공시 요약문 | `own_projects`·`own_docs` | 사내 유사과제·차별화 (기능 1·2) | 사내 파일 (P2) | — | — | `adapters/sources/own/` | 적재 완료 (1,119 + 120건). 공개 자료(public) — 공시용이 없는 일반 요약문 5건만 internal. 티어는 모두 own(철도연구원/공사 구분) |
| NTIS 과제검색 | `ntis` | 국가R&D 중복 (기능 1·2·3) — 유사과제 티어 `national_rnd`(0.80, "국가R&D 과제") | ntis.go.kr OpenAPI [활용신청] — **소속기관 등록 필요**(내정보 > 소속기관 등록), **서버 IP 등록**(다르면 HTTP 200 + `<error>접근 허용 IP가 아닙니다.</error>`; 등록 IP 는 `sources.yaml ntis.registered_ips` 59.0.166.199·59.0.251.250, `rra sources check` 가 현재 공인 IP 와 대조 — 레인 I), 콜센터 042-865-1115 | `RRA_NTIS_KEY` (rndopen apprvKey, 4개 서비스 승인 2027-05-27 까지) | 무료 (매뉴얼 30 tps, 설정 2 req/s) | `ntis/client.py`·`projects.py` — record_tag HIT, 실응답 FIELDS 확정, 사람 이름 미저장, Accept json → JSON 문자열 감싸기 풂(`unwrap_json_string`) | 2026-10-27 19:11 실응답 녹화 완료(과제 2질의·보고서·성과·연관, docs/status.d/feat-ntis-live2.md). `sources check` ok(총 1,087/202). 적재는 통합 세션 |
| NTIS 연구보고서 검색 | `ntis_reports` → 문서 `source=ntis`, doc_type `report` | 국가R&D 보고서 근거 (선행연구·섹션) | 같은 키, 서비스별 활용신청(승인됨) — `rresearchpdf/` | `RRA_NTIS_KEY` | 무료 | `ntis/reports.py` — ScienceON 보고서와 과제번호+제목+연도로 하나로(dedup.report_identity), DocUrl 맨 `&` 복구(`_xml.repair_bare_ampersands`) | 2026-10-27 실응답 fixture·매핑 확정(DocUrl 은 scienceon originalView, ManagerName 미저장) |
| NTIS 성과검색·연관콘텐츠 | (문서 아님) | ② 과제 카드 "주요 성과"(참고용)·"NTIS 추천" | 같은 키 (승인됨) — `public_result`·`ConnectionContent`(공개 구현 기준, 매뉴얼 미확보) | `RRA_NTIS_KEY` | 무료 | `ntis/insights.py`·`usecases/ntis_insights.py`·`POST /v1/precheck/ntis-outcomes`·파일 캐시 `data/cache/ntis` | 2026-10-27 실응답 확정 — 성과 `HIT SITID=PAP|PAT`, 과제번호는 `ProjectID`, 연관콘텐츠는 JSON 안의 JSON + `NaN` |
| ScienceON | `scienceon` | 국내 논문·보고서·특허 근거 (기능 3·4) | KISTI ScienceON API 활용신청 → **client_id(64자) + 인증키(32자)**, **호출 기기 MAC 등록** — **호출 IP 제한 없음**(`sources.yaml scienceon.ip_restricted: false`, 레인 I) | `RRA_SCIENCEON_CLIENT_ID`·`_KEY`·`_MAC` | 무료, 429 이력 → 초당 1회·run 예산(sources.yaml) | `scienceon/` — target ARTI·REPORT·PATENT, 사람 이름 미저장 | 실응답 확인(2026-10-27): 토큰·검색 ok, fixture 3종, 매핑 확정. 적재는 통합 세션 대기 |
| KIPRIS 특허 (국내) | `kipris` → 문서 `kipris_kr` | 특허 선행기술·차별성 (기능 3·4) | plus.kipris.or.kr 회원가입 → "특허·실용신안 정보" 활용신청 (오퍼레이션 단위 권한) | `RRA_KIPRIS_KEY` (accessKey) | 무료 구간 + 유료, 미신청 기능 호출 시 resultCode 30 | `kipris/` (P4) | 코드 완료, 키·실응답 대기 |
| KIPRIS 해외 특허 | `kipris_intl` | 해외 특허 | KIPRIS Plus 별도 서비스 | 같은 키 | — | 미구현 | 국내 특허 실응답 확정 뒤 |

## 2. KIPRIS — KIPRIS Plus 와 공공데이터포털 비교 (기본: KIPRIS Plus)

| 항목 | KIPRIS Plus (plus.kipris.or.kr) | 공공데이터포털 (data.go.kr) |
|---|---|---|
| 데이터·키 체계 | 특허청 공식 개방 플랫폼, 서비스별 활용신청 → 단일 키 | 같은 KIPRIS 데이터, 같은 키 체계(비공식 구현 문서 기준) |
| 호출 한도 | 무료 구간 뒤 유료·대량(BULK) 창구 | 월 1,000회 수준 무료, 초과·대량은 KIPRIS Plus 로 안내 |
| 엔드포인트 | `https://plus.kipris.or.kr/openapi/rest/patUtiModInfoSearchSevice/freeSearchInfo` (키 `accessKey`) | 서비스별 `ServiceKey` 경로 |
| 선택 | **기본** — 활용신청·권한·대량 호출이 여기서 관리됨 | 월 상한이 낮아 수집용으로 부적합 |

`config/sources.yaml kipris` 의 `search_path`·`key_param`·`record_tag` 로 공공데이터포털 경로(`ServiceKey`)로 바꿀 수 있다.
파라미터(`word`·`patent`·`utility`·`docsStart`·`docsCount`·`descSort`·`sortSpec`)와 레코드 태그 `PatentUtilityInfo`·필드
(`ApplicationNumber`·`InventionName`·`Abstract`·`Applicant`·`ApplicationDate`·`OpeningDate`·`RegistrationStatus`·
`InternationalpatentclassificationNumber`)는 공개 구현(korean-patent-mcp api-client/xml-parser) 기준이다. 발명자 이름은 읽지
않고, 출원인은 기관명만 남긴다(개인 출원인은 `applicant_kind=person` 표시).

## 3. 검증 명령 (키 투입 뒤)

```bash
rra sources check                       # scienceon·ntis·kipris 키 유무(값 미표시)·허용 호스트·왕복 1회
rra sources check --source kipris       # probe: 총건수·record_tag 후보·설정 태그 일치 여부
python -m tests.tools.record_fixture kipris --query "철도 궤도" --rows 10   # 실응답 녹화 (키 REDACTED)
python -m tests.tools.record_fixture ntis --query 궤도 --rows 10           # record_tag 후보 출력
pytest -q tests/adapters/test_real_source_fixtures.py                      # fixture 가 있으면 매핑 확정 테스트
rra ingest --source kipris --limit 100                                     # 적재 → rra precheck 에 KIPRIS 알림
```

### NTIS `record_tag` 진단
레코드 요소는 `HIT`(`sources.yaml ntis.record_tag`, 2026-10-27 실응답 확정). `rra sources check --source ntis` 의 probe 는
`total`(TOTALHITS)·`hits`(설정 태그 레코드 수)·`record_tag_matches`·`record_tag_candidates` 를 낸다. 자동 탐지는 "자식 있는 형제가
가장 많은 묶음" 이라 과제검색에서는 NAVIGATIONENTRY(13개) 가 HIT(≤10) 를 이긴다 — 설정 태그가 응답에 있으면 후보에 같이
넣는다. `ntis_reports`·`ntis_insights` 행은 ntis 설정을 같이 본다. KIPRIS 도 같은 진단을 한다(기본 `PatentUtilityInfo`).

### NTIS 응답 형식 (2026-10-27 실측 — ParseError 원인)
- Accept 에 `application/json` 이 있으면 서버가 **XML 전체를 JSON 문자열 하나로 감싸** 보낸다(`"<?xml …"`, content-type
  `application/json;charset=UTF-8`). Accept 에 json 이 없으면 `text/plain` 날 XML. 오류 본문(`<error>접근 허용 IP가 아닙니다.</error>`)
  의 한글은 json Accept 가 있어야 살아오므로 json 을 유지하고 `ntis/client.py unwrap_json_string` 으로 푼다. 종전 코드는 감싼 본문을
  그대로 defusedxml 에 넘겨 `XmlResponseError (ParseError)` 였다.
- 연구보고서 검색은 `DocUrl` 의 `&cn=` 처럼 맨 `&` 를 그대로 내보낸다 → `_xml.repair_bare_ampersands`(이스케이프만 더함, DTD 금지 유지).
- 연관콘텐츠는 JSON 객체가 다시 JSON 문자열 안에 들어 있고 `creat_dt` 에 비표준 `NaN` 이 섞인다.

### ScienceON 키 길이·MAC 안내
- client_id 는 **64자**, 인증키는 **32자**(AES-256 키). `.env` 에 둘을 서로 바꿔 넣으면 `rra sources check` 가
  "인증키는 32자여야 합니다 (지금 64바이트)" 로 멈춘다 — 값만 서로 바꾼다. (2026-10-27 실제로 그랬다.)
- 토큰 응답은 JSON(access_token·refresh_token·*_expire·issued_at), 재발급 파라미터는 `refresh_token`. 복호화 실패는
  XML `E5001`, MAC 불일치는 JSON `E4107`. 검색 응답은 XML — Accept 에 `text/xml` 이 없으면 406.
- 응답 `parameterData` 에 client_id·token 이 그대로 들어 있다. 녹화·로그에 본문을 남길 때 반드시 REDACTED 처리.

ScienceON 토큰 발급은 활용신청 때 등록한 **기기 MAC** 과 요청의 MAC 이 같아야 한다.
- MAC 확인: macOS `ifconfig en0 | grep ether` (Wi-Fi 끄고 유선이면 `en1` 등 실제 인터페이스), WSL/리눅스 `ip link`.
- 형식: `AA-BB-CC-DD-EE-FF` (대문자·하이픈). `.env RRA_SCIENCEON_MAC` 에 적는다. 값은 어디에도 출력되지 않는다.
- 기기마다 다르므로 개발 MacBook 과 배포 Mac mini 를 각각 ScienceON 에 등록하고 `.env` 도 기기별로 둔다.
- 429 가 반복되면 `sources.yaml scienceon.rate_limit`·`max_requests_per_run` 을 낮춘다.

## 4. NTIS 연구보고서 검색 — 구현됨, 실응답 확정 (2026-10-27)
"국가R&D 연구보고서 검색 서비스" 는 같은 apprvKey 로 승인돼 있다. 경로 `/rndopen/openApi/rresearchpdf/`, 파라미터
`query·searchField(BI)·startPosition·displayCount·returnType(xml)`, 레코드 `HIT`. 실응답 필드(tests/fixtures/ntis/README.md):
TermSn·PublicationYear·ResearchPublicNo·PublicationAgency·ResultTitle/Korean|English·Abstract/Korean|English·Keyword/Korean(`;`)·
Contents·PublicationCountry·PublicationLanguage·DocUrl(scienceon originalView, https)·SpecializedAgency·ProjectNumber·ProjectTitle·
LeadAgency·ManagerName(읽지 않음)·AgencyDetailProjectNumber. 어댑터 `adapters/sources/ntis/reports.py`(`rra ingest --source ntis_reports`,
doc_type `report`, raw.kind national_rnd_report). `rra sources check --source ntis_reports` ok(철도 궤도 202건).
