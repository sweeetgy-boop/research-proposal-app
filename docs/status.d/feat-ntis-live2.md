## NTIS 실응답 확정 (레인 R-NTIS, feat/ntis-live2, 2026-10-27 19:01~)

### ParseError 원인
- `rra sources check --source ntis,ntis_reports,ntis_insights` → 셋 다 `XmlResponseError: XML 파싱 실패 (ParseError)`.
- 원인 1 (셋 공통): 어댑터 Accept 에 `application/json` 이 있어(오류 본문 한글 때문에 레인 N 이 넣음) 서버가 **XML 전체를 JSON 문자열
  하나로 감싸** 돌려준다 — `"<?xml version=…` 로 시작, content-type `application/json;charset=UTF-8`. 통합 담당의 curl(Accept `*/*`)은
  `text/plain` 날 XML 을 받았다. 종전 코드는 감싼 본문을 그대로 defusedxml 에 넘겼다. → `ntis/client.py unwrap_json_string`(본문이 JSON
  문자열이면 풂, 객체면 그대로) + `parse_response`. json Accept 는 유지(없으면 오류 문구가 `?? ?? IP? ????.`).
- 원인 2 (연구보고서만, 1 을 고친 뒤 드러남): `DocUrl` 의 `…originalView.do?dbt=TRKO&cn=…` 맨 `&` 가 이스케이프 없이 온다 →
  `_xml.repair_bare_ampersands`(엔티티 꼴이 아닌 `&` 만 `&amp;` 로; 이스케이프를 더할 뿐이라 DTD 금지·크기 상한 그대로).
- 연관콘텐츠는 JSON 객체가 JSON 문자열 안에 있고(`creat_dt: NaN` 비표준) → 같은 unwrap, NaN 점수는 None.
- BOM·네임스페이스·루트 이름은 원인이 아니었다(루트 `RESULT`, xsi 속성만, 네임스페이스 없음).

### FIELDS 확정 (실응답 = 공개 매뉴얼 2021 과 동일)
- 과제검색(`ntis/projects.py`): id ProjectNumber · title ProjectTitle/Korean · abstract [연구목표] Goal/Full + [연구내용] Abstract/Full +
  [기대효과] Effect/Full(Teaser 는 "AB01" 같은 코드가 섞여 Full 우선) · orgs ResearchAgency/Name → korail/krri/kr · pub_date ProjectPeriod/
  TotalStart(`YYYY-MM-DD 00:00:00.0`)·Start(`YYYYMMDD`) · project_period TotalStart~TotalEnd · codes Keyword/Korean(`,`) ·
  raw{kind national_rnd, project_no, agencies, order_agency, ministry, budget TotalFunds, year ProjectYear, phase DevelopmentPhases,
  science_class ScienceClass/Medium(반복 요소 중복 제거, ≤5), **business**(BusinessName|BudgetProject/Name|BigprojectTitle, 사업명),
  **manage_agency**(ManageAgency/Name, 전문기관)}. 강조는 이스케이프된 `&lt;span class="search_word"&gt;` → strip_highlight. 수행 부서 필드 없음
  → department None, 티어 national_rnd. Manager/Name·Researchers/Name 은 읽지 않음(authors=[]).
- 연구보고서(`ntis/reports.py`): id TermSn(`REP-2011-0115023251`) · report_no ResearchPublicNo(TRKO…) · title ResultTitle/Korean · abstract
  Abstract/Korean · pub_date PublicationYear-01-01 · url DocUrl(https://scienceon.kisti.re.kr/commons/util/originalView.do?dbt=TRKO&cn=…) ·
  orgs LeadAgency·PublicationAgency · toc Contents · codes Keyword/Korean(`;`) · raw{project_no ProjectNumber, project_title, orgs_named,
  year, **specialized_agency** SpecializedAgency, **agency_project_no** AgencyDetailProjectNumber}. 강조는 날 `<span>`(flatten 이 잎으로). ManagerName 미저장.
- 성과검색(`ntis/insights.py`): 레코드 `HIT NO SITID=PAP|PAT`. 논문 ResultTitle·JournalName·PubYear|Year·ResultID(JNL-…)·**DigitalObjectIdentifier→doi**;
  특허 ResultTitle·RegistNumber·Registrant(기관만)·**RegistType(출원|등록)→regist_type**·ResultID(PTR-…). **과제번호는 `ProjectID`**(ProjectNumber 없음) —
  조회 과제와 대조. Author 미저장.
- 연관콘텐츠: `{PJT_ID, KOR_PJT_NM, exist, items:[{PJT_ID, similarity_score, rank, creat_dt, KOR_PJT_NM}], count}` — 기존 normalize_related 그대로.
- `_orgs` 태그: 과제 "철도 궤도" 10건 중 한국철도기술연구원 7 → krri, 한국철도공사 1 → korail, 서울과기대 2 → []. 보고서 LeadAgency 한국철도기술연구원 → krri,
  한국철도시설공단 → kr. 확인됨.
- `record_tag: HIT` 확정. probe 는 `hits`·`record_tag_matches` 를 더 낸다(자동 탐지는 NAVIGATIONENTRY 13개를 고르므로 설정 태그를 후보에 넣음).
  `views.NTIS_PROJECT_URL`(pjtInfo.do?pjtId=)은 이번에 확인하지 않음(페이지 호출은 범위 밖).

### 녹화 내역 (NTIS 호출 17회: 원문 확인 6·녹화 6·sources check 5)
| fixture | 서비스 | 질의 | 건수/총건수 | 가명 처리 |
|---|---|---|---|---|
| ntis_project_20261027_track.xml | public_project | 철도 궤도 | 10 / 1,087 | Manager/Name·Researchers/Name → NAME-REMOVED |
| ntis_project_20261027_catenary.xml | public_project | 전차선 | 10 / 193 | 〃 |
| ntis_report_20261027_track.xml | rresearchpdf/ | 철도 궤도 | 10 / 202 | ManagerName → NAME-REMOVED |
| ntis_outcome_20261027_rpaper.xml | public_result rpaper | 1615007833 | 10 / 13 | Author → NAME-REMOVED |
| ntis_outcome_20261027_rpatent.xml | public_result rpatent | 1615007833 | 2 / 2 | Registrant 기관(한국철도기술연구원)만 |
| ntis_related_20261027.json | ConnectionContent | 1615007833 | 10 | 이름 없음 |
키·URL 없음(`redact` + `test_fixtures_hold_no_obvious_secrets`). 합성 `*SYNTHETIC*` 5종 + meta 삭제. 녹화 도구: `ntis_insights` 소스·`--label`·
JSON 문자열 풀어 저장(`meta.json_wrapped`)·Registrant 기관 필터. `PROBE_PROJECT_NO` 는 1615007833(성과 12·연관 10 이 보이는 과제).

### 그 밖의 수정
- `build_ntis_source` 가 `per_query_limit` 을 넘기지 않았다 → "철도 궤도" 1,087건이면 질의당 11페이지 × 13 = 143회 > 예산 60. 전달하도록 고침(26회/소스).
- CLI `_record_tag_hints`: `ntis_reports`·`ntis_insights` 행이 ntis 설정을 보도록(실호출에서 "record_tag 가 비어 있습니다" 오안내).

### 테스트
- `tests/adapters/test_ntis.py` 합성 fixture 참조 → 실응답으로 이동 + 새 테스트 8건(JSON 문자열 풀기·ParseError 재현·맨 & 복구·probe_result·
  실응답 search/probe·CheckSources ok 행·다른 과제 성과 걸러냄·NaN 연관). `test_real_source_fixtures.py` NTIS 3건 강화(10건·근거·krri·https).
  `test_record_fixture_tool.py` NTIS 오프라인 녹화 1건. `test_cli.py` 힌트 1건. 전체 1,769 passed·16 skipped(변경 전 기존 테스트 약화 없음).
- 드라이런: `rra ingest` 에 dry-run 옵션이 없고 13 질의 실호출은 예산을 넘기므로 normalize 는 fixture 테스트로 확인(과제 20건·보고서 10건 모두 Document 생성, 실 DB 미접촉).

### sources check (실호출, 2026-10-27 19:1x, 공인 IP 59.0.166.199)
`[ntis] 왕복 ok {"total": 1087, "hits": 5, "record_tag_matches": true, …}` · `[ntis_reports] ok {"total": 202, …}` ·
`[ntis_insights] ok {"probe_project_no": "1615007833", "outcomes": 12, "related": 10}` — 종료 코드 0.

### 통합 담당이 실행할 적재 (무거운 작업 잠금, 한 번에 하나)
```bash
cd /Users/chan/projects/research-proposal-app && .venv/bin/rra db backup && \
.venv/bin/python tools/with_heavy_lock.py -- .venv/bin/rra ingest --source ntis --limit 2000 && \
.venv/bin/python tools/with_heavy_lock.py -- .venv/bin/rra ingest --source ntis_reports --limit 1500
.venv/bin/rra precheck …   # national_rnd 알림·골든셋 임계치(0.80) 확인
```
요청 예산 26회/소스(13 질의 × 2페이지, per_query_limit 150). 예상 과제 ≤ 1,950·보고서 ≤ 1,950(중복 제거 전).

### 판단·미완
- 매핑은 설계 변경이 아니라 확정이라 ADR 없음(ADR 0020 유지). source 이름·티어·중복 규칙 그대로.
- 보고서 `toc` 는 Contents 가 한 덩어리 텍스트라 `,` 로 쪼갠 조각이 거칠다 — 근거 검색에는 abstract 를 쓰므로 그대로 둠(후속: 페이지 번호 패턴으로 분리).
- `views.NTIS_PROJECT_URL` 실제 페이지 확인, 나머지 11개 질의의 총건수, 골든셋 임계치는 적재 뒤 통합 세션.
